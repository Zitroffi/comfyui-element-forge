import importlib.util
import os

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


N, FPS, W, H, ON = 24, 24.0, 320, 180, 6
Y0, Y1, X0, X1 = 50, 130, 100, 220


def masks():
    m = np.zeros((N, H, W), np.float32)
    m[ON:, Y0:Y1, X0:X1] = 1.0
    return m


still = dict(speed=0.0, speed_var=0.0, gravity=0.0, wind=[0.0, 0.0], turbulence=0.0, drag=0.0, inherit=0.0, radius=0.0,
             life=3.0, life_var=0.0, rate=600.0, burst=0, flicker=0.0)


def births(over, kind="object edge + area"):
    P = pt.params("magic dust", dict(still, **over))
    em = pt.Emitter(kind, N, FPS, W, H, P, np.random.default_rng(1), a=(160, 90), masks=masks())
    rec = pt.simulate(P, em, seed=3)
    x, y = rec["x"], rec["y"]
    seen = ~np.isnan(x)
    f0 = np.argmax(seen, 0)
    k = seen.any(0)
    return x[f0[k], np.nonzero(k)[0]], y[f0[k], np.nonzero(k)[0]], em, rec


def on_edge(x, y):
    return (np.minimum.reduce([x - X0, X1 - 1 - x, y - Y0, Y1 - 1 - y]) < 1.5)


check("object edge + area" in pt.EMITTERS and "object edge + area" in pt.OBJECT_EMITTERS and pt.BASE["edge_share"] == 0.5,
      "the engine knows the emitter (EMITTERS, OBJECT_EMITTERS, edge_share 0.5)")
read = lambda p: open(os.path.join(PACK, p), encoding="utf-8").read()
check('"edge_share"' in read("element_forge/app/live.py"), "the live preview sends edge_share (live.py PANEL)")
ejs = read("web/efa/emitter.js")
check('["object edge + area", "Object outline + inside"' in ejs and 'key("edge_share", "On the outline"' in ejs
      and 'shapeOf(e, st) === "object edge + area" ? [numRow(ctx, EDGE_SHARE)]' in ejs,
      "the panel offers the shape and shows On the outline only with it (emitter.js)")
check(all('"object edge + area"' in read(p) for p in ("element_forge/app/compact_values.py", "element_forge/app_mode/nodes.py", "web/efa/ui/presets.js")),
      "the placement choice treats it as an object shape (compact_values, app nodes, presets.js)")
x, y, em, _ = births(dict(edge_share=1.0))
check(len(x) > 300 and on_edge(x, y).all(), f"edge_share 1: every particle on the outline ({len(x)})")
ga = pt._mask_points(masks()[ON], False)[0]
inside_edge = on_edge(ga[:, 0], ga[:, 1]).mean()
x, y, em, _ = births(dict(edge_share=0.0))
check(abs(on_edge(x, y).mean() - inside_edge) < 0.03,
      f"edge_share 0: inside the object ({on_edge(x, y).mean():.3f} on the outline, as the grid's outer rows {inside_edge:.3f})")
check(((x >= X0) & (x < X1) & (y >= Y0) & (y < Y1)).all(), "edge_share 0: all of them on the object")
x, y, em, _ = births(dict(edge_share=0.3))
share = on_edge(x, y).mean()
check(abs(share - (0.3 + 0.7 * inside_edge)) < 0.06, f"edge_share 0.3: about 30 % on the outline ({share:.2f})")
i = ON + 2
ce, _ = pt._mask_points(masks()[i], True)
check(em.n_edge[i] == len(ce) and np.allclose(em.pts[i][:em.n_edge[i]], ce), "the outline points are those of the emitter object contour")
check(len(em.pts[i]) - em.n_edge[i] == len(pt._mask_points(masks()[i], False)[0]), "the inside points are those of the emitter object mask")
x, y, em, rec = births(dict(edge_share=0.5))
alive = (~np.isnan(rec["x"])).sum(1)
check(alive[:ON].sum() == 0 and alive[ON] > 0 and abs(em.first_on(0.0) - ON / FPS) < 1e-9, "it starts with the first frame with a mask")
P = pt.params("magic dust", dict(still, edge_share=0.0, direction_mode="outward", spread=0.0, speed=200.0))
em = pt.Emitter("object edge + area", N, FPS, W, H, P, np.random.default_rng(1), a=(160, 90), masks=masks())
rec = pt.simulate(P, em, seed=3)
seen = ~np.isnan(rec["x"])
k = np.nonzero(seen[ON] & seen[ON + 3])[0]
c = np.array([(X0 + X1 - 1) / 2, (Y0 + Y1 - 1) / 2])
r0 = np.hypot(rec["x"][ON, k] - c[0], rec["y"][ON, k] - c[1])
r1 = np.hypot(rec["x"][ON + 3, k] - c[0], rec["y"][ON + 3, k] - c[1])
check(len(k) > 20 and np.mean(r1 > r0) > 0.9, f"outward: the inside's particles fly off the object too ({np.mean(r1 > r0):.2f})")
P = pt.params("lightning", dict(path="random", rand_rate=20.0, rand_life=0.5 / FPS, radius=0.0, branches=0, edge_share=1.0))
em = pt.Emitter("object edge + area", N, FPS, W, H, P, np.random.default_rng(1), a=(160, 90), masks=masks())
out = pt.make_paths(P, em, 3)
s = np.array([p[0][0] for f in out for p in f])
check(len(s) > 3 and on_edge(s[:, 0], s[:, 1]).all(), "random bolts shoot from it too (edge_share 1: from the outline)")
print(f"{ok} checks ok")
