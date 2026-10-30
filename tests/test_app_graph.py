import copy
import importlib.util
import json
import os

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("app_graph", os.path.join(PACK, "element_forge/app/app_graph.py"))
ag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ag)
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


def load(name):
    with open(os.path.join(PACK, "api_workflows", name), encoding="utf-8") as f:
        return json.load(f)


def links(g):
    return [(k, a, v[0]) for k, nd in g.items() for a, v in nd["inputs"].items() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)]


RTX = {"RTXVideoSuperResolution", "RTXTrueHDR"}
for name in ("element_forge_app.json", "element_forge_climb.json", "element_forge_dissolve.json", "element_forge.json"):
    g0 = load(name)
    used = {v[0] for _, _, v in [(k, a, v) for k, nd in g0.items() for a, v in nd["inputs"].items() if isinstance(v, list) and len(v) == 2]}
    sinks = {k for k in g0 if k not in used}
    out_classes = {g0[k]["class_type"] for k in sinks}
    is_out = lambda c: c in out_classes
    known = {nd["class_type"] for nd in g0.values()}
    g = copy.deepcopy(g0)
    check(ag.without_unused(g, known, is_out) is g and g == g0, f"{name}: every pack there -> graph unchanged")
    g = ag.without_unused(copy.deepcopy(g0), known - RTX, is_out)
    check(not any(nd["class_type"] in RTX for nd in g.values()), f"{name}: no NVIDIA node left")
    check(all(src in g for _, _, src in links(g)), f"{name}: every link points to a node in the graph")
    check(sinks <= set(g), f"{name}: every output node kept ({len(sinks)})")
    nv = next(k for k, nd in g0.items() if nd.get("_meta", {}).get("title") == "NVIDIA SR + HDR")
    gone = [k for k, nd in g0.items() if nd["class_type"] == "ComfySwitchNode" and nd["inputs"].get("switch") == [nv, 0]]
    check(gone and not any(k in g for k in gone), f"{name}: the {len(gone)} switches of 'NVIDIA SR + HDR' resolved")
    for sw in gone:
        off = g0[sw]["inputs"]["on_false"]
        readers = [(k, a) for k, a, src in links(g0) if src == sw and k in g]
        check(all(g[k]["inputs"][a] == off or (g0[off[0]]["class_type"] == "ComfySwitchNode" and off[0] not in g) for k, a in readers),
              f"{name}: readers of switch {sw} take {off}")
    g1 = copy.deepcopy(g0)
    g1[nv]["inputs"]["value"] = True
    needed = ag.without_unused(dict(copy.deepcopy(g1), x={"class_type": "Unknown", "inputs": {}}), known, is_out)
    needed = sum(nd["class_type"] in RTX for nd in needed.values())
    g1 = ag.without_unused(g1, known - RTX, is_out)
    check(sum(nd["class_type"] in RTX for nd in g1.values()) == needed and (needed == 2 or name == "element_forge_dissolve.json"),
          f"{name}: switch on -> NVIDIA nodes stay where an output needs them ({needed}; dissolve makes no element on black)")

known = {"Src", "Out", "ComfySwitchNode", "PrimitiveBoolean", "Missing"}
g = {"1": {"class_type": "Src", "inputs": {}}, "2": {"class_type": "Gone", "inputs": {}},
     "3": {"class_type": "PrimitiveBoolean", "inputs": {"value": False}},
     "4": {"class_type": "ComfySwitchNode", "inputs": {"switch": ["3", 0], "on_false": ["1", 0], "on_true": ["2", 0]}},
     "5": {"class_type": "ComfySwitchNode", "inputs": {"switch": True, "on_false": ["2", 0], "on_true": ["4", 0]}},
     "6": {"class_type": "Out", "inputs": {"x": ["5", 0]}}}
r = ag.without_unused(copy.deepcopy(g), known, lambda c: c == "Out")
check(r == {"1": g["1"], "6": {"class_type": "Out", "inputs": {"x": ["1", 0]}}}, "chain of two fixed switches -> output reads the source")
g["3"] = {"class_type": "Src", "inputs": {}}
r = ag.without_unused(copy.deepcopy(g), known, lambda c: c == "Out")
check("4" in r and "2" in r and r["6"]["inputs"]["x"] == ["4", 0], "switch with a computed value stays, with both inputs")
print(f"{ok} checks passed")
