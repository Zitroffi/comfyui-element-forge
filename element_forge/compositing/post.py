import torch
import torch.nn.functional as F

from .light3d import gaussian_blur, linear_to_srgb, srgb_to_linear

LUMA = torch.tensor([0.2126, 0.7152, 0.0722])


def _device():
    try:
        import comfy.model_management as mm
        return mm.get_torch_device()
    except Exception:
        return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")


def hex_rgb(text):
    t = text.strip().lstrip("#")
    if len(t) != 6:
        raise ValueError(f"colour must be a hex value like #ffb060, got {text!r}")
    return torch.tensor([int(t[k:k + 2], 16) / 255 for k in (0, 2, 4)])


class EFGlow:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "What glows: e.g. the element layer (layer_plate_linear) or a whole comp."}),
                "input_is": (["linear", "sRGB"], {"tooltip": "linear: layers from EF Place Element / Light. sRGB: normal images and videos."}),
                "exposure": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.1, "tooltip": "Brightness of the glow in stops."}),
                "radius": ("FLOAT", {"default": 400.0, "min": 2.0, "max": 4000.0, "step": 1.0, "tooltip": "Reach of the glow in pixels (the largest blur is half of it). Large values (600-1000 at 1080p) give the wide halo of Deep Glow."}),
                "falloff": ("FLOAT", {"default": 2.0, "min": 0.5, "max": 4.0, "step": 0.05, "tooltip": "Shape of the tail: 2 = inverse square (physical), lower = longer, brighter tail, higher = tighter glow."}),
                "threshold": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10.0, "step": 0.01, "tooltip": "Only light above this (linear) glows; soft knee."}),
            },
            "optional": {
                "tint": ("STRING", {"default": "", "tooltip": "Color the glow, hex like #ffb060. Empty = the image's own color."}),
                "tint_amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
                "aspect": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 10.0, "step": 0.05, "tooltip": "Stretches the glow horizontally (above 1) or vertically (below 1)."}),
                "chromatic": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Red reaches further than blue (like a real lens): 0 = off."}),
                "background": ("IMAGE", {"tooltip": "Image the glow is added onto (sRGB), e.g. the comp. Without it: added onto the input."}),
                "core": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 64.0, "step": 0.5, "tooltip": "Smallest blur in pixels. Larger values put less glow right on the element, so a strong glow keeps the element's own structure instead of burning it white."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("comp", "glow_linear")
    FUNCTION = "glow"
    CATEGORY = "Element Forge/Post"
    DESCRIPTION = ("Physically motivated glow in linear light: a pyramid of gaussians with doubling radii, weighted to "
                   "an inverse-power point spread (falloff 2 = inverse square), with threshold, tint, aspect and "
                   "chromatic spread. glow_linear is a separate pass for compositing (Add).")

    def glow(self, image, input_is, exposure, radius, falloff, threshold, tint="", tint_amount=1.0, aspect=1.0,
             chromatic=0.0, background=None, core=1.0):
        n, h, w = image.shape[0], image.shape[1], image.shape[2]
        sigmas = []
        sg = min(core, radius / 2)
        while sg <= radius / 2 + 1e-6:
            sigmas.append(sg)
            sg *= 2 ** 0.5
        col = None
        if tint and tint.strip():
            col = srgb_to_linear(hex_rgb(tint))
            col = col / (col * LUMA).sum().clamp(min=1e-8)
        dev = _device()
        g_out = torch.empty((n, h, w, 3), dtype=torch.float32)
        comp_out = torch.empty((n, h, w, 3), dtype=torch.float32)
        for c0 in range(0, n, 8):
            x = image[c0:c0 + 8, ..., :3].float()
            lin = srgb_to_linear(x.clamp(0, 1)) if input_is == "sRGB" else x.clamp(min=0)
            if threshold > 0:
                lum = (lin * LUMA).sum(-1, keepdim=True)
                knee = threshold * 0.5
                soft = ((lum - threshold + knee).clamp(0, 2 * knee) ** 2) / (4 * knee + 1e-8)
                lin = lin * (torch.maximum(soft, lum - threshold) / lum.clamp(min=1e-8)).clamp(0, 1)
            try:
                g = self._spread(lin.to(dev), sigmas, falloff, aspect, chromatic).cpu()
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                g = self._spread(lin, sigmas, falloff, aspect, chromatic)
            g = g * (2.0 ** exposure)
            if col is not None:
                lum = (g * LUMA).sum(-1, keepdim=True)
                g = g * (1 - tint_amount) + lum * col * tint_amount
            if background is not None:
                idx = torch.arange(c0, c0 + len(g)) % len(background)
                base = background[idx][..., :3].float()
                if base.shape[1:3] != (h, w):
                    base = F.interpolate(base.permute(0, 3, 1, 2), size=(h, w), mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
            else:
                base = linear_to_srgb(lin) if input_is == "linear" else x
            g_out[c0:c0 + len(g)] = g
            comp_out[c0:c0 + len(g)] = linear_to_srgb((srgb_to_linear(base.clamp(0, 1)) + g).clamp(0, 1)).clamp(0, 1)
        return (comp_out, g_out)

    def _spread(self, lin, sigmas, falloff, aspect, chromatic):
        src = lin.permute(0, 3, 1, 2)
        n, _, h, w = src.shape
        out = torch.zeros_like(src)
        groups = [(0, 3, 1.0)] if chromatic == 0 else [(c, c + 1, 1.0 + chromatic * (0.25 if c == 0 else (-0.25 if c == 2 else 0.0)))
                                                        for c in range(3)]
        for c0, c1, scale in groups:
            x = src[:, c0:c1].reshape(n * (c1 - c0), 1, h, w)
            ws = torch.tensor([(s * scale) ** (2 - falloff) for s in sigmas])
            ws = ws / ws.sum()
            for s, wk in zip(sigmas, ws.tolist()):
                se = s * scale
                f = max(1, int(se // 2))
                small = F.avg_pool2d(x, f, ceil_mode=True) if f > 1 else x
                b = self.blur_xy(small, se * aspect / f, se / f)
                if f > 1:
                    b = F.interpolate(b, size=(h, w), mode="bilinear", align_corners=False)
                out[:, c0:c1] += wk * b.reshape(n, c1 - c0, h, w)
        return out.permute(0, 2, 3, 1)

    @staticmethod
    def blur_xy(x, sx, sy):
        if abs(sx - sy) < 1e-6:
            return gaussian_blur(x, sx)
        r = max(1, int(3 * sx))
        k = torch.exp(-0.5 * (torch.arange(-r, r + 1, dtype=x.dtype, device=x.device) / sx) ** 2)
        x = F.conv2d(F.pad(x, (r, r, 0, 0), mode="replicate"), (k / k.sum()).view(1, 1, 1, -1))
        r = max(1, int(3 * sy))
        k = torch.exp(-0.5 * (torch.arange(-r, r + 1, dtype=x.dtype, device=x.device) / sy) ** 2)
        return F.conv2d(F.pad(x, (0, 0, r, r), mode="replicate"), (k / k.sum()).view(1, 1, -1, 1))


class EFDither:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "sRGB images on their way into an 8-bit video (Create Video / Save Video)."}),
                "amount": ("FLOAT", {"default": 1.5, "min": 0.0, "max": 8.0, "step": 0.1, "tooltip": "Noise in 8-bit steps (triangular). 1-2 hides banding in dark gradients; 0 = off."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2 ** 31 - 1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "dither"
    CATEGORY = "Element Forge/Post"
    DESCRIPTION = ("Against banding in 8-bit video: adds a fine triangular noise of about one 8-bit step before the video is "
                   "written, so smooth dark gradients (light falloff, glow) do not break into visible steps. Use with a "
                   "low crf in Save Video (re-encode, crf about 10), otherwise H.264 removes the noise again. EXR passes "
                   "do not need it.")

    def dither(self, images, amount, seed=0):
        if amount <= 0:
            return (images,)
        g = torch.Generator().manual_seed(int(seed))
        x = images.float()
        noise = (torch.rand(x.shape, generator=g) - torch.rand(x.shape, generator=g)) * (amount / 255.0)
        if x.shape[-1] == 4:
            noise[..., 3] = 0
        return ((x + noise).clamp(0, 1),)


class EFAddLayers:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "base": ("IMAGE", {"tooltip": "A linear light layer (e.g. the AI element on black)."}),
                "layer": ("IMAGE", {"tooltip": "A second linear light layer (e.g. the drawn particles); scaled to the base."}),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "add"
    CATEGORY = "Element Forge/Post"
    DESCRIPTION = ("Adds two light layers in linear light (base + gain x layer), without clipping: values above 1 stay, "
                   "so an HDR element keeps its core. The shorter clip holds its last frame.")

    def add(self, base, layer, gain=1.0):
        b = base.float()
        lay = layer.float()[..., :3]
        n = max(b.shape[0], lay.shape[0])
        if lay.shape[1:3] != b.shape[1:3]:
            lay = F.interpolate(lay.movedim(-1, 1), size=tuple(b.shape[1:3]), mode="bilinear", align_corners=False).movedim(1, -1)
        idx = lambda m: torch.clamp(torch.arange(n), max=m - 1)
        out = b[idx(b.shape[0])].clone()
        out[..., :3] = out[..., :3] + lay[idx(lay.shape[0])] * float(gain)
        return (out,)
