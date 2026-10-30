import copy
import math
from fractions import Fraction
import glob
import json
import os
import time

import numpy as np
import torch
import torch.nn.functional as F

import folder_paths

from ..compositing.light3d import linear_to_srgb, srgb_to_linear
from ..compositing.post import EFGlow

LUMA = torch.tensor([0.2126, 0.7152, 0.0722])
LOG_A, LOG_MAX = 16.0, 64.0
TILES = ["plate", "element", "light", "smoke", "element_alpha", "depth", "smoke_alpha", "glow"]

FINISH_DEFAULTS = {
    "plate": {"exposure": 0.0, "contrast": 1.0, "saturation": 1.0, "temperature": 0.0, "tint": 0.0},
    "element": {"mode": "add", "gain": 0.0, "opacity": 1.0, "saturation": 1.0, "color": "#ffffff", "color_amount": 0.0,
                "offset_x": 0.0, "offset_y": 0.0, "scale": 1.0, "stretch": 1.0, "rotation": 0.0, "pivot_x": None, "pivot_y": None, "time_offset": 0, "visible": True},
    "light": {"strength": 1.0, "color": "#ffffff", "color_amount": 0.0},
    "glow": {"exposure": -1.0, "radius": 200.0, "falloff": 2.0, "threshold": 0.1, "core": 2.0, "color": "", "color_amount": 1.0},
    "smoke": {"opacity": 1.0},
    "lit": {"others": 0.0},
    "haze": {"amount": 0.0, "color": "#8090a0", "near": 0.3},
    "dof": {"amount": 0.0, "range": 0.15, "focus": -1.0},
    "finish": {"exposure": 0.0, "rolloff": 0.0, "vignette": 0.0, "grain": 0.0, "saturation": 1.0},
}


def merge_settings(s):
    out = copy.deepcopy(FINISH_DEFAULTS)
    if isinstance(s, str):
        s = json.loads(s) if s.strip() else {}
    for grp, vals in (s or {}).items():
        if grp in out and isinstance(vals, dict):
            out[grp].update({k: v for k, v in vals.items() if k in out[grp]})
    return out


def hex_lin(h):
    h = (h or "").strip().lstrip("#") or "ffffff"
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"colour must be a hex value like #ffb060 or #fff, got {h!r}")
    c = torch.tensor([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    return srgb_to_linear(c)


def run_dir(run_folder):
    base = os.path.realpath(folder_paths.get_output_directory())
    d = os.path.realpath(os.path.join(base, run_folder))
    if os.path.commonpath([base, d]) != base or not os.path.isdir(d):
        raise ValueError(f"Run folder not found inside the ComfyUI output folder: {run_folder}")
    return d


def read_exr(path):
    import OpenImageIO as oiio
    inp = oiio.ImageInput.open(path)
    if inp is None:
        raise ValueError(f"Cannot read {path}")
    a = inp.read_image(format="float")
    inp.close()
    a = np.asarray(a, np.float32)
    return a[..., None] if a.ndim == 2 else a


def last_run_frames(d):
    comps = sorted(glob.glob(os.path.join(d, "comp_*.mp4")))
    if comps:
        try:
            import av
            with av.open(comps[-1]) as c:
                n = c.streams.video[0].frames
            if n:
                return int(n)
        except Exception:
            pass
    try:
        with open(os.path.join(d, "app_recipe.json"), encoding="utf-8") as f:
            n = (json.load(f).get("values") or {}).get("Frames")
        return int(n) if n else None
    except Exception:
        return None


def pass_files(d):
    found = {}
    n = None
    for name in ("plate", "element", "light", "smoke", "glow", "depth"):
        fs = sorted(glob.glob(os.path.join(d, f"{name}_*.exr")))
        if name == "depth" and not fs:
            fs = sorted(glob.glob(os.path.join(d, "d_*.exr")))
        if fs:
            n = last_run_frames(d) if n is None else n
            found[name] = fs[-n:] if n and len(fs) > n else fs
    if "plate" not in found:
        raise ValueError("The run folder has no plate_*.exr: not an Element Forge pass folder.")
    return found


def run_fps(d, default=25.0):
    for f in sorted(glob.glob(os.path.join(d, "*.mp4"))):
        try:
            import av
            with av.open(f) as c:
                r = c.streams.video[0].average_rate
                if r:
                    return float(r)
        except Exception:
            continue
    return default


def load_frame(files, name, i, h, w):
    fs = files.get(name)
    if not fs:
        return None
    a = read_exr(fs[min(i, len(fs) - 1)])
    if a.shape[2] == 1:
        a = np.repeat(a, 3, 2)
    if a.shape[2] == 3:
        a = np.concatenate([a, np.ones_like(a[..., :1])], 2)
    a = a[..., :4]
    if a.shape[:2] != (h, w):
        t = torch.from_numpy(np.ascontiguousarray(a)).permute(2, 0, 1)[None]
        a = F.interpolate(t, size=(h, w), mode="bilinear", align_corners=False)[0].permute(1, 2, 0).numpy()
    return a


def _per_frame(v, n, default=0.0):
    t = torch.as_tensor(default if v is None else v, dtype=torch.float64).reshape(-1)
    return t.expand(n) if t.numel() == 1 else t


def _shift_scale(x, ox, oy, sc, rot=0.0, pivot=None, stretch=1.0):
    n, h, w, c = x.shape
    ox, oy, rot = _per_frame(ox, n), _per_frame(oy, n), _per_frame(rot, n)
    sc, st = _per_frame(sc, n, 1.0), _per_frame(stretch, n, 1.0)
    sc = torch.where(sc == 0, torch.ones_like(sc), sc)
    st = torch.where(st == 0, torch.ones_like(st), st)
    if not (ox.any() or oy.any() or rot.any() or (sc != 1).any() or (st != 1).any()):
        return x
    sx, sy = sc, sc * st
    a, b = w / 2, h / 2
    qx = 0.0 if pivot is None or pivot[0] is None else float(pivot[0]) - a
    qy = 0.0 if pivot is None or pivot[1] is None else float(pivot[1]) - b
    r = rot * (math.pi / 180)
    cs, sn = torch.cos(r), torch.sin(r)
    mx, my = qx + ox, qy + oy
    th = torch.stack([torch.stack([cs / sx, sn * b / (a * sx), -(cs * mx + sn * my) / (a * sx) + qx / a], -1),
                      torch.stack([-sn * a / (b * sy), cs / sy, (sn * mx - cs * my) / (b * sy) + qy / b], -1)], 1).to(x.dtype)
    grid = F.affine_grid(th, (n, c, h, w), align_corners=False)
    return F.grid_sample(x.permute(0, 3, 1, 2), grid, mode="bilinear", padding_mode="zeros", align_corners=False).permute(0, 2, 3, 1)


def grade_plate(p, plate):
    lum = LUMA.to(plate)
    P = plate[..., :3] * 2.0 ** p["exposure"]
    wb = torch.tensor([1 + 0.1 * p["temperature"] - 0.05 * p["tint"], 1 + 0.1 * p["tint"], 1 - 0.1 * p["temperature"] - 0.05 * p["tint"]]).to(P)
    P = P * wb
    pl = (P * lum).sum(-1, keepdim=True)
    P = pl + (P - pl) * p["saturation"]
    return 0.18 * (P.clamp(min=0) / 0.18) ** p["contrast"]


def layer_terms(s, element, light, smoke, like, glow_node=None):
    lum = LUMA.to(like)
    e = s["element"]
    E = element if element is not None else torch.zeros(like.shape[:-1] + (4,), dtype=like.dtype)
    E = _shift_scale(E, e["offset_x"], e["offset_y"], e["scale"], e["rotation"], (e["pivot_x"], e["pivot_y"]), e.get("stretch", 1.0))
    Ec, Ea = E[..., :3] * 2.0 ** e["gain"] * e["opacity"], (E[..., 3:4] * e["opacity"]).clamp(0, 1)
    el = (Ec * lum).sum(-1, keepdim=True)
    Ec = el + (Ec - el) * e["saturation"]
    if e["color_amount"] > 0:
        col = hex_lin(e["color"]).to(Ec)
        col = col / (col * lum).sum().clamp(min=1e-6)
        Ec = Ec * (1 - e["color_amount"]) + (Ec * lum).sum(-1, keepdim=True) * col * e["color_amount"]
    L = light[..., :3] * s["light"]["strength"] if light is not None else torch.zeros_like(like[..., :3])
    if light is not None and s["light"]["color_amount"] > 0:
        col = hex_lin(s["light"]["color"]).to(L)
        col = col / (col * lum).sum().clamp(min=1e-6)
        L = L * (1 - s["light"]["color_amount"]) + (L * lum).sum(-1, keepdim=True) * col * s["light"]["color_amount"]
    g = s["glow"]
    if element is None:
        G = torch.zeros_like(Ec)
    else:
        G = (glow_node or EFGlow()).glow(Ec, "linear", g["exposure"], max(2.0, g["radius"]), g["falloff"], g["threshold"],
                                          tint=g["color"] or "", tint_amount=g["color_amount"], core=max(0.5, g["core"]))[1]
    S = None
    if smoke is not None:
        S = (smoke[..., :3] * s["smoke"]["opacity"], (smoke[..., 3:4] * s["smoke"]["opacity"]).clamp(0, 1))
    return {"Ec": Ec, "Ea": Ea, "L": L, "G": G, "S": S, "mode": e["mode"], "visible": bool(e.get("visible", True))}


LIT_FLOOR, LIT_MAX = 0.05, 8.0
LIT_SOFT = 5


def soft(x, levels=LIT_SOFT):
    y = x.permute(0, 3, 1, 2)
    h, w = y.shape[-2:]
    for _ in range(levels):
        if min(y.shape[-2:]) < 2:
            break
        y = F.avg_pool2d(y, 2, ceil_mode=True)
    return F.interpolate(y, size=(h, w), mode="bilinear", align_corners=False).permute(0, 2, 3, 1)


def lit_by(t, Lo, P, amount):
    if amount <= 0:
        return t
    irr = (soft(Lo) / (soft((P[..., :3] * LUMA.to(P)).sum(-1, keepdim=True)) + LIT_FLOOR)).clamp(0, LIT_MAX)
    g = 1 + amount * irr
    t = dict(t, Ec=t["Ec"] * g)
    if t["S"] is not None:
        t["S"] = (t["S"][0] * g, t["S"][1])
    return t


def add_layer(C, t, wgt=None):
    k = 1.0 if wgt is None else wgt
    C = C + t["L"] * k
    if t.get("visible", True):
        C = C * (1 - t["Ea"] * k) + t["Ec"] * k if t["mode"] == "over" else C + t["Ec"] * k
    if t["S"] is not None:
        C = C * (1 - t["S"][1] * k) + t["S"][0] * k
    return C + t["G"] * k


DOF_STEPS = 4
DOF_SHARP = 0.02


DOF_AROUND = 0.03
DOF_NEAR = 95


def focus_depth(element, depth):
    el = np.asarray(element, np.float32)
    a = el[..., 3] if el.shape[-1] > 3 and float(el[..., 3].min()) < 0.99 else el[..., :3].max(-1)
    d = np.asarray(depth[..., 0], np.float32)
    if a.shape != d.shape or float(a.clip(0, 1).sum()) < 1.0:
        return None
    k = max(1, max(a.shape) // 512)
    m = torch.from_numpy(np.ascontiguousarray(a[::k, ::k] > 0.1, np.float32))[None, None]
    r = max(1, round(DOF_AROUND * max(a.shape) / k))
    m = F.max_pool2d(m, 2 * r + 1, stride=1, padding=r)[0, 0].numpy() > 0.5
    under = d[::k, ::k][m]
    return float(np.percentile(under, DOF_NEAR)) if under.size else None


def fill_focus(vals, default=0.5):
    out = list(vals)
    last = next((v for v in out if v is not None), default)
    for i, v in enumerate(out):
        if v is None:
            out[i] = last
        else:
            last = v
    return [round(float(v), 4) for v in out]


def run_focus(files, n, h, w, toff=0):
    if not files.get("element") or not files.get("depth"):
        return []
    vals = []
    for i in range(n):
        el = load_frame(files, "element", i - toff, h, w) if i - toff >= 0 else None
        vals.append(focus_depth(el, load_frame(files, "depth", i, h, w)) if el is not None else None)
    return fill_focus(vals)


def _gauss(C, sigma):
    if sigma < 0.3:
        return C
    x = C.permute(0, 3, 1, 2)
    h, w = x.shape[-2:]
    k = 1
    while sigma / k > 4 and min(h, w) // (k * 2) >= 8:
        k *= 2
    if k > 1:
        x = F.avg_pool2d(x, k, ceil_mode=True)
    sg = sigma / k
    r = max(1, int(math.ceil(sg * 3)))
    t = torch.arange(-r, r + 1, dtype=x.dtype, device=x.device)
    g = torch.exp(-(t ** 2) / (2 * sg * sg))
    g = (g / g.sum()).to(x)
    c = x.shape[1]
    x = F.conv2d(F.pad(x, (r, r, 0, 0), mode="replicate"), g.view(1, 1, 1, -1).repeat(c, 1, 1, 1), groups=c)
    x = F.conv2d(F.pad(x, (0, 0, r, r), mode="replicate"), g.view(1, 1, -1, 1).repeat(c, 1, 1, 1), groups=c)
    if k > 1:
        x = F.interpolate(x, size=(h, w), mode="bilinear", align_corners=False)
    return x.permute(0, 2, 3, 1)


def depth_blur(C, depth, focus, amount, rng):
    n, h, w, _ = C.shape
    smax = amount * 0.01 * max(h, w)
    if smax < 0.5 or depth is None or not focus:
        return C
    f = torch.tensor(focus[:n], dtype=C.dtype).view(-1, 1, 1, 1).to(C)
    coc = (((depth[..., :1] - f).abs() - DOF_SHARP).clamp(min=0) / max(1e-3, rng)).clamp(0, 1) * DOF_STEPS
    out = torch.zeros_like(C)
    prev = C
    for k in range(DOF_STEPS):
        nxt = _gauss(C, smax * (k + 1) / DOF_STEPS)
        wt = (1 - (coc - k).abs()).clamp(0, 1)
        out = out + prev * wt
        prev = nxt
    return out + prev * (1 - (coc - DOF_STEPS).abs()).clamp(0, 1)


def dof_plate(s, P, depth, frame_idx, focus=None):
    dof = s.get("dof") or {}
    if float(dof.get("amount", 0)) <= 0 or depth is None:
        return P
    fv = [float(dof["focus"])] * P.shape[0] if float(dof.get("focus", -1)) >= 0 else (
        [focus[min(int(i), len(focus) - 1)] for i in frame_idx] if focus else [0.5] * P.shape[0])
    return depth_blur(P, depth, fv, float(dof["amount"]), float(dof.get("range", 0.15)))


def finish_comp(s, C, depth, frame_idx):
    lum = LUMA.to(C)
    hz = s["haze"]
    if hz["amount"] > 0 and depth is not None:
        far = (1 - depth[..., :1]).clamp(0, 1)
        k = (hz["amount"] * ((far - (1 - hz["near"])) / max(1e-3, hz["near"])).clamp(0, 1)).clamp(0, 1)
        C = C * (1 - k) + hex_lin(hz["color"]).to(C) * k
    f = s["finish"]
    C = C * 2.0 ** f["exposure"]
    cl = (C * lum).sum(-1, keepdim=True)
    C = cl + (C - cl) * f["saturation"]
    if f["rolloff"] > 0:
        k = 1 - 0.6 * f["rolloff"]
        over = (C - k).clamp(min=0)
        C = torch.where(C > k, k + over / (1 + over / (1 - k + 1e-6)), C)
    n, h, w, _ = C.shape
    if f["vignette"] > 0:
        yy, xx = torch.meshgrid(torch.linspace(-1, 1, h), torch.linspace(-1, 1, w), indexing="ij")
        r2 = (xx ** 2 + yy ** 2) / 2
        C = C * (1 - f["vignette"] * r2.to(C)[None, ..., None] ** 1.5)
    if f["grain"] > 0:
        gen = torch.Generator().manual_seed(1)
        out = []
        for k_, fi in enumerate(frame_idx):
            gen.manual_seed(1000 + int(fi))
            nz = torch.randn((h, w, 1), generator=gen).to(C)
            out.append(C[k_] + nz * f["grain"] * 0.04 * C[k_].clamp(0, 1).sqrt())
        C = torch.stack(out)
    return C.clamp(min=0)


def apply_finish(s, plate, element, light, smoke, depth, frame_idx, glow_node=None, focus=None):
    P = dof_plate(s, grade_plate(s["plate"], plate), depth, frame_idx, focus)
    t = layer_terms(s, element, light, smoke, P, glow_node)
    return finish_comp(s, add_layer(P, t), depth, frame_idx), t["G"]


def _mp4_stream(c, fps, w, h):
    st = c.add_stream("libx264", rate=Fraction(fps).limit_denominator(1001))
    st.width, st.height, st.pix_fmt = w, h, "yuv420p"
    cc = st.codec_context
    cc.colorspace, cc.color_primaries, cc.color_trc, cc.color_range = 1, 1, 1, 1
    st.options = {"crf": "12", "x264-params": "colorprim=bt709:transfer=bt709:colormatrix=bt709"}
    return st


def _mp4_frame(q):
    import av
    from av.video.reformatter import ColorRange, Colorspace
    fr = av.VideoFrame.from_ndarray(np.ascontiguousarray(q), format="rgb24")
    return fr.reformat(format="yuv420p", dst_colorspace=Colorspace.ITU709, dst_color_range=ColorRange.MPEG)


def fade_weight(layer, frames):
    a, e = float(layer.get("start", 0)), float(layer.get("end", 1e9))
    fi, fo = max(0.0, float(layer.get("fade_in", 0))), max(0.0, float(layer.get("fade_out", 0)))
    out = []
    for f in frames:
        if f < a or f > e:
            out.append(0.0)
            continue
        w_ = 1.0
        if fi > 0:
            w_ = min(w_, (f - a + 1) / fi)
        if fo > 0:
            w_ = min(w_, (e - f + 1) / fo)
        out.append(max(0.0, min(1.0, w_)))
    return torch.tensor(out, dtype=torch.float32)[:, None, None, None]


EASES = {"even": lambda t: t, "in": lambda t: t * t, "out": lambda t: 1 - (1 - t) ** 2, "smooth": lambda t: t * t * (3 - 2 * t)}


def key_value(keys, f):
    ks = sorted(keys, key=lambda k: k[0])
    if f <= ks[0][0]:
        return float(ks[0][1])
    for k0, k1 in zip(ks, ks[1:]):
        if f < k1[0]:
            t = (f - k0[0]) / max(1e-9, k1[0] - k0[0])
            e = EASES.get(k0[2] if len(k0) > 2 else "even", EASES["even"])
            return float(k0[1]) + (float(k1[1]) - float(k0[1])) * e(t)
    return float(ks[-1][1])


KEYED = ("offset_x", "offset_y", "scale", "stretch", "rotation")


def keyed_settings(ss, keys, frames):
    keys = {k: v for k, v in (keys or {}).items() if v}
    if not any(k in keys for k in KEYED):
        return ss
    el = dict(ss["element"])
    for k in KEYED:
        if k in keys:
            el[k] = [key_value(keys[k], f) for f in frames]
    return {**ss, "element": el}


def key_weight(keys, frames):
    ks = (keys or {}).get("brightness")
    return torch.tensor([max(0.0, key_value(ks, f)) if ks else 1.0 for f in frames], dtype=torch.float32)[:, None, None, None]


def PASS_TILE(name, src):
    return EFPassPreview._tile(name, src)


class EFPassPreview:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "run_folder": ("STRING", {"default": "element-forge/my_run", "tooltip": "Pass folder of a run, relative to the ComfyUI output folder (plate_*.exr, element_*.exr, ...)."}),
            "long_side": ("INT", {"default": 768, "min": 128, "max": 2048, "step": 16, "tooltip": "Long side of one tile of the preview atlas (the atlas of 4 x 2 tiles stays within 4096 px per side, so a tile is at most 1024 wide)."}),
            "fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 240.0, "step": 0.001, "tooltip": "0 = read from the run's MP4."}),
        }, "optional": {
            "full_size": ("BOOLEAN", {"default": True, "tooltip": "Also write the passes at the clip's own size (long side up to 2048) as two 2 x 2 atlas videos, so the app shows a paused frame at full resolution."}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("manifest",)
    FUNCTION = "build"
    OUTPUT_NODE = True
    CATEGORY = "Element Forge/App"
    @classmethod
    def IS_CHANGED(s, run_folder, **kw):
        return float("nan")

    PREVIEW_BUILD = 2

    @staticmethod
    def _exr_key(d):
        return ";".join(f"{f}:{os.path.getmtime(os.path.join(d, f)):.0f}" for f in sorted(os.listdir(d)) if f.lower().endswith(".exr"))

    @staticmethod
    def _made(od, made_with):
        try:
            with open(os.path.join(od, "manifest.json"), encoding="utf-8") as f:
                man = json.load(f)
        except (OSError, ValueError):
            return None
        vids = [man.get("video") or "atlas.mp4"] + ((man.get("full") or {}).get("videos") or [])
        if man.get("made_with") != made_with or not all(os.path.isfile(os.path.join(od, v)) for v in vids):
            return None
        return man

    DESCRIPTION = ("Packs the passes of a run into one atlas video for the Element Forge app's live post (4 x 2 tiles: plate, "
                   "element, light, smoke / element alpha, depth, smoke alpha, glow; HDR passes log encoded). Writes "
                   "<run>/app_preview/atlas.mp4 and manifest.json.")

    @staticmethod
    def _stream(c, fps, w, h, crf):
        st = c.add_stream("libx264", rate=Fraction(fps).limit_denominator(1001))
        st.width, st.height, st.pix_fmt = w, h, "yuvj420p"
        st.codec_context.color_range = 2
        st.options = {"crf": crf, "preset": "medium", "g": "1",
                      "x264-params": "colorprim=bt709:transfer=bt709:colormatrix=bt709:fullrange=on"}
        return st

    @staticmethod
    def _frame(at, gen, bank=None):
        import av
        r, g, b = at.unbind(-1)
        y = 0.2126 * r + 0.7152 * g + 0.0722 * b
        cb = (b - y) / 1.8556 + 0.5
        cr = (r - y) / 1.5748 + 0.5
        pool = lambda x: F.avg_pool2d(x[None, None], 2)[0, 0]
        cb, cr, ym = pool(cb), pool(cr), pool(((y > 0) & (y < 1)).float()) > 0

        def q(x, live):
            h, w = x.shape
            if bank is not None and bank.shape[0] >= h + 64 and bank.shape[1] >= w + 64:
                oy, ox = (int(v) for v in torch.randint(0, 64, (2,), generator=gen))
                noise = bank[oy:oy + h, ox:ox + w]
            else:
                noise = torch.rand(x.shape, generator=gen) - torch.rand(x.shape, generator=gen)
            return (x * 255.0 + noise * live + 0.5).clamp_(0, 255).to(torch.uint8)
        yuv = torch.cat([q(y, (y > 0) & (y < 1)).flatten(), q(cb, ym).flatten(), q(cr, ym).flatten()])
        h, w = y.shape
        return av.VideoFrame.from_ndarray(yuv.numpy().reshape(h * 3 // 2, w), format="yuvj420p")

    @staticmethod
    def _tile(name, src):
        if name.endswith("_alpha"):
            return src[..., 3:4].expand(-1, -1, 3)
        if name == "plate":
            return linear_to_srgb(src[..., :3].clamp(0, 1))
        if name == "depth":
            return src[..., :1].clamp(0, 1).expand(-1, -1, 3)
        return torch.log2(1 + LOG_A * src[..., :3].clamp(0, LOG_MAX)) / math.log2(1 + LOG_A * LOG_MAX)

    @staticmethod
    def _atlas(tiles, names, h, w, cols):
        at = torch.zeros((h * ((len(names) + cols - 1) // cols), w * cols, 3))
        for k, name in enumerate(names):
            src = tiles.get(name.replace("_alpha", ""))
            if src is None:
                continue
            r, cc = divmod(k, cols)
            at[r * h:(r + 1) * h, cc * w:(cc + 1) * w] = PASS_TILE(name, src)
        return at

    def build(self, run_folder, long_side, fps, full_size=True):
        import av
        from concurrent.futures import ThreadPoolExecutor
        d = run_dir(run_folder)
        files = pass_files(d)
        made_with = {"build": self.PREVIEW_BUILD, "long_side": long_side, "fps": fps, "full_size": bool(full_size), "exr": self._exr_key(d)}
        man = self._made(os.path.join(d, "app_preview"), made_with)
        if man:
            return {"ui": {"text": [json.dumps(man)]}, "result": (json.dumps(man),)}
        n = len(files["plate"])
        ph, pw = read_exr(files["plate"][0]).shape[:2]
        sc = long_side / max(ph, pw)
        sc = min(sc, 1024 / pw, 2048 / ph)
        th, tw = int(round(ph * sc / 2)) * 2, int(round(pw * sc / 2)) * 2
        fs = min(1.0, 2048 / max(ph, pw))
        fh, fw = int(round(ph * fs / 2)) * 2, int(round(pw * fs / 2)) * 2
        rh, rw = (fh, fw) if full_size else (th, tw)
        fps = fps or run_fps(d)
        od = os.path.join(d, "app_preview")
        os.makedirs(od, exist_ok=True)
        gen = torch.Generator().manual_seed(7)
        bh, bw = max(th * 2, fh * 2 if full_size else 0) + 64, max(tw * 4, fw * 2 if full_size else 0) + 64
        bank = torch.rand((bh, bw), generator=gen) - torch.rand((bh, bw), generator=gen)
        names_full = ["atlas_full_a.mp4", "atlas_full_b.mp4"]
        outs, streams = [], []
        passes = ("plate", "element", "light", "smoke", "glow", "depth")
        io = ThreadPoolExecutor(len(passes))
        read = lambda i: {k: v for k, v in zip(passes, io.map(lambda nm: load_frame(files, nm, i, rh, rw), passes)) if v is not None}
        try:
            outs.append(av.open(os.path.join(od, "atlas.part.mp4"), "w"))
            streams.append(self._stream(outs[-1], fps, tw * 4, th * 2, "12"))
            if full_size:
                for x in names_full:
                    outs.append(av.open(os.path.join(od, x.replace(".mp4", ".part.mp4")), "w"))
                    streams.append(self._stream(outs[-1], fps, fw * 2, fh * 2, "14"))
            ahead = io.submit(read, 0)
            focus = []
            for i in range(n):
                frame = ahead.result()
                if i + 1 < n:
                    ahead = io.submit(read, i + 1)
                if "element" in frame and "depth" in frame:
                    focus.append(focus_depth(frame["element"], frame["depth"]))
                big = {k: torch.from_numpy(np.ascontiguousarray(v)) for k, v in frame.items()}
                small = big if (rh, rw) == (th, tw) else {
                    k: F.interpolate(v.permute(2, 0, 1)[None], size=(th, tw), mode="bilinear", align_corners=False, antialias=True)[0].permute(1, 2, 0)
                    for k, v in big.items()}
                ats = [self._atlas(small, TILES, th, tw, 4)]
                if full_size:
                    ats += [self._atlas(big, TILES[:4], fh, fw, 2), self._atlas(big, TILES[4:], fh, fw, 2)]
                for c, st, at in zip(outs, streams, ats):
                    for pkt in st.encode(self._frame(at, gen, bank)):
                        c.mux(pkt)
            for c, st in zip(outs, streams):
                for pkt in st.encode():
                    c.mux(pkt)
        finally:
            io.shutdown(wait=True)
            for c in outs:
                c.close()
        full = None
        if full_size:
            names = names_full
            full = {"tile_size": [fw, fh], "grid": [2, 2], "videos": names}
        man = {"schema": "element-forge-pass-preview/1", "run_folder": run_folder.replace("\\", "/"), "frames": n, "fps": fps,
               "plate_size": [pw, ph], "tile_size": [tw, th], "grid": [4, 2], "tiles": TILES,
               "passes": {k: len(v) for k, v in files.items()},
               "encoding": {"hdr": {"kind": "log2", "a": LOG_A, "max": LOG_MAX}, "plate": "sRGB", "depth": "linear, near = 1",
                            "alpha": "linear"},
               "video": "atlas.mp4", "full": full, "focus": fill_focus(focus) if focus else [], "made_with": made_with}
        with open(os.path.join(od, "manifest.part.json"), "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1)
        for x in ["atlas.mp4"] + (full["videos"] if full else []) + ["manifest.json"]:
            src, dst = os.path.join(od, x.replace(".mp4", ".part.mp4").replace(".json", ".part.json")), os.path.join(od, x)
            for k in range(40):
                try:
                    os.replace(src, dst)
                    break
                except PermissionError:
                    if k == 39:
                        raise
                    time.sleep(0.25)
        return {"ui": {"text": [json.dumps(man)]}, "result": (json.dumps(man),)}


def _exr_comp(path, a):
    import OpenImageIO as oiio
    spec = oiio.ImageSpec(a.shape[1], a.shape[0], 3, "half")
    spec.attribute("compression", "zip")
    spec.attribute("oiio:ColorSpace", "lin_rec709")
    o = oiio.ImageOutput.create(path)
    o.open(path, spec)
    o.write_image(np.ascontiguousarray(a[..., :3], dtype=np.float32))
    o.close()


def _exr_layer(path, rgb, a=None):
    import OpenImageIO as oiio
    px = rgb[..., :3] if a is None else np.concatenate([rgb[..., :3], a[..., :1]], axis=-1)
    spec = oiio.ImageSpec(px.shape[1], px.shape[0], px.shape[2], "half")
    spec.channelnames = ("R", "G", "B") if a is None else ("R", "G", "B", "A")
    if a is not None:
        spec.alpha_channel = 3
    spec.attribute("compression", "zip")
    spec.attribute("oiio:ColorSpace", "lin_rec709")
    o = oiio.ImageOutput.create(path)
    if not o or not o.open(path, spec):
        raise RuntimeError(f"EXR write failed: {oiio.geterror()}")
    o.write_image(np.ascontiguousarray(px, dtype=np.float32))
    o.close()


class EFFinishStack:

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "layers": ("STRING", {"default": "[]", "multiline": True, "tooltip": "JSON list, bottom to top: {run_folder, settings, start, end, fade_in, fade_out, keys} (frames). keys (optional): {offset_x | offset_y | scale | stretch | rotation | brightness: [[frame, value, ease], ...]}, ease even / in / out / smooth. All runs must come from the same clip."}),
            "common": ("STRING", {"default": "{}", "multiline": True, "tooltip": "Post settings for the whole comp (plate grade, haze, finish) as JSON; the groups element/light/glow/smoke are taken per layer."}),
            "out_folder": ("STRING", {"default": "element-forge/studio/comp", "tooltip": "Folder for the result, relative to the ComfyUI output folder (comp.mp4, comp_#####.exr, stack.json)."}),
            "write_exr": ("BOOLEAN", {"default": True}),
            "fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 240.0, "step": 0.001, "tooltip": "0 = read from the first run's MP4."}),
            "chunk": ("INT", {"default": 8, "min": 1, "max": 128}),
        }, "optional": {
            "write_layers": ("BOOLEAN", {"default": False, "tooltip": "Also write every effect's passes (light, element, smoke, glow) as they go into the comp, the plate and the depth as EXR sequences under layers/."}),
            "comp_name": ("STRING", {"default": "Element Forge shot", "tooltip": "Name of the export (kept for older calls)."}),
            "format": (["mp4", "prores", "h265", "png8", "png16", "exr"], {"default": "mp4", "tooltip": "The comp as H.264 MP4 (8 bit), ProRes 422 HQ (10 bit, .mov), H.265 (10 bit), a PNG sequence (8 or 16 bit) or an EXR sequence (half, linear). comp.mp4 is always written too, to watch it."}),
            "frame_start": ("INT", {"default": 0, "min": 0, "max": 100000, "tooltip": "First frame of the export (0 = the clip's first)."}),
            "frame_end": ("INT", {"default": -1, "min": -1, "max": 100000, "tooltip": "Last frame of the export, inclusive (-1 = the clip's last)."}),
            "hdr": ("BOOLEAN", {"default": False, "tooltip": "H.265 only: HDR10 (PQ, BT.2020) through NVIDIA RTX TrueHDR; needs an RTX card and NVIDIA's nodes."}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("preview", "report")
    FUNCTION = "stack"
    OUTPUT_NODE = True
    CATEGORY = "Element Forge/App"
    DESCRIPTION = ("Renders the comp of several runs of one plate at full resolution: the plate of the first run graded once, "
                   "then every run's element, light, glow and smoke with its own post settings and visibility window "
                   "(start/end with fades), then haze and finish for the whole comp.")

    def stack(self, layers, common, out_folder, write_exr, fps, chunk, write_layers=False, comp_name="Element Forge shot",
              format="mp4", frame_start=0, frame_end=-1, hdr=False):
        from ..output.video_out import CompWriter, srgb_encode, true_hdr
        if hdr and format != "h265":
            raise ValueError("HDR is written as H.265 10 bit: choose format h265")
        L = json.loads(layers) if isinstance(layers, str) else layers
        if not L:
            raise ValueError("No layers.")
        base = os.path.realpath(folder_paths.get_output_directory())
        od = os.path.realpath(os.path.join(base, out_folder))
        if os.path.commonpath([base, od]) != base:
            raise ValueError("out_folder must be inside the ComfyUI output folder")
        os.makedirs(od, exist_ok=True)
        cs = merge_settings(common)
        runs = []
        for ly in L:
            d = run_dir(ly["run_folder"])
            runs.append((ly, merge_settings(ly.get("settings") or {}), pass_files(d), d))
        files0 = runs[0][2]
        n = len(files0["plate"])
        h, w = read_exr(files0["plate"][0]).shape[:2]
        fps = fps or run_fps(runs[0][3])
        glow = EFGlow()
        to = lambda a: torch.from_numpy(np.stack(a)) if a and a[0] is not None else None
        previews = []
        names, passes = [], []
        for j, (ly, ss, files, _) in enumerate(runs):
            nm = "".join(c for c in str(ly.get("name") or f"effect {j + 1}") if c.isalnum() or c in " _-").strip().replace(" ", "_").lower() or f"effect{j + 1}"
            names.append(f"{j + 1:02d}_{nm}")
            ps = []
            if "light" in files and ss["light"]["strength"] > 0:
                ps.append("light")
            if "element" in files and ss["element"].get("visible", True):
                ps.append("element")
            if "smoke" in files and ss["smoke"]["opacity"] > 0:
                ps.append("smoke")
            if "element" in files and ss["glow"]["exposure"] > -29:
                ps.append("glow")
            passes.append(ps)
        lay_dir = os.path.join(od, "layers")
        def put(sub, i, rgb, a=None):
            os.makedirs(os.path.join(lay_dir, sub), exist_ok=True)
            _exr_layer(os.path.join(lay_dir, sub, f"{sub}_{i + 1:05d}.exr"), rgb, a)
        ss0, fl0 = runs[0][1], runs[0][2]
        focus = (run_focus(fl0, n, h, w, int(ss0["element"]["time_offset"]))
                 if cs["dof"]["amount"] > 0 and cs["dof"]["focus"] < 0 else None)
        a0 = max(0, min(n - 1, int(frame_start)))
        a1 = n - 1 if int(frame_end) < 0 else max(a0, min(n - 1, int(frame_end)))
        view = CompWriter(od, "mp4", fps, w, h)
        own = CompWriter(od, format, fps, w, h, hdr=hdr) if format != "mp4" or hdr else None
        try:
            for c0 in range(a0, a1 + 1, chunk):
                idx = list(range(c0, min(a1 + 1, c0 + chunk)))
                dep = to([load_frame(files0, "depth", i, h, w) for i in idx]) if "depth" in files0 else None
                P = dof_plate(cs, grade_plate(cs["plate"], to([load_frame(files0, "plate", i, h, w) for i in idx])), dep, idx, focus)
                C = P
                if write_layers:
                    for k, i in enumerate(idx):
                        put("plate", i, P[k].numpy())
                terms = {}
                for j, (ly, ss, files, _) in enumerate(runs):
                    wgt = fade_weight(ly, idx) * key_weight(ly.get("keys"), idx)
                    if float(wgt.max()) <= 0:
                        continue
                    toff = int(ss["element"]["time_offset"])
                    el = [load_frame(files, "element", i - toff, h, w) if i - toff >= 0 else np.zeros((h, w, 4), np.float32)
                          for i in idx] if "element" in files else [None]
                    terms[j] = (layer_terms(keyed_settings(ss, ly.get("keys"), idx), to(el), to([load_frame(files, "light", i, h, w) for i in idx]) if "light" in files else None,
                                            to([load_frame(files, "smoke", i, h, w) for i in idx]) if "smoke" in files else None, P, glow), wgt)
                Lsum = sum(t["L"] * wg for t, wg in terms.values()) if terms else None
                for j, (ly, ss, files, _) in enumerate(runs):
                    wgt = fade_weight(ly, idx) * key_weight(ly.get("keys"), idx)
                    if float(wgt.max()) <= 0:
                        if write_layers:
                            zero = np.zeros((h, w, 3), np.float32)
                            for i in idx:
                                for p in passes[j]:
                                    put(f"{names[j]}_{p}", i, zero, np.zeros((h, w, 1), np.float32) if p in ("element", "smoke") else None)
                        continue
                    t = terms[j][0]
                    if len(terms) > 1 and ss["lit"]["others"] > 0:
                        t = lit_by(t, (Lsum - t["L"] * wgt).clamp(min=0), P, ss["lit"]["others"])
                    C = add_layer(C, t, wgt)
                    if write_layers:
                        for k, i in enumerate(idx):
                            kk = float(wgt[k])
                            for p in passes[j]:
                                if p == "light":
                                    put(f"{names[j]}_light", i, (t["L"][k] * kk).numpy())
                                elif p == "element":
                                    put(f"{names[j]}_element", i, (t["Ec"][k] * kk).numpy(), (t["Ea"][k] * kk).numpy() if t["mode"] == "over" else None)
                                elif p == "smoke" and t["S"] is not None:
                                    put(f"{names[j]}_smoke", i, (t["S"][0][k] * kk).numpy(), (t["S"][1][k] * kk).numpy())
                                elif p == "glow":
                                    put(f"{names[j]}_glow", i, (t["G"][k] * kk).numpy())
                if write_layers and dep is not None:
                    for k, i in enumerate(idx):
                        put("depth", i, dep[k][..., :1].repeat(1, 1, 3).numpy())
                C = finish_comp(cs, C, dep, idx)
                srgb = linear_to_srgb(C.clamp(0, 1))
                for k, i in enumerate(idx):
                    if write_exr and format != "exr":
                        _exr_comp(os.path.join(od, f"comp_{i + 1:05d}.exr"), C[k].numpy())
                view.add(C, idx)
                if own is not None:
                    own.add(true_hdr(srgb_encode(C)) if hdr else C, idx)
                small = F.interpolate(srgb.permute(0, 3, 1, 2), scale_factor=512 / max(h, w), mode="area") if max(h, w) > 512 else srgb.permute(0, 3, 1, 2)
                previews.append(small.permute(0, 2, 3, 1))
        finally:
            view.close()
            if own is not None:
                own.close()
        rep = {"layers": [ly["run_folder"] for ly in L], "frames": n, "size": [w, h], "fps": fps,
               "out": os.path.relpath(od, base).replace("\\", "/"), "exr": bool(write_exr), "format": format, "hdr": bool(hdr),
               "range": [a0, a1], "file": (own.files[0] if own is not None and own.files else "comp.mp4")}
        with open(os.path.join(od, "stack.json"), "w", encoding="utf-8") as f:
            json.dump({"layers": L, "common": cs, "report": rep}, f, indent=1)
        return (torch.cat(previews).float(), json.dumps(rep))


def _latent_path(run_folder, name):
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "latent"
    return os.path.join(run_dir(run_folder), f"latent_{safe}.safetensors")


class EFRunLatent:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "samples": ("LATENT",),
            "run_folder": ("STRING", {"default": "element-forge/my_run", "tooltip": "Run folder, relative to the ComfyUI output folder."}),
            "name": ("STRING", {"default": "pass1", "tooltip": "File name part: latent_<name>.safetensors"}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "keep"
    CATEGORY = "Element Forge/App"
    DESCRIPTION = "Keeps the generated latent in the run folder (latent_<name>.safetensors) and passes it on unchanged."

    def keep(self, samples, run_folder, name):
        from safetensors.torch import save_file
        os.makedirs(os.path.join(folder_paths.get_output_directory(), run_folder), exist_ok=True)
        tensors = {k: v.detach().cpu().contiguous() for k, v in samples.items() if torch.is_tensor(v)}
        meta = {"other": json.dumps({k: v for k, v in samples.items() if not torch.is_tensor(v)}, default=str)}
        save_file(tensors, _latent_path(run_folder, name), metadata=meta)
        return (samples,)


class EFLoadRunLatent:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "run_folder": ("STRING", {"default": "element-forge/my_run", "tooltip": "Run folder of the preview, relative to the ComfyUI output folder."}),
            "name": ("STRING", {"default": "pass1"}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "load"
    CATEGORY = "Element Forge/App"
    DESCRIPTION = "Loads a latent kept by EF Run Latent, to finish a preview without generating it again."

    @classmethod
    def IS_CHANGED(s, run_folder, name):
        try:
            return os.path.getmtime(_latent_path(run_folder, name))
        except (OSError, ValueError):
            return float("nan")

    def load(self, run_folder, name):
        from safetensors import safe_open
        p = _latent_path(run_folder, name)
        if not os.path.isfile(p):
            raise ValueError(f"No kept latent {os.path.basename(p)} in {run_folder}: make the preview first.")
        out = {}
        with safe_open(p, framework="pt") as f:
            for k in f.keys():
                out[k] = f.get_tensor(k)
            other = json.loads((f.metadata() or {}).get("other") or "{}")
        for k, v in other.items():
            out.setdefault(k, v)
        return (out,)
