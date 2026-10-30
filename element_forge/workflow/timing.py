import json

import numpy as np
import torch


def _np(t):
    return t.detach().cpu().numpy() if torch.is_tensor(t) else np.asarray(t)


class EFStartAt:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The element (RGB or RGBA) as generated: its first frame is the moment the effect begins."}),
                "start_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 600.0, "step": 0.05, "tooltip": "Second of the clip at which the effect begins (dust when the board lands, a muzzle flash). Before it the element is empty."}),
                "fps": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "length": ("INT", {"default": 0, "min": 0, "max": 100000, "tooltip": "Frames of the clip. 0 = as many as the element has."}),
                "fade_in_frames": ("INT", {"default": 0, "min": 0, "max": 240, "tooltip": "Soft start over this many frames (0 = the effect is there at once, right for flashes and impacts)."}),
            },
            "optional": {
                "alpha": ("MASK",),
                "hdr": ("IMAGE", {"tooltip": "HDR version of the element; gets the same shift."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "IMAGE", "STRING")
    RETURN_NAMES = ("images", "alpha", "hdr", "report")
    FUNCTION = "shift"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Lets an element begin at a given second of the clip: empty frames before, the element from its first "
                   "frame on, cut to the clip length. For effects that start with an event (an impact, a shot).")

    def shift(self, images, start_seconds, fps, length, fade_in_frames, alpha=None, hdr=None):
        im = _np(images).astype(np.float32, copy=False)
        n = int(length) if length > 0 else len(im)
        k = int(round(start_seconds * fps))
        same = k == 0 and n == len(im) and fade_in_frames <= 0

        def move(a):
            if a is None:
                return None
            if same:
                return a
            out = np.zeros((n,) + a.shape[1:], np.float32)
            m = max(0, min(len(a), n - k))
            if m > 0:
                out[k:k + m] = a[:m]
                if fade_in_frames > 0:
                    ramp = np.clip((np.arange(m) + 1) / (fade_in_frames + 1), 0, 1).astype(np.float32)
                    out[k:k + m] *= ramp.reshape((m,) + (1,) * (a.ndim - 1))
            return out

        al = move(_np(alpha).reshape(-1, *_np(alpha).shape[-2:]).astype(np.float32)) if alpha is not None else None
        if al is None:
            al = move(im[..., 3]) if im.shape[-1] == 4 else move(im.max(axis=-1))
        hd = move(_np(hdr).astype(np.float32)) if hdr is not None else None
        out = move(im)
        rep = f"element starts at frame {k} ({start_seconds:.2f} s at {fps:g} fps), clip {n} frames"
        if k >= n:
            rep += "; start is after the end of the clip: the element is empty"
        elif len(im) < n - k:
            rep += f"; element ends at frame {k + len(im) - 1}"
        return (torch.from_numpy(out), torch.from_numpy(al), torch.from_numpy(hd if hd is not None else out[..., :3]), rep)


class EFPoints:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "a_x": ("INT", {"default": 960, "min": -1, "max": 16384, "tooltip": "Point A in plate pixels (where the effect sits: the emitter, the hand, the object)."}),
                "a_y": ("INT", {"default": 540, "min": -1, "max": 16384}),
                "b_x": ("INT", {"default": -1, "min": -1, "max": 16384, "tooltip": "Point B (optional, -1 = off): the second end for effects between two points."}),
                "b_y": ("INT", {"default": -1, "min": -1, "max": 16384}),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "BOOLEAN", "STRING", "STRING")
    RETURN_NAMES = ("a_x", "a_y", "b_x", "b_y", "has_b", "a_coords", "b_coords")
    FUNCTION = "points"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("The clicked points of the shot in one place. a_coords / b_coords are the point prompts for SAM3_Detect "
                   "(a click gives the object's mask without a word); has_b says whether a second point is set.")

    def points(self, a_x, a_y, b_x, b_y):
        has_b = b_x >= 0 and b_y >= 0
        a = json.dumps([{"x": int(a_x), "y": int(a_y)}])
        b = json.dumps([{"x": int(b_x), "y": int(b_y)}]) if has_b else a
        return (int(a_x), int(a_y), int(b_x if has_b else a_x), int(b_y if has_b else a_y), bool(has_b), a, b)


class EFTrackPreview:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE",),
                "track": ("EF_TRACK", {"tooltip": "Track of point A (EF Track ROI, EF Point Camera Track, EF Follow Crop …)."}),
            },
            "optional": {
                "track_b": ("EF_TRACK", {"tooltip": "Track of point B, for effects between two points."}),
                "window": ("EF_TRACK", {"tooltip": "The window the effect is generated in (EF Track ROI / EF Follow Crop): drawn as a box."}),
                "mask": ("MASK", {"tooltip": "Object mask, drawn as a tint."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("preview", "report")
    FUNCTION = "draw"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Check the track before the long generation: the plate with the tracked point(s), their path, the "
                   "window of the effect and the object mask. Warns when the window touches the border of the plate.")

    def draw(self, plate, track, track_b=None, window=None, mask=None):
        import cv2
        pl = _np(plate)[..., :3].astype(np.float32)
        n, h, w = pl.shape[:3]
        out = pl.copy()
        if mask is not None:
            m = _np(mask).reshape(-1, *_np(mask).shape[-2:]).astype(np.float32)
            for i in range(n):
                mi = m[min(i, len(m) - 1)]
                if mi.shape != (h, w):
                    mi = cv2.resize(mi, (w, h), interpolation=cv2.INTER_LINEAR)
                out[i] = out[i] * (1 - 0.35 * mi[..., None]) + np.array([0.2, 0.6, 1.0], np.float32) * 0.35 * mi[..., None]
        notes = []
        edge = 0
        lw = max(2, int(round(min(h, w) / 360)))
        for tr, col in ((track, (1.0, 0.75, 0.1)), (track_b, (0.3, 1.0, 0.4))):
            if tr is None:
                continue
            pts = np.array(tr["point_track_px"], np.float64)
            pw, ph = tr.get("plate_size", [w, h])
            pts = pts * [w / pw, h / ph]
            for i in range(n):
                p = pts[min(i, len(pts) - 1)]
                tail = pts[max(0, min(i, len(pts) - 1) - 15):min(i, len(pts) - 1) + 1].round().astype(np.int32)
                if len(tail) > 1:
                    cv2.polylines(out[i], [tail.reshape(-1, 1, 2)], False, col, lw, cv2.LINE_AA)
                cv2.circle(out[i], (int(round(p[0])), int(round(p[1]))), 4 * lw, col, lw, cv2.LINE_AA)
        if window is not None and "crop_origin_plate_px" in window:
            org = np.array(window["crop_origin_plate_px"], np.float64)
            sc = np.array(window.get("scale_per_frame", [window["scale_roi_per_plate_px"]] * len(org)), np.float64)
            rw, rh = window["roi_size"]
            pw, ph = window.get("plate_size", [w, h])
            for i in range(n):
                k = min(i, len(org) - 1)
                x0, y0 = org[k]
                x1, y1 = x0 + rw / sc[k], y0 + rh / sc[k]
                touch = x0 <= 1 or y0 <= 1 or x1 >= pw - 1 or y1 >= ph - 1
                edge += touch
                c = (1.0, 0.25, 0.2) if touch else (1.0, 1.0, 1.0)
                cv2.rectangle(out[i], (int(x0 * w / pw), int(y0 * h / ph)), (int(x1 * w / pw), int(y1 * h / ph)), c, lw, cv2.LINE_AA)
            if edge:
                notes.append(f"window touches the border of the plate in {edge} of {n} frames (red box): the effect may be cut there")
        rep = "; ".join(notes) if notes else "track drawn; window inside the plate"
        return (torch.from_numpy(np.clip(out, 0, 1)), rep)


class EFVideoLatentMask:

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "samples": ("LATENT", {"tooltip": "The video latent (e.g. VAE Encode of the start video)."}),
                "mask": ("MASK", {"tooltip": "Per-frame mask in pixel frames (1 = may change), e.g. the particle region in the window."}),
                "grow": ("INT", {"default": 1, "min": 0, "max": 16, "tooltip": "Grows the mask by this many latent cells (1 cell = 32 px), so the edge can blend."}),
                "floor": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Minimum value outside the mask: 0 = keep exactly, 0.2 = may change a little (light spill, shadows)."}),
            }
        }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "make"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Puts a per-frame mask on a video latent as LTX expects it (latent frames x latent cells), union over the "
                   "8 pixel frames of each latent frame. Works with the LTX guide nodes (IC-LoRA, Add Guide).")

    def make(self, samples, mask, grow=1, floor=0.0):
        lat = samples["samples"]
        b, _, t, h, w = lat.shape
        m = mask if mask.ndim == 3 else mask.reshape(-1, mask.shape[-2], mask.shape[-1])
        m = m.float().clamp(0, 1)
        n = m.shape[0]
        frames = []
        for i in range(t):
            a, e = (0, 1) if i == 0 else (8 * i - 7, 8 * i + 1)
            a, e = min(a, n - 1), max(min(e, n), min(a, n - 1) + 1)
            frames.append(m[a:e].amax(0))
        mm = torch.stack(frames)[:, None]
        mm = torch.nn.functional.adaptive_max_pool2d(mm, (h, w))
        if grow > 0:
            mm = torch.nn.functional.max_pool2d(mm, 2 * grow + 1, stride=1, padding=grow)
        mm = floor + (1 - floor) * mm
        out = samples.copy()
        out["noise_mask"] = mm[:, 0][None, None].expand(b, 1, t, h, w).to(lat.dtype).clone()
        return (out,)


class EFMarginMask:

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "width": ("INT", {"default": 512, "min": 8, "max": 8192}),
            "height": ("INT", {"default": 768, "min": 8, "max": 8192}),
            "frames": ("INT", {"default": 81, "min": 1, "max": 100000}),
            "margin": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 0.45, "step": 0.01, "tooltip": "Share of the shorter side kept black at every border."}),
        }}

    RETURN_TYPES = ("MASK",)
    FUNCTION = "make"
    CATEGORY = "Element Forge"
    DESCRIPTION = "A mask that is 1 inside and 0 in a margin along the border (for a latent noise mask: border stays as is)."

    def make(self, width, height, frames, margin):
        m = torch.zeros((frames, height, width))
        b = int(round(margin * min(width, height)))
        m[:, b:height - b, b:width - b] = 1.0
        return (m,)
