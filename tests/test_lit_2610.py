import os
import sys
import types

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PACK))
ok = 0
fails = []


def check(cond, msg):
    global ok
    if cond:
        ok += 1
        print("ok  ", msg)
    else:
        fails.append(msg)
        print("FAIL", msg)


import importlib
import tempfile

from aiohttp import web

T = tempfile.mkdtemp(prefix="ef_test_lit_")
fp = types.ModuleType("folder_paths")
for name in ("get_output_directory", "get_temp_directory", "get_input_directory", "get_user_directory"):
    setattr(fp, name, lambda: T)
fp.get_annotated_filepath = lambda n: os.path.join(T, n)
sys.modules["folder_paths"] = fp
srv = types.ModuleType("server")
srv.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=web.RouteTableDef()))
sys.modules["server"] = srv
comfy = types.ModuleType("comfy")
cu = types.ModuleType("comfy.utils")
cu.ProgressBar = type("PB", (), {"__init__": lambda s, n: None, "update": lambda s, n=1: None, "update_absolute": lambda s, *a, **k: None})
mm = types.ModuleType("comfy.model_management")
mm.throw_exception_if_processing_interrupted = lambda: None
comfy.utils, comfy.model_management = cu, mm
sys.modules.update({"comfy": comfy, "comfy.utils": cu, "comfy.model_management": mm})
sys.modules[os.path.basename(PACK) + ".element_forge.bonsai.bonsai"] = types.ModuleType("bonsai")
importlib.import_module(os.path.basename(PACK))
AN = importlib.import_module(os.path.basename(PACK) + ".element_forge.app.app_nodes")

h, w = 4, 6
P = torch.full((1, h, w, 3), 0.1)
Ec = torch.full((1, h, w, 3), 0.2)
t = {"Ec": Ec, "Ea": torch.ones(1, h, w, 1), "L": torch.zeros(1, h, w, 3), "G": torch.zeros(1, h, w, 3),
     "S": (torch.full((1, h, w, 3), 0.3), torch.full((1, h, w, 1), 0.5)), "mode": "over", "visible": True}
Lo = torch.zeros(1, h, w, 3)
Lo[:, :, :2] = torch.tensor([0.3, 0.15, 0.05])

same = AN.lit_by(t, Lo, P, 0.0)
check(same is t, "amount 0: the layer stays as it is")
soft_ = AN.soft
AN.soft = lambda x, levels=0: x
lit = AN.lit_by(t, Lo, P, 1.0)
irr = 0.3 / (0.1 + AN.LIT_FLOOR)
check(abs(float(lit["Ec"][0, 0, 0, 0]) - 0.2 * (1 + irr)) < 1e-5, f"lit where the light falls (red x{1 + irr:.2f})")
check(torch.equal(lit["Ec"][:, :, 2:], Ec[:, :, 2:]), "unlit where no light falls")
check(float(lit["Ec"][0, 0, 0, 0]) > float(lit["Ec"][0, 0, 0, 2]), "the light's colour carries over (warm light, warmer layer)")
check(abs(float(lit["S"][0][0, 0, 0, 0]) - 0.3 * (1 + irr)) < 1e-5 and torch.equal(lit["S"][1], t["S"][1]),
      "smoke lit as well, its alpha unchanged")
huge = AN.lit_by(t, Lo * 100, P, 1.0)
check(float(huge["Ec"].max()) <= 0.2 * (1 + AN.LIT_MAX) + 1e-5, "capped (LIT_MAX)")
AN.soft = soft_
H, W = 256, 256
Lw = torch.zeros(1, H, W, 3)
Lw[:, :, : W // 2] = 0.4
Pw = torch.full((1, H, W, 3), 0.2)
Pw[:, :, 100:110] = 0.02
sm = {"Ec": torch.full((1, H, W, 3), 0.3), "Ea": torch.ones(1, H, W, 1), "L": torch.zeros(1, H, W, 3), "G": torch.zeros(1, H, W, 3),
      "S": None, "mode": "over", "visible": True}
row = AN.lit_by(sm, Lw, Pw, 1.0)["Ec"][0, 128, :, 0]
step = (row[1:] - row[:-1]).abs().max().item()
check(step < 0.05 * float(row.max()), f"soft field: no hard step at the light's edge or the pillar (largest step {step:.4f})")
check(float(row[20]) > float(row[236]) > 0.3 - 1e-4, "soft field: still more light where the light falls")
check(AN.merge_settings({"lit": {"others": 1}})["lit"]["others"] == 1 and AN.merge_settings({})["lit"]["others"] == 0,
      "settings: lit.others, off by default")
print(f"{ok}/{ok + len(fails)} checks passed")
sys.exit(1 if fails else 0)
