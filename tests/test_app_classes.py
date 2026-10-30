import glob
import importlib
import json
import os
import re
import sys
import tempfile
import types

S = tempfile.mkdtemp(prefix="ef_test_")
fp = types.ModuleType("folder_paths"); fp.get_output_directory = lambda: os.path.join(S, "out"); fp.get_temp_directory = lambda: os.path.join(S, "out")
sys.modules["folder_paths"] = fp
comfy = types.ModuleType("comfy"); cu = types.ModuleType("comfy.utils")
cu.ProgressBar = type("PB", (), {"__init__": lambda self, n: None, "update": lambda self, n=1: None, "update_absolute": lambda self, *a, **k: None})
comfy.utils = cu; sys.modules["comfy"] = comfy; sys.modules["comfy.utils"] = cu
mm = types.ModuleType("comfy.model_management"); mm.throw_exception_if_processing_interrupted = lambda: None
comfy.model_management = mm; sys.modules["comfy.model_management"] = mm
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = PACK if os.path.isfile(os.path.join(PACK, "app_mode", "nodes.py")) else None
sys.path.insert(0, os.path.dirname(PACK))
pack = importlib.import_module(os.path.basename(PACK))
M = pack.NODE_CLASS_MAPPINGS
ok, failed = 0, []


def check(cond, msg):
    global ok
    if cond:
        ok += 1
        print("ok  ", msg)
    else:
        failed.append(msg)
        print("FAIL", msg)


need = {}
for f in glob.glob(os.path.join(PACK, "api_workflows", "*.json")):
    g = json.load(open(f, encoding="utf-8"))
    if isinstance(g, dict) and g and all(isinstance(v, dict) and "class_type" in v for v in g.values()):
        for v in g.values():
            if v["class_type"].startswith("EF"):
                need.setdefault(v["class_type"], set()).add(os.path.basename(f))
for name in ("app_routes.py", "stages.py", "live.py", "analysis.py", "app_nodes.py"):
    src = open(os.path.join(PACK, name), encoding="utf-8").read()
    for c in re.findall(r"[\"']class_type[\"']\s*:\s*[\"'](EF[A-Za-z]+)[\"']", src):
        need.setdefault(c, set()).add(name)
if APP:
    for f in glob.glob(os.path.join(APP, "web", "**", "*.js"), recursive=True) + [os.path.join(APP, "app_mode", "nodes.py")]:
        src = open(f, encoding="utf-8").read()
        for c in re.findall(r"class_type[\"']?\s*:\s*[\"'](EF[A-Za-z]+)[\"']", src):
            if not c.startswith("EFApp"):
                need.setdefault(c, set()).add(os.path.relpath(f, APP).replace(os.sep, "/"))
else:
    print("note: app_mode/ not found, only the graphs and the stage code are checked")
for c in sorted(need):
    check(c in M, f"{c} registered (needed by {', '.join(sorted(need[c]))})")
for c in ("EFForgeModels", "EFForgeShot", "EFForgeTrack", "EFForgeElement", "EFForgePlace", "EFForgeLight", "EFForgeExport",
          "EFForgeParticles", "EFForgeGuide", "EFForgeDissolve", "EFForgeLTX", "EFForgeUnpack", "EFForgeFromImages", "EFForgeLibraryElement"):
    check(c in M and not getattr(M[c], "DEV_ONLY", False), f"{c} registered and in the node list")
hidden = sorted(k for k, c in M.items() if getattr(c, "DEV_ONLY", False))
shown = sorted(k for k, c in M.items() if not getattr(c, "DEV_ONLY", False))
check(all(M[k].CATEGORY.startswith("Element Forge") for k in shown), f"{len(shown)} nodes in the list, {len(hidden)} hidden building blocks")
if failed:
    print(f"{len(failed)} checks failed, {ok} passed")
    sys.exit(1)
print(f"{ok} checks passed")
