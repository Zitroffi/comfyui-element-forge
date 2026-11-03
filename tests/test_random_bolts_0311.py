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


N, FPS, W, H, ON = 48, 24.0, 320, 180, 10
BOX = (70, 110, 140, 180)


def masks(on=ON):
    m = np.zeros((N, H, W), np.float32)
    m[on:, BOX[0]:BOX[1], BOX[2]:BOX[3]] = 1.0
    return m


def paths(over, kind="object mask", on=ON, seed=3, a=(160, 90)):
    P = pt.params("lightning", dict(dict(path="random", radius=0.0, branches=0), **over))
    em = pt.Emitter(kind, N, FPS, W, H, P, np.random.default_rng(1), a=a, masks=masks(on) if kind != "point A" else None)
    return pt.make_paths(P, em, seed), P, em


def mains(out, P, em):
    w = P["width"] * min(W, H) / pt.REF
    return [[p for p in f if abs(p[1] - w) < 1e-6] for f in out]


one = dict(rand_life=0.5 / FPS)
check(pt.BASE["rand_rate"] > 0 and pt.BASE["rand_aim"] == "random" and pt.BASE["rand_life"] > 0, "path random: defaults in BASE")
live = open(os.path.join(PACK, "element_forge/app/live.py"), encoding="utf-8").read()
ejs = open(os.path.join(PACK, "web/efa/emitter.js"), encoding="utf-8").read()
check(all(f'"{k}"' in live for k in ("rand_rate", "rand_length", "rand_length_var", "rand_life", "rand_aim")),
      "the live preview sends the random bolts' values (live.py PANEL)")
check('["random", "Random bolts"' in ejs and re.search(r'key\("rand_rate", "Bolts per second"', ejs)
      and 'choiceRow(ctx, "rand_aim", "Aim", AIMS' in ejs, "the panel offers Random bolts with its rows and the aim (emitter.js)")
out, P, em = paths(dict(one, rand_rate=24.0))
m = mains(out, P, em)
check(all(len(m[i]) == 0 for i in range(ON)), "no bolt before the object's mask is there (first frame with a mask)")
n_b = sum(len(f) for f in m)
check(18 <= n_b <= 60, f"about rand_rate bolts per second: {n_b} in {(N - ON) / FPS:.2f} s at 24/s")
starts = np.array([p[0][0] for f in m for p in f])
inside = (starts[:, 0] >= BOX[2] - 1) & (starts[:, 0] <= BOX[3]) & (starts[:, 1] >= BOX[0] - 1) & (starts[:, 1] <= BOX[1])
check(inside.all(), "every bolt starts on the object's mask")
spread = np.ptp(starts, 0)
check(spread[0] > 15 and spread[1] > 15, f"from random places of the mask, not one point (spread {spread.round(1)})")
ang = np.array([np.arctan2(*(p[0][-1] - p[0][0])[::-1]) for f in m for p in f])
check(np.histogram(ang, 4, (-np.pi, np.pi))[0].min() >= 2, "in random directions (all four quarters)")
L = np.array([np.hypot(*(p[0][-1] - p[0][0])) for f in m for p in f])
ref = P["rand_length"] * min(W, H) / pt.REF
check(L.min() >= ref * (1 - P["rand_length_var"]) - 1e-6 and L.max() <= ref * (1 + P["rand_length_var"]) + 1e-6,
      f"lengths within rand_length ± rand_length_var ({L.min():.1f}..{L.max():.1f}, mean {ref:.1f})")
out, P, em = paths(dict(rand_rate=3.0, rand_life=0.2, reroll_frames=1))
m = mains(out, P, em)
born = next(i for i in range(N) if m[i])
first = m[born][0]
seq = [next((p for p in m[f] if np.allclose(p[0][0], first[0][0], atol=1e-6)), None) for f in range(born, min(N, born + 6))]
life_f = sum(s is not None for s in seq)
check(life_f == int(np.ceil(0.2 * FPS)), f"a bolt flashes for rand_life ({life_f} frames at 0.2 s)")
op = [float(s[2][0]) for s in seq if s is not None]
check(all(b < a for a, b in zip(op, op[1:])) and op[0] >= 0.7, f"and fades ({np.round(op, 2).tolist()})")
check(not np.allclose(seq[0][0], seq[1][0]), "a new shape every reroll_frames")
out, P, em = paths(dict(one, rand_rate=24.0, rand_aim="emitter", direction=90.0, spread=0.0))
d = np.array([p[0][-1] - p[0][0] for f in mains(out, P, em) for p in f])
check((d[:, 0] > 0).all() and (np.abs(d[:, 1]) < 1e-3).all(), "aim as the particles: direction 90, spread 0 -> all to the right")
out, P, em = paths(dict(one, rand_rate=24.0, rand_aim="outward", spread=0.0))
c = np.array([(BOX[2] + BOX[3]) / 2, (BOX[0] + BOX[1]) / 2])
rel = [np.hypot(*(p[0][-1] - c)) > np.hypot(*(p[0][0] - c)) for f in mains(out, P, em) for p in f]
check(np.mean(rel) > 0.95, f"aim outward: the bolts end farther from the object than they start ({np.mean(rel):.2f})")
out, P, em = paths(dict(one, rand_rate=24.0, rate_curve=[[0.0, 0.0], [0.5, 0.0], [0.5001, 1.0], [1.0, 1.0]]))
m = mains(out, P, em)
half = ON + int((N - 1 - ON) * 0.5)
check(sum(len(f) for f in m[:half]) == 0 and sum(len(f) for f in m[half + 1:]) > 0, "the rate curve shapes the bolts over the emitter's time")
a1, _, _ = paths(dict(rand_rate=10.0), seed=5)
a2, _, _ = paths(dict(rand_rate=10.0), seed=5)
a3, _, _ = paths(dict(rand_rate=10.0), seed=6)
same = lambda x, y: all(len(f) == len(g) and all(np.allclose(p[0], q[0]) for p, q in zip(f, g)) for f, g in zip(x, y))
check(same(a1, a2) and not same(a1, a3), "the same seed gives the same bolts, another seed others")
out, P, em = paths(dict(rand_rate=10.0, branches=3))
check(sum(len(f) for f in out) > sum(len(f) for f in mains(out, P, em)), "Branches add forks to the bolts")
out, P, em = paths(dict(one, rand_rate=12.0), kind="point A", a=(100, 60))
m = mains(out, P, em)
check(sum(len(f) for f in m[:ON]) > 0 and all(np.allclose(p[0][0], (100, 60)) for f in m for p in f),
      "point A: the bolts shoot from A (from the start, no mask needed)")
out, P, em = paths(dict(one, rand_rate=12.0, end=1.0))
check(all(len(f) == 0 for f in mains(out, P, em)[int(FPS) + 1:]), "no bolts after the emitter's end")
print(f"{ok} checks ok")
