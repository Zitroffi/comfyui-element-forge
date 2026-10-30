import importlib
import json
import os
import sys
import tempfile
import types

import numpy as np
import torch

S = tempfile.mkdtemp(prefix="ef_test_")
fp = types.ModuleType("folder_paths"); fp.get_output_directory = lambda: os.path.join(S, "out"); fp.get_temp_directory = lambda: os.path.join(S, "out")
sys.modules["folder_paths"] = fp
comfy = types.ModuleType("comfy"); cu = types.ModuleType("comfy.utils")


class PB:
    def __init__(self, n): pass
    def update(self, n=1): pass
    def update_absolute(self, *a, **k): pass


cu.repeat_to_batch_size = lambda t, n: t.repeat((n + len(t) - 1) // len(t), *([1] * (t.dim() - 1)))[:n]
cu.ProgressBar = PB; comfy.utils = cu; sys.modules["comfy"] = comfy; sys.modules["comfy.utils"] = cu
mm = types.ModuleType("comfy.model_management"); mm.throw_exception_if_processing_interrupted = lambda: None
mm.get_torch_device = lambda: torch.device("cpu")
comfy.model_management = mm; sys.modules["comfy.model_management"] = mm
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))
pack = importlib.import_module(os.path.basename(PACK))
an = importlib.import_module(pack.__name__ + ".element_forge.app.app_nodes")
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


def peak(img):
    y, x = np.unravel_index(int(img[..., 0].argmax()), img.shape[:2])
    return int(x), int(y)


dot = torch.zeros(1, 64, 96, 4)
dot[0, 20, 30] = 1.0
y = an._shift_scale(dot, 0, 0, 1, 90, (20.5, 20.5))[0].numpy()
check(peak(y) == (20, 30), f"turn 90 degrees clockwise about (20.5, 20.5): (30, 20) -> {peak(y)}, expected (20, 30)")
y = an._shift_scale(dot, 0, 0, 2, 0, (20.5, 20.5))[0].numpy()
check(peak(y)[1] == 20 and peak(y)[0] in (40, 39), f"scale 2 about (20.5, 20.5): (30, 20) -> {peak(y)}, expected (40, 20)")
y = an._shift_scale(dot, 5, -3, 1, 0, (20.5, 20.5))[0].numpy()
check(peak(y) == (35, 17), f"move by (5, -3) with a pivot: (30, 20) -> {peak(y)}")
y = an._shift_scale(dot, 0, 0, 1, 90, None)[0].numpy()
check(peak(y) == (59, 14), f"turn about the plate centre (48, 32): (30, 20) -> {peak(y)}, expected (59, 14)")
y = an._shift_scale(dot, 0.0, 0.0, 0.0)
check(torch.allclose(y, dot), "no placement (scale 0 = unset) leaves the element as it is")
two = dot.repeat(2, 1, 1, 1)
y = an._shift_scale(two, [0, 10], [0, 0], [1, 1], [0, 0], (20.5, 20.5)).numpy()
check(peak(y[0]) == (30, 20) and peak(y[1]) == (40, 20), f"one value per frame: frame 0 {peak(y[0])}, frame 1 {peak(y[1])}")
low = torch.zeros(1, 64, 96, 4)
low[0, 26, 20] = 1.0
y = an._shift_scale(low, 0, 0, 1, 0, (20.5, 20.5), 2.0)[0].numpy()
check(peak(y)[0] == 20 and peak(y)[1] in (31, 32), f"stretch 2: 6 px below the pivot -> 12 px below: (20, 26) -> {peak(y)}")
y = an._shift_scale(dot, 0, 0, 1, 0, (20.5, 20.5), 2.0)[0].numpy()
check(peak(y) == (30, 20), f"stretch leaves the width alone: (30, 20) -> {peak(y)}")
y = an._shift_scale(low, 0, 0, 1, 90, (20.5, 20.5), 2.0)[0].numpy()
check(peak(y)[1] == 20 and peak(y)[0] in (8, 9), f"stretch, then turn 90 degrees clockwise: the own height ends up horizontal: (20, 26) -> {peak(y)}")
ks2 = an.keyed_settings(an.merge_settings({}), {"stretch": [[0, 1], [2, 2]]}, [0, 1, 2])
check(ks2["element"]["stretch"] == [1, 1.5, 2] and an.merge_settings({})["element"]["stretch"] == 1.0, "stretch has a default and can be keyed")

K = [[0, 0, "even"], [10, 100, "in"], [20, 0, "smooth"]]
vals = [an.key_value(K, f) for f in (-5, 0, 5, 10, 15, 20, 25)]
check(np.allclose(vals, [0, 0, 50, 100, 75, 0, 0]), f"key_value holds outside, even and slow start between: {vals}")
check(abs(an.key_value([[0, 0, "out"], [10, 100]], 5) - 75) < 1e-9 and abs(an.key_value([[0, 0, "smooth"], [10, 100]], 5) - 50) < 1e-9,
      "slow end and smooth eases")
check(an.key_value([[10, 100, "even"], [0, 0, "even"]], 5) == 50, "keys in any order")
ss = an.merge_settings({"element": {"offset_x": 7}})
check(an.keyed_settings(ss, {}, [0, 1]) is ss and an.keyed_settings(ss, {"offset_x": []}, [0, 1]) is ss, "no keys: settings unchanged")
ks = an.keyed_settings(ss, {"offset_y": [[0, 0], [2, 20]]}, [0, 1, 2])
check(ks["element"]["offset_y"] == [0, 10, 20] and ks["element"]["offset_x"] == 7, f"keyed offset per frame: {ks['element']['offset_y']}")
w = an.key_weight({"brightness": [[0, 1], [2, 0]]}, [0, 1, 2, 3]).flatten().tolist()
check(np.allclose(w, [1, 0.5, 0, 0]), f"brightness keys as weight: {w}")
check(an.key_weight(None, [0, 1]).flatten().tolist() == [1.0, 1.0], "no brightness keys: weight 1")


def wexr(path, a):
    import OpenImageIO as oiio
    spec = oiio.ImageSpec(a.shape[1], a.shape[0], a.shape[2], "half")
    o = oiio.ImageOutput.create(path); o.open(path, spec); o.write_image(np.ascontiguousarray(a, dtype=np.float32)); o.close()


def rexr(path):
    import OpenImageIO as oiio
    o = oiio.ImageInput.open(path); a = o.read_image(format="float"); o.close()
    return np.asarray(a)


RUN = os.path.join(S, "out", "element-forge", "k_run")
os.makedirs(RUN, exist_ok=True)
for i in range(3):
    wexr(os.path.join(RUN, f"plate_{i + 1:05d}.exr"), np.full((48, 64, 3), 0.1, np.float32))
    el = np.zeros((48, 64, 4), np.float32); el[20, 10] = [3.0, 3.0, 3.0, 1.0]
    wexr(os.path.join(RUN, f"element_{i + 1:05d}.exr"), el)
layer = {"run_folder": "element-forge/k_run", "settings": {"glow": {"exposure": -30}},
         "keys": {"offset_x": [[0, 0, "even"], [2, 20, "even"]], "brightness": [[0, 1, "even"], [2, 0, "even"]]}}
an.EFFinishStack().stack(json.dumps([layer]), "{}", "element-forge/k_stack", True, 25.0, 2)
fr = [rexr(os.path.join(S, "out", "element-forge", "k_stack", f"comp_{i:05d}.exr")) for i in (1, 2, 3)]
check(peak(fr[0]) == (10, 20) and peak(fr[1]) == (20, 20), f"stack: keyed offset moves the element per frame ({peak(fr[0])}, {peak(fr[1])})")
check(abs(fr[1][20, 20, 0] - (0.1 + 3.0 * 0.5)) < 0.02, f"stack: brightness key halves the layer at frame 1 ({fr[1][20, 20, 0]:.3f})")
check(abs(float(fr[2].max()) - 0.1) < 0.01, f"stack: brightness 0 at frame 2 leaves the plate ({float(fr[2].max()):.3f})")
an.EFFinishStack().stack(json.dumps([{"run_folder": "element-forge/k_run",
                                      "settings": {"glow": {"exposure": -30}, "element": {"rotation": 90, "pivot_x": 10.5, "pivot_y": 10.5}}}]),
                         "{}", "element-forge/k_rot", True, 25.0, 2)
c = rexr(os.path.join(S, "out", "element-forge", "k_rot", "comp_00001.exr"))
check(peak(c) == (0, 10), f"finish: rotation about the pivot from the settings: (10, 20) -> {peak(c)}, expected (0, 10)")
glow_on = {"glow": {"exposure": 0, "radius": 8}}
an.EFFinishStack().stack(json.dumps([{"run_folder": "element-forge/k_run", "settings": glow_on}]), "{}", "element-forge/k_vis", True, 25.0, 2)
an.EFFinishStack().stack(json.dumps([{"run_folder": "element-forge/k_run", "settings": {**glow_on, "element": {"visible": False}}}]), "{}",
                         "element-forge/k_hid", True, 25.0, 2)
vis = rexr(os.path.join(S, "out", "element-forge", "k_vis", "comp_00001.exr"))
hid = rexr(os.path.join(S, "out", "element-forge", "k_hid", "comp_00001.exr"))
dot_gone = hid[20, 10, 0] < vis[20, 10, 0] - 2.5
halo = hid[20, 14, 0] - 0.1
check(dot_gone and halo > 0.005 and abs(hid[20, 14, 0] - vis[20, 14, 0]) < 1e-3,
      f"element hidden: the element is gone ({vis[20, 10, 0]:.2f} -> {hid[20, 10, 0]:.2f}), its glow stays ({halo:.4f} above the plate)")
print(f"{ok} checks passed")
