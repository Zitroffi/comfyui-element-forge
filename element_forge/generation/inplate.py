import cv2
import numpy as np

from ..tracking.track import to_np, to_t


class EFInPlateGuides:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "roi": ("IMAGE", {"tooltip": "The plate crop the element is rendered into (EF Follow Crop / Track ROI roi), at generation size."}),
                "canny_low": ("INT", {"default": 25, "min": 0, "max": 255, "tooltip": "Lower Canny threshold (8-bit gradient)."}),
                "canny_high": ("INT", {"default": 70, "min": 0, "max": 255, "tooltip": "Upper Canny threshold (8-bit gradient)."}),
                "blur": ("FLOAT", {"default": 1.2, "min": 0.0, "max": 10.0, "step": 0.1, "tooltip": "Gaussian blur before the edges (px): fewer edges from noise and fine texture."}),
            },
            "optional": {
                "lines": ("IMAGE", {"tooltip": "The element's guide lines in the same crop (e.g. EF Lightning Guides guide -> Image Scale to the plate -> EF Follow Crop)."}),
                "line_threshold": ("FLOAT", {"default": 0.235, "min": 0.0, "max": 1.0, "step": 0.005, "tooltip": "Brightness above which a pixel of lines counts as a line."}),
                "line_width": ("INT", {"default": 2, "min": 1, "max": 9, "tooltip": "Lines are widened to this many pixels."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("guide_element", "guide_control", "lines_mask")
    FUNCTION = "build"
    CATEGORY = "Element Forge/Guides"
    DESCRIPTION = ("Guides for the in-plate route: guide_control = the crop's own edges (Canny), guide_element = the same edges plus "
                   "the element's lines. Run LTX + Union Control twice from the encoded crop with the same seed (element prompt / "
                   "prompt without it); EF Effect Layer pulls the difference out, lines_mask keeps it near the lines.")

    def build(self, roi, canny_low, canny_high, blur, lines=None, line_threshold=0.235, line_width=2):
        r = (np.clip(to_np(roi)[..., :3], 0, 1) * 255 + 0.5).astype(np.uint8)
        n, h, w = r.shape[:3]
        li = to_np(lines)[..., :3] if lines is not None else None
        ge, gc, lm = [], [], []
        k = np.ones((line_width, line_width), np.uint8)
        for i in range(n):
            g = cv2.cvtColor(r[i], cv2.COLOR_RGB2GRAY)
            if blur > 0:
                g = cv2.GaussianBlur(g, (0, 0), blur)
            e = cv2.Canny(g, canny_low, canny_high).astype(np.float32) / 255.0
            ln = np.zeros((h, w), np.float32)
            if li is not None:
                a = li[min(i, len(li) - 1)].max(-1)
                if a.shape != (h, w):
                    a = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA)
                ln = cv2.dilate((a > line_threshold).astype(np.uint8), k).astype(np.float32)
            gc.append(e)
            ge.append(np.maximum(e, ln))
            lm.append(ln)
        rgb = lambda a: to_t(np.repeat(np.stack(a)[..., None], 3, -1))
        return rgb(ge), rgb(gc), to_t(np.stack(lm))
