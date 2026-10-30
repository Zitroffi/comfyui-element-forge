import ast
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_func(fname, name, extra):
    src = open(os.path.join(HERE, fname), encoding="utf-8").read()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == name)
    g = dict(extra)
    exec(compile(ast.Module([node], []), fname, "exec"), g)
    return g[name]


pick_object = load_func("element_forge/tracking/follow_crop.py", "pick_object", {"np": np, "cv2": cv2})


def frame(size):
    m = np.zeros((200, 200), bool)
    m[50:50 + size, 50:50 + size] = True
    return m


for which in ("all", "largest", "nearest"):
    for seq in ([70, 6, 70], [6, 70, 6]):
        out = pick_object([frame(s) for s in seq], which)
        assert len(out) == 3 and all(o.shape == (200, 200) for o in out), (which, seq)
        assert out[1].sum() == frame(seq[1]).sum(), (which, seq)
print("follow_crop small bits: ok")

src = open(os.path.join(HERE, "element_forge/generation/elements.py"), encoding="utf-8").read()
assert "start_frame %= n" in src
for n, start, frames, want in [(5, 0, 0, 5), (5, 3, 0, 2), (5, 5, 0, 5), (5, 7, 0, 3), (5, 7, 8, 8), (5, 12, 4, 4)]:
    s = start % n
    idx = np.arange(s, s + (frames or n - s)) % n
    assert len(idx) == want, (n, start, frames, len(idx))
print("load_element start_frame: ok")


src = open(os.path.join(HERE, "element_forge/tracking/track.py"), encoding="utf-8").read()
assert "np.clip(rgba, 0, 1, out=rgba)" in src
rng = np.random.default_rng(0)
rgba_out = [rng.normal(0.5, 0.6, (8, 6, 4)).astype(np.float32) for _ in range(5)]
old = np.clip(np.stack(rgba_out), 0, 1)
rgba = np.stack(rgba_out); np.clip(rgba, 0, 1, out=rgba)
assert np.array_equal(old, rgba) and rgba.dtype == old.dtype
print("effect_layer stack/clip: ok")
src = open(os.path.join(HERE, "element_forge/bonsai/bonsai.py"), encoding="utf-8").read()
ast.parse(src)
assert "Windows only" not in src and "the release for this system" in src and "LIB_NAMES" in src
print("bonsai message: ok")
print("ALL OK")
