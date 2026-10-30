import cv2
import numpy as np
import torch


def to_np(t):
    return t.detach().cpu().float().numpy()


def object_shape(dp, mk, grow, softness, floor):
    h, w = mk.shape[1:3]
    ctrl, att = [], []
    g = int(grow * w) * 2 + 1
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (g, g)) if g > 1 else None
    for i in range(len(mk)):
        d = dp[min(i, len(dp) - 1)]
        if d.shape != (h, w):
            d = cv2.resize(d, (w, h), interpolation=cv2.INTER_LINEAR)
        m = mk[i]
        inside = d[m > 0.5]
        lo, hi = (np.percentile(inside, 2), np.percentile(inside, 98)) if inside.size > 50 else (0.0, 1.0)
        c = (floor + (1 - floor) * np.clip((d - lo) / max(hi - lo, 1e-3), 0, 1)) * m
        ctrl.append(np.repeat(np.clip(c, 0, 1)[..., None], 3, -1))
        a = (m > 0.5).astype(np.float32)
        if kern is not None:
            a = cv2.dilate(a, kern)
        if softness > 0:
            a = cv2.GaussianBlur(a, (0, 0), softness * w)
        att.append(np.clip(a, 0, 1))
    return ctrl, att
