import hashlib
import json
import os
import re

import cv2
import numpy as np
import torch

import folder_paths

SCHEMA = "element-forge/rgba-sequence-v1"
FOLDER = "element-forge/elements"
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _root():
    return os.path.join(folder_paths.get_output_directory(), *FOLDER.split("/"))


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _inside(root, name):
    p = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([p, os.path.realpath(root)]) != os.path.realpath(root):
        raise ValueError("Element name must stay inside the element folder.")
    return p


def _elements():
    root = _root()
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, "element.json")))


def _write_exr(path, px):
    import OpenImageIO as oiio
    h, w = px.shape[:2]
    spec = oiio.ImageSpec(w, h, 3, oiio.HALF)
    spec.channelnames = ("R", "G", "B")
    spec.attribute("compression", "zip")
    spec.attribute("oiio:ColorSpace", "lin_rec709")
    out = oiio.ImageOutput.create(path)
    if not out or not out.open(path, spec):
        raise RuntimeError(f"EXR write failed: {oiio.geterror()}")
    out.write_image(np.ascontiguousarray(px, dtype=np.float32))
    out.close()


def _read_exr(path):
    import OpenImageIO as oiio
    inp = oiio.ImageInput.open(path)
    if not inp:
        raise ValueError(f"Cannot read EXR: {path}")
    px = inp.read_image(format="float")
    inp.close()
    return np.asarray(px, np.float32)[..., :3]


def _split(rgba, alpha):
    if alpha is not None:
        a = alpha if alpha.ndim == 3 else alpha[..., 0]
        if a.shape[0] == 1 and rgba.shape[0] > 1:
            a = a.expand(rgba.shape[0], -1, -1)
        return rgba[..., :3], a
    if rgba.shape[-1] > 3:
        return rgba[..., :3], rgba[..., 3]
    return rgba[..., :3], rgba[..., :3].amax(dim=-1)


class EFSaveElement:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "rgba": ("IMAGE", {"tooltip": "Element with alpha, e.g. rgba from EF Unmult (straight sRGB color, linear alpha)."}),
                "name": ("STRING", {"default": "fire_01", "tooltip": "Folder name in output/element-forge/elements. Letters, digits, space, - and _."}),
                "fps": ("FLOAT", {"default": 25.0, "min": 0.1, "max": 240.0, "step": 0.001}),
                "overwrite": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "alpha": ("MASK", {"tooltip": "Alpha if the image has none."}),
                "hdr": ("IMAGE", {"tooltip": "Optional HDR version (EF HDR Merge: linear premultiplied, values above 1). Saved as EXR next to the PNGs and loaded again by EF Load Element."}),
            },
            "hidden": {"prompt": "PROMPT"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("element_name",)
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "Element Forge"
    DESCRIPTION = "Saves an element as a 16-bit RGBA PNG sequence with a manifest, so it can be placed again in other shots without generating it again."

    def save(self, rgba, name, fps, overwrite, alpha=None, hdr=None, prompt=None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,79}", name) or name.endswith(" "):
            raise ValueError("Use a short name with letters, digits, spaces, - or _ (no space at the end).")
        if name.upper() in _RESERVED:
            raise ValueError(f"'{name}' is a reserved name on Windows. Choose another name.")
        rgb, a = _split(rgba, alpha)
        if rgb.shape[:3] != a.shape:
            raise ValueError("Color and alpha must have the same frame count and size.")
        if not torch.isfinite(rgb).all() or not torch.isfinite(a).all():
            raise ValueError("Element contains non-finite values.")
        root = _root()
        os.makedirs(root, exist_ok=True)
        out = _inside(root, name)
        if os.path.exists(out):
            if not overwrite:
                raise ValueError(f"Element '{name}' exists. Choose another name or switch on overwrite.")
            for f in os.listdir(out):
                if f.endswith(".png") or f == "element.json":
                    os.remove(os.path.join(out, f))
            hd = os.path.join(out, "hdr")
            for f in (os.listdir(hd) if os.path.isdir(hd) else []):
                if f.endswith(".exr"):
                    os.remove(os.path.join(hd, f))
        os.makedirs(out, exist_ok=True)
        px = torch.cat((rgb, a[..., None]), dim=-1).clamp(0.0, 1.0).cpu().numpy()
        files = []
        for i, fr in enumerate(px):
            u16 = np.rint(fr * 65535.0).astype(np.uint16)
            ok, buf = cv2.imencode(".png", cv2.cvtColor(u16, cv2.COLOR_RGBA2BGRA))
            if not ok:
                raise ValueError("PNG encoding failed.")
            fn = f"{i:05d}.png"
            buf.tofile(os.path.join(out, fn))
            files.append({"file": fn, "sha256": hashlib.sha256(buf.tobytes()).hexdigest()})
        hdr_files = []
        if hdr is not None:
            hp = hdr[..., :3].float().cpu().numpy()
            if hp.shape[:3] != px.shape[:3]:
                raise ValueError(f"HDR must match the element (frames, height, width): {hp.shape[:3]} vs {px.shape[:3]}.")
            if not np.isfinite(hp).all():
                raise ValueError("HDR contains non-finite values.")
            os.makedirs(os.path.join(out, "hdr"), exist_ok=True)
            for i, fr in enumerate(hp):
                fn = f"hdr/{i:05d}.exr"
                _write_exr(os.path.join(out, "hdr", f"{i:05d}.exr"), np.maximum(fr, 0))
                hdr_files.append({"file": fn, "sha256": _digest(os.path.join(out, "hdr", f"{i:05d}.exr"))})
        manifest = {
            "schema": SCHEMA, "fps": fps, "frame_count": len(files),
            "width": int(px.shape[2]), "height": int(px.shape[1]), "bit_depth": 16,
            "color": "sRGB, straight (not premultiplied)",
            "alpha": "straight alpha (from EF Unmult: max channel, luminance or an external matte); comp in linear light as linear(color) * alpha",
            "files": files, "prompt": prompt,
        }
        if hdr_files:
            manifest["hdr"] = {"color": "linear Rec.709, premultiplied, values above 1 kept (half float EXR)", "files": hdr_files}
        with open(os.path.join(out, "element.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        return {"ui": {"text": [out]}, "result": (name,)}


class EFLoadElement:
    @classmethod
    def INPUT_TYPES(s):
        names = _elements()
        return {"required": {
            "element": (names or ["(no saved elements yet)"], {"tooltip": "Elements saved with EF Save Element (output/element-forge/elements)."}),
            "frames": ("INT", {"default": 0, "min": 0, "max": 10000, "tooltip": "0 = all frames. Otherwise the element loops or is cut to this length."}),
            "start_frame": ("INT", {"default": 0, "min": 0, "max": 10000}),
        }}

    RETURN_TYPES = ("IMAGE", "MASK", "FLOAT", "IMAGE")
    RETURN_NAMES = ("rgba", "alpha", "fps", "hdr_premult_linear")
    FUNCTION = "load"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Loads a saved element (checks every frame against its manifest). hdr_premult_linear: the saved HDR "
                   "version if there is one (values above 1), otherwise the element itself as linear premultiplied.")

    @classmethod
    def VALIDATE_INPUTS(s, element):
        return True

    @classmethod
    def IS_CHANGED(s, element, frames, start_frame):
        p = os.path.join(_inside(_root(), element), "element.json")
        return _digest(p) if os.path.isfile(p) else element

    def load(self, element, frames, start_frame):
        d = _inside(_root(), element)
        man_path = os.path.join(d, "element.json")
        if not os.path.isfile(man_path):
            raise ValueError(f"Element '{element}' not found in output/{FOLDER}. Save one with EF Save Element or pick a saved one.")
        man = json.load(open(man_path, encoding="utf-8"))
        if man.get("schema") != SCHEMA or len(man["files"]) != man["frame_count"]:
            raise ValueError("Element manifest is not an Element Forge RGBA sequence or is incomplete.")
        seq = []
        for e in man["files"]:
            p = _inside(d, e["file"])
            buf = np.fromfile(p, dtype=np.uint8)
            if hashlib.sha256(buf.tobytes()).hexdigest() != e["sha256"]:
                raise ValueError(f"Element frame differs from its manifest: {e['file']}")
            px = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
            if px is None or px.ndim != 3 or px.shape[2] != 4:
                raise ValueError(f"Expected an RGBA PNG: {e['file']}")
            seq.append(cv2.cvtColor(px, cv2.COLOR_BGRA2RGBA).astype(np.float32) / np.iinfo(px.dtype).max)
        arr = np.stack(seq)
        n = len(arr)
        start_frame %= n
        idx = np.arange(start_frame, start_frame + (frames or n - start_frame)) % n
        out = torch.from_numpy(arr[idx])
        hdr_files = (man.get("hdr") or {}).get("files") or []
        if len(hdr_files) == n:
            hdr = []
            for e in hdr_files:
                p = _inside(d, e["file"])
                if _digest(p) != e["sha256"]:
                    raise ValueError(f"HDR frame differs from its manifest: {e['file']}")
                hdr.append(_read_exr(p))
            hdr = torch.from_numpy(np.stack(hdr)[idx])
        else:
            rgb = out[..., :3]
            lin = torch.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055).pow(2.4))
            hdr = lin * out[..., 3:4]
        return (out, out[..., 3].clone(), float(man["fps"]), hdr.contiguous())

