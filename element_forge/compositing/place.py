import cv2
import numpy as np
import torch

from ..simulation.particles import snap_to_edges
from ..tracking.track import linear_to_srgb, srgb_to_linear, to_np, to_t, warp_down


def base_point(a, core_thr, base_fraction, side="bottom"):
    ys, xs = np.nonzero(a > core_thr)
    if len(ys) == 0:
        ys, xs = np.nonzero(a > 0.3 * a.max()) if a.max() > 0 else (np.array([a.shape[0] // 2]), np.array([a.shape[1] // 2]))
    q = 100 * base_fraction
    low = {"bottom": ys >= np.percentile(ys, 100 - q), "top": ys <= np.percentile(ys, q),
           "left": xs <= np.percentile(xs, q), "right": xs >= np.percentile(xs, 100 - q)}.get(side, np.ones(len(ys), bool))
    w = a[ys[low], xs[low]] + 1e-6
    return float((xs[low] * w).sum() / w.sum()), float((ys[low] * w).sum() / w.sum())


def hex_rgb(text):
    t = text.strip().lstrip("#")
    if len(t) != 6:
        raise ValueError(f"colour must be a hex value like #a6a6a6, got {text!r}")
    return np.array([int(t[k:k + 2], 16) / 255 for k in (0, 2, 4)], np.float32)


def split_rgba(img, alpha=None):
    arr = to_np(img)
    if alpha is not None:
        a = to_np(alpha)
        a = np.broadcast_to(a, arr.shape[:3]) if a.shape[0] == 1 else a[:arr.shape[0]]
    elif arr.shape[-1] > 3:
        a = arr[..., 3]
    else:
        a = arr[..., :3].max(axis=-1)
    return arr[..., :3], np.ascontiguousarray(a)


class EFAnchor:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "element": ("IMAGE", {"tooltip": "Element with alpha, e.g. rgba from EF Unmult."}),
                "core_threshold": ("FLOAT", {"default": 0.9, "min": 0.05, "max": 1.0, "step": 0.01, "tooltip": "Alpha above this counts as the dense core of the element."}),
                "base_fraction": ("FLOAT", {"default": 0.3, "min": 0.05, "max": 1.0, "step": 0.05, "tooltip": "Part of the core used as base point, counted from the base side (0.3 = the 30 % nearest to it)."}),
                "stabilize": (["remove slow drift", "lock base point", "off"], {"tooltip": "remove slow drift: keeps the flicker, removes sinking or wandering. lock: base point fixed every frame."}),
                "smooth_frames": ("INT", {"default": 25, "min": 1, "max": 241, "tooltip": "Window for the slow drift (frames)."}),
                "floor_fade_start": ("INT", {"default": 0, "min": -2048, "max": 2048, "tooltip": "Rows below the base point (px) where the fade-out starts. Removes glow the model put on an imagined floor."}),
                "floor_fade_length": ("INT", {"default": 0, "min": 0, "max": 2048, "tooltip": "Length of the fade in px. 0 = no floor fade."}),
            },
            "optional": {
                "alpha": ("MASK", {"tooltip": "Alpha if the element image has none."}),
                "hdr": ("IMAGE", {"tooltip": "HDR version of the element (EF HDR Merge / EF Load Element). Gets the same shift and floor fade."}),
                "lock_base": ("BOOLEAN", {"default": False, "tooltip": "Lock base point instead of stabilize: the base stays on the tracked point in every frame, so a flame on a wick or a blossom does not jitter. Off: as stabilize says."}),
                "base": (["bottom", "top", "left", "right", "centre"], {"tooltip": "Side of the element that sits on the emitter: bottom for rising effects (flame, smoke), top for falling ones (drips, liquid), centre for effects without an emitter (an aura, a ball). The floor fade works on the far side of the base."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "EF_ANCHOR", "STRING", "IMAGE")
    RETURN_NAMES = ("rgba", "alpha", "anchor", "report", "hdr_premult_linear")
    FUNCTION = "anchor"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Pins an element at its base point (the lower end of its dense core, e.g. the root of a flame). "
                   "Removes slow drift so it stays where it is placed, and can fade out glow below the base. "
                   "The anchor output tells EF Place Element which pixel to put on the tracked point.")

    def anchor(self, element, core_threshold, base_fraction, stabilize, smooth_frames, floor_fade_start, floor_fade_length, alpha=None, hdr=None,
               base="bottom", lock_base=False):
        if lock_base:
            stabilize = "lock base point"
        rgb, a = split_rgba(element, alpha)
        n, h, w = a.shape
        pts = np.array([base_point(a[i], core_threshold, base_fraction, base) for i in range(n)])
        if stabilize == "off":
            target = pts.copy()
        elif stabilize == "lock base point":
            target = np.repeat(pts[:1], n, axis=0)
        else:
            win = min(smooth_frames, n) | 1
            pad = win // 2
            padded = np.pad(pts, ((pad, pad), (0, 0)), mode="edge")
            slow = np.stack([np.convolve(padded[:, k], np.ones(win) / win, mode="valid") for k in range(2)], axis=1)
            target = pts - (slow - slow[0])
        shift = target - pts
        prem = rgb * a[..., None]
        hd = to_np(hdr)[..., :3] if hdr is not None else srgb_to_linear(rgb) * a[..., None]
        out_rgb, out_a, out_h = [], [], []
        for i in range(n):
            m = np.float32([[1, 0, shift[i, 0]], [0, 1, shift[i, 1]]])
            pa = cv2.warpAffine(a[i], m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
            pc = cv2.warpAffine(prem[i], m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
            ph = cv2.warpAffine(np.ascontiguousarray(hd[min(i, len(hd) - 1)]), m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
            if floor_fade_length > 0 and base != "centre":
                ax, sign, size = {"bottom": (1, 1, h), "top": (1, -1, h), "right": (0, 1, w), "left": (0, -1, w)}[base]
                pos = (np.arange(size) - target[i, ax]) * sign - floor_fade_start
                ramp = np.clip(1 - pos / floor_fade_length, 0, 1).astype(np.float32)
                ramp = ramp * ramp * (3 - 2 * ramp)
                fade = ramp[:, None] if ax == 1 else ramp[None, :]
                pa = pa * fade
                pc = pc * fade[..., None]
                ph = ph * fade[..., None]
            out_h.append(ph)
            out_a.append(pa)
            out_rgb.append(np.where(pa[..., None] > 1e-6, pc / np.maximum(pa[..., None], 1e-6), 0))
        out_a = np.clip(np.stack(out_a), 0, 1)
        rgba = np.concatenate([np.clip(np.stack(out_rgb), 0, 1), out_a[..., None]], axis=-1)
        after = np.array([base_point(out_a[i], core_threshold, base_fraction, base) for i in range(n)])
        anchor = {"base_point_px": after.round(2).tolist(), "canvas": [w, h], "reference_px": [float(after[0, 0]), float(after[0, 1])]}
        rng = lambda v: float(v.max() - v.min())
        report = (f"base point range before x {rng(pts[:, 0]):.1f} y {rng(pts[:, 1]):.1f} px, "
                  f"after x {rng(after[:, 0]):.1f} y {rng(after[:, 1]):.1f} px, max shift {np.abs(shift).max():.1f} px")
        return (to_t(rgba), to_t(out_a), anchor, report, to_t(np.stack(out_h)))


def in_front_of_surface(dep, track, n, scale, follow_scale, base, size, offset, depth_offset, softness, hw):
    h, w = hw
    (bx, by), (eh, ew), (ox, oy) = base, size, offset
    votes = total = 0
    for i in range(0, n, max(1, n // 12)):
        d = dep[min(i, len(dep) - 1)]
        if d.shape != (h, w):
            d = cv2.resize(d, (w, h), interpolation=cv2.INTER_LINEAR)
        s = scale * (track.get("point_scale", [1.0] * n)[i] if follow_scale else 1.0)
        px, py = track["point_track_px"][i]
        tx, ty = px + ox * s / scale, py + oy * s / scale
        x0, y0 = int(max(0, tx - s * bx)), int(max(0, ty - s * by))
        x1, y1 = int(min(w, tx - s * bx + s * ew)), int(min(h, ty - s * by + s * eh))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        r = max(2, int(0.004 * max(h, w)))
        yy, xx = int(np.clip(py, 0, h - 1)), int(np.clip(px, 0, w - 1))
        d0 = float(np.median(d[max(0, yy - r):yy + r + 1, max(0, xx - r):xx + r + 1]))
        seen = float(np.clip((d0 + depth_offset - d[y0:y1, x0:x1]) / softness + 0.5, 0, 1).mean())
        total += 1
        votes += d0 <= float(np.median(d[::4, ::4])) and seen < 0.1
    return total > 0 and votes * 2 > total


class EFPlaceElement:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE",),
                "element": ("IMAGE", {"tooltip": "rgba from EF Anchor (straight alpha, sRGB)."}),
                "anchor": ("EF_ANCHOR",),
                "track": ("EF_TRACK", {"tooltip": "From EF Track ROI: the element's base point follows its point."}),
                "scale": ("FLOAT", {"default": 0.25, "min": 0.01, "max": 8.0, "step": 0.01, "tooltip": "Element pixels to plate pixels."}),
                "offset_x": ("FLOAT", {"default": 0.0, "min": -4096, "max": 4096, "step": 1.0, "tooltip": "Shift of the base point from the tracked point, plate px (scaled with the track)."}),
                "offset_y": ("FLOAT", {"default": 0.0, "min": -4096, "max": 4096, "step": 1.0}),
                "mode": (["add", "screen", "over"], {"tooltip": "add/screen for glowing elements (in linear light), over for opaque ones."}),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 16.0, "step": 0.05, "tooltip": "Brightness of the element. Above 1 gives HDR values in the linear output."}),
                "follow_scale": ("BOOLEAN", {"default": True, "tooltip": "Scale the element with the tracked point (camera moves closer or away)."}),
            },
            "optional": {
                "holdout": ("MASK", {"tooltip": "Plate-space mask of things in front of the element (e.g. fingers). Removes the element there."}),
                "edge_feather": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.5, "step": 0.01, "tooltip": "Fades the element out towards the borders of its own frame (fraction of the shorter frame side). Use it for elements that leave the frame, e.g. smoke."}),
                "round_edge": ("BOOLEAN", {"default": False, "tooltip": "Round soft edge instead of the frame border: an ellipse fading over its outer half. For short bright effects that fill their own frame (muzzle flash) - a soft light instead of a box."}),
                "color": ("STRING", {"default": "", "tooltip": "Recolour the element, hex like #a6a6a6. Empty = keep its colour. Smoke from the white-background fallback comes out near black; real smoke near a light is light grey."}),
                "color_amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "How much of the colour replaces the element's own colour."}),
                "density": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 8.0, "step": 0.1, "tooltip": "Thicker (above 1) or thinner (below 1) element: alpha' = 1 - (1 - alpha)^density, as if it were that many layers deep."}),
                "depth": ("IMAGE", {"tooltip": "Plate depth map (DA3 Render min_max, near = bright). Gives the element a depth: it sits at the depth of the tracked point plus depth_offset, and only what is nearer to the camera hides it. With a holdout mask: only the masked parts that are nearer (e.g. fingers in front, not the palm behind). A point on a far surface that would hide the element almost completely (a back wall, the sky) puts it in front of that surface."}),
                "depth_offset": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.005, "tooltip": "Moves the element in depth (depth map units, 0..1): positive = towards the camera (in front of the hand), negative = behind it."}),
                "depth_softness": ("FLOAT", {"default": 0.02, "min": 0.001, "max": 0.5, "step": 0.005, "tooltip": "Width of the soft edge where the plate passes the element's depth."}),
                "element_hdr": ("IMAGE", {"tooltip": "HDR version of the element (hdr_premult_linear of EF Anchor). Used for the light instead of the SDR colour, so layer_plate_linear and the EXR keep values above 1. Alpha, holdout, density and edge feather still come from the element; colour applies to the SDR element only."}),
                "object_mask": ("MASK", {"lazy": True, "tooltip": "Plate-space mask of the clicked object. With object_in_front on it hides the element wherever the object is; only read then."}),
                "object_in_front": ("BOOLEAN", {"default": False, "tooltip": "The object mask cuts the element out everywhere, whatever the depth map says: a person in front of a ring of fire. Sharper than the depth edge."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("comp", "layer_plate_linear", "alpha_plate")
    FUNCTION = "place"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Places the element into the plate: its base point sits on the tracked point (plus offset), comp in linear light."

    def check_lazy_status(self, object_in_front=False, object_mask=None, **kw):
        return ["object_mask"] if object_in_front and object_mask is None else []

    def place(self, plate, element, anchor, track, scale, offset_x, offset_y, mode, gain, follow_scale, holdout=None, edge_feather=0.0,
              color="", color_amount=1.0, density=1.0, depth=None, depth_offset=0.0, depth_softness=0.02, element_hdr=None,
              round_edge=False, object_mask=None, object_in_front=False):
        pl = to_np(plate)[..., :3]
        rgb, a = split_rgba(element)
        a0 = a
        if color and color.strip():
            rgb = rgb * (1 - color_amount) + hex_rgb(color) * color_amount
        if density != 1.0:
            a = 1 - (1 - np.clip(a, 0, 1)) ** density
        win = border_window(a.shape[1], a.shape[2], edge_feather, round_edge) if edge_feather > 0 or round_edge else None
        if element_hdr is not None:
            hd = to_np(element_hdr)[..., :3]
            if hd.shape[1:3] != a.shape[1:3]:
                raise ValueError(f"element_hdr {hd.shape[2]}x{hd.shape[1]} must have the size of the element {a.shape[2]}x{a.shape[1]}.")
            ratio = np.where(a0 > 1e-4, a / np.maximum(a0, 1e-4), 0).astype(np.float32)
        if win is not None:
            a = a * win[None]
        hold = to_np(holdout) if holdout is not None else None
        obj = to_np(object_mask) if object_mask is not None and object_in_front else None
        dep = to_np(depth)[..., :3].mean(-1) if depth is not None else None
        n = min(len(pl), track["frames"])
        h, w = pl.shape[1:3]
        bx, by = anchor["reference_px"]
        front = dep is not None and in_front_of_surface(dep, track, n, scale, follow_scale, (bx, by), a.shape[1:3], (offset_x, offset_y),
                                                        depth_offset, depth_softness, (h, w))
        comps, layers, alphas = np.empty((n, h, w, 3), np.float32), np.empty((n, h, w, 3), np.float32), np.empty((n, h, w), np.float32)
        for i in range(n):
            e = i % len(a)
            s = scale * (track.get("point_scale", [1.0] * n)[i] if follow_scale else 1.0)
            px, py = track["point_track_px"][i]
            tx, ty = px + offset_x * s / scale, py + offset_y * s / scale
            m = np.float32([[s, 0, tx - s * bx], [0, s, ty - s * by]])
            if element_hdr is not None:
                src = hd[e % len(hd)] * ratio[e][..., None]
                if win is not None:
                    f = win[..., None]
                    if mode == "add":
                        f = f / (1.0 + np.max(src, axis=-1, keepdims=True).clip(0, None) * gain * (1.0 - f))
                    src = src * f
                src = np.ascontiguousarray(src.astype(np.float32))
            else:
                src = srgb_to_linear(rgb[e]) * a[e][..., None]
            el = warp_down(src, m, (w, h))
            al = warp_down(np.ascontiguousarray(a[e]), m, (w, h))
            k = None
            if hold is not None:
                k = 1 - hold[min(i, len(hold) - 1)]
                if k.shape != al.shape:
                    k = cv2.resize(k, (w, h), interpolation=cv2.INTER_LINEAR)
            if dep is not None:
                d = dep[min(i, len(dep) - 1)]
                if d.shape != al.shape:
                    d = cv2.resize(d, (w, h), interpolation=cv2.INTER_LINEAR)
                r = max(2, int(0.004 * max(h, w)))
                yy, xx = int(np.clip(py, 0, h - 1)), int(np.clip(px, 0, w - 1))
                d0 = float(np.median(d[max(0, yy - r):yy + r + 1, max(0, xx - r):xx + r + 1]))
                ed = d0 + depth_offset
                if front:
                    ed = max(ed, d0 + 4 * depth_softness)
                vis = np.clip((ed - d) / depth_softness + 0.5, 0, 1).astype(np.float32)
                vis = snap_to_edges(vis, pl[i][..., :3].astype(np.float32), max(2, int(round(0.006 * min(h, w)))))
                k = vis if k is None else 1 - (1 - k) * (1 - vis)
            if obj is not None:
                ko = 1 - np.clip(obj[min(i, len(obj) - 1)], 0, 1).astype(np.float32)
                if ko.shape != al.shape:
                    ko = cv2.resize(ko, (w, h), interpolation=cv2.INTER_LINEAR)
                ko = snap_to_edges(ko, pl[i][..., :3].astype(np.float32), max(2, int(round(0.006 * min(h, w)))))
                ko = cv2.GaussianBlur(ko, (0, 0), max(0.7, 0.0008 * min(w, h)))
                k = ko if k is None else k * ko
            if k is not None:
                el, al = el * k[..., None], al * k
            el = el * gain
            bg = srgb_to_linear(pl[i])
            if mode == "add":
                out = bg + el
            elif mode == "screen":
                out = 1 - (1 - np.clip(el, 0, 1)) * (1 - bg)
            else:
                out = el + bg * (1 - al[..., None])
            comps[i] = np.clip(linear_to_srgb(out), 0, 1)
            layers[i] = el
            alphas[i] = np.clip(al, 0, 1)
        return (to_t(comps), to_t(layers), to_t(alphas))


class EFMaskTrack:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "mask": ("MASK", {"tooltip": "Per-frame mask of one object, e.g. one hand from SAM3 (SAM3_TrackToMask with a single index)."}),
                "point": (["centroid", "top", "bottom", "left", "right"], {"tooltip": "Which point of the mask to follow. top/bottom/left/right = mean of the outermost 5 % of the mask in that direction."}),
                "smoothing": ("INT", {"default": 3, "min": 1, "max": 31, "step": 2, "tooltip": "Moving average over frames (odd)."}),
            }
        }

    RETURN_TYPES = ("EF_TRACK", "STRING")
    RETURN_NAMES = ("track", "report")
    FUNCTION = "track"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Turns a per-frame object mask into a point track (EF_TRACK), e.g. for fast hands where optical flow "
                   "fails. Frames where the mask is empty keep the last position (at the start: the first one). Scale follows the square root of the mask area.")

    def track(self, mask, point, smoothing):
        m = to_np(mask)
        n, h, w = m.shape
        pts, areas = [], []
        for i in range(n):
            ys, xs = np.nonzero(m[i] > 0.5)
            if len(xs) < 10:
                pts.append(None)
                areas.append(None)
                continue
            if point == "centroid":
                p = (xs.mean(), ys.mean())
            else:
                key = {"top": ys, "bottom": -ys, "left": xs, "right": -xs}[point]
                sel = key <= np.percentile(key, 5)
                p = (xs[sel].mean(), ys[sel].mean())
            pts.append(p)
            areas.append(float(len(xs)))
        valid = [i for i in range(n) if pts[i] is not None]
        src = valid[0] if valid else None
        for i in range(n):
            if pts[i] is not None:
                src = i
            elif src is None:
                pts[i], areas[i] = (w / 2, h / 2), 1.0
            else:
                pts[i], areas[i] = pts[src], areas[src]
        pts = np.array(pts, dtype=np.float64)
        k = min(smoothing, n) | 1
        if k > 1:
            pad = k // 2
            pp = np.pad(pts, ((pad, pad), (0, 0)), mode="edge")
            pts = np.stack([np.convolve(pp[:, j], np.ones(k) / k, mode="valid") for j in range(2)], 1)
        scale = np.sqrt(np.array(areas) / max(areas[valid[0]] if valid else 1.0, 1.0))
        track = {"plate_size": [w, h], "frames": n, "point_track_px": pts.round(3).tolist(), "point_scale": scale.round(5).tolist(),
                 "source": f"mask {point}"}
        empty = sum(1 for i in range(n) if (m[i] > 0.5).sum() < 10)
        return (track, f"{n} frames, {empty} without mask, x {pts[:, 0].min():.0f}..{pts[:, 0].max():.0f}, y {pts[:, 1].min():.0f}..{pts[:, 1].max():.0f}")


def _shape(m):
    ys, xs = np.nonzero(m)
    if len(xs) < 10:
        return None
    ev = np.linalg.eigvalsh(np.cov(np.stack([xs, ys]).astype(np.float64)) + np.eye(2) * 0.25)
    return float(len(xs)), float(np.sqrt(ev[1] / ev[0]))


class EFTrackKeepAlike:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "track_data": ("SAM3_TRACK_DATA", {"tooltip": "SAM3 Video Track with an object word and room for more objects (max_objects > 1): "
                                                              "the word finds the object again when the track lost it - and sometimes other things."}),
                "area_ratio": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 20.0, "step": 0.1, "tooltip": "A later object counts in a frame when its area is within this factor of the first object's."}),
                "shape_ratio": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 20.0, "step": 0.1, "tooltip": "... and its elongation (long axis / short axis) within this factor."}),
            },
            "optional": {
                "fill_in_below": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 100.0, "step": 0.05, "tooltip": "Later objects only fill in while the first one is lost: smaller than this share of its first area (0.3). A large value (100) takes alike objects in every frame - a second hand or person would come along."}),
                "fallback": ("MASK", {"tooltip": "The clicked object's own track without the word (SAM3 Track To Mask): used in frames where the first object is lost and nothing was found again - the word track dropped a large surface SAM held without it."}),
            },
        }

    RETURN_TYPES = ("MASK", "STRING")
    RETURN_NAMES = ("mask", "report")
    FUNCTION = "keep"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Object mask from a SAM3 track that re-detects the object word: the first object (the clicked one) always, later "
                   "objects only while the first one is lost and only where they are about as big and as long as the first one was. "
                   "A word with two meanings found other things (q7l 22.10.: 'staff' also took the fighter's jacket), and a second "
                   "hand or person of the same word must not join the clicked one.")

    def keep(self, track_data, area_ratio, shape_ratio, fill_in_below=0.3, fallback=None):
        packed = track_data["packed_masks"]
        H, W = track_data["orig_size"]
        if packed is None:
            n = track_data["n_frames"]
            return (torch.zeros(n, H, W), "no object")
        bits = torch.tensor([1, 2, 4, 8, 16, 32, 64, 128], dtype=torch.uint8, device=packed.device)
        n, no = packed.shape[0], packed.shape[1]
        m = (packed.unsqueeze(-1) & bits).bool().view(*packed.shape[:-1], -1).cpu().numpy()
        ref = next((sh for sh in (_shape(m[i, 0]) for i in range(n)) if sh is not None), None)
        keep = m[:, 0].copy()
        a0 = m[:, 0].reshape(n, -1).sum(1)
        lost = a0 < fill_in_below * (ref[0] if ref else 1.0)
        took, left, same, held = 0, 0, 0, 0
        last = None
        for i in range(n):
            for j in range(1, no) if lost[i] else ():
                sh = _shape(m[i, j])
                if sh is None:
                    continue
                inter = int((m[i, j] & last).sum()) if last is not None else 0
                if inter >= 0.5 * sh[0] or (inter >= 0.6 * last.sum() and (ref is None or sh[0] <= 8 * ref[0])):
                    keep[i] |= m[i, j]
                    same += 1
                elif ref is None or (abs(np.log(sh[0] / ref[0])) <= np.log(area_ratio) and abs(np.log(sh[1] / ref[1])) <= np.log(shape_ratio)):
                    keep[i] |= m[i, j]
                    took += 1
                else:
                    left += 1
            if fallback is not None and lost[i] and keep[i].sum() < fill_in_below * (ref[0] if ref else 1.0):
                fb = fallback[min(i, len(fallback) - 1)]
                fb = torch.nn.functional.interpolate(fb[None, None].float(), size=keep.shape[1:], mode="nearest")[0, 0] > 0.5
                if fb.any():
                    keep[i] |= fb.cpu().numpy()
                    held += 1
            if keep[i].any():
                last = keep[i]
        out = torch.nn.functional.interpolate(torch.from_numpy(keep).float().unsqueeze(1), size=(H, W), mode="bilinear",
                                              align_corners=False)[:, 0]
        empty = int(sum(1 for i in range(n) if not keep[i].any()))
        rep = ((f"{no} objects; first: area {ref[0]:.0f} px, elongation {ref[1]:.1f}; " if ref else f"{no} objects; first empty; ") +
               f"first lost in {int(lost.sum())} frame(s), found again where it was in {same}, alike objects taken in {took}, "
               f"left out in {left}, own track without the word in {held}; {empty} of {n} frames without mask")
        return (out, rep)

def border_window(h, w, feather, round_edge=False):
    ramp = lambda t: np.clip(t, 0, 1) ** 2 * (3 - 2 * np.clip(t, 0, 1))
    if round_edge:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.hypot((xx - (w - 1) / 2) / (w / 2), (yy - (h - 1) / 2) / (h / 2))
        return ramp((1 - d) / max(2 * feather, 0.5)).astype(np.float32)
    f = max(feather * min(h, w), 1.0)
    yy = np.minimum(np.arange(h), h - 1 - np.arange(h)) / f
    xx = np.minimum(np.arange(w), w - 1 - np.arange(w)) / f
    return (ramp(yy)[:, None] * ramp(xx)[None, :]).astype(np.float32)


class EFPlaceBetween:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE",),
                "element": ("IMAGE", {"tooltip": "Element with alpha (EF Unmult rgba), e.g. a lightning arc running from left to right."}),
                "track_a": ("EF_TRACK", {"tooltip": "Start point (e.g. left hand)."}),
                "track_b": ("EF_TRACK", {"tooltip": "End point (e.g. right hand)."}),
                "start_x": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "Where the element starts inside its own frame (fraction of width)."}),
                "end_x": ("FLOAT", {"default": 0.95, "min": 0.0, "max": 1.0, "step": 0.01}),
                "axis_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "Height of the start-end line inside the element frame."}),
                "thickness": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.05, "tooltip": "Extra scale across the line (1 = keep proportions)."}),
                "mode": (["add", "screen", "over"],),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 16.0, "step": 0.05}),
            },
            "optional": {
                "holdout": ("MASK", {"tooltip": "Plate-space mask of things in front of the element."}),
                "edge_feather": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.5, "step": 0.01, "tooltip": "Fades the element out towards the borders of its own frame, so glow cut off by the frame edge shows no hard box. Fraction of the shorter frame side."}),
                "element_hdr": ("IMAGE", {"tooltip": "Optional HDR version of the element (hdr_premult_linear of EF Load Element, values above 1 in the core). Used as the light of the layer instead of linear(rgb) x alpha, so the EXR keeps the HDR values; alpha and edges stay from the element."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("comp", "layer_plate_linear", "alpha_plate")
    FUNCTION = "place"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Stretches an element between two tracked points (scale and rotation per frame), e.g. lightning from hand to hand."

    def place(self, plate, element, track_a, track_b, start_x, end_x, axis_y, thickness, mode, gain, holdout=None, edge_feather=0.08,
              element_hdr=None):
        pl = to_np(plate)[..., :3]
        rgb, a = split_rgba(element)
        win = border_window(a.shape[1], a.shape[2], edge_feather) if edge_feather > 0 else None
        if win is not None:
            a = a * win[None]
        hd = None
        if element_hdr is not None:
            hd = to_np(element_hdr)[..., :3]
            if hd.shape[1:3] != a.shape[1:3]:
                hd = np.stack([cv2.resize(f, (a.shape[2], a.shape[1]), interpolation=cv2.INTER_LINEAR) for f in hd])
        hold = to_np(holdout) if holdout is not None else None
        n = min(len(pl), track_a["frames"], track_b["frames"])
        h, w = pl.shape[1:3]
        eh, ew = a.shape[1:3]
        e0 = np.array([start_x * ew, axis_y * eh])
        e1 = np.array([end_x * ew, axis_y * eh])
        span = np.linalg.norm(e1 - e0)
        comps, layers, alphas = np.empty((n, h, w, 3), np.float32), np.empty((n, h, w, 3), np.float32), np.empty((n, h, w), np.float32)
        for i in range(n):
            pa = np.array(track_a["point_track_px"][i])
            pb = np.array(track_b["point_track_px"][i])
            d = pb - pa
            s = np.linalg.norm(d) / max(span, 1e-6)
            ang = np.arctan2(d[1], d[0])
            c, si = np.cos(ang), np.sin(ang)
            A = np.array([[c, -si], [si, c]]) @ np.diag([s, s * thickness])
            t = pa - A @ e0
            m = np.hstack([A, t[:, None]]).astype(np.float32)
            e = i % len(a)
            if hd is not None:
                src = hd[e % len(hd)] * (win[..., None] if win is not None else 1.0)
            else:
                src = srgb_to_linear(rgb[e]) * a[e][..., None]
            if np.linalg.norm(d) < 1e-3:
                el, al = np.zeros((h, w, 3), np.float32), np.zeros((h, w), np.float32)
            else:
                el = warp_down(np.ascontiguousarray(src, dtype=np.float32), m, (w, h))
                al = warp_down(np.ascontiguousarray(a[e]), m, (w, h))
            if hold is not None:
                k = 1 - hold[min(i, len(hold) - 1)]
                if k.shape != al.shape:
                    k = cv2.resize(k, (w, h), interpolation=cv2.INTER_LINEAR)
                el, al = el * k[..., None], al * k
            el = el * gain
            bg = srgb_to_linear(pl[i])
            out = bg + el if mode == "add" else (1 - (1 - np.clip(el, 0, 1)) * (1 - bg) if mode == "screen" else el + bg * (1 - al[..., None]))
            comps[i] = np.clip(linear_to_srgb(out), 0, 1)
            layers[i] = el
            alphas[i] = np.clip(al, 0, 1)
        return (to_t(comps), to_t(layers), to_t(alphas))
