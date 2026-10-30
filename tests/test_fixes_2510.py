import ast
import os

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_funcs(fname, names, extra):
    src = open(os.path.join(HERE, fname), encoding="utf-8").read()
    nodes = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in names]
    g = dict(extra)
    exec(compile(ast.Module(nodes, []), fname, "exec"), g)
    return g


crop_box = load_funcs("app_routes.py", {"crop_box"}, {})["crop_box"]
im = Image.new("RGB", (1280, 720))
assert crop_box(im, [100, 50, 512, 512]).size == (512, 512)
assert crop_box(im, [1000, 400, 512, 512]).size == (280, 320)
assert crop_box(im, [-40.4, -10, 300, 200]).size == (260, 190)
assert crop_box(im, None) is im and crop_box(im, ["a", 1, 2, 3]) is im and crop_box(im, [1, 2]) is im
assert crop_box(im, [1275, 715, 512, 512]) is im
print("crop_box: area around the effect, held inside the frame, the whole frame without a usable box")

import math

import numpy as np
import torch
import torch.nn.functional as F

g = load_funcs("app_nodes.py", {"focus_depth", "fill_focus", "_gauss", "depth_blur"},
               {"np": np, "torch": torch, "F": F, "math": math, "DOF_STEPS": 4, "DOF_SHARP": 0.02, "DOF_AROUND": 0.03, "DOF_NEAR": 95})
el = np.zeros((40, 60, 4), np.float32); el[10:20, 10:20, 3] = 1
dep = np.full((40, 60, 4), 0.2, np.float32); dep[10:20, 10:20, 0] = 0.8
assert abs(g["focus_depth"](el, dep) - 0.8) < 1e-6 and g["focus_depth"](np.zeros_like(el), dep) is None
fl = np.zeros((400, 300, 3), np.float32); fl[100:180, 140:170] = 2.0
dp = np.full((400, 300, 3), 0.1, np.float32); dp[185:260, 120:190] = 0.45
assert abs(g["focus_depth"](fl, dp) - 0.45) < 1e-6, g["focus_depth"](fl, dp)
fl4 = np.concatenate([fl, np.ones_like(fl[..., :1])], 2)
assert abs(g["focus_depth"](fl4, dp) - 0.45) < 1e-6, g["focus_depth"](fl4, dp)
assert g["fill_focus"]([None, 0.8, None, 0.3, None]) == [0.8, 0.8, 0.8, 0.3, 0.3] and g["fill_focus"]([None, None]) == [0.5, 0.5]
C = torch.zeros((1, 64, 96, 3)); C[0, :, ::2] = 1.0
D = torch.zeros((1, 64, 96, 4)); D[0, :, 48:, 0] = 1.0
out = g["depth_blur"](C, D, [1.0], 1.0, 0.15)
contrast = lambda x: float(x[0, 20:40, :, 0].std(dim=1).mean())
right, left = out[:, :, 56:], out[:, :, :40]
assert abs(contrast(right) - contrast(C[:, :, 56:])) < 1e-4, "the focus (near) stays sharp"
assert contrast(left) < 0.5 * contrast(C[:, :, :40]), "far from the focus is blurred"
assert torch.equal(g["depth_blur"](C, D, [1.0], 0.0, 0.15), C)
big = torch.rand((1, 200, 300, 3))
assert abs(float(g["_gauss"](big, 20.0).mean()) - float(big.mean())) < 0.02
print("depth blur: focus on the effect, sharp at the focus, soft away from it, off at 0")
print("ALL OK")
