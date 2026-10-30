import torch

import comfy.utils

from ..generation.unmult import linear_to_srgb, srgb_to_linear


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
            k = side / max(height, width)
            height, width = max(2, 2 * round(height * k / 2)), max(2, 2 * round(width * k / 2))
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
