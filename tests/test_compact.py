import importlib.util
import json
import os
import subprocess

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_CASES = os.path.join(PACK, "tests", "compact_cases.mjs")
spec = importlib.util.spec_from_file_location("compact_values", os.path.join(PACK, "element_forge/app/compact_values.py"))
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


def same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) < 1e-9
    return a == b


with open(os.path.join(PACK, "element_forge", "app", "app_presets.json"), encoding="utf-8") as f:
    presets = json.load(f)
cases = json.loads(subprocess.run(["node", APP_CASES], cwd=PACK, capture_output=True,
                                  text=True, encoding="utf-8", check=True).stdout)
bad = []
for c in cases:
    py = cv.values_for(presets, c["effect"], c["shot"], c["scale"])
    js = c["values"]
    diff = sorted(k for k in set(py) | set(js) if k not in py or k not in js or not same(py[k], js[k]))
    if diff:
        bad.append((c["name"], {k: (py.get(k), js.get(k)) for k in diff[:4]}))
for b in bad[:10]:
    print("DIFF", b)
check(not bad, f"values_for == the app's valuesFor in all {len(cases)} cases ({len({c['name'].split()[0] for c in cases})} styles)")

print(f"{ok} checks passed")
