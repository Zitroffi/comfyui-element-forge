import importlib
import io
import json
import os
import sys
import tempfile
import types

import cv2
import numpy as np
import torch

S = tempfile.mkdtemp(prefix="ef_test_")
fp = types.ModuleType("folder_paths"); fp.get_output_directory = lambda: os.path.join(S, "out"); fp.get_temp_directory = lambda: os.path.join(S, "out")
sys.modules["folder_paths"] = fp
comfy = types.ModuleType("comfy"); cu = types.ModuleType("comfy.utils")


class PB:
    def __init__(self, n): pass
    def update(self, n=1): pass
    def update_absolute(self, *a, **k): pass


cu.repeat_to_batch_size = lambda t, n: t.repeat((n + len(t) - 1) // len(t), *([1] * (t.dim() - 1)))[:n]
cu.ProgressBar = PB; comfy.utils = cu; sys.modules["comfy"] = comfy; sys.modules["comfy.utils"] = cu
mm = types.ModuleType("comfy.model_management"); mm.throw_exception_if_processing_interrupted = lambda: None
mm.get_torch_device = lambda: torch.device("cpu")
comfy.model_management = mm; sys.modules["comfy.model_management"] = mm
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))
pack = importlib.import_module(os.path.basename(PACK))
M = pack.NODE_CLASS_MAPPINGS
an = importlib.import_module(pack.__name__ + ".element_forge.app.app_nodes")

KEEP = os.environ.get("EF_TEST_KEEP_GOING") == "1"
ok, failed = 0, []


def check(cond, msg):
    global ok
    if not cond:
        if not KEEP:
            raise AssertionError(msg)
        failed.append(msg)
        print("FAIL", msg)
        return
    ok += 1
    print("ok  ", msg)


def section(fn):
    try:
        fn()
    except Exception as e:
        if not KEEP:
            raise
        failed.append(f"{fn.__name__}: {type(e).__name__}: {e}")
        print("FAIL", fn.__name__, "raised", type(e).__name__, str(e)[:120])
    return fn


def flicker(v):
    v = np.asarray(v, np.float64)
    return float((v.max() - v.min()) / max(v.mean(), 1e-9))


def wexr(path, a):
    import OpenImageIO as oiio
    spec = oiio.ImageSpec(a.shape[1], a.shape[0], a.shape[2], "half")
    o = oiio.ImageOutput.create(path); o.open(path, spec); o.write_image(np.ascontiguousarray(a, dtype=np.float32)); o.close()


def rexr(path):
    import OpenImageIO as oiio
    o = oiio.ImageInput.open(path); a = o.read_image(format="float"); o.close()
    return np.asarray(a)


def srgb_lin(v):
    v = np.asarray(v, np.float64)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


GREEN = np.array([40, 200, 60], np.float64)
RUN = os.path.join(S, "out", "element-forge", "rv_run")
os.makedirs(RUN, exist_ok=True)
for i in range(3):
    wexr(os.path.join(RUN, f"plate_{i + 1:05d}.exr"), np.broadcast_to(srgb_lin(GREEN / 255), (48, 64, 3)).astype(np.float32))
RUN_EL = os.path.join(S, "out", "element-forge", "rv_run_el")
os.makedirs(RUN_EL, exist_ok=True)
for i in range(3):
    wexr(os.path.join(RUN_EL, f"plate_{i + 1:05d}.exr"), np.full((48, 64, 3), 0.2, np.float32))
el1 = np.zeros((48, 64, 4), np.float32); el1[10:20, 20:30] = [2.0, 2.0, 2.0, 1.0]
wexr(os.path.join(RUN_EL, "element_00001.exr"), el1)


def decode_709(path):
    import av
    with av.open(path) as d:
        tag = d.streams.video[0].codec_context.colorspace
        f = next(d.decode(video=0))
        y = f.to_ndarray(format="yuv420p")
    h = y.shape[0] * 2 // 3
    Y, U, V = y[:h].mean(), y[h:h + h // 4].mean(), y[h + h // 4:].mean()
    kr, kb = 0.2126, 0.0722
    yy, cb, cr = (Y - 16) / 219, (U - 128) / 224, (V - 128) / 224
    r, b = yy + 2 * (1 - kr) * cr, yy + 2 * (1 - kb) * cb
    g = (yy - kr * r - kb * b) / (1 - kr - kb)
    return np.array([r, g, b]) * 255, tag


@section
def mask_track_empty_start():
    m = torch.zeros(6, 100, 100)
    for i in (2, 3, 5):
        m[i, 10:30, 60 + i:80 + i] = 1.0
    tr, rep = M["EFMaskTrack"]().track(m, "centroid", 1)
    sc, pts = np.array(tr["point_scale"]), np.array(tr["point_track_px"])
    check(np.abs(sc - 1).max() < 0.01, f"mask track: scale stays 1 with empty first frames (max {sc.max():.2f})")
    check(np.allclose(pts[0], pts[2]) and np.allclose(pts[1], pts[2]) and np.allclose(pts[4], pts[3]),
          f"mask track: empty start takes the first point {pts[2].tolist()}, a gap holds the last (frame 0: {pts[0].tolist()})")



@section
def finish_stack_bt709():
    an.EFFinishStack().stack(json.dumps([{"run_folder": "element-forge/rv_run"}]), "{}", "element-forge/rv_stack", False, 25.0, 2)
    rgb, tag = decode_709(os.path.join(S, "out", "element-forge", "rv_stack", "comp.mp4"))
    dev = float(np.abs(rgb - GREEN).max())
    check(dev < 2.0 and tag == 1, f"finish stack mp4: green decoded as BT.709 off by {dev:.1f} (8 bit), matrix tag {tag}")


def line_element(h=200, w=400, n=1):
    e = np.zeros((n, h, w, 4), np.float32)
    e[:, :, w // 2:w // 2 + 2] = 1.0
    return torch.from_numpy(e)


@section
def place_element_area():
    n = 8
    plate = torch.zeros(n, 80, 120, 3)
    tr = {"frames": n, "point_track_px": [[50 + 0.25 * i, 40.0] for i in range(n)], "point_scale": [1.0] * n}
    _, lay, _ = M["EFPlaceElement"]().place(plate, line_element(), {"reference_px": [200.0, 100.0]}, tr, 0.25, 0.0, 0.0, "add", 1.0, False)
    e = lay.numpy().sum((1, 2, 3))
    check(flicker(e) < 0.02 and abs(e.mean() - 2 * 200 * 0.25 ** 2 * 3) < 0.05 * e.mean(),
          f"place element 0.25x: line energy per frame constant (flicker {flicker(e):.3f})")


@section
def place_element_far_surface():
    n, h, w = 4, 80, 120
    plate = torch.zeros(n, h, w, 3)
    dep = np.zeros((n, h, w, 3), np.float32)
    dep[:, :, 70:90] = 0.8
    el = np.zeros((1, 100, 100, 4), np.float32)
    el[..., :3], el[..., 3] = 1.0, 1.0
    tr = {"frames": n, "point_track_px": [[60.0, 40.0]] * n, "point_scale": [1.0] * n}
    args = (plate, torch.from_numpy(el), {"reference_px": [50.0, 50.0]}, tr, 0.6, 0.0, 0.0, "add", 1.0, False)
    _, lay, _ = M["EFPlaceElement"]().place(*args, depth=torch.from_numpy(dep), depth_offset=-0.015, depth_softness=0.01)
    a = lay.numpy()[..., 0]
    check(a[:, 40, 50].min() > 0.9 and a[:, 40, 80].max() < 0.01,
          f"place element on the farthest surface: shows on the wall ({a[:, 40, 50].min():.2f}), hidden by the figure ({a[:, 40, 80].max():.2f})")
    tr2 = {**tr, "point_track_px": [[80.0, 40.0]] * n}
    _, lay2, _ = M["EFPlaceElement"]().place(plate, torch.from_numpy(el), {"reference_px": [50.0, 50.0]}, tr2, 0.6, 0.0, 0.0, "add", 1.0, False,
                                             depth=torch.from_numpy(dep), depth_offset=-0.015, depth_softness=0.01)
    b = lay2.numpy()[..., 0]
    check(b[:, 40, 80].max() < 0.01 and b[:, 40, 60].min() > 0.9,
          f"place element on a nearer object: unchanged, hidden on the object ({b[:, 40, 80].max():.2f}), shown over the wall ({b[:, 40, 60].min():.2f})")
    rng = np.random.default_rng(1)
    dep3 = np.zeros((n, h, w, 3), np.float32)
    dep3[:] = (0.06 + 0.04 * np.linspace(0, 1, h)[:, None] + rng.normal(0, 0.004, (h, w)))[None, ..., None]
    dep3[:, :8] = 0.03
    dep3[:, :, 70:90] = 0.8
    _, lay3, _ = M["EFPlaceElement"]().place(*args, depth=torch.from_numpy(dep3), depth_offset=-0.015, depth_softness=0.01)
    c3 = lay3.numpy()[..., 0]
    check(float(c3[:, 20:60, 35:65].mean()) > 0.9 and c3[:, 40, 80].max() < 0.01,
          f"place element on the back wall (not the farthest place, with a gradient): shows ({float(c3[:, 20:60, 35:65].mean()):.2f}), figure in front ({c3[:, 40, 80].max():.2f})")


@section
def place_between_area():
    n = 8
    plate = torch.zeros(n, 80, 120, 3)
    ta = {"frames": n, "point_track_px": [[10 + 0.25 * i, 40.0] for i in range(n)]}
    tb = {"frames": n, "point_track_px": [[110 + 0.25 * i, 40.0] for i in range(n)]}
    _, lay, _ = M["EFPlaceBetween"]().place(plate, line_element(), ta, tb, 0.0, 1.0, 0.5, 1.0, "add", 1.0, edge_feather=0.0)
    e = lay.numpy().sum((1, 2, 3))
    check(flicker(e) < 0.02, f"place between 0.25x: line energy per frame constant (flicker {flicker(e):.3f})")
    ang = np.radians(30)
    ta = {"frames": n, "point_track_px": [[20 + 0.25 * i, 15.0] for i in range(n)]}
    tb = {"frames": n, "point_track_px": [[20 + 0.25 * i + 100 * np.cos(ang), 15 + 100 * np.sin(ang)] for i in range(n)]}
    _, lay, _ = M["EFPlaceBetween"]().place(plate, line_element(), ta, tb, 0.0, 1.0, 0.5, 1.0, "add", 1.0, edge_feather=0.0)
    e = lay.numpy().sum((1, 2, 3))
    check(flicker(e) < 0.01, f"place between 0.25x, rotated: line energy per frame constant (flicker {flicker(e):.3f})")


@section
def place_layer_area():
    n = 8
    plate = torch.zeros(n, 80, 120, 3)
    tr = {"frames": n, "scale_roi_per_plate_px": 4.0, "roi_size": [400, 200], "crop_origin_plate_px": [[10 + 0.25 * i, 10.0] for i in range(n)]}
    _, lay, _ = M["EFPlaceLayer"]().place(plate, line_element(n=n)[..., :3].contiguous(), tr, 1.0)
    e = lay.numpy().sum((1, 2, 3))
    check(flicker(e) < 0.02, f"place layer 0.25x: line energy per frame constant (flicker {flicker(e):.3f})")


@section
def effect_layer_short_lines():
    n = 8
    g = torch.full((n, 64, 64, 3), 0.2); g[:, 20:40, 20:40, 0] = 0.9
    r = torch.full((n, 64, 64, 3), 0.2)
    lines = torch.zeros(1, 64, 64); lines[0, 30, 10:50] = 1
    out = M["EFEffectLayer"]().extract(g, r, False, 0.0, key="off", lines=lines, line_reach=20.0, line_window=2)
    e = out[0].sum((1, 2, 3)).numpy()
    check(e.min() > 0.99 * e.max() > 0, f"effect layer, one line frame: every frame keeps the layer ({np.round(e, 1).tolist()})")


@section
def place_layer_point_track():
    m = torch.zeros(3, 64, 64); m[:, 20:40, 20:40] = 1
    tr, _ = M["EFMaskTrack"]().track(m, "centroid", 1)
    try:
        M["EFPlaceLayer"]().place(torch.zeros(3, 64, 64, 3), torch.zeros(3, 32, 32, 3), tr, 1.0)
        err = None
    except Exception as e:
        err = e
    check(isinstance(err, ValueError) and "EF Track ROI" in str(err) and "EF Place Element" in str(err),
          f"place layer, point track: clear error ({type(err).__name__}: {str(err)[:60]})")


@section
def place_between_same_point():
    plate = torch.full((1, 90, 160, 3), 0.3)
    el = torch.zeros(1, 40, 80, 4); el[0, 0, 0] = torch.tensor([1.0, 0.5, 0.2, 1.0]); el[0, 15:25, 4:76] = 1.0
    t = {"frames": 1, "point_track_px": [[80.0, 45.0]]}
    comp, layer, alpha = M["EFPlaceBetween"]().place(plate, el, t, t, 0.05, 0.95, 0.5, 1.0, "over", 1.0, edge_feather=0.0)
    check(float(alpha.max()) == 0 and float(layer.abs().max()) == 0 and torch.allclose(comp, plate, atol=1e-5),
          f"place between, one point: empty layer (alpha cover {float((alpha > 0.5).float().mean()):.2f})")


@section
def finish_holds_element():
    an.EFFinishStack().stack(json.dumps([{"run_folder": "element-forge/rv_run_el", "settings": {"glow": {"exposure": -30}}}]), "{}",
                             "element-forge/rv_stack_el", True, 25.0, 2)
    c3 = rexr(os.path.join(S, "out", "element-forge", "rv_stack_el", "comp_00003.exr"))
    check(abs(c3[15, 25, 0] - 2.2) < 0.02, f"finish stack: element holds its last frame ({c3[15, 25, 0]:.2f})")


@section
def atlas_width():
    man = json.loads(an.EFPassPreview().build("element-forge/rv_run", 2048, 25.0, full_size=False)["result"][0])
    tw, th = man["tile_size"]
    check(tw * 4 <= 4096 and th * 2 <= 4096, f"pass preview: atlas {tw * 4}x{th * 2} within 4096")


@section
def short_hex():
    check(torch.allclose(an.hex_lin("#fff"), an.hex_lin("#ffffff")) and torch.allclose(an.hex_lin("f80"), an.hex_lin("#ff8800")),
          "hex_lin: short form #fff")


@section
def scale_zero():
    x = torch.rand(1, 8, 8, 4)
    y = an._shift_scale(x, 0.0, 0.0, 0.0)
    check(not torch.isnan(y).any() and torch.allclose(y, x), "shift/scale: scale 0 = unset (1, as in the app), no NaN")


class CountGlow(M["EFGlow"]):
    calls = 0

    def blur_xy(self, x, sx, sy):
        CountGlow.calls += 1
        return super().blur_xy(x, sx, sy)


@section
def glow_once():
    img = torch.zeros(2, 64, 96, 3); img[:, 30:34, 40:44] = torch.tensor([4.0, 2.0, 1.0])
    g = CountGlow()
    CountGlow.calls = 0
    g0 = g.glow(img, "linear", 0.0, 40.0, 2.0, 0.0, chromatic=0.0)[1]
    c0 = CountGlow.calls
    CountGlow.calls = 0
    g.glow(img, "linear", 0.0, 40.0, 2.0, 0.0, chromatic=0.5)
    c1 = CountGlow.calls
    gt = M["EFGlow"]().glow(img, "linear", 0.0, 40.0, 2.0, 0.0, chromatic=1e-12)[1]
    check(3 * c0 == c1, f"glow chromatic 0: one pass for all channels ({c0} blurs, per channel {c1})")
    check(torch.allclose(g0[..., :2], gt[..., :2], atol=1e-6), "glow chromatic 0: same result as per channel")


@section
def no_glow_without_element():
    class Probe:
        calls = 0

        def glow(self, *a, **k):
            Probe.calls += 1
            return M["EFGlow"]().glow(*a, **k)

    like = torch.full((2, 16, 16, 3), 0.2)
    t = an.layer_terms(an.merge_settings({}), None, None, None, like, Probe())
    check(Probe.calls == 0 and float(t["G"].abs().max()) == 0 and t["G"].shape == like.shape,
          f"finish without element: no glow pass on an empty layer ({Probe.calls} glow calls)")


if failed:
    print(f"{len(failed)} checks failed, {ok} passed")
    sys.exit(1)
print(f"{ok} checks passed")
