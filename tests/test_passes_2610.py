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

T = tempfile.mkdtemp(prefix="ef_test_passes_")
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

import json

import av
import numpy as np


def folder(name, n_files, comps=(), frames=None):
    d = os.path.join(T, name)
    os.makedirs(d, exist_ok=True)
    for p in ("plate", "element", "depth"):
        for i in range(1, n_files + 1):
            open(os.path.join(d, f"{p}_{i:05d}.exr"), "wb").close()
    for k, n in enumerate(comps, 1):
        with av.open(os.path.join(d, f"comp_{k:05d}_.mp4"), "w") as c:
            s = c.add_stream("libx264", rate=30)
            s.width, s.height, s.pix_fmt = 64, 64, "yuv420p"
            for _ in range(n):
                for pk in s.encode(av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), np.uint8), format="rgb24")):
                    c.mux(pk)
            for pk in s.encode():
                c.mux(pk)
    if frames:
        json.dump({"values": {"Frames": frames}}, open(os.path.join(d, "app_recipe.json"), "w"))
    return d


d = folder("twice", 162, comps=(81, 81))
f = AN.pass_files(d)
check(len(f["plate"]) == 81 and f["plate"][0].endswith("plate_00082.exr") and f["plate"][-1].endswith("plate_00162.exr"),
      "run twice: the newest run's 81 frames (00082-00162)")
check(all(len(v) == 81 for v in f.values()), "run twice: every pass the same 81 frames")
d = folder("once", 81, comps=(81,))
check(len(AN.pass_files(d)["plate"]) == 81, "run once: all 81 frames")
d = folder("recipe", 48, frames=24)
check(len(AN.pass_files(d)["plate"]) == 24 and AN.pass_files(d)["plate"][0].endswith("plate_00025.exr"),
      "no comp: \"Frames\" of app_recipe.json")
d = folder("bare", 30)
check(len(AN.pass_files(d)["depth"]) == 30, "neither comp nor recipe: all files as before")
check(AN.last_run_frames(folder("short", 81, comps=(40, 81))) == 81, "newest comp counts (ComfyUI's counter)")
print(f"{ok}/{ok + len(fails)} checks passed")
sys.exit(1 if fails else 0)
