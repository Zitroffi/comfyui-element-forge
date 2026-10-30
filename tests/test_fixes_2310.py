import ast
import importlib.util
import json
import os
import sys
import tempfile
import types

import numpy as np
import torch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="ef_fixes_2310_")


def load_funcs(fname, names, extra):
    src = open(os.path.join(HERE, fname), encoding="utf-8").read()
    nodes = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in names]
    g = dict(extra)
    exec(compile(ast.Module(nodes, []), fname, "exec"), g)
    return g


cfg_path = os.path.join(TMP, "bonsai.json")
fp = types.SimpleNamespace(models_dir=os.path.join(TMP, "models"), folder_names_and_paths={},
                           get_folder_paths=lambda kind: [os.path.join(TMP, "models", kind)])
DEFAULTS = {"runtime": "", "model": "", "mmproj": "", "context": 4096, "image_max_tokens": 1024, "keep_seconds": 120,
            "mmproj_on_gpu": False}
g = load_funcs("bonsai.py", {"settings", "_register_folder"},
               {"json": json, "os": os, "SETTINGS": cfg_path, "DEFAULTS": DEFAULTS, "folder_paths": fp})
with open(cfg_path, "w", encoding="utf-8-sig") as f:
    f.write('{"model": "Ternary-Bonsai-2-27B-PTQ1_0.gguf", "keep_seconds": 30}')
s = g["settings"]()
assert s["model"] == "Ternary-Bonsai-2-27B-PTQ1_0.gguf" and s["keep_seconds"] == 30 and s["context"] == 4096, s
print("bonsai.json with a BOM: read")
with open(cfg_path, "w", encoding="utf-8") as f:
    f.write('{"model": "x.gguf",\n "keep_seconds": 30,}')
try:
    g["settings"]()
    raise AssertionError("a typo was accepted")
except RuntimeError as e:
    assert "bonsai.json" in str(e) and "line 2" in str(e), e
print("bonsai.json with a typo: the file and the line are named")
src = open(os.path.join(HERE, "bonsai.py"), encoding="utf-8").read()
st = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "status")
assert any(isinstance(h, ast.ExceptHandler) for n in ast.walk(st) for h in getattr(n, "handlers", [])), "status() catches nothing"
print("bonsai status: catches a broken bonsai.json")

fp.folder_names_and_paths["LLM"] = (["/elsewhere/LLM"], {".safetensors", ".bin"})
g["_register_folder"]()
paths, exts = fp.folder_names_and_paths["LLM"]
assert exts == {".safetensors", ".bin", ".gguf"} and paths[0] == "/elsewhere/LLM", (paths, exts)
fp.folder_names_and_paths.pop("LLM")
g["_register_folder"]()
assert fp.folder_names_and_paths["LLM"][1] == {".gguf"}
print("LLM folder: other packs keep their endings")

sys.modules["folder_paths"] = types.SimpleNamespace(get_output_directory=lambda: TMP, get_input_directory=lambda: TMP)
spec = importlib.util.spec_from_file_location("ef_elements_test", os.path.join(HERE, "elements.py"))
el = importlib.util.module_from_spec(spec)
spec.loader.exec_module(el)
rgba = torch.zeros((2, 8, 8, 4))
for bad in ("NUL", "nul", "COM3", "fire "):
    try:
        el.EFSaveElement().save(rgba, bad, 24.0, False)
        raise AssertionError(f"{bad!r} was accepted")
    except ValueError as e:
        assert "reserved" in str(e) or "end" in str(e), (bad, e)
assert not os.path.exists(os.path.join(TMP, "element-forge", "elements")) or not os.listdir(os.path.join(TMP, "element-forge", "elements"))
out = el.EFSaveElement().save(torch.rand((2, 8, 8, 4)), "aux flame", 24.0, False)
assert os.path.isdir(os.path.join(TMP, "element-forge", "elements", "aux flame")), out
print("element names: NUL, COM3 and a space at the end refused, 'aux flame' saved")

class OldLoader:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"vae_name": (["have.safetensors"],)}}
class ComboLoader:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"lora_name": ("COMBO", {"options": ["have-lora.safetensors"]}), "strength": ("FLOAT", {})}}
class FreeName:
    @classmethod
    def INPUT_TYPES(cls): return {"required": {"model": ("STRING", {"default": "x.pth"})}}
sys.modules["nodes"] = types.SimpleNamespace(NODE_CLASS_MAPPINGS={"OldLoader": OldLoader, "ComboLoader": ComboLoader, "FreeName": FreeName})
m = load_funcs("app_routes.py", {"missing_for"}, {"MODEL_EXT": (".safetensors", ".gguf", ".pth")})["missing_for"]
graph = {"1": {"class_type": "OldLoader", "inputs": {"vae_name": "gone-vae.safetensors"}},
         "2": {"class_type": "ComboLoader", "inputs": {"lora_name": "ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors", "strength": 1.0}},
         "3": {"class_type": "ComboLoader", "inputs": {"lora_name": "have-lora.safetensors", "strength": 1.0}},
         "4": {"class_type": "FreeName", "inputs": {"model": "downloads-itself.pth"}},
         "5": {"class_type": "NotInstalled", "inputs": {}}}
r = m(graph)
assert r == {"nodes": ["NotInstalled"], "models": ["gone-vae.safetensors", "ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors"]}, r
print("start check: missing IC-LoRA (COMBO loader) and VAE named, present LoRA and free names pass")

ec = load_funcs("__init__.py", {"edge_contact"}, {"torch": torch})["edge_contact"]
a = torch.zeros((20, 200, 100))
a[:, 60:150, 40:60] = 1.0
a[10:, 0:80, 35:65] = 0.6
r = ec(a)
assert r["frames"] == 20 and r["size"] == [100, 200], r
assert r["sides"]["top"]["frames"] == 10 and r["sides"]["top"]["max"] == 0.3, r["sides"]
assert all(r["sides"][s]["frames"] == 0 for s in ("bottom", "left", "right")), r["sides"]
b = torch.zeros((20, 200, 100)); b[:, 60:150, 40:60] = 1.0; b[5, 0:60, 48:53] = 1.0
assert ec(b)["sides"]["top"]["frames"] == 1 and ec(torch.zeros((3, 50, 50)))["sides"]["left"]["max"] == 0.0
thin = torch.zeros((20, 200, 100)); thin[:, 60:150, 40:60] = 0.3; thin[10:, 0:80, 35:65] = 0.15
thin[:, :, 0:3] = 0.02
t = ec(thin)
assert t["sides"]["top"]["frames"] == 10 and t["sides"]["left"]["frames"] == 0 and 0.08 < t["threshold"] < 0.1, t
print("edge contact: smoke leaving the top counted in 10 of 20 frames (30 % of the edge), a centred flame nowhere")
spec = importlib.util.spec_from_file_location("ef_light3d_test", os.path.join(HERE, "light3d.py"))
l3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l3)
plate = torch.full((2, 48, 64, 3), 0.3)
lay = torch.zeros((2, 48, 64, 3)); lay[:, 20:28, 28:36] = torch.tensor([2.0, 1.0, 0.3])
dep = torch.linspace(0.2, 1.0, 48)[None, :, None, None].expand(2, 48, 64, 3).contiguous()
args = dict(strength=0.9, depth_range=2.0, fov=65.0, light_size=0.15, wrap=0.25, shadows=True, max_light=0.8, saturation=1.6, device="cpu")
c_on, lt_on, _ = l3.EFDepthLight().light(plate, lay, dep, **args)
c_off, lt_off, _ = l3.EFDepthLight().light(plate, lay, dep, add_element=False, **args)
s2l = lambda x: torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
want = (s2l(plate) + lt_off).clamp(0, 1)
assert torch.allclose(lt_on, lt_off) and (s2l(c_off) - want).abs().max() < 2e-3, (s2l(c_off) - want).abs().max()
assert c_on[:, 24, 32].mean() > c_off[:, 24, 32].mean() + 0.2 and lt_off.max() > 0.01
print("depth light add_element off: comp = plate + light (element not added twice), light pass the same")
print("ALL OK")
