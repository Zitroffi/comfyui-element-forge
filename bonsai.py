import json
import os
import threading
import time

import numpy as np
from PIL import Image

import comfy.model_management as mm
import folder_paths
import server

from . import bonsai_rt
from .json_grammar import schema_to_grammar
from .setup_bonsai import MODEL_FILES

SETTINGS = os.path.join(folder_paths.get_user_directory(), "element-forge", "bonsai.json")
PACK_RUNTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
DEFAULTS = {"runtime": "", "model": "", "mmproj": "", "context": 4096, "image_max_tokens": 1024, "keep_seconds": 120, "mmproj_on_gpu": False}
FROM_SETTINGS = "(bonsai.json)"


def _register_folder():
    paths = [os.path.join(folder_paths.models_dir, "LLM")]
    for p in folder_paths.get_folder_paths("checkpoints"):
        sib = os.path.join(os.path.dirname(os.path.normpath(p)), "LLM")
        if os.path.isdir(sib) and sib not in paths:
            paths.append(sib)
    known, exts = folder_paths.folder_names_and_paths.get("LLM", ([], set()))
    folder_paths.folder_names_and_paths["LLM"] = (list(dict.fromkeys(list(known) + paths)), set(exts) | {".gguf"})


_register_folder()

_lock = threading.Lock()
_model = None
_key = None
_idle = None
_env = None


def settings():
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        return dict(DEFAULTS)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{SETTINGS} is not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}") from None
    if not isinstance(cfg, dict):
        raise RuntimeError(f"{SETTINGS} must hold one JSON object like {{\"model\": \"…\"}}.")
    return {**DEFAULTS, **cfg}


def _runtime(cfg):
    for d in (cfg["runtime"], PACK_RUNTIME):
        if bonsai_rt.is_runtime(d):
            return d
    return None


def _file(name):
    if not name or name == "none":
        return None
    if os.path.isabs(name):
        return name if os.path.isfile(name) else None
    return folder_paths.get_full_path("LLM", name)


def spec(model=FROM_SETTINGS, mmproj=FROM_SETTINGS, context=None):
    cfg = settings()
    m = _file((cfg["model"] or MODEL_FILES[0]) if model == FROM_SETTINGS else model)
    if not m:
        raise RuntimeError(f"No Bonsai model found: put the .gguf into models/LLM or set \"model\" in {SETTINGS}.")
    p = _file((cfg["mmproj"] or MODEL_FILES[1]) if mmproj == FROM_SETTINGS else mmproj)
    return {"model": m, "mmproj": p, "context": int(context or cfg["context"])}


def status():
    try:
        cfg = settings()
    except RuntimeError as e:
        return {"running": _model is not None, "ours": True, "can_start": False, "vision": False, "runtime": None,
                "settings": SETTINGS, "in_process": True, "error": str(e)}
    try:
        s = spec()
    except RuntimeError:
        s = None
    rt = _runtime(cfg)
    return {"running": _model is not None, "ours": True, "can_start": bool(s and rt), "vision": bool(s and s["mmproj"]),
            "runtime": rt, "settings": SETTINGS, "in_process": True}


def _gpu():
    return mm.cpu_state != mm.CPUState.CPU


def _free():
    global _model, _key
    if _model is not None:
        _model.free()
        _model, _key = None, None


def stop():
    global _idle
    with _lock:
        if _idle:
            _idle.cancel()
            _idle = None
        _free()


def _load(s):
    global _model, _key
    cfg = settings()
    key = (s["model"], s["mmproj"], s["context"], _gpu())
    if _model is not None and _key == key:
        return _model
    _free()
    rt = _runtime(cfg)
    if not rt:
        raise RuntimeError(f"PrismML's llama.cpp libraries ({', '.join(bonsai_rt.LIB_NAMES)}) were not found: set \"runtime\" in "
                           f"{SETTINGS} or put the release for this system (prism-b10743-adfffbe) into {PACK_RUNTIME}.")
    if _gpu():
        mm.unload_all_models()
        mm.soft_empty_cache()
    _model = bonsai_rt.Model(bonsai_rt.libraries(rt), s["model"], s["mmproj"], n_ctx=s["context"], gpu=_gpu(),
                             mmproj_gpu=bool(cfg["mmproj_on_gpu"]), image_max_tokens=int(cfg["image_max_tokens"]))
    _key = key
    return _model


def _after(keep):
    global _idle
    if not keep:
        _free()
        return
    try:
        keep_s = float(settings()["keep_seconds"])
    except (RuntimeError, TypeError, ValueError):
        keep_s = float(DEFAULTS["keep_seconds"])
    _idle = threading.Timer(keep_s, stop)
    _idle.daemon = True
    _idle.start()


def _prompt(model, system, text, with_image):
    global _env
    user = (model.marker + "\n" + text) if with_image else text
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
    if not model.template:
        return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages) + "<|im_start|>assistant\n"
    if _env is None:
        import jinja2.sandbox

        def raise_exception(msg):
            raise ValueError(msg)
        _env = jinja2.sandbox.ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
        _env.globals["raise_exception"] = raise_exception
    return _env.from_string(model.template).render(messages=messages, add_generation_prompt=True, enable_thinking=False)


def _rgb(image, edge=1024):
    if not isinstance(image, Image.Image):
        image = Image.fromarray((image[0].clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8))
    image = image.convert("RGB")
    if max(image.size) > edge:
        s = edge / max(image.size)
        image = image.resize((max(1, round(image.width * s)), max(1, round(image.height * s))), Image.LANCZOS)
    return np.asarray(image)


def chat(text, system="", image=None, schema=None, max_tokens=400, temperature=0.7, keep=False, seed=0, which=None):
    global _idle
    grammar = schema_to_grammar(schema) if schema else None
    with _lock:
        if _idle:
            _idle.cancel()
            _idle = None
        t0 = time.time()
        try:
            model = _load(which or spec())
            out, st = model.generate(_prompt(model, system, text, image is not None), _rgb(image) if image is not None else None,
                                     grammar, max_tokens, temperature, top_p=0.8, top_k=20, seed=seed)
        except Exception:
            _free()
            raise
        finally:
            if _model is not None:
                _after(keep)
    if st["cut"] and grammar:
        raise RuntimeError("The answer was cut off (max_tokens too small).")
    return out.strip(), round(time.time() - t0, 2), st["tokens_per_second"]


def _on_prompt(json_data):
    if _model is not None and not _lock.locked():
        threading.Thread(target=stop, daemon=True).start()
    return json_data


server.PromptServer.instance.add_on_prompt_handler(_on_prompt)

