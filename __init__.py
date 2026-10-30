import torch

import comfy.utils


def srgb_to_linear(x):
    return torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055).clamp(min=0.0).pow(2.4))


def linear_to_srgb(x):
    return torch.where(x <= 0.0031308, x * 12.92, 1.055 * x.clamp(min=0.0).pow(1.0 / 2.4) - 0.055)


def edge_contact(alpha, line=0.03):
    n, h, w = alpha.shape
    k = max(2, round(0.01 * min(h, w)))
    hist = torch.histc(alpha[:, ::4, ::4].float().clamp(0, 1), 200, 0.0, 1.0)[2:]
    cum = hist.cumsum(0)
    ref = float((torch.searchsorted(cum, 0.995 * cum[-1]) + 2.5) / 200) if n and cum[-1] > 0 else 0.0
    thr = max(0.04, 0.3 * ref)
    strips = {"top": alpha[:, :k, :].amax(1), "bottom": alpha[:, -k:, :].amax(1),
              "left": alpha[:, :, :k].amax(2), "right": alpha[:, :, -k:].amax(2)}
    sides = {}
    for s, v in strips.items():
        share = (v > thr).float().mean(1)
        sides[s] = {"frames": int((share > line).sum()), "max": round(float(share.max()), 3) if n else 0.0}
    return {"frames": n, "size": [w, h], "threshold": round(thr, 3), "sides": sides}


class EFUnmult:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "background": (["black", "white"], {"tooltip": "black: glowing elements rendered on black (fire, sparks, energy). white: absorbing elements rendered on white (dark smoke, dust)."}),
                "black_point": ("FLOAT", {"default": 0.03, "min": 0.0, "max": 0.5, "step": 0.005, "tooltip": "How far from the background color a pixel may be and still become fully transparent. Removes noise in the rendered background."}),
                "alpha_gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.05, "tooltip": "Shapes the alpha only. Above 1 makes faint parts more transparent, below 1 more opaque."}),
            },
            "optional": {
                "auto_background": ("BOOLEAN", {"default": False, "tooltip": "Measures the rendered background per color channel (it is rarely exactly black or white, often slightly tinted) and normalizes it, so the background becomes fully transparent. Recommended for elements on white."}),
                "alpha_from": (["max channel", "luminance"], {"tooltip": "max channel: keeps colored light (fire, energy). luminance: one alpha for all channels, removes color noise in faint parts; good for smoke and dust."}),
                "matte": ("MASK", {"tooltip": "External alpha, e.g. from the LTX-2.5 Alpha Gen IC-LoRA (matte video -> Image To Mask). Replaces the computed alpha; the color is solved for it against the background (black or white, after auto_background). Resized to the frame size."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("rgba", "color", "alpha")
    FUNCTION = "run"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Turns an element rendered on black or white into a layer with straight alpha. Works in linear light: alpha is the strongest linear channel, the color is divided by alpha, so the layer added back in linear light gives exactly the rendered light."

    @staticmethod
    def background_level(lin, white):
        n, h, w, _ = lin.shape
        return EFUnmult._level(torch.nn.functional.avg_pool2d(lin.permute(0, 3, 1, 2), 8, ceil_mode=True), h, w, white)

    @staticmethod
    def _level(x, h, w, white):
        n = x.shape[0]
        x = torch.quantile(x, 0.9 if white else 0.1, dim=0, keepdim=True) if n > 1 else x
        k = max(3, (min(x.shape[2:]) // 6) | 1)
        x = torch.nn.functional.max_pool2d(x if white else -x, k, 1, k // 2)
        x = x if white else -x
        x = torch.nn.functional.avg_pool2d(x, k, 1, k // 2, count_include_pad=False)
        x = torch.nn.functional.interpolate(x, size=(h, w), mode="bilinear", align_corners=False)
        return x.permute(0, 2, 3, 1)

    def unmult(self, image, background, black_point, alpha_gamma, auto_background=False, alpha_from="max channel", matte=None):
        n, h, w = image.shape[:3]
        ch = max(1, (1 << 28) // max(h * w * 12, 1))
        lin_of = lambda s: srgb_to_linear(image[s:s + ch, ..., :3].float().clamp(0.0, 1.0))
        lvl = None
        if auto_background:
            pooled = torch.cat([torch.nn.functional.avg_pool2d(lin_of(s).permute(0, 3, 1, 2), 8, ceil_mode=True) for s in range(0, n, ch)])
            lvl = self._level(pooled, h, w, background == "white")
        out = None
        for s in range(0, n, ch):
            r = self._unmult(lin_of(s), background, black_point, alpha_gamma, lvl, alpha_from, matte, s)
            if out is None:
                out = torch.empty((n, h, w, 4), dtype=r.dtype)
            out[s:s + len(r)] = r
        return (out, out[..., :3], out[..., 3])

    def run(self, **kw):
        res = self.unmult(**kw)
        return {"ui": {"edge": [edge_contact(res[2])]}, "result": res}

    def _unmult(self, lin, background, black_point, alpha_gamma, lvl, alpha_from, matte, offset):
        if lvl is not None:
            if background == "white":
                lin = (lin / lvl.clamp(min=1e-3)).clamp(0.0, 1.0)
            else:
                lin = ((lin - lvl) / (1.0 - lvl).clamp(min=1e-3)).clamp(0.0, 1.0)
        if matte is not None:
            return self.with_matte(lin, background == "white", matte, alpha_gamma, offset)[0]
        if background == "white":
            lin = 1.0 - lin
        bp = float(srgb_to_linear(torch.tensor(black_point)))
        lin = ((lin - bp) / (1.0 - bp)).clamp(0.0, 1.0)
        if alpha_from == "luminance":
            alpha = (lin * lin.new_tensor([0.2126, 0.7152, 0.0722])).sum(-1, keepdim=True).clamp(0.0, 1.0)
        else:
            alpha = lin.amax(dim=-1, keepdim=True)
        straight = (lin / alpha.clamp(min=1e-6)).clamp(0.0, 1.0)
        if background == "white":
            straight = 1.0 - straight
        color = linear_to_srgb(straight).clamp(0.0, 1.0)
        if alpha_gamma != 1.0:
            alpha = alpha.pow(alpha_gamma)
        return torch.cat((color, alpha), dim=-1)

    @staticmethod
    def with_matte(lin, white, matte, alpha_gamma, offset=0):
        n, h, w, _ = lin.shape
        m = matte.float()
        m = m if m.dim() == 3 else m.reshape(-1, *m.shape[-2:])
        m = m[(torch.arange(n) + offset) % m.shape[0]]
        if m.shape[-2:] != (h, w):
            m = torch.nn.functional.interpolate(m[:, None], size=(h, w), mode="bilinear", align_corners=False)[:, 0]
        alpha = m.clamp(0.0, 1.0)[..., None].to(lin)
        a = alpha.clamp(min=1e-4)
        straight = ((lin - 1.0 + alpha) / a if white else lin / a).clamp(0.0, 1.0)
        straight = torch.where(alpha > 1e-4, straight, torch.zeros_like(straight))
        if alpha_gamma != 1.0:
            alpha = alpha.pow(alpha_gamma)
        color = linear_to_srgb(straight).clamp(0.0, 1.0)
        return (torch.cat((color, alpha), dim=-1), color, alpha.squeeze(-1))


class EFCompPreview:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "element": ("IMAGE", {"tooltip": "Layer with alpha, e.g. the rgba output of EF Unmult. Without alpha the layer counts as fully opaque."}),
                "mode": (["over", "screen", "add", "multiply"], {"tooltip": "over: normal comp with alpha. screen and add: classic comp for glowing elements. multiply: for elements unmulted from white."}),
            },
            "optional": {
                "background": ("IMAGE", {"tooltip": "Plate to comp onto. A still is repeated for every frame. Without a plate a checkerboard shows the alpha."}),
                "largest side": ("INT", {"default": 0, "min": 0, "max": 16384, "advanced": True,
                                         "tooltip": "Shrinks the result so its longer side is at most this many pixels: a preview of a long, large clip needs far less memory. 0 = full size."}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "comp"
    CATEGORY = "Element Forge"

    def comp(self, element, mode, background=None, **kw):
        frames, height, width = element.shape[:3]
        side = kw.get("largest side", 0)
        if side and max(height, width) > side:
            height, width = max(1, round(height * side / max(height, width))), max(1, round(width * side / max(height, width)))
        out = None
        for i in range(0, frames, 16):
            part = element[i:i + 16]
            if part.shape[1:3] != (height, width):
                part = comfy.utils.common_upscale(part.movedim(-1, 1), width, height, "area", "disabled").movedim(1, -1)
            bg = background
            if background is not None and background.shape[0] > 1:
                if background.shape[0] < frames:
                    background = comfy.utils.repeat_to_batch_size(background, frames)
                bg = background[i:i + part.shape[0]]
            res = self._comp(part, mode, bg)
            if out is None:
                out = torch.empty((frames, height, width, 3), dtype=res.dtype)
            out[i:i + res.shape[0]] = res
        return (out,)

    def _comp(self, element, mode, background=None):
        frames, height, width = element.shape[:3]
        color = element[..., :3]
        if element.shape[-1] > 3:
            alpha = element[..., 3:4]
        else:
            alpha = torch.ones_like(color[..., :1])

        if background is None:
            ys = torch.arange(height) // 16
            xs = torch.arange(width) // 16
            checker = ((ys[:, None] + xs[None, :]) % 2) * 0.2 + 0.4
            background = checker[None, :, :, None].expand(1, height, width, 3)
        background = background[..., :3]
        if background.shape[1] != height or background.shape[2] != width:
            background = comfy.utils.common_upscale(background.movedim(-1, 1), width, height, "bilinear", "center").movedim(1, -1)
        background = comfy.utils.repeat_to_batch_size(background, frames).to(color)

        premult = srgb_to_linear(color) * alpha
        bg = srgb_to_linear(background)
        if mode == "over":
            out = premult + bg * (1.0 - alpha)
        elif mode == "screen":
            out = 1.0 - (1.0 - premult.clamp(0.0, 1.0)) * (1.0 - bg)
        elif mode == "add":
            out = premult + bg
        else:
            out = (premult + 1.0 - alpha) * bg
        return linear_to_srgb(out.clamp(0.0, 1.0)).cpu()


from .export import EFSaveEXR
from .light3d import EFDepthLight
from .post import EFAddLayers, EFDither, EFGlow
from .temporal import EFClipFrames, EFDeflicker, EFFreeVRAM, EFMoGeNormals, EFStillClip
from .analysis import EFLoadAnalysis, EFLoadTrack, EFSaveAnalysis, EFSaveTrack
from .follow_crop import EFFollowCrop
from .inplate import EFInPlateGuides
from .app_nodes import EFFinishStack, EFLoadRunLatent, EFPassPreview, EFRunLatent
from .hdr import EFHDRMerge
from .look import EFNightGrade
from .place import EFAnchor, EFMaskTrack, EFPlaceBetween, EFPlaceElement, EFTrackKeepAlike
from .motion import EFMotionTracks
from .track import EFEffectLayer, EFPlaceLayer, EFTrackROI
from .elements import EFLoadElement, EFSaveElement
from .guides import EFGuide, EFGuideChoice
from .timing import EFMarginMask, EFPoints, EFStartAt, EFTrackPreview, EFVideoLatentMask
from .particles_node import EFParticles, EFParticleSettings
from .dissolve import EFCleanPlateCrop, EFCleanPlateReference, EFCleanPlateUncrop, EFCompToLayer, EFDissolve, EFDissolveBackground, EFScreen

NODE_CLASS_MAPPINGS = {
    "EFUnmult": EFUnmult,
    "EFParticles": EFParticles,
    "EFParticleSettings": EFParticleSettings,
    "EFDissolve": EFDissolve,
    "EFCleanPlateReference": EFCleanPlateReference,
    "EFCleanPlateCrop": EFCleanPlateCrop,
    "EFCompToLayer": EFCompToLayer,
    "EFCleanPlateUncrop": EFCleanPlateUncrop,
    "EFScreen": EFScreen,
    "EFDissolveBackground": EFDissolveBackground,
    "EFCompPreview": EFCompPreview,
    "EFTrackROI": EFTrackROI,
    "EFEffectLayer": EFEffectLayer,
    "EFPlaceLayer": EFPlaceLayer,
    "EFSaveEXR": EFSaveEXR,
    "EFAnchor": EFAnchor,
    "EFPlaceElement": EFPlaceElement,
    "EFMotionTracks": EFMotionTracks,
    "EFDepthLight": EFDepthLight,
    "EFGlow": EFGlow,
    "EFDeflicker": EFDeflicker,
    "EFFreeVRAM": EFFreeVRAM,
    "EFMoGeNormals": EFMoGeNormals,
    "EFClipFrames": EFClipFrames,
    "EFStillClip": EFStillClip,
    "EFSaveAnalysis": EFSaveAnalysis,
    "EFLoadAnalysis": EFLoadAnalysis,
    "EFSaveTrack": EFSaveTrack,
    "EFLoadTrack": EFLoadTrack,
    "EFDither": EFDither,
    "EFAddLayers": EFAddLayers,
    "EFFollowCrop": EFFollowCrop,
    "EFInPlateGuides": EFInPlateGuides,
    "EFPassPreview": EFPassPreview,
    "EFFinishStack": EFFinishStack,
    "EFRunLatent": EFRunLatent,
    "EFLoadRunLatent": EFLoadRunLatent,
    "EFHDRMerge": EFHDRMerge,
    "EFNightGrade": EFNightGrade,
    "EFMaskTrack": EFMaskTrack,
    "EFTrackKeepAlike": EFTrackKeepAlike,
    "EFPlaceBetween": EFPlaceBetween,
    "EFSaveElement": EFSaveElement,
    "EFLoadElement": EFLoadElement,
    "EFGuide": EFGuide,
    "EFGuideChoice": EFGuideChoice,
    "EFStartAt": EFStartAt,
    "EFPoints": EFPoints,
    "EFVideoLatentMask": EFVideoLatentMask,
    "EFMarginMask": EFMarginMask,
    "EFTrackPreview": EFTrackPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EFMarginMask": "Element Forge · Margin Mask",
    "EFParticles": "Element Forge · Particles",
    "EFParticleSettings": "Element Forge · Particle Settings",
    "EFDissolve": "Element Forge · Dissolve",
    "EFCleanPlateReference": "Element Forge · Clean Plate Reference",
    "EFCleanPlateCrop": "Element Forge · Clean Plate Crop",
    "EFCompToLayer": "Element Forge · Comp To Layer",
    "EFCleanPlateUncrop": "Element Forge · Clean Plate Uncrop",
    "EFScreen": "Element Forge · Screen",
    "EFDissolveBackground": "Element Forge · Dissolve Background",
    "EFUnmult": "Element Forge · Unmult",
    "EFCompPreview": "Element Forge · Comp Preview",
    "EFTrackROI": "Element Forge · Track ROI",
    "EFEffectLayer": "Element Forge · Effect Layer",
    "EFPlaceLayer": "Element Forge · Place Layer",
    "EFSaveEXR": "Element Forge · Save EXR",
    "EFAnchor": "Element Forge · Anchor",
    "EFPlaceElement": "Element Forge · Place Element",
    "EFMotionTracks": "Element Forge · Motion Tracks (LTX)",
    "EFDepthLight": "Element Forge · Depth Light",
    "EFGlow": "Element Forge · Glow",
    "EFDeflicker": "Element Forge · Deflicker",
    "EFFreeVRAM": "Element Forge · Free VRAM",
    "EFMoGeNormals": "Element Forge · MoGe Normals",
    "EFClipFrames": "Element Forge · Clip Frames",
    "EFStillClip": "Element Forge · Still Clip",
    "EFSaveAnalysis": "Element Forge · Save Analysis",
    "EFLoadAnalysis": "Element Forge · Load Analysis",
    "EFSaveTrack": "Element Forge · Save Track",
    "EFLoadTrack": "Element Forge · Load Track",
    "EFDither": "Element Forge · Dither",
    "EFAddLayers": "Element Forge · Add Layers",
    "EFFollowCrop": "Element Forge · Follow Crop",
    "EFInPlateGuides": "Element Forge · In-Plate Guides",
    "EFPassPreview": "Element Forge · Pass Preview (App)",
    "EFFinishStack": "Element Forge · Finish Stack (App, several runs)",
    "EFRunLatent": "Element Forge · Keep Run Latent (App)",
    "EFLoadRunLatent": "Element Forge · Load Run Latent (App)",
    "EFHDRMerge": "Element Forge · HDR Merge",
    "EFNightGrade": "Element Forge · Night Grade",
    "EFMaskTrack": "Element Forge · Mask Track",
    "EFTrackKeepAlike": "Element Forge · Track: Keep Objects Alike",
    "EFPlaceBetween": "Element Forge · Place Between",
    "EFSaveElement": "Element Forge · Save Element",
    "EFLoadElement": "Element Forge · Load Element",
    "EFGuide": "Element Forge · Guide",
    "EFGuideChoice": "Element Forge · Guide Choice",
    "EFStartAt": "Element Forge · Start At",
    "EFPoints": "Element Forge · Points",
    "EFVideoLatentMask": "Element Forge · Video Latent Mask",
    "EFTrackPreview": "Element Forge · Track Preview",
}

from .stages import NODE_CLASS_MAPPINGS as _STAGES, NODE_DISPLAY_NAME_MAPPINGS as _STAGE_NAMES
NODE_CLASS_MAPPINGS.update(_STAGES)
NODE_DISPLAY_NAME_MAPPINGS.update(_STAGE_NAMES)
try:
    from server import PromptServer as _PS
    from .stages import on_prompt as _stages_on_prompt, register_routes as _stage_routes
    if getattr(_PS, "instance", None) is not None and not getattr(_PS.instance, "_ef_stages_on_prompt", False):
        _PS.instance.add_on_prompt_handler(_stages_on_prompt)
        _stage_routes(_PS.instance.routes)
        _PS.instance._ef_stages_on_prompt = True
except Exception:
    pass

_TOOLS = {"EFLoadElement": "EF Load Element", "EFSaveElement": "EF Save Element", "EFGlow": "EF Glow", "EFDepthLight": "EF Depth Light",
          "EFDeflicker": "EF Deflicker", "EFDither": "EF Dither", "EFUnmult": "EF Unmult", "EFMoGeNormals": "EF MoGe Normals"}
for _name, _cls in NODE_CLASS_MAPPINGS.items():
    if _name in _TOOLS:
        _cls.CATEGORY = "Element Forge/Tools"
        NODE_DISPLAY_NAME_MAPPINGS[_name] = _TOOLS[_name]
    elif _name not in _STAGES:
        _cls.DEV_ONLY = True

from .memory_guard import guard_class as _guard_class
for _cls in NODE_CLASS_MAPPINGS.values():
    _guard_class(_cls)
try:
    from server import PromptServer as _PS
    from .memory_guard import on_prompt as _gpu_room_on_prompt
    if getattr(_PS, "instance", None) is not None and not getattr(_PS.instance, "_ef_gpu_room", False):
        _PS.instance.add_on_prompt_handler(_gpu_room_on_prompt)
        _PS.instance._ef_gpu_room = True
except Exception:
    pass

try:
    import os as _os

    import folder_paths as _fp
    _blank = _os.path.join(_fp.get_input_directory(), "ef_guide_blank.png")
    if not _os.path.isfile(_blank):
        import numpy as _np
        from PIL import Image as _Image
        _os.makedirs(_os.path.dirname(_blank), exist_ok=True)
        _Image.fromarray(_np.zeros((64, 64, 3), _np.uint8)).save(_blank)
except Exception as e:
    print(f"[Element Forge] could not create input/ef_guide_blank.png: {e}")

WEB_DIRECTORY = "./web"
try:
    from . import app_routes
except Exception as e:
    print(f"[Element Forge] app routes not loaded: {e}")
try:
    from . import live
except Exception as e:
    print(f"[Element Forge] live preview not loaded: {e}")

try:
    from .app_mode import NODE_CLASS_MAPPINGS as _APP_NODES, NODE_DISPLAY_NAME_MAPPINGS as _APP_NAMES
    NODE_CLASS_MAPPINGS.update(_APP_NODES)
    NODE_DISPLAY_NAME_MAPPINGS.update(_APP_NAMES)
except Exception as e:
    print(f"[Element Forge] App-mode nodes not loaded: {e}")
