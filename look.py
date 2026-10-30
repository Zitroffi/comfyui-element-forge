import cv2
import numpy as np

from .track import linear_to_srgb, srgb_to_linear, to_np, to_t


class EFNightGrade:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE", {"tooltip": "Day plate (sRGB). Grade it before adding element and light, so the element stays bright."}),
                "exposure": ("FLOAT", {"default": -2.5, "min": -8.0, "max": 2.0, "step": 0.1, "tooltip": "Stops. -2 to -3 gives dusk to night."}),
                "temperature": ("FLOAT", {"default": 0.35, "min": -1.0, "max": 1.0, "step": 0.01, "tooltip": "Positive = cooler (moonlight blue)."}),
                "saturation": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": "Night vision loses color."}),
                "contrast": ("FLOAT", {"default": 1.15, "min": 0.5, "max": 2.0, "step": 0.01, "tooltip": "Contrast around middle grey in log space."}),
                "sky_lift": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "Keeps the brightest areas (sky, windows) a little brighter than the rest."}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("night", "night_linear")
    FUNCTION = "grade"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Day-for-night grade of the plate: exposure down, cool white balance, less saturation, a bit more "
                   "contrast. Then place the element and the light pass on top: their light reads much stronger at night.")

    def grade(self, plate, exposure, temperature, saturation, contrast, sky_lift):
        pl = to_np(plate)
        n, h, w = pl.shape[:3]
        night, night_lin = np.empty((n, h, w, 3), np.float32), np.empty((n, h, w, 3), np.float32)
        wb = np.array([1 - 0.35 * temperature, 1 - 0.05 * temperature, 1 + 0.45 * temperature], np.float32)
        mid = 0.18
        for i in range(n):
            x = srgb_to_linear(pl[i, ..., :3])
            lum = (x * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
            x = lum + (x - lum) * saturation
            x = x * wb
            x = mid * np.power(np.clip(x, 1e-6, None) / mid, contrast)
            gain = 2.0 ** exposure
            if sky_lift > 0:
                hi = np.clip((lum - 0.5) / 0.5, 0, 1)
                gain = gain * (1 + hi * sky_lift * (1 / gain - 1) * 0.5)
            x = x * gain
            night[i], night_lin[i] = np.clip(linear_to_srgb(x), 0, 1), x
        return (to_t(night), to_t(night_lin))
