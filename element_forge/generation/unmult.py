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
