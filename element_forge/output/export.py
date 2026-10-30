import json
import os

import numpy as np

import folder_paths

from ..tracking.track import srgb_to_linear, to_np


class EFSaveEXR:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "element-forge/layer"}),
                "input_is": (["linear", "sRGB"], {"tooltip": "linear: layers from EF Effect Layer / EF Place Layer. sRGB: normal Comfy images (plates, decoded video); they are converted to linear."}),
                "precision": (["half", "float"], {"default": "half"}),
            },
            "optional": {
                "alpha": ("MASK", {"tooltip": "Written as the A channel. The RGB is expected premultiplied, as EXR requires."}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("first_file",)
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Writes one EXR per frame (scene-linear Rec.709, ZIP compression). Values above 1 are kept."

    def save(self, images, filename_prefix, input_is, precision, alpha=None):
        import OpenImageIO as oiio

        imgs = to_np(images)[..., :3]
        if input_is == "sRGB":
            imgs = srgb_to_linear(imgs)
        a = to_np(alpha) if alpha is not None else None
        n, h, w = imgs.shape[:3]
        out_dir, name, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, folder_paths.get_output_directory(), w, h)
        fmt = oiio.HALF if precision == "half" else oiio.FLOAT
        files = []
        for i in range(n):
            px = imgs[i]
            chans = ("R", "G", "B")
            if a is not None:
                px = np.concatenate([px, a[min(i, len(a) - 1)][..., None]], axis=-1)
                chans = ("R", "G", "B", "A")
            spec = oiio.ImageSpec(w, h, len(chans), fmt)
            spec.channelnames = chans
            if a is not None:
                spec.alpha_channel = 3
            spec.attribute("compression", "zip")
            spec.attribute("oiio:ColorSpace", "lin_rec709")
            fn = f"{name}_{counter + i:05d}.exr"
            out = oiio.ImageOutput.create(os.path.join(out_dir, fn))
            if not out or not out.open(os.path.join(out_dir, fn), spec):
                raise RuntimeError(f"EXR write failed: {oiio.geterror()}")
            out.write_image(np.ascontiguousarray(px, dtype=np.float32))
            out.close()
            files.append({"filename": fn, "subfolder": subfolder, "type": "output"})
        first = os.path.join(out_dir, files[0]["filename"]) if files else ""
        return {"ui": {"text": [f"{n} EXR frames: {os.path.join(subfolder, name)}_#####.exr"]}, "result": (first,)}
