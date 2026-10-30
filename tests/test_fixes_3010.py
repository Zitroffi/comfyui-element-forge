import importlib
import json
import os
import sys
import tempfile
import types

import torch

S = tempfile.mkdtemp(prefix="ef_test_")
fp = types.ModuleType("folder_paths"); fp.get_output_directory = lambda: os.path.join(S, "out"); fp.get_temp_directory = lambda: os.path.join(S, "out")
fp.get_input_directory = lambda: os.path.join(S, "in")
sys.modules["folder_paths"] = fp
comfy = types.ModuleType("comfy"); cu = types.ModuleType("comfy.utils")


class PB:
    def __init__(self, n): pass
    def update(self, n=1): pass
    def update_absolute(self, *a, **k): pass


cu.ProgressBar = PB; comfy.utils = cu; sys.modules["comfy"] = comfy; sys.modules["comfy.utils"] = cu
mm = types.ModuleType("comfy.model_management"); mm.throw_exception_if_processing_interrupted = lambda: None
mm.get_torch_device = lambda: torch.device("cpu")
comfy.model_management = mm; sys.modules["comfy.model_management"] = mm
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))
pack = importlib.import_module(os.path.basename(PACK))
M = pack.NODE_CLASS_MAPPINGS
FRONT = "Object in front (its mask hides the element)"
LOCK = "Base locked to the point (no jitter of the base)"
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


n, H, W = 3, 64, 64
plate = torch.full((n, H, W, 3), 0.2)
el = torch.ones((n, 32, 32, 4)); el[..., :3] = 0.8
anchor = {"reference_px": (16, 31)}
track = {"frames": n, "point_track_px": [(32, 50)] * n}
obj = torch.zeros((n, H, W)); obj[:, :, 24:40] = 1
depth = torch.full((n, H, W, 3), 0.5)
node = M["EFPlaceElement"]()
check(node.check_lazy_status(object_in_front=True) == ["object_mask"], "lazy: the mask is asked for with the switch on")
check(node.check_lazy_status(object_in_front=False) == [], "lazy: the mask is not computed with the switch off")
alpha = {}
for on in (False, True):
    _, _, a = node.place(plate, el, anchor, track, 1.0, 0, 0, "over", 1.0, False, depth=depth, depth_offset=0.0,
                         depth_softness=0.01, object_mask=obj, object_in_front=on)
    alpha[on] = a.numpy()
check(abs(alpha[False][0, 35, 32] - 0.5) < 0.05, "switch off: as before (same depth: half hidden)")
check(alpha[True][0, 35, 32] < 1e-3, "switch on: the element is gone where the object is")
check(abs(alpha[True][0, 35, 20] - alpha[False][0, 35, 20]) < 1e-6, "switch on: outside the object nothing changes")
_, _, a = node.place(plate, el, anchor, track, 1.0, 0, 0, "over", 1.0, False, object_mask=obj[:, ::2, ::2], object_in_front=True)
check(float(a[0, 35, 32]) < 1e-3 and float(a[0, 35, 20]) > 0.99, "a mask of another size is scaled to the plate, no depth map needed")

pl2 = torch.full((n, H, W, 3), 0.9); pl2[:, :, 30:] = 0.05
steps = torch.zeros((n, H, W)); steps[:, :, 30:] = 1
for y in range(0, H, 8):
    steps[:, y:y + 4, 28:30] = 1
_, _, a = node.place(pl2, el, anchor, track, 1.0, 0, 0, "over", 1.0, False, object_mask=steps, object_in_front=True)
col = a[0, 20:48, 29].numpy()
check(float(col.max() - col.min()) < 0.15, "object mask: the steps are gone, the cut follows the plate's edge")

an_node = M["EFAnchor"]()
fl = torch.zeros((6, 48, 32, 4))
for i, dy in enumerate([0, 3, -2, 3, 0, -3]):
    fl[i, 10 + dy:40 + dy, 12:20, :] = 1.0
outs = {}
for lock in (False, True):
    _, _, anc, _, _ = an_node.anchor(fl, 0.9, 0.3, "remove slow drift", 25, 0, 0, lock_base=lock)
    outs[lock] = [p[1] for p in anc["base_point_px"]]
check(max(outs[False]) - min(outs[False]) >= 5, "remove slow drift keeps the base's jitter (as before)")
check(max(outs[True]) - min(outs[True]) < 1.0, "lock_base: the base point stays in place")

API = os.path.join(PACK, "api_workflows")
sets = json.load(open(os.path.join(API, "element_forge.settings.json"), encoding="utf-8"))["settings"]
check(FRONT in sets, "setting in element_forge.settings.json")
nid = sets[FRONT][0]
for f in ("element_forge.json", "element_forge_app.json", "element_forge_climb.json", "element_forge_dissolve.json"):
    g = json.load(open(os.path.join(API, f), encoding="utf-8"))
    pa = [k for k, v in g.items() if v["class_type"] == "EFPlaceElement" and (v.get("_meta") or {}).get("title") == "At point A"]
    check(g[nid]["inputs"]["value"] is False and pa and g[pa[0]]["inputs"].get("object_in_front") == [nid, 0]
          and isinstance(g[pa[0]]["inputs"].get("object_mask"), list), f"{f}: off by default, wired to At point A")
    lid = sets[LOCK][0]
    an_ids = [k for k, v in g.items() if v["class_type"] == "EFAnchor" and v["inputs"].get("lock_base") == [lid, 0]]
    check(g[lid]["inputs"]["value"] is False and an_ids, f"{f}: base lock off by default, wired to the anchor")

st = importlib.import_module(pack.__name__ + ".element_forge.workflow.stages")
check(st.FRONT == FRONT, "stages: the setting's name")
lay = st.EFForgePlace().build({"id": "e"}, size=-1.0, side=st.STYLE, **{"depth offset": 0.0, "blend": st.STYLE, "object in front": True})[0]
check(lay["place"]["front"] is True, "EF Place: object in front is kept in the layer")
lay2 = st.EFForgePlace().build({"id": "e"}, size=-1.0, side=st.STYLE, **{"depth offset": 0.0, "blend": st.STYLE, "lock base": True})[0]
check(lay2["place"]["lock"] is True and st.LOCK == LOCK, "EF Place: lock base is kept in the layer")
an = importlib.import_module(pack.__name__ + ".element_forge.app_mode.nodes")
on, off = an.apply_effect({}, {"object_in_front": True}), an.apply_effect({}, {"object_in_front": False})
check(on.get(FRONT) is True and FRONT not in off, "App-mode effect: the setting only when on")
check("object_in_front" in an.EFAppEffect.INPUT_TYPES()["optional"], "App-mode effect node: the widget, optional (old workflows load)")
adv_on = an.apply_effect({}, {"mode": "advanced", "lock_base": True})
check(adv_on.get(LOCK) is True, "App-mode effect: base lock in Advanced")
check(LOCK not in an.apply_effect({}, {"mode": "basic", "lock_base": True}), "App-mode effect: no base lock in Basic")
check(LOCK not in an.apply_effect({}, {"mode": "advanced", "lock_base": False}), "App-mode effect: no base lock when off")
check("lock_base" in an.EFAppEffect.INPUT_TYPES()["optional"], "App-mode effect node: the base lock widget, optional")
js = open(os.path.join(PACK, "web", "efa", "panel.js"), encoding="utf-8").read()
check('"lock_base"' in js and 'mode !== "advanced"' in js[js.index("function lockBaseRow"):js.index("function objectGroup")],
      "panel: the switch only in Advanced, with its short note")
print(f"{ok} checks passed")
