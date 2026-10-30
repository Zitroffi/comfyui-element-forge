import os
import sys

import cv2
import numpy as np
import torch

T = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_particles_node.py")
_g = {"__file__": T}
exec(chr(10).join(open(T, encoding="utf-8").read().splitlines()[:33]), _g)
pack = _g["pack"]
N = pack.NODE_CLASS_MAPPINGS["EFTrackKeepAlike"]

n, h, w = 6, 64, 96
m = np.zeros((n, 3, h, w), np.uint8)
for i in range(n):
    if i < 2:
        cv2.line(m[i, 0], (10, 50), (60, 10 + i), 1, 3)
    else:
        cv2.line(m[i, 1], (12, 52), (62, 12 + i), 1, 3)
    if i >= 3:
        cv2.rectangle(m[i, 2], (60, 20), (90, 60), 1, -1)
bits = 1 << np.arange(8)
packed = torch.from_numpy((m.reshape(n, 3, h, w // 8, 8) * bits).sum(-1).astype(np.uint8))
out, rep = N().keep({"packed_masks": packed, "orig_size": (h * 2, w * 2), "n_frames": n}, 3.0, 2.0, 0.3)
o = out.numpy() > 0.5
ok = o.shape == (n, h * 2, w * 2) and all(o[i].any() for i in range(n)) and not o[:, 40 * 2:60 * 2, 75 * 2:90 * 2].any()
print("ok  " if ok else "FAIL", "keep alike: staff in all frames, jacket left out |", rep)
m2 = np.zeros((n, 2, h, w), np.uint8)
for i in range(n):
    cv2.circle(m2[i, 0], (25, 32), 9, 1, -1)
    cv2.circle(m2[i, 1], (70, 32), 9, 1, -1)
p2 = torch.from_numpy((m2.reshape(n, 2, h, w // 8, 8) * bits).sum(-1).astype(np.uint8))
o2 = N().keep({"packed_masks": p2, "orig_size": (h, w), "n_frames": n}, 3.0, 2.0, 0.3)[0].numpy() > 0.5
ok2 = o2[:, 32, 25].all() and not o2[:, 32, 70].any()
print("ok  " if ok2 else "FAIL", "keep alike: a second hand of the same word stays out while the clicked one is tracked")
m3 = np.zeros((n, 2, h, w), np.uint8)
for i in range(n):
    if i in (3, 4):
        m3[i, 1, 20:64, 0:96] = 1
    else:
        m3[i, 0, 40:64, 10:60] = 1
p3 = torch.from_numpy((m3.reshape(n, 2, h, w // 8, 8) * bits).sum(-1).astype(np.uint8))
o3, rep3 = N().keep({"packed_masks": p3, "orig_size": (h, w), "n_frames": n}, 3.0, 2.0, 0.3)
ok3 = all((o3[i].numpy() > 0.5).any() for i in range(n))
print("ok  " if ok3 else "FAIL", "keep alike: a surface found again bigger under a new id where it was stays in the mask |", rep3)
m4 = np.zeros((n, 1, h, w), np.uint8)
for i in range(n):
    if i not in (2, 4):
        m4[i, 0, 40:64, 10:60] = 1
p4 = torch.from_numpy((m4.reshape(n, 1, h, w // 8, 8) * bits).sum(-1).astype(np.uint8))
fb = torch.zeros(n, h * 2, w * 2)
fb[:, 80:128, 20:120] = 1
o4, rep4 = N().keep({"packed_masks": p4, "orig_size": (h, w), "n_frames": n}, 3.0, 2.0, 0.3, fallback=fb)
o4n = N().keep({"packed_masks": p4, "orig_size": (h, w), "n_frames": n}, 3.0, 2.0, 0.3)[0]
ok4 = all((o4[i].numpy() > 0.5).any() for i in range(n)) and not (o4n[2].numpy() > 0.5).any()
print("ok  " if ok4 else "FAIL", "keep alike: frames the word track dropped come from the own track without the word |", rep4)
sys.exit(0 if ok and ok2 and ok3 and ok4 else 1)
