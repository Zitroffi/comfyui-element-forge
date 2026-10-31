import importlib.util
import json
import os
import sys

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(PACK, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PA = load("particle_assist", "element_forge/app/particle_assist.py")
JG = load("json_grammar", "element_forge/bonsai/json_grammar.py")
n = bad = 0


def check(cond, name):
    global n, bad
    n += 1
    bad += not cond
    print("ok  " if cond else "FAIL", name)


CONTROLS = [
    {"k": "direction", "label": "Direction", "min": 0, "max": 359, "step": 1, "int": True, "angle": True, "now": 0},
    {"k": "rate", "label": "Rate", "min": 0, "max": 2000, "step": 1, "unit": "/s", "now": 120},
    {"k": "speed", "label": "Speed", "min": 0, "max": 3000, "step": 5, "unit": "px/s", "now": 700},
    {"k": "trail", "label": "Trail", "min": 0, "max": 60, "step": 1, "int": True, "now": 0},
    {"k": "gravity", "label": "Gravity", "min": -3000, "max": 3000, "step": 10, "now": 1400},
    {"k": "broken", "label": "no range", "min": 5, "max": 5, "step": 1, "now": 5},
]
STOPS = [[0.0, [1.0, 1.0, 0.9]], [0.5, [1.0, 0.5, 0.12]], [1.0, [0.7, 0.15, 0.03]]]
body = {"prompt": {"what": "A few slow blue sparks"}, "style_prompt": {"what": "Bright orange-white sparks fly fast"},
        "style": "Sparks - burst", "controls": CONTROLS, "now": {"mode": "angle", "collide": "bounce", "sprite": "spark"},
        "modes": ["angle", "random"], "collides": ["none", "bounce"], "sprites": ["soft", "spark"], "stops": STOPS}
system, text, sch, ctl = PA.request(body)
check([c["k"] for c in ctl] == ["direction", "rate", "speed", "trail", "gravity"], "a control without a range is left out")
check(sch["properties"]["changes"]["items"]["properties"]["key"]["enum"] == [c["k"] for c in ctl], "the keys Bonsai may name are the controls")
check(sch["properties"]["changes"]["maxItems"] == PA.MAX_CHANGES, "at most ten changes")
check(list(sch["properties"])[:2] == ["colour_birth", "colour_end"], "the colours come first in the answer")
check("Bright orange-white sparks fly fast" in text and "A few slow blue sparks" in text, "the style's own prompt and the prompt now")
check(text.index("style's own prompt") < text.index("Prompt now"), "the style's own prompt before the prompt now")
check("white at birth, deep red at the end" in text, "the colours now by name")
g = JG.schema_to_grammar(sch)
check('ws ::= | " "' in g and "\\n" not in g.split("ws ::=")[1].split("\n")[0], "compact grammar: no line breaks or indents")
check('ws ::= | " " | "\\n"' in JG.schema_to_grammar({"type": "object", "properties": {"a": {"type": "number"}}}), "other schemas keep their spacing")
try:
    PA.request({**body, "controls": []})
    check(False, "no controls: an error")
except ValueError:
    check(True, "no controls: an error")

answer = json.dumps({"colour_birth": "light blue", "colour_end": "blue", "mode": "keep", "collide": "bounce", "sprite": "soft",
                     "changes": [{"key": "rate", "value": 5000, "why": "thousands"}, {"key": "speed", "value": 50, "why": "slow"},
                                 {"key": "trail", "value": 7.6, "why": "trails"}, {"key": "gravity", "value": -9000, "why": "rise"},
                                 {"key": "direction", "value": 180, "why": "down"}, {"key": "rate", "value": 10, "why": "again"},
                                 {"key": "nope", "value": 1, "why": "x"}, {"key": "speed", "value": 700, "why": "same"}],
                     "note": "Slow blue sparks."})
r = PA.read(answer, ctl, {"mode": "angle", "collide": "bounce", "sprite": "spark"}, STOPS)
by = {c["key"]: c for c in r["changes"]}
check(by["rate"]["to"] == 600, f"above 0 at most 5x: rate 120 -> {by['rate']['to']}")
check(by["speed"]["to"] == 140, f"and at least a fifth: speed 700 -> {by['speed']['to']}")
check(by["trail"]["to"] == 8, "an integer control is rounded")
check(by["gravity"]["to"] == -3000, "a value that can turn negative is held only to its range")
check(by["direction"]["to"] == 180, "a direction is not held to the factor")
check(list(by).count("rate") == 1 and by["rate"]["why"] == "thousands", "a key named twice is taken once (the first)")
check("nope" not in by, "an unknown key is left out")
check(len(r["changes"]) == 5, "a change to the value now is left out")
check(r["mode"] is None and r["collide"] is None and r["sprite"] == "soft", "keep and the choice now are no change")
check(r["colour_names"] == ["light blue", "blue"] and len(r["colors"]) == 3, "colours by name on the style's stops")
check(r["colors"][0][1] == PA.COLOURS["light blue"] and r["colors"][-1][1] == PA.COLOURS["blue"], "birth and end colour")
check(r["colors"][1][0] == 0.5, "the stops keep their places")
keep = PA.read(json.dumps({"colour_birth": "keep", "colour_end": "keep", "mode": "keep", "collide": "keep", "sprite": "keep",
                           "changes": [], "note": ""}), ctl, {}, STOPS)
check(keep["changes"] == [] and keep["colors"] is None and keep["colour_names"] is None, "all keep: nothing to change")
burst = [{"k": "rate", "label": "Rate", "min": 0, "max": 2000, "step": 1, "now": 0},
         {"k": "burst", "label": "Burst", "min": 0, "max": 2000, "step": 1, "now": 150}]
b = PA.read(json.dumps({"colour_birth": "keep", "colour_end": "keep", "mode": "keep", "collide": "keep", "sprite": "keep",
                        "changes": [{"key": "rate", "value": 300, "why": "puff"}, {"key": "burst", "value": 60, "why": "small"}], "note": ""}),
            PA.clean_controls(burst), {}, STOPS)
check([c["key"] for c in b["changes"]] == ["burst"], "a burst style gets no stream")
try:
    PA.read("{not json", ctl, {}, STOPS)
    check(False, "an answer that is no JSON: an error")
except ValueError:
    check(True, "an answer that is no JSON: an error")
one = PA.gradient(STOPS, "green", "keep")
check(PA.nearest(one[0][1]) == "green" and PA.nearest(one[-1][1]) == "dark green" and one[-1][1][1] < one[0][1][1],
      f"one colour named: the whole life takes it, darker at the end ({PA.nearest(one[-1][1])})")
check(PA.gradient(STOPS, "keep", "keep") is None, "no colour named: keep")
check(PA.nearest([1.0, 0.5, 0.1]) == "orange" and PA.nearest([0.04, 0.04, 0.04]) == "black", "nearest colour name")

print(f"{n - bad}/{n} passed")
sys.exit(1 if bad else 0)
