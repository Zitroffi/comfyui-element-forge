import json

import cv2
import numpy as np

from .track import srgb_to_linear, to_np, to_t

LK = dict(winSize=(31, 31), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.01))


def camera_share(plate, pts, n):
    pl = to_np(plate)[..., :3]
    h, w = pl.shape[1:3]
    k = min(1.0, 540.0 / min(h, w))
    gray = [cv2.cvtColor(cv2.resize((np.clip(pl[i], 0, 1) * 255).astype(np.uint8), None, fx=k, fy=k, interpolation=cv2.INTER_AREA),
                         cv2.COLOR_RGB2GRAY) for i in range(min(n, len(pl)))]
    own = [pts[0].copy()]
    for i in range(1, len(gray)):
        p0 = pts[i - 1] * k
        mask = np.full(gray[0].shape, 255, np.uint8)
        cv2.circle(mask, (int(p0[0]), int(p0[1])), int(0.12 * max(mask.shape)), 0, -1)
        c0 = cv2.goodFeaturesToTrack(gray[i - 1], 600, 0.01, 8, mask=mask)
        moved = pts[i] - pts[i - 1]
        if c0 is not None and len(c0) >= 8:
            c1, st, _ = cv2.calcOpticalFlowPyrLK(gray[i - 1], gray[i], c0, None, **LK)
            good = st.ravel() == 1
            if good.sum() >= 8:
                H, _ = cv2.findHomography(c0[good], c1[good], cv2.RANSAC, 2.0)
                if H is not None:
                    pred = cv2.perspectiveTransform(p0.reshape(1, 1, 2).astype(np.float32), H)[0, 0] / k
                    moved = pts[i] - pred
        own.append(own[-1] + moved)
    short = n - len(own)
    while len(own) < n:
        own.append(own[-1])
    return np.array(own, np.float64), short


def clean_path(path, fps):
    p = np.asarray(path, np.float64)
    n = len(p)
    if n < 5:
        return p
    pad = np.pad(p, ((2, 2), (0, 0)), mode="edge")
    med = np.stack([np.median(pad[i:i + 5], 0) for i in range(n)])
    sig = max(1.0, 0.05 * fps)
    r = int(3 * sig)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    pad = np.pad(med, ((r, r), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, j], k, mode="valid") for j in range(2)], 1)


def spring_bands(path, fps, bands, k_tip, zeta, k_base=600.0):
    n, dt = len(path), 1.0 / fps
    sub = max(8, int(np.ceil(8 * 30.0 / fps)))
    out = np.zeros((bands, n, 2), np.float64)
    for b in range(bands):
        k = k_base * (k_tip / k_base) ** (b / (bands - 1))
        c = 2 * zeta * np.sqrt(k)
        q, v = path[0].copy(), np.zeros(2)
        for i in range(n):
            for _ in range(sub):
                a = k * (path[i] - q) - c * v
                v += a * dt / sub
                q += v * dt / sub
            out[b, i] = q
    return out


class EFMotionTracks:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "track": ("EF_TRACK", {"tooltip": "The emitter's track. With EF Track ROI / EF Follow Crop the tracks are drawn in the crop (where the element is generated), else in the plate."}),
                "tip_height": ("INT", {"default": 45, "min": 4, "max": 1024, "step": 1, "tooltip": "Height of the tip point above the emitter, in pixels of the generated frame. Keep it short (about the flame's lower half): a long track makes LTX stretch the emitter itself."}),
                "tip_share": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": "Share of the spring's lag given to the tip point (0.6 tested: the flame trails, swings past at stops, settles)."}),
                "motion": (["object only (needs plate)", "track as is"], {"tooltip": "object only: the camera's share of the track is removed using the plate."}),
                "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.05}),
                "inertia": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "As in EF Emitter Drag: 0 stiff, 1 lazy."}),
                "damping": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 1.5, "step": 0.05, "tooltip": "As in EF Emitter Drag: below 1 the tip swings past when the emitter stops."}),
                "min_speed": ("FLOAT", {"default": 80.0, "min": 0.0, "max": 2000.0, "step": 5.0, "tooltip": "Below this object speed (p90, px/s at 1080 px) the tip stays straight above the emitter."}),
            },
            "optional": {
                "plate": ("IMAGE", {"tooltip": "The plate, for 'object only'."}),
                "fps": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "body_points": ("STRING", {"default": "", "tooltip": "Extra points on the emitter below it, pixels of the generated frame, comma separated (e.g. '120, 230' for a candle). They move with the emitter and hold it rigid."}),
                "crop": ("EF_TRACK", {"tooltip": "The crop the element is generated in (EF Follow Crop / EF Track ROI), when it follows something else than the emitter (e.g. the mask of the placed element): the emitter point comes from 'track', the mapping into the crop from here."}),
                "stabilise": ("BOOLEAN", {"default": False, "tooltip": "For a plate track without a crop: the emitter stands still on its own canvas (an element generated on black and placed later with EF Place Element); only the tip carries the motion."}),
                "canvas_width": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 32}),
                "canvas_height": ("INT", {"default": 768, "min": 64, "max": 4096, "step": 32}),
                "emitter_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "Where the emitter stands on the canvas (share of its width)."}),
                "emitter_y": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01}),
                "cut_below": ("INT", {"default": 6, "min": -256, "max": 256, "step": 1, "tooltip": "below_emitter mask starts this many pixels below the emitter point (soft edge of 6 px). Use it to black out the carrier (e.g. the glowing top of a black candle) before Unmult."}),
                "plate_to_canvas": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 16.0, "step": 0.01, "tooltip": "Canvas pixels per plate pixel: 1 / the scale of EF Place Element."}),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "INT", "STRING", "MASK")
    RETURN_NAMES = ("tracks", "width", "height", "report", "below_emitter")
    FUNCTION = "tracks"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Motion data for LTX: point tracks for LTXVDrawTracks and the motion-track IC-LoRA. One point on the "
                   "emitter, one short tip point that lags behind like a spring (the same model as EF Emitter Drag). In a "
                   "stabilised crop the emitter stands still and only the tip carries the motion; tested: the generated "
                   "flame leans, trails and swings past exactly along it.")

    def tracks(self, track, tip_height, tip_share, motion, amount, inertia, damping, min_speed, plate=None, fps=30.0, body_points="",
               stabilise=False, canvas_width=512, canvas_height=768, emitter_x=0.5, emitter_y=0.65, plate_to_canvas=1.0, cut_below=6,
               crop=None):
        n = int(track["frames"])
        pts = np.array(track["point_track_px"], np.float64)[:n]
        W, H = track.get("plate_size", [1920, 1080])
        pre = ""
        if motion.startswith("object") and plate is not None:
            path, short = camera_share(plate, pts, n)
            pre = f"plate has {short} frames fewer than the track. " if short else ""
        else:
            path = pts
            pre = "no plate connected: used the track as is (camera motion counts too). " if motion.startswith("object") else ""
        path = clean_path(path, fps)
        speed = np.linalg.norm(np.diff(path, axis=0), axis=1) * fps * 1080.0 / min(W, H) if n > 1 else np.zeros(1)
        p90 = float(np.percentile(speed, 90))
        if stabilise:
            sc = np.full((n, 1), plate_to_canvas)
            emit = np.tile([[emitter_x * canvas_width, emitter_y * canvas_height]], (n, 1)).astype(np.float64)
            cw, ch = canvas_width, canvas_height
        elif "crop_origin_plate_px" in (crop or track):
            cr = crop or track
            m = min(n, int(cr["frames"]))
            org = np.array(cr["crop_origin_plate_px"], np.float64)[:m]
            sc = np.array(cr.get("scale_per_frame", [cr["scale_roi_per_plate_px"]] * m), np.float64)[:m, None]
            if m < n:
                org, sc = np.pad(org, ((0, n - m), (0, 0)), mode="edge"), np.pad(sc, ((0, n - m), (0, 0)), mode="edge")
            emit = (pts - org) * sc
            cw, ch = cr["roi_size"]
        else:
            sc = np.ones((n, 1))
            emit = pts.copy()
            cw, ch = W, H
        if p90 >= min_speed and amount > 0:
            k_tip = 200.0 * (10.0 / 200.0) ** inertia
            tip = spring_bands(path, fps, 2, k_tip, damping)[1]
            lag = (tip - path) * sc * amount * tip_share
            lag[:, 1] *= 0.5
            lim = 2.0 * tip_height
            mag = np.linalg.norm(lag, axis=1, keepdims=True)
            lag = lag * np.where(mag > 1e-6, lim * np.tanh(mag / lim) / np.maximum(mag, 1e-6), 1.0)
            note = f"own speed p90 {p90:.0f} px/s: tip lags up to {np.abs(lag[:, 0]).max():.0f} px"
        else:
            lag = np.zeros((n, 2))
            note = f"own speed p90 {p90:.0f} px/s < {min_speed:.0f}: tip straight above the emitter"
        pt = lambda x, y: {"x": round(float(x), 2), "y": round(float(y), 2)}
        out = [[pt(*emit[i]) for i in range(n)],
               [pt(emit[i, 0] + lag[i, 0], emit[i, 1] - tip_height + lag[i, 1]) for i in range(n)]]
        for b in [float(v) for v in body_points.replace(";", ",").split(",") if v.strip()]:
            out.append([pt(emit[i, 0], emit[i, 1] + b) for i in range(n)])
        rows = np.arange(int(ch), dtype=np.float32)[None, :, None]
        cut = np.clip((rows - (emit[:, 1][:, None, None] + cut_below)) / 6.0, 0, 1)
        below = to_t(np.broadcast_to(cut, (n, int(ch), int(cw))).copy())
        return (json.dumps(out), int(cw), int(ch), pre + note + f", canvas {cw}x{ch}, {len(out)} tracks, {n} frames", below)
