import ast
import re
import json
import os
import types

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(PACK, "element_forge/app/app_routes.py"), encoding="utf-8").read()
tree = ast.parse(src)
keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in ("use_ltx", "use_depthcrafter", "depthcrafter_half_loaded"))
        or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("LTX_ATTENTION", "CLEAN_PLATE_STRENGTH", "DEPTHCRAFTER_FILES") for t in n.targets))]
import tempfile
MODELS = tempfile.mkdtemp(prefix="ef_test_dc_")
FILES = ["LTX25-distilled-DiT-comfy-int8.safetensors", "other.safetensors"]
GGUF = ["ltx-2.5-22b-distilled-transformer-bf16-Q4_K_M.gguf"]
TE = ["gemma4-12b-with-proj-ltx-2.5-bf16.safetensors", "gemma4_e2b_it_int8_convrot.safetensors"]
ns = {"folder_paths": types.SimpleNamespace(get_filename_list=lambda kind: FILES if kind == "diffusion_models" else GGUF if kind == "unet_gguf" else TE if kind == "text_encoders" else [],
                                              folder_names_and_paths={"unet_gguf": None}, models_dir=MODELS), "os": os}
ns["LTX_ATTENTION"] = ast.literal_eval(re.search(r"^LTX_ATTENTION = (.+)$", open(os.path.join(PACK, "element_forge/app/compact_values.py"), encoding="utf-8").read(), re.M).group(1))
exec(compile(ast.Module(body=keep, type_ignores=[]), "use_ltx", "exec"), ns)
use_ltx = ns["use_ltx"]

n = bad = 0
def check(ok, msg):
    global n, bad
    n += 1; bad += not ok
    print(("ok   " if ok else "FAIL ") + msg)

base = json.load(open(os.path.join(PACK, "api_workflows", "element_forge_app.json"), encoding="utf-8"))
g = use_ltx(json.loads(json.dumps(base)), None)
check(g == base, "no choice: graph unchanged")
g = use_ltx(json.loads(json.dumps(base)), {"file": FILES[0]})
lo = [nd for nd in g.values() if nd["class_type"] == "UNETLoader"]
check(len(lo) == 1 and lo[0]["inputs"] == {"unet_name": FILES[0], "weight_dtype": "default"} and not any(nd["class_type"] == "UnetLoaderGGUF" for nd in g.values()),
      "other INT8 file: UNETLoader reads it")
check(any(nd["class_type"] == "UNETLoader" and nd["inputs"]["unet_name"].endswith("int8-convrot.safetensors") for nd in base.values()),
      "the workflow itself loads LTX INT8 with UNETLoader")
g = use_ltx(json.loads(json.dumps(base)), {"file": GGUF[0]})
gl = [nd for nd in g.values() if nd["class_type"] == "UnetLoaderGGUF"]
check(len(gl) == 1 and gl[0]["inputs"] == {"unet_name": GGUF[0]} and not any(nd["class_type"] == "UNETLoader" and "ltx" in nd["inputs"]["unet_name"].lower() for nd in g.values()),
      "GGUF file: UNETLoader replaced by UnetLoaderGGUF")
cps = lambda gr: [nd["inputs"]["strength_model"] for nd in gr.values() if nd["class_type"] == "LTXICLoRALoaderModelOnly"
                 and "clean-plate" in nd["inputs"]["lora_name"]]
check(cps(g) == [1.0], f"GGUF file: clean plate LoRA back to 1.0 ({cps(g)})")
check(cps(base) == [1.5], f"workflow (INT8): clean plate LoRA 1.5 ({cps(base)})")
check(cps(use_ltx(json.loads(json.dumps(base)), {"file": FILES[0]})) == [1.5], "other INT8 file: clean plate LoRA stays 1.5")
g = use_ltx(json.loads(json.dumps(base)), {"file": FILES[0], "attention": "comfy kitchen attention"})
att = [(k, nd) for k, nd in g.items() if nd["class_type"] == "ModelAttentionBackend"]
dt = [k for k, nd in g.items() if nd["class_type"] == "ModelComputeDtype"]
users = [k for k, nd in g.items() for v in nd["inputs"].values() if v == [dt[0], 0]]
check(len(att) == 1 and att[0][1]["inputs"]["model"] == [dt[0], 0] and users == [att[0][0]], "INT8 attention: one node after the dtype node, only it reads the dtype node")
check(any(v == [att[0][0], 0] for nd in g.values() for v in nd["inputs"].values()), "the sampler side reads the attention node")
for bad_choice, msg in (({"file": "missing.safetensors"}, "unknown file"), ({"attention": "magic"}, "unknown backend")):
    try:
        use_ltx(json.loads(json.dumps(base)), bad_choice)
        check(False, msg + " rejected")
    except ValueError:
        check(True, msg + " rejected")
g = use_ltx(json.loads(json.dumps(base)), {"te": TE[0]})
cl = [nd["inputs"]["clip_name"] for nd in g.values() if nd["class_type"] == "CLIPLoader"]
diff = [k for k in base if base[k] != g[k]]
check(TE[0] in cl and all(g[k]["class_type"] == "CLIPLoader" for k in diff) and len(diff) >= 1,
      f"text encoder: the Gemma 12B loader reads the chosen bf16 file ({len(diff)} node(s) changed, nothing else)")
try:
    use_ltx(json.loads(json.dumps(base)), {"te": "missing.safetensors"})
    check(False, "unknown text encoder rejected")
except ValueError:
    check(True, "unknown text encoder rejected")
g = use_ltx(json.loads(json.dumps(base)), {"attention": "pytorch attention"})
check(g == base, "default backend: graph unchanged")
import sys as _sys
_sys.modules["nodes"] = types.SimpleNamespace(NODE_CLASS_MAPPINGS={"DepthCrafter": object})
g = use_ltx(json.loads(json.dumps(base)), {"depth": "depthcrafter"})
dc = [k for k, nd in g.items() if nd["class_type"] == "DepthCrafter"]
sc = [nd for nd in g.values() if nd["class_type"] == "ImageScale" and nd["inputs"].get("image") == ["dc", 0]]
check(dc == ["dc"] and len(sc) == 1 and g["dc_in"]["inputs"]["image"] == next(nd for nd in base.values() if nd["class_type"] == "VideoDepthAnythingProcess")["inputs"]["images"],
      "DepthCrafter: takes the clip of VDA and feeds the depth scale (then EF Deflicker)")
check(not any(nd["class_type"] == "DepthCrafter" for nd in use_ltx(json.loads(json.dumps(base)), {"file": FILES[0]}).values()), "DepthCrafter only when chosen")
_sys.modules["nodes"] = types.SimpleNamespace(NODE_CLASS_MAPPINGS={})
try:
    use_ltx(json.loads(json.dumps(base)), {"depth": "depthcrafter"})
    check(False, "DepthCrafter chosen without its nodes: error")
except ValueError as e:
    check("not installed" in str(e), "DepthCrafter chosen without its nodes: a clear error")
_sys.modules["nodes"] = types.SimpleNamespace(NODE_CLASS_MAPPINGS={"DepthCrafter": object})
os.makedirs(os.path.join(MODELS, "depthcrafter", "tencent_DepthCrafter", ".cache"))
try:
    use_ltx(json.loads(json.dumps(base)), {"depth": "depthcrafter"})
    check(False, "DepthCrafter half loaded: error")
except ValueError as e:
    check("half way" in str(e) and "tencent_DepthCrafter" in str(e), "DepthCrafter half loaded: a clear error naming the folder")

print(f"{n - bad}/{n} passed")
raise SystemExit(1 if bad else 0)
