import cv2
import numpy as np
import torch

from .track import srgb_to_linear

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)
ACESCG_TO_REC709 = np.array([[1.70505, -0.62179, -0.08326],
                             [-0.13026, 1.14080, -0.01055],
                             [-0.02400, -0.12897, 1.15297]], np.float32)


def to_np(t):
    return t.detach().cpu().float().numpy()


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / max(e1 - e0, 1e-6), 0, 1)
    return t * t * (3 - 2 * t)


def merge_frame(rgb, a, hdr, clip_from, max_gain, hue_from_hdr):
    h, w = a.shape
    sdr = srgb_to_linear(rgb) * a[..., None]
    hd = cv2.resize(np.maximum(hdr, 0), (w, h), interpolation=cv2.INTER_LINEAR)
    s_lo = cv2.resize(sdr, (hdr.shape[1], hdr.shape[0]), interpolation=cv2.INTER_AREA)
    s_lo = cv2.resize(s_lo, (w, h), interpolation=cv2.INTER_LINEAR)
    ls, lh = s_lo @ LUMA, hd @ LUMA
    gain = np.clip((lh + 1e-4) / (ls + 1e-4), 1.0, max_gain)
    wgt = smoothstep(clip_from, 1.0, rgb.max(-1) * a)
    blur = max(1.0, 0.5 * w / hdr.shape[1])
    wgt = cv2.GaussianBlur(wgt.astype(np.float32), (0, 0), blur)
    gain = 1 + wgt * (cv2.GaussianBlur(gain.astype(np.float32), (0, 0), blur) - 1)
    out = sdr * gain[..., None]
    if hue_from_hdr > 0:
        lo = out @ LUMA
        hue = hd / np.maximum(lh, 1e-4)[..., None] * lo[..., None]
        k = (wgt * hue_from_hdr)[..., None]
        out = out * (1 - k) + hue * k
    return out.astype(np.float32)


class EFHDRMerge:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "rgba": ("IMAGE", {"tooltip": "The element (straight sRGB with alpha, e.g. from EF Load Element or EF Unmult) at full resolution."}),
                "hdr": ("IMAGE", {"tooltip": "hdr_linear of LTXV HDR Decode Postprocess: the same element run through the SDR-to-HDR IC-LoRA (smaller is fine)."}),
                "hdr_space": (["ACEScg (LTX HDR)", "linear Rec.709"], {"tooltip": "The LTX HDR decoder gives ACEScg; it is converted to linear Rec.709 like the rest of Element Forge."}),
                "clip_from": ("FLOAT", {"default": 0.85, "min": 0.3, "max": 1.0, "step": 0.01, "tooltip": "SDR value from which the HDR result takes over (premultiplied, max channel). Below it the element stays unchanged."}),
                "max_gain": ("FLOAT", {"default": 16.0, "min": 1.0, "max": 256.0, "step": 0.5, "tooltip": "Highest brightening of the core over the SDR value."}),
                "hue_from_hdr": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "How much of the HDR hue replaces the white of the clipped SDR core."}),
            },
            "optional": {"alpha": ("MASK", {"tooltip": "Alpha if the element image has none."})},
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("hdr_premult_linear", "report")
    FUNCTION = "merge"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Gives the element real HDR values: where it clips to flat white, the core is brightened with the "
                   "result of the LTX SDR-to-HDR IC-LoRA (values above 1, colour back in the core); the rest, the edges "
                   "and the alpha stay exactly as generated. Output: linear premultiplied Rec.709 for EF Save Element "
                   "(hdr), EF Anchor (hdr) and EF Place Element (element_hdr), or straight into EF Save EXR.")

    def merge(self, rgba, hdr, hdr_space, clip_from, max_gain, hue_from_hdr, alpha=None):
        el = to_np(rgba)
        rgb = el[..., :3]
        a = to_np(alpha) if alpha is not None else (el[..., 3] if el.shape[-1] > 3 else rgb.max(-1))
        if a.shape[0] == 1 and len(rgb) > 1:
            a = np.repeat(a, len(rgb), 0)
        hd = to_np(hdr)[..., :3]
        aces = hdr_space.startswith("ACEScg")
        out = None
        for i in range(len(rgb)):
            h = hd[min(i, len(hd) - 1)]
            f = merge_frame(rgb[i], a[i], h @ ACESCG_TO_REC709.T if aces else h, clip_from, max_gain, hue_from_hdr)
            if out is None:
                out = np.empty((len(rgb),) + f.shape, f.dtype)
            out[i] = f
        lum = out @ LUMA
        core = a > 0.5
        share = float((lum[core] > 1).mean() * 100) if core.any() else 0.0
        frames = f"{len(rgb)} frames" + ("" if len(hd) >= len(rgb) else f" (HDR has only {len(hd)}, last one repeated)")
        report = f"{frames}, max {out.max():.2f}, p99.9 {np.percentile(lum, 99.9):.2f}, {share:.1f} % of the core above 1"
        return (torch.from_numpy(out), report)
