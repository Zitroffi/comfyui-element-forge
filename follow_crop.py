import cv2
import numpy as np

from .track import to_np, to_t


def smooth(x, sigma):
    if sigma <= 0 or len(x) < 3:
        return x
    r = int(np.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    xp = np.pad(x, ((r, r),) + ((0, 0),) * (x.ndim - 1), mode="edge")
    return np.stack([np.convolve(xp[:, j], k, mode="valid") for j in range(x.shape[1])], 1) if x.ndim > 1 else np.convolve(xp, k, mode="valid")


def pick_object(masks, which):
    out, last = [], None
    for m in masks:
        if which == "all" or not m.any():
            out.append(m)
            continue
        n, lab, st, c = cv2.connectedComponentsWithStats(cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)))
        cand = [k for k in range(1, n) if st[k, 4] >= max(64, 0.05 * st[1:, 4].max())]
        if not cand:
            cand = [1 + int(np.argmax(st[1:, 4]))]
        if which == "largest" or last is None:
            k = max(cand, key=lambda k: st[k, 4])
        else:
            k = min(cand, key=lambda k: np.hypot(*(c[k] - last)))
        last = c[k]
        out.append((lab == k) & m)
    return out


class EFFollowCrop:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE",),
                "mask": ("MASK", {"tooltip": "Per-frame mask of the object to follow (SAM3_TrackToMask: hand, person, ...)."}),
                "object": (["nearest", "largest", "all"], {"tooltip": "nearest: one part of the mask, the one closest to the part followed in the frame before (one hand of two). largest: the biggest part in every frame. all: the whole mask (both hands, a group)."}),
                "frames": ("INT", {"default": 81, "min": 9, "max": 1025, "step": 8, "tooltip": "Number of frames to cut. LTX needs 8n+1."}),
                "crop_width": ("INT", {"default": 720, "min": 64, "max": 8192, "step": 8, "tooltip": "Crop size in plate pixels (size = fixed), or the smallest crop (size = follow object)."}),
                "crop_height": ("INT", {"default": 960, "min": 64, "max": 8192, "step": 8}),
                "roi_width": ("INT", {"default": 768, "min": 64, "max": 4096, "step": 32, "tooltip": "Size the crop is scaled to for generation (multiple of 32; LTX guides: 64)."}),
                "roi_height": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 32}),
                "size": (["fixed", "follow object", "fit object (fixed)"], {"tooltip": "follow object: the crop grows and shrinks with the object box (times padding), never below crop_width x crop_height. fit object (fixed): one size for the whole clip, big enough for the largest object box (times padding) - the effect keeps its scale (lightning climbing a moving staff)."}),
                "padding": ("FLOAT", {"default": 1.6, "min": 1.0, "max": 6.0, "step": 0.05, "tooltip": "follow object: crop = object box x padding (room for the effect around the object)."}),
                "smoothing": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 30.0, "step": 0.5, "tooltip": "Gaussian smoothing of the crop path over frames (sigma in frames). Higher = calmer crop, follows fast moves later."}),
                "keep_inside": ("BOOLEAN", {"default": True, "tooltip": "Keep the crop inside the plate (no mirrored edges in the ROI); the object may then sit off-centre at the border."}),
                "mask_grow": ("INT", {"default": 24, "min": 0, "max": 512, "tooltip": "Grows the object mask in the ROI output (plate px), e.g. as the inpainting area."}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "EF_TRACK", "IMAGE", "STRING")
    RETURN_NAMES = ("roi", "roi_mask", "track", "plate_frames", "report")
    FUNCTION = "crop"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Cuts a crop that follows an object mask (SAM3) through the shot and scales it for generation. For moving hands "
                   "and people, where a point track loses the object. EF Place Layer puts the result back along the track.")

    def crop(self, plate, mask, object, frames, crop_width, crop_height, roi_width, roi_height, size, padding, smoothing, keep_inside, mask_grow):
        imgs = to_np(plate[:frames])[..., :3]
        n, h, w = imgs.shape[:3]
        if n < frames:
            raise ValueError(f"Plate has {n} frames, {frames} requested.")
        if abs(roi_width / crop_width - roi_height / crop_height) > 1e-3:
            crop_height = int(round(crop_width * roi_height / roi_width))
        ms = to_np(mask)
        ms = [cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST) > 0.5 if m.shape != (h, w) else m > 0.5 for m in ms[:n]]
        ms += [ms[-1]] * (n - len(ms))
        obj = pick_object(ms, object)
        box, missing = [], 0
        for o in obj:
            ys, xs = np.nonzero(o)
            if len(xs) < 10:
                missing += 1
                box.append(box[-1] if box else [w / 2, h / 2, 0.0, 0.0])
                continue
            box.append([(xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, xs.max() - xs.min() + 1, ys.max() - ys.min() + 1])
        box = np.array(box, np.float64)
        if missing == n:
            raise ValueError("The mask is empty in every frame. Nothing was found at the click: click on a clearer object or surface, or name it with an object word.")
        if missing and not obj[0].any():
            first = next(i for i, o in enumerate(obj) if o.any())
            box[:first] = box[first]
        aspect = crop_width / crop_height
        if size != "fixed":
            need = np.maximum(box[:, 2] * padding, box[:, 3] * padding * aspect)
            cw = np.maximum(smooth(need, smoothing * 2), crop_width)
            if size == "fit object (fixed)":
                cw = np.full(n, float(np.maximum(need, crop_width).max()))
        else:
            cw = np.full(n, float(crop_width))
        cw = np.minimum(cw, min(w, h * aspect)) if keep_inside else cw
        ch = cw / aspect
        cen = smooth(box[:, :2], smoothing)
        obj_pt = cen.copy()
        if keep_inside:
            cen[:, 0] = np.clip(cen[:, 0], cw / 2, w - cw / 2)
            cen[:, 1] = np.clip(cen[:, 1], ch / 2, h - ch / 2)
        origins = np.stack([cen[:, 0] - cw / 2, cen[:, 1] - ch / 2], 1)
        scales = roi_width / cw
        rois, rmask = [], []
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * mask_grow + 1,) * 2) if mask_grow else None
        for i in range(n):
            s = scales[i]
            m = np.array([[s, 0, -origins[i, 0] * s], [0, s, -origins[i, 1] * s]], np.float64)
            rois.append(cv2.warpAffine(imgs[i], m, (roi_width, roi_height), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT))
            om = obj[i].astype(np.uint8)
            if k is not None:
                om = cv2.dilate(om, k)
            rmask.append(cv2.warpAffine(om.astype(np.float32), m, (roi_width, roi_height), flags=cv2.INTER_LINEAR, borderValue=0))
        o = origins
        jit = float(np.abs(o[2:] - 2 * o[1:-1] + o[:-2]).sum(1).mean()) if n > 2 else 0.0
        track = {"plate_size": [w, h], "frames": n, "scale_roi_per_plate_px": float(scales[0]), "scale_per_frame": scales.round(6).tolist(),
                 "roi_size": [roi_width, roi_height], "crop_origin_plate_px": origins.round(3).tolist(),
                 "point_track_px": obj_pt.round(3).tolist(), "point_scale": (scales[0] / scales).round(5).tolist(),
                 "mapping": "plate = crop_origin + roi / scale (scale per frame: scale_per_frame)", "source": f"mask box ({object}, {size})"}
        report = (f"{n} frames, {missing} without mask, crop {cw.min():.0f}-{cw.max():.0f} px wide, centre x {cen[:, 0].min():.0f}..{cen[:, 0].max():.0f} "
                  f"y {cen[:, 1].min():.0f}..{cen[:, 1].max():.0f}, jitter {jit:.2f} px/frame^2")
        return (to_t(np.clip(np.stack(rois), 0, 1)), to_t(np.clip(np.stack(rmask), 0, 1)), track, plate[:frames], report)
