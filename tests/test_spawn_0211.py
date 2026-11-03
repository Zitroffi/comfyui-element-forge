import importlib.util
import os
import re

import numpy as np

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("ef_particles", os.path.join(PACK, "element_forge/simulation/particles.py"))
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


N, FPS, W, H, ON = 40, 24.0, 320, 180, 10


def masks(on=ON):
    m = np.zeros((N, H, W), np.float32)
    m[on:, 70:110, 140:180] = 1.0
    return m


def sim(over, on=ON, kind="object mask", look=False, preset="magic dust"):
    P = pt.params(preset, over)
    em = pt.Emitter(kind, N, FPS, W, H, P, np.random.default_rng(1), a=(160, 90), masks=masks(on) if on is not None else None)
    return pt.simulate(P, em, seed=3, look_state=look), P, em


def alive(rec):
    return (~np.isnan(rec["x"])).sum(1)


still = dict(speed=0.0, speed_var=0.0, gravity=0.0, wind=[0.0, 0.0], turbulence=0.0, drag=0.0, inherit=0.0, flicker=0.0,
             life=2.4, life_var=0.0, radius=0.0)
check(pt.BASE["fade_in_max"] == 0.0 and pt.PRESETS["magic dust"]["fade_in_max"] == 0.08 and "fade_in_max" in pt.LOOK_ONLY,
      "fade_in_max: off in BASE, 0.08 s for magic dust, look only")
live = open(os.path.join(PACK, "element_forge/app/live.py"), encoding="utf-8").read()
ejs = open(os.path.join(PACK, "web/efa/emitter.js"), encoding="utf-8").read()
check(re.search(r'"fade_in", "fade_in_max", "fade_out"', live) and 'key("fade_in_max", "Fade in at most"' in ejs,
      "the panel shows Fade in at most (live.py PANEL, emitter.js)")
_, _, em = sim(still)
check(abs(em.first_on(0.0) - ON / FPS) < 1e-9, "first_on: the first frame with a mask")
_, _, em0 = sim(still, on=0)
check(em0.first_on(0.0) == 0.0 and em0.first_on(0.3) == 0.3, "first_on: a mask at the start leaves the start as it is")
check(sim(still, on=None, kind="point A")[2].first_on(0.25) == 0.25, "first_on: other emitters start at the start")
early = np.zeros((N, H, W), np.float32)
early[:5, 70:110, 140:180] = 1.0
emn = pt.Emitter("object mask", N, FPS, W, H, pt.params("magic dust", still), np.random.default_rng(1), masks=early)
check(emn.first_on(0.5) is None, "first_on: no mask from the start on, None")
check(pt.burst_times({"start": 0.0, "burst_at": 0.25, "end": -1.0}, N, FPS) == [0.25] and
      pt.burst_times({"start": 0.0, "burst_at": 0.25, "end": -1.0}, N, FPS, 0.5) == [0.75], "burst_times: start given or not")
b = dict(still, rate=0.0, burst=50, burst_at=0.0)
r, _, _ = sim(b)
a = alive(r)
check(a[:ON].sum() == 0 and abs(a[ON] - 50) <= 2 and r["stats"]["spawned"] == a[ON],
      f"burst on a mask empty at the start: all of it on frame {ON} ({a[ON]}, spawned {r['stats']['spawned']})")
r, _, _ = sim(dict(b, burst_at=0.5))
a = alive(r)
k = ON + int(round(0.5 * FPS))
check(a[:k].sum() == 0 and abs(a[k] - 50) <= 2, f"Burst at counts from the first frame with a mask (frame {k})")
r, _, _ = sim(b, on=0)
check(abs(alive(r)[0] - 50) <= 2, "a mask at the start: the burst on frame 0 as before")
c = dict(still, rate=240.0, burst=0, rate_curve=[[0.0, 1.0], [0.1, 1.0], [0.11, 0.0]])
r, _, _ = sim(c)
a = alive(r)
check(a[:ON].sum() == 0 and a[ON + 2] > 0 and r["stats"]["spawned"] > 0,
      f"rate curve: the emitter's time starts at frame {ON}, the short start of the curve still emits ({r['stats']['spawned']})")
f = dict(still, rate=0.0, burst=50, fade_in=0.2, fade_out=0.0)
r1, _, _ = sim(dict(f, fade_in_max=0.08))
r0, _, _ = sim(dict(f, fade_in_max=0.0))
m1, m0 = np.nanmean(r1["alpha"][ON + 2]), np.nanmean(r0["alpha"][ON + 2])
check(m1 > 0.99 and m0 < 0.1, f"fade_in_max 0.08 s: full two frames after birth ({m1:.3f}); without it {m0:.3f}")
r9, _, _ = sim(dict(f, fade_in_max=10.0))
check(np.allclose(np.nan_to_num(r9["alpha"]), np.nan_to_num(r0["alpha"])), "a limit longer than the fade changes nothing")
rl, P0, _ = sim(dict(f, fade_in_max=0.0), look=True)
re_ = pt.relook(rl, pt.params("magic dust", dict(f, fade_in_max=0.08)))
check(re_ is not None and np.allclose(np.nan_to_num(re_["alpha"]), np.nan_to_num(r1["alpha"]), atol=1e-5),
      "relook with another fade_in_max: the same as a new simulation")
s = dict(still, path="strike", rate=0.0, burst=1, burst_at=0.0, strike_strokes=1)
Ps = pt.params("lightning strike", s)
ems = pt.Emitter("object mask", N, FPS, W, H, Ps, np.random.default_rng(1), a=(160, 90), masks=masks())
paths = pt.make_paths(Ps, ems, 3)
lead = int(np.ceil(Ps["strike_leader"] * FPS)) + 1
check(not any(paths[i] for i in range(ON - lead)) and any(paths[i] for i in range(ON, N)),
      "strike on an object emitter: it strikes with the first frame with a mask, not on the empty start")
print(f"{ok} checks passed")
