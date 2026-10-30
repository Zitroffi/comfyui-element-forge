
import json
import os
import sys
import time

try:
    from .nodes import run_id
except ImportError:
    import importlib.util

    _spec = importlib.util.spec_from_file_location("efa_nodes_for_run", os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodes.py"))
    _nodes = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_nodes)
    run_id = _nodes.run_id

RUN_CLASS = "EFAppRun"


def forge():
    for name, mod in list(sys.modules.items()):
        if name.endswith(".app_routes") and all(hasattr(mod, a) for a in ("build_graph", "app_job", "VARIANTS", "VIDEO_SAVES")):
            cv = sys.modules.get(name.rsplit(".", 1)[0] + ".compact_values")
            if cv is not None and hasattr(cv, "style_def"):
                return mod, cv
    raise ValueError("Element Forge: the main pack (comfyui-element-forge) is not loaded")


def variant_of(ar, cv, effect):
    kind, style = (effect or {}).get("kind"), (effect or {}).get("style")
    st = cv.style_def(ar._load_json("app_presets.json"), kind, style)
    if st is None:
        raise ValueError(f"Element Forge: unknown effect style {kind}/{style}")
    return st.get("variant") or "app"


def build(settings, effect, exr_passes=True, track_check=True, run_name=None, models=None):
    import folder_paths

    ar, cv = forge()
    if not isinstance(settings, dict) or not settings:
        raise ValueError("Element Forge: add an effect in the canvas first.")
    variant = variant_of(ar, cv, effect)
    run = run_name or run_id(settings)
    settings = dict(settings)
    app = settings.pop("_app", None) or {}
    mode = "preview" if app.get("mode") == "preview" and variant == "app" else "full"
    skip = [p for p in (app.get("skip") or []) if p in ("depth", "normals", "mask")]
    eid = str(app.get("effect") or "")[:64]
    ltx = app.get("ltx") if isinstance(app.get("ltx"), dict) else None
    swaps = {}
    if isinstance(models, dict):
        ltx, swaps = _models().run_choice(models)
        ltx = ltx or None
    out_dir = folder_paths.get_output_directory()
    variant, values, run, edit, recipe, _ = ar.app_job({"variant": variant, "values": settings, "run": run, "mode": mode,
                                                        "save_element": bool(app.get("save_element"))}, out_dir)

    def edit_all(g):
        edit(g)
        for p in skip:
            g.pop(ar.PASS_SAVES[p], None)
            if p == "normals":
                g.pop(ar.DISSOLVE_LIGHT_SAVES.get("normals"), None)
        if not exr_passes:
            for nid in list(ar.PASS_SAVES.values()) + list(ar.DISSOLVE_LIGHT_SAVES.values()):
                g.pop(nid, None)
        if not track_check:
            g.pop(ar.VIDEO_SAVES[1], None)
    graph = _models().swap_files(ar.build_graph(variant, values, run, ltx, edit_all), swaps)
    folder = ar._inside(out_dir, f"element-forge/{run}")
    os.makedirs(folder, exist_ok=True)
    rec = {"variant": variant, **recipe(), "recipe": None, "source": "EF App Run", "time": time.time(), **({"skip": skip} if skip else {}), **({"effect": eid} if eid else {}),
           **({"models": {**(ltx or {}), **({"swaps": swaps} if swaps else {})}} if isinstance(models, dict) else {}),
           "model_files": ar.model_files(graph),
           **({"attention": models["attention"]} if isinstance(models, dict) and models.get("attention") else {})}
    with open(os.path.join(folder, "app_recipe.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return graph, run


def is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], (str, int))


MODEL_EXT = (".safetensors", ".sft", ".pth", ".pt", ".ckpt", ".gguf", ".bin")


def _models():
    try:
        from . import models
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("efa_models_for_run", os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.py"))
        models = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(models)
    return models


def missing_models(graph, node_classes=None):
    if node_classes is None:
        try:
            import nodes as comfy_nodes
            node_classes = comfy_nodes.NODE_CLASS_MAPPINGS
        except ImportError:
            return []
    outputs = [k for k, nd in graph.items() if getattr(node_classes.get(nd.get("class_type")), "OUTPUT_NODE", False)]
    seen, todo = set(), list(outputs)
    while todo:
        k = str(todo.pop())
        if k in seen or k not in graph:
            continue
        seen.add(k)
        todo += [v[0] for v in (graph[k].get("inputs") or {}).values() if is_link(v)]
    known = {m["file"]: m for m in _models().MODELS}
    out, listed = [], set()
    for k in sorted(seen):
        cls = node_classes.get(graph[k].get("class_type"))
        if cls is None:
            continue
        try:
            spec = cls.INPUT_TYPES()
        except Exception:
            continue
        specs = {**(spec.get("required") or {}), **(spec.get("optional") or {})}
        for name, v in (graph[k].get("inputs") or {}).items():
            if not (isinstance(v, str) and v.lower().endswith(MODEL_EXT)) or v in listed:
                continue
            choices = specs.get(name, [None])[0]
            if isinstance(choices, (list, tuple)) and v not in choices:
                m = known.get(v, {})
                out.append({"file": v, "folder": m.get("folder"), "source": m.get("source")})
                listed.add(v)
    return out


def missing_message(missing):
    lines = [f"- {m['file']} -> models/{m['folder']}" if m.get("folder") else f"- {m['file']}" for m in missing]
    lines = [ln + (f" ({m['source']})" if m.get("source") else "") for ln, m in zip(lines, missing)]
    msg = ("Element Forge: this run needs model files that are not installed:\n" + "\n".join(lines) +
            "\nPut them into these folders (or let ComfyUI download them when the workflow opens) and run again. "
            "Or choose another file in the Element Forge - Models node (the gear at the top of the app panel shows the same "
            "choices and lists every model with its folder and source).")
    return msg.encode("ascii", "replace").decode("ascii")


MODELS_CLASS = "EFAppModels"


def models_in(prompt, link):
    if is_link(link):
        nd = prompt.get(str(link[0]))
        if not isinstance(nd, dict) or nd.get("class_type") != MODELS_CLASS:
            return False
        vals = nd.get("inputs") or {}
        return False if any(is_link(v) for v in vals.values()) else dict(vals)
    found = [nd for nd in prompt.values() if isinstance(nd, dict) and nd.get("class_type") == MODELS_CLASS]
    if len(found) != 1 or any(is_link(v) for v in (found[0].get("inputs") or {}).values()):
        return None
    return dict(found[0].get("inputs") or {})


def queue_expand(prompt, effect_of):
    notes = []
    for rid in [k for k, nd in prompt.items() if isinstance(nd, dict) and nd.get("class_type") == RUN_CLASS]:
        ins = prompt[rid].get("inputs") or {}
        settings = ins.get("settings")
        effect = effect_of(ins.get("effect"))
        models = models_in(prompt, ins.get("models"))
        opts = {a: ins.get(a, True) for a in ("exr_passes", "track_check")}
        if not isinstance(settings, dict) or effect is None or models is False or any(not isinstance(v, bool) for v in opts.values()):
            notes.append(f"{rid}: values not known before the run, expanded when it runs")
            continue
        ar, _ = forge()
        graph, run = build(settings, effect, **opts, models=models)
        miss = missing_models(graph)
        if miss:
            notes.append(f"{rid}: missing model files {[m['file'] for m in miss]}, not expanded")
            continue
        name = lambda k: str(rid) if k == ar.VIDEO_SAVES[0] else f"{rid}.{k}"
        del prompt[rid]
        for k, nd in graph.items():
            prompt[name(k)] = {"class_type": nd["class_type"],
                               "inputs": {a: [name(v[0]), v[1]] if is_link(v) else v for a, v in nd["inputs"].items()},
                               "_meta": {"title": f"EF App Run · {nd.get('_meta', {}).get('title', nd['class_type'])}"}}
        notes.append(f"{rid}: {len(graph)} nodes, run element-forge/{run}")
    return notes


class EFAppRun:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings": ("EF_SETTINGS",),
                "effect": ("EF_EFFECT",),
                "exr_passes": ("BOOLEAN", {"default": True, "tooltip": "Write the passes as EXR (plate, element, light, glow, depth, normals) for compositing."}),
                "track_check": ("BOOLEAN", {"default": True, "tooltip": "Write a small video that shows the track on the clip."}),
            },
            "optional": {
                "models": ("EF_MODELS", {"tooltip": "The model files of the run (Element Forge · Models)."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("folder",)
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = "Element Forge/App"
    DESCRIPTION = ("Makes the run of the App: builds the graph of the chosen style (the same as the standalone app) and puts "
                   "it in here. The comp shows on this node; passes and track check go to output/element-forge/<run>/.")

    def run(self, settings, effect, exr_passes=True, track_check=True, models=None, unique_id=None):
        from comfy_execution.graph_utils import GraphBuilder
        ar, cv = forge()
        graph, run = build(settings, effect, exr_passes, track_check, models=models)
        miss = missing_models(graph)
        if miss:
            raise ValueError(missing_message(miss))
        return {"result": (f"element-forge/{run}",),
                "expand": cv.expand(graph, GraphBuilder.alloc_prefix(), unique_id, {ar.VIDEO_SAVES[0]})}
