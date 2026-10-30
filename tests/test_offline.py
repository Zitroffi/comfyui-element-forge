import importlib
import os
import sys
import tempfile
import types

S = tempfile.mkdtemp(prefix="ef_test_")
fp = types.ModuleType("folder_paths"); fp.get_output_directory = lambda: os.path.join(S, "out"); fp.get_temp_directory = lambda: os.path.join(S, "out")
fp.models_dir = os.path.join(S, "models"); fp.get_filename_list = lambda folder: []
sys.modules["folder_paths"] = fp
comfy = types.ModuleType("comfy"); cu = types.ModuleType("comfy.utils")
class PB:
    def __init__(self, n): pass
    def update(self, n=1): pass
    def update_absolute(self, *a, **k): pass
cu.repeat_to_batch_size = lambda t, n: t.repeat((n + len(t) - 1) // len(t), *([1] * (t.dim() - 1)))[:n]
cu.ProgressBar = PB; comfy.utils = cu; sys.modules["comfy"] = comfy; sys.modules["comfy.utils"] = cu
mm = types.ModuleType("comfy.model_management"); mm.throw_exception_if_processing_interrupted = lambda: None
comfy.model_management = mm; sys.modules["comfy.model_management"] = mm
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))
import torch
pack = importlib.import_module(os.path.basename(PACK))
M = pack.NODE_CLASS_MAPPINGS
print(len(M), "nodes; display names", len(pack.NODE_DISPLAY_NAME_MAPPINGS))
for k, c in M.items():
    c.INPUT_TYPES(); assert hasattr(c, c.FUNCTION), k
torch.manual_seed(0)
img = torch.rand(3, 32, 32, 3) ** 3
rgba, color, alpha = M["EFUnmult"]().unmult(img, "black", 0.0, 1.0)
lin = lambda x: torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
err = (lin(color) * alpha[..., None] - lin(img)).abs().max().item()
old = (img / img.amax(-1, keepdim=True).clamp(min=1e-6)); old_err = (lin(old) * img.amax(-1, keepdim=True) - lin(img)).abs().max().item()
print("unmult linear round trip max err %.2e (old sRGB unmult %.3f)" % (err, old_err))
assert err < 1e-4
nd = M["EFUnmult"]().run(image=img, background="black", black_point=0.0, alpha_gamma=1.0)
assert torch.equal(nd["result"][0], rgba) and nd["ui"]["edge"][0]["frames"] == 3 and set(nd["ui"]["edge"][0]["sides"]) == {"top", "bottom", "left", "right"}
name = M["EFSaveElement"]().save(rgba, "test_el", 25.0, True)["result"][0]
r2, a2, fps, h2 = M["EFLoadElement"]().load(name, 0, 0)
print("save/load max diff %.2e, fps %s, frames %d" % ((r2 - rgba).abs().max().item(), fps, r2.shape[0]))
assert (r2 - rgba).abs().max().item() < 2e-5
assert (h2 - lin(r2[..., :3]) * r2[..., 3:4]).abs().max().item() < 1e-5
r3, _, _, _ = M["EFLoadElement"]().load(name, 7, 2)
print("loop frames", r3.shape[0])
print("load list", M["EFLoadElement"].INPUT_TYPES()["required"]["element"][0])
p = os.path.join(S, "out", "element-forge", "elements", "test_el", "00001.png")
b = bytearray(open(p, "rb").read()); b[-20] ^= 1; open(p, "wb").write(b)
try:
    M["EFLoadElement"]().load(name, 0, 0); print("tamper NOT detected")
except ValueError as e:
    print("tamper detected:", e)
print("all offline checks passed")
import numpy as np
el = torch.ones(2, 90, 160, 4)
plate = torch.zeros(2, 400, 600, 3)
tr_a = {"frames": 2, "point_track_px": [[100, 200], [100, 200]]}
tr_b = {"frames": 2, "point_track_px": [[500, 200], [500, 220]]}
comp, layer, al = M["EFPlaceBetween"]().place(plate, el, tr_a, tr_b, 0.05, 0.95, 0.5, 1.0, "add", 1.0, None, 0.08)
row = al[0, 200].numpy()
assert al.max() > 0.99 and row[max(int(np.nonzero(row)[0][0]), 0)] < 0.2, "edge feather missing"
print("place between edge feather ok, alpha max %.2f, first nonzero alpha in row %.3f" % (al.max(), row[np.nonzero(row)[0][0]]))
print("all offline checks passed (incl. place between)")
el = torch.zeros(1, 40, 40, 4)
el[..., 3] = 0.3
anc = {"reference_px": [20.0, 20.0]}
tr = {"frames": 1, "point_track_px": [[50, 50]]}
plate = torch.zeros(1, 100, 100, 3)
_, layer, al = M["EFPlaceElement"]().place(plate, el, anc, tr, 1.0, 0.0, 0.0, "over", 1.0, False, color="#808080", density=3.0)
expect_a = 1 - 0.7 ** 3
assert abs(al[0, 50, 50].item() - expect_a) < 1e-3, al[0, 50, 50].item()
grey_lin = ((128 / 255 + 0.055) / 1.055) ** 2.4
assert abs(layer[0, 50, 50, 0].item() - grey_lin * expect_a) < 2e-3, layer[0, 50, 50, 0].item()
print("place element colour + density ok, alpha %.3f" % al[0, 50, 50].item())
el = torch.tensor([[[[0.8, 0.3, 0.1, 0.5]]]])
bgi = torch.full((1, 1, 1, 3), 0.5)
lin = lambda x: torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
enc = lambda x: torch.where(x <= 0.0031308, x * 12.92, 1.055 * x.clamp(min=0) ** (1 / 2.4) - 0.055)
for mode, ref in (("over", lin(el[..., :3]) * 0.5 + lin(bgi) * 0.5), ("add", lin(el[..., :3]) * 0.5 + lin(bgi))):
    got = M["EFCompPreview"]().comp(el, mode, bgi)[0]
    assert (got - enc(ref.clamp(0, 1))).abs().max().item() < 1e-5, (mode, got, enc(ref))
print("comp preview linear blend ok")
lin = lambda x: torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
enc = lambda x: torch.where(x <= 0.0031308, x * 12.92, 1.055 * x.clamp(min=0) ** (1 / 2.4) - 0.055)
torch.manual_seed(1)
c_true = torch.rand(2, 16, 16, 3) * 0.8 + 0.1
a_true = torch.rand(2, 16, 16)
src_black = enc(c_true * a_true[..., None])
src_white = enc(c_true * a_true[..., None] + (1 - a_true[..., None]))
for bg, src in (("black", src_black), ("white", src_white)):
    rgba = M["EFUnmult"]().unmult(src, bg, 0.0, 1.0, matte=a_true)[0]
    back = lin(rgba[..., :3]) * rgba[..., 3:] + (0 if bg == "black" else (1 - rgba[..., 3:]))
    err = (back - lin(src)).abs().max().item()
    assert err < 1e-4, (bg, err)
print("unmult with matte ok (black and white)")
h = w = 96
plate = torch.full((1, h, w, 3), 0.05)
depth = torch.full((1, h, w, 3), 0.5)
el = torch.zeros(1, h, w, 3)
el[0, 46:50, 46:50] = 4.0
tr = {"frames": 1, "point_track_px": [[48.0, 48.0]]}
DL = M["EFDepthLight"]()
args = (plate, el, depth, 50.0, 2.0, 65.0, 0.15, 0.25, True, 0.8, 1.0)
comp, lt, nrm = DL.light(*args, track=tr, light_offset=0.05)
c, edge = lt[0, 48, 48, 1].item(), lt[0, 48, 2, 1].item()
assert c > edge > 0, (c, edge)
lin_plate = ((0.05 + 0.055) / 1.055) ** 2.4
assert (lt.max().item() - lin_plate * 0.8) < 1e-4, lt.max().item()
_, lt_t, _ = DL.light(*args, track=tr, light_offset=0.05, color="#ff8000")
px = lt_t[0, 48, 30]
assert px[0] > px[1] > px[2], px
_, lt0, _ = DL.light(plate, torch.zeros_like(el), depth, *args[3:], track=tr)
assert lt0.abs().max().item() == 0
print("depth light ok: centre %.4f edge %.4f" % (c, edge))
src = torch.zeros(1, 256, 256, 3)
src[0, 126:130, 126:130] = 1.0
G = M["EFGlow"]()
g = G.glow(src, "linear", 1.0, 120.0, 2.0, 0.0)[1]
ratio = g.sum().item() / (src.sum().item() * 2)
assert abs(ratio - 1) < 0.05, ratio
assert g[0, 128, 128, 0] > g[0, 128, 150, 0] > g[0, 128, 200, 0] > 0
dim = G.glow(src * 0.2, "linear", 0.0, 120.0, 2.0, 0.5)[1]
assert dim.abs().max().item() == 0
gt = G.glow(src, "linear", 0.0, 120.0, 2.0, 0.0, tint="#ff8000")[1][0, 128, 140]
assert gt[0] > gt[1] > gt[2], gt
g0 = G.glow(src, "linear", 0.0, 120.0, 2.0, 0.0)[1]
gc = G.glow(src, "linear", 0.0, 120.0, 2.0, 0.0, core=8.0)[1]
assert gc[0, 128, 128, 0] < 0.5 * g0[0, 128, 128, 0] and abs(gc.sum().item() / g0.sum().item() - 1) < 0.05
assert g0[0, 128, 128 + 55, 0] > 0.3 * g0[0, 128, 128 + 25, 0] * (25 / 55) ** 2
print("glow ok: energy ratio %.3f" % ratio)
el = torch.zeros(1, 40, 40, 4)
el[0, 5:35, 5:35] = torch.tensor([1.0, 0.5, 0.2, 1.0])
_, _, anc, _, _ = M["EFAnchor"]().anchor(el, 0.5, 0.3, "off", 1, 0, 0)
tr = {"frames": 1, "point_track_px": [[50.0, 50.0]]}
plate = torch.zeros(1, 100, 100, 3)
dep = torch.full((1, 100, 100, 3), 0.5)
dep[0, :, :45] = 0.9
for off, left_vis in ((0.05, False), (0.6, True)):
    _, layer, al = M["EFPlaceElement"]().place(plate, el, anc, tr, 1.0, 0.0, 0.0, "add", 1.0, False, depth=dep, depth_offset=off, depth_softness=0.01)
    assert (al[0, 40, 40].item() > 0.5) == left_vis, (off, al[0, 40, 40].item())
    assert al[0, 40, 55].item() > 0.5, (off, "element must stay visible at its own depth")
plate_e = torch.full((1, 100, 100, 3), 0.1); plate_e[0, :, :48] = 0.8
_, _, al_e = M["EFPlaceElement"]().place(plate_e, el, anc, tr, 1.0, 0.0, 0.0, "add", 1.0, False, depth=dep, depth_offset=0.05, depth_softness=0.01)
assert al_e[0, 40, 46].item() < 0.2 and al_e[0, 40, 50].item() > 0.8, (al_e[0, 40, 44:52])
print("place element depth holdout ok (snaps to the plate edge)")

h = w = 96
plate = torch.full((1, h, w, 3), 0.05)
depth = torch.full((1, h, w, 3), 0.5)
el = torch.zeros(1, h, w, 3)
el[0, 46:50, 46:50] = 4.0
DL = M["EFDepthLight"]()
near = DL.light(plate, el, depth, 50.0, 2.0, 65.0, 0.15, 0.25, False, 100.0, 1.0, element_depth=torch.full((1, h, w), 0.9))[1]
far = DL.light(plate, el, depth, 50.0, 2.0, 65.0, 0.15, 0.25, False, 100.0, 1.0, element_depth=torch.full((1, h, w), 0.0))[1]
assert near[0, 48, 48, 1] > 1e-4 and far[0, 48, 48, 1] < near[0, 48, 48, 1], (near[0, 48, 48, 1], far[0, 48, 48, 1])
print("depth light element_depth ok")
dep = torch.zeros(2, 64, 48, 3)
dep[:, 30:50, 10:30] = torch.linspace(0.4, 0.8, 20)[None, None, :, None]
mk = torch.zeros(2, 64, 48)
mk[:, 30:50, 10:30] = 1.0
ctrl, att = importlib.import_module(os.path.basename(PACK) + ".guide").object_shape(dep.numpy().mean(-1), mk.numpy(), 0.1, 0.0, 0.35)
ctrl, att = np.stack(ctrl), np.stack(att)
assert np.abs(ctrl[0, 5, 5]).max() == 0 and ctrl[0, 40, 12, 0] >= 0.35 - 1e-4 and ctrl[0, 40, 28, 0] > 0.9, (ctrl[0, 40, 12], ctrl[0, 40, 28])
assert att[0, 40, 7] == 1 and att[0, 40, 3] == 0, (att[0, 40, 7], att[0, 40, 3])
rgba = torch.zeros(1, 20, 20, 4)
rgba[0, 5:15, 5:15] = torch.tensor([1.0, 0.5, 0.0, 0.5])
trk = {"frames": 1, "crop_origin_plate_px": [[10.0, 10.0]], "scale_roi_per_plate_px": 1.0}
_, lay, _ = M["EFPlaceLayer"]().place(torch.zeros(1, 40, 40, 3), rgba, trk, 1.0, layer_is="rgba (EF Unmult)")
half = ((0.5 + 0.055) / 1.055) ** 2.4
assert abs(lay[0, 20, 20, 0].item() - 0.5) < 1e-4 and abs(lay[0, 20, 20, 1].item() - half * 0.5) < 1e-4, lay[0, 20, 20]
print("guide from mask + place layer rgba ok")

el = torch.zeros(2, 40, 30, 4)
el[:, 10:30, 8:22] = torch.tensor([1.0, 0.5, 0.1, 0.3])
el[:, 16:24, 12:18] = torch.tensor([1.0, 1.0, 1.0, 1.0])
sdr_lin = lin(el[..., :3]) * el[..., 3:4]
hd = torch.nn.functional.interpolate(sdr_lin.permute(0, 3, 1, 2), size=(20, 15), mode="area").permute(0, 2, 3, 1).clone()
hd[:, 8:12, 6:9] = torch.tensor([6.0, 3.0, 1.0])
hm, rep = M["EFHDRMerge"]().merge(el, hd, "linear Rec.709", 0.85, 16.0, 0.5)
print("hdr merge:", rep)
assert hm[0, 20, 15].max() > 2 and hm[0, 20, 15, 0] > hm[0, 20, 15, 2] * 1.5, hm[0, 20, 15]
assert (hm[0, 11, 9] - sdr_lin[0, 11, 9]).abs().max() < 1e-5, (hm[0, 11, 9], sdr_lin[0, 11, 9])
assert hm[0, 2, 2].abs().max() == 0
grey = torch.ones(1, 4, 4, 3)
g, _ = M["EFHDRMerge"]().merge(torch.ones(1, 8, 8, 4), grey * 3, "ACEScg (LTX HDR)", 0.85, 16.0, 1.0)
assert abs(g[0, 4, 4].mean().item() - 3.0) < 0.01 and (g[0, 4, 4].max() - g[0, 4, 4].min()) < 0.01, g[0, 4, 4]
rgba_el = torch.cat([el[..., :3], el[..., 3:4]], -1)
nm = M["EFSaveElement"]().save(rgba_el, "test_hdr", 24.0, True, hdr=hm)["result"][0]
_, _, _, hl = M["EFLoadElement"]().load(nm, 0, 0)
assert hl.max() > 2 and ((hl - hm).abs() / (hm.abs() + 1e-2)).max() < 2e-3, ((hl - hm).abs().max())
rgb_a, _, anc, _, ha = M["EFAnchor"]().anchor(rgba_el, 0.9, 0.3, "off", 1, 0, 0, hdr=hl)
assert (ha - hl).abs().max() < 1e-5
pl = torch.zeros(2, 80, 80, 3)
trk = {"frames": 2, "point_track_px": [[40.0, 60.0]] * 2, "point_scale": [1.0] * 2}
_, lay_sdr, al_sdr = M["EFPlaceElement"]().place(pl, rgb_a, anc, trk, 1.0, 0.0, 0.0, "add", 1.0, False)
_, lay_hdr, al_hdr = M["EFPlaceElement"]().place(pl, rgb_a, anc, trk, 1.0, 0.0, 0.0, "add", 1.0, False, element_hdr=ha)
assert lay_sdr.max() <= 1.0 + 1e-5 and lay_hdr.max() > 2 and (al_sdr - al_hdr).abs().max() == 0, (lay_sdr.max(), lay_hdr.max())
_, lay_half, _ = M["EFPlaceElement"]().place(pl, rgb_a, anc, trk, 1.0, 0.0, 0.0, "add", 1.0, False, density=0.5, element_hdr=ha)
assert lay_half.sum() < lay_hdr.sum() and abs(lay_half.max() - lay_hdr.max()) < 1e-4
print("hdr merge + element library HDR + anchor/place passthrough ok")
hot_el, hot_hdr = torch.ones(1, 40, 40, 4), torch.full((1, 40, 40, 3), 10.0)
anc_c, trk_c = {"reference_px": [20.0, 20.0]}, {"frames": 1, "point_track_px": [[40.0, 40.0]], "point_scale": [1.0]}
_, lh, _ = M["EFPlaceElement"]().place(torch.zeros(1, 80, 80, 3), hot_el, anc_c, trk_c, 1.0, 0.0, 0.0, "add", 1.0, False,
                                         edge_feather=0.25, element_hdr=hot_hdr)
_, lo, _ = M["EFPlaceElement"]().place(torch.zeros(1, 80, 80, 3), hot_el, anc_c, trk_c, 1.0, 0.0, 0.0, "over", 1.0, False,
                                         edge_feather=0.25, element_hdr=hot_hdr)
assert lh[0, 40, 40, 0] > 9.9 and lh[0, 40, 23, 0] < 1.0 and lh[0, 40, 27, 0] > 1.0, lh[0, 40, 18:32, 0]
assert lo[0, 40, 23, 0] > 2.0, lo[0, 40, 18:32, 0]
print("place element hdr edge feather ok")
full = torch.ones(1, 40, 40, 3) * 0.5
trk = {"frames": 1, "crop_origin_plate_px": [[20.0, 20.0]], "scale_roi_per_plate_px": 1.0}
_, hard, _ = M["EFPlaceLayer"]().place(torch.zeros(1, 80, 80, 3), full, trk, 1.0)
_, soft, _ = M["EFPlaceLayer"]().place(torch.zeros(1, 80, 80, 3), full, trk, 1.0, edge_feather=0.2)
assert abs(hard[0, 20, 40, 0].item() - 0.5) < 1e-4 and soft[0, 20, 40, 0] < 0.01 and abs(soft[0, 40, 40, 0].item() - 0.5) < 1e-4, (hard[0, 20, 40], soft[0, 20, 40])
print("place layer edge feather ok")
h = w = 64
plate = torch.full((1, h, w, 3), 0.2)
el = torch.zeros(1, h, w, 3)
el[0, 30:34, 30:34] = 2.0
flat = torch.full((1, h, w, 3), 0.5)
nm = M["EFDepthLight"]().light(plate, el, flat, 1.0, 2.0, 65.0, 0.15, 0.25, False, 1.0, 1.0, surface_detail=0.0)[2]
assert abs(nm[0, 32, 32, 2].item() - 1.0) < 1e-3 and abs(nm[0, 32, 32, 0].item() - 0.5) < 1e-3, nm[0, 32, 32]
ramp = torch.linspace(1.0, 0.0, h)[None, :, None, None].expand(1, h, w, 3).contiguous()
nm2 = M["EFDepthLight"]().light(plate, el, ramp, 1.0, 2.0, 65.0, 0.15, 0.25, False, 1.0, 1.0, surface_detail=0.0)[2]
assert nm2[0, 32, 32, 1] < 0.5 < nm2[0, 32, 32, 2], nm2[0, 32, 32]
print("normal pass convention ok")
import cv2
rng = np.random.default_rng(1)
tex = cv2.GaussianBlur(rng.random((96, 160)).astype(np.float32), (0, 0), 2)
tex = (tex - tex.min()) / (tex.max() - tex.min())
nf = 9
pl_d = np.stack([np.repeat(tex[:, 2 * i:2 * i + 96][..., None], 3, -1) for i in range(nf)]).astype(np.float32)
truth = pl_d * 0.5
pump = (1 + 0.2 * np.array([1, -1] * 5)[:nf]).astype(np.float32)
on_grid = (np.arange(96) % 14 == 0)
grid = 0.03 * (on_grid[None, :] | on_grid[:, None]).astype(np.float32)
pas = truth * pump[:, None, None, None] + grid[None, ..., None]
DF = M["EFDeflicker"]()
c = DF.deflicker(torch.from_numpy(pas), torch.from_numpy(pl_d), 3, 1.0, 4, 0, 0.001)[0].numpy()
m_b, m_a = pas.reshape(nf, -1).mean(1), c.reshape(nf, -1).mean(1)
assert np.std(m_a) / m_a.mean() < 0.3 * np.std(m_b) / m_b.mean(), (np.std(m_a) / m_a.mean(), np.std(m_b) / m_b.mean())
inner = (slice(2, -2), slice(12, -12), slice(12, -12))
corr = np.corrcoef(c[inner].ravel(), truth[inner].ravel())[0, 1]
assert corr > 0.95, corr
ce, comp_sw = DF.deflicker(torch.from_numpy(pas), torch.from_numpy(pl_d), 0, 1.0, 0, 6, 0.0001,
                           comp=torch.from_numpy(pack.linear_to_srgb(torch.from_numpy(pas + 0.1)).numpy()))
ce = ce.numpy()
line, nxt = ce[:, 14:84, 28, 0].mean(), ce[:, 14:84, 30, 0].mean()
line0, nxt0 = pas[:, 14:84, 28, 0].mean(), pas[:, 14:84, 30, 0].mean()
assert abs(line - nxt) < 0.3 * abs(line0 - nxt0), (line - nxt, line0 - nxt0)
assert np.abs(comp_sw.numpy() - pack.linear_to_srgb(torch.from_numpy(ce + 0.1)).numpy()).max() < 2e-3
print("deflicker ok: level spread %.3f -> %.3f, structure corr %.3f, grid step %.4f -> %.4f"
      % (np.std(m_b) / m_b.mean(), np.std(m_a) / m_a.mean(), corr, line0 - nxt0, line - nxt))
el_rgba = torch.zeros(2, 32, 64, 4)
el_rgba[:, 12:20, 8:56, :3] = 1.0
el_rgba[:, 12:20, 8:56, 3] = 1.0
el_hdr = el_rgba[..., :3].clone() * 3.0
plate_b = torch.full((2, 96, 128, 3), 0.2)
tra = {"frames": 2, "point_track_px": [[20.0, 48.0]] * 2}
trb = {"frames": 2, "point_track_px": [[108.0, 48.0]] * 2}
PB = M["EFPlaceBetween"]()
_, lay_s, al_s = PB.place(plate_b, el_rgba, tra, trb, 0.125, 0.875, 0.5, 1.0, "add", 1.0, edge_feather=0.0)
_, lay_h, al_h = PB.place(plate_b, el_rgba, tra, trb, 0.125, 0.875, 0.5, 1.0, "add", 1.0, edge_feather=0.0, element_hdr=el_hdr)
assert lay_s.max().item() <= 1.0001 and abs(lay_h.max().item() - 3.0) < 0.05, (lay_s.max(), lay_h.max())
assert torch.allclose(al_s, al_h)
print("place between HDR ok")
img = torch.full((1, 64, 64, 4), 0.1)
d = M["EFDither"]().dither(img, 1.5, 3)[0]
diff = (d[..., :3] - 0.1) * 255
assert abs(diff.mean().item()) < 0.05 and 0.3 < diff.std().item() < 0.9 and diff.abs().max().item() <= 1.5 + 1e-4, (diff.mean(), diff.std())
assert torch.equal(d[..., 3], img[..., 3]) and torch.equal(M["EFDither"]().dither(img, 0.0)[0], img)
print("dither ok: std %.2f LSB" % diff.std().item())
base_l = torch.full((3, 8, 8, 3), 2.5)
lay_l = torch.zeros((1, 4, 4, 3)); lay_l[0, :, :, 1] = 0.5
sl = M["EFAddLayers"]().add(base_l, lay_l, 2.0)[0]
assert sl.shape == (3, 8, 8, 3) and abs(sl[..., 0].max().item() - 2.5) < 1e-6 and abs(sl[2, ..., 1].mean().item() - 3.5) < 1e-5, sl.shape
print("add layers ok")
nfr = 4
nfr, fh, fw = 9, 240, 320
pl_f = torch.full((nfr, fh, fw, 3), 0.2)
mk_f = torch.zeros(nfr, fh, fw)
for i in range(nfr):
    s2 = 10 + 2 * i
    cx, cy = 40 + 30 * i, 60 + 12 * i
    mk_f[i, cy - s2:cy + s2, cx - s2:cx + s2] = 1
FC = M["EFFollowCrop"]()
for size in ("fixed", "follow object", "fit object (fixed)"):
    roi_f, rm_f, tr_f, _, rep_f = FC.crop(pl_f, mk_f, "largest", nfr, 96, 72, 128, 96, size, 1.6, 1.0, True, 0)
    assert roi_f.shape == (nfr, 96, 128, 3) and rm_f.shape == (nfr, 96, 128), roi_f.shape
    for i in range(nfr):
        ox, oy = tr_f["crop_origin_plate_px"][i]
        cw_f = 128 / tr_f["scale_per_frame"][i]
        assert -2e-3 <= ox and ox + cw_f <= fw + 2e-3 and -2e-3 <= oy and oy + cw_f * 72 / 96 <= fh + 2e-3, (size, i, ox, oy, cw_f)
    assert float(rm_f.sum((1, 2)).min()) > 0, "object visible in every ROI"
    lay_f = torch.from_numpy(np.ascontiguousarray(rm_f.numpy()[..., None].repeat(3, -1)))
    _, lp_f, _ = M["EFPlaceLayer"]().place(pl_f, lay_f, tr_f, 1.0)
    inter = float(((lp_f.amax(-1) > 0.5) & (mk_f > 0.5)).sum() / ((lp_f.amax(-1) > 0.5) | (mk_f > 0.5)).sum())
    assert inter > 0.85, (size, inter)
    if size == "fit object (fixed)":
        assert len(set(tr_f["scale_per_frame"])) == 1, tr_f["scale_per_frame"]
        assert 128 / tr_f["scale_per_frame"][0] >= min(2 * (10 + 2 * (nfr - 1)) * 1.6, fw) - 1, tr_f["scale_per_frame"][0]
print("follow crop ok:", rep_f)
import json as _json
import OpenImageIO as _oiio
run_d = os.path.join(S, "out", "element-forge", "t_run")
os.makedirs(run_d, exist_ok=True)
def _wexr(path, a):
    spec = _oiio.ImageSpec(a.shape[1], a.shape[0], a.shape[2], "half")
    o = _oiio.ImageOutput.create(path); o.open(path, spec); o.write_image(np.ascontiguousarray(a, dtype=np.float32)); o.close()
for i in range(3):
    _wexr(os.path.join(run_d, f"plate_{i + 1:05d}.exr"), np.full((48, 64, 3), 0.2, np.float32))
    _wexr(os.path.join(run_d, f"light_{i + 1:05d}.exr"), np.full((48, 64, 3), 0.05, np.float32))
    el_a = np.zeros((48, 64, 4), np.float32); el_a[10:20, 20:30] = [2.0, 2.0, 2.0, 1.0]
    _wexr(os.path.join(run_d, f"element_{i + 1:05d}.exr"), el_a)
man_s = M["EFPassPreview"]().build("element-forge/t_run", 64, 25.0)["result"][0]
man_a = _json.loads(man_s)
assert man_a["frames"] == 3 and os.path.isfile(os.path.join(run_d, "app_preview", "atlas.mp4")), man_a
for mode, inside in (("add", 2.25), ("over", 2.0)):
    M["EFFinishStack"]().stack(_json.dumps([{"run_folder": "element-forge/t_run", "settings": {"element": {"mode": mode}, "glow": {"exposure": -30}}}]),
                               "{}", f"element-forge/t_fin_{mode}", True, 25.0, 2)
    fin_d = os.path.join(S, "out", "element-forge", f"t_fin_{mode}")
    inp_f = _oiio.ImageInput.open(os.path.join(fin_d, "comp_00002.exr")); comp_f = inp_f.read_image(format="float"); inp_f.close()
    assert abs(comp_f[15, 25, 0] - inside) < 0.01 and abs(comp_f[40, 5, 0] - 0.25) < 0.01, (mode, comp_f[15, 25], comp_f[40, 5])
    assert os.path.isfile(os.path.join(fin_d, "comp.mp4"))
print("app nodes ok: preview tiles", man_a["tile_size"])
lay_set = {"glow": {"exposure": -30}}
_, rep_st = M["EFFinishStack"]().stack(_json.dumps([{"run_folder": "element-forge/t_run", "settings": lay_set},
                                                    {"run_folder": "element-forge/t_run", "settings": lay_set, "start": 1, "end": 1}]),
                                       "{}", "element-forge/t_stack", True, 25.0, 2)
def _rd(i):
    o = _oiio.ImageInput.open(os.path.join(S, "out", "element-forge", "t_stack", f"comp_{i:05d}.exr")); a = o.read_image(format="float"); o.close(); return a
c1, c2 = _rd(1), _rd(2)
assert abs(c1[15, 25, 0] - 2.25) < 0.02 and abs(c1[40, 5, 0] - 0.25) < 0.01, (c1[15, 25], c1[40, 5])
assert abs(c2[15, 25, 0] - 4.3) < 0.03 and abs(c2[40, 5, 0] - 0.3) < 0.01, (c2[15, 25], c2[40, 5])
print("finish stack ok:", _json.loads(rep_st)["layers"])
ref_i = torch.full((3, 96, 128, 3), 0.3); ref_i[:, 30:60, 40:90] = 0.6
lines_i = torch.zeros(3, 96, 128, 3)
for xx in range(20, 110):
    lines_i[:, 20 + (xx - 20) // 2, xx] = 1.0
ge_i, gc_i, lm_i = M["EFInPlateGuides"]().build(ref_i, 25, 70, 1.2, lines=lines_i)
assert gc_i[0, 27:34, 60:70, 0].max() > 0.5 and ge_i[0].sum() > gc_i[0].sum() and lm_i[0, 20, 20] > 0.5, "edges and lines"
with_i = ref_i.clone()
for xx in range(20, 110):
    with_i[:, 20 + (xx - 20) // 2, xx] = torch.tensor([0.75, 0.85, 1.0])
with_i[:, 70:80, 20:30] = torch.tensor([0.6, 0.4, 0.3])
with_i[:, 85:92, 100:110] = torch.tensor([0.5, 0.55, 0.7])
lay_i, _, _, _ = M["EFEffectLayer"]().extract(with_i, ref_i, False, 0.0, key="cold (lightning)", lines=lm_i, line_reach=4.0)
assert lay_i[1, 45, 70].max() > 0.2 and lay_i[1, 75, 25].max() < 1e-4 and lay_i[1, 88, 105].max() < 1e-4, (lay_i[1, 45, 70], lay_i[1, 75, 25], lay_i[1, 88, 105])
print("in-plate guides + cold effect layer ok")
hands_i = torch.zeros(3, 96, 128); hands_i[:, 40:50, 5:15] = 1; hands_i[:, 40:50, 113:123] = 1
lay_h0, _, _, _ = M["EFEffectLayer"]().extract(with_i, ref_i, False, 0.0, mask=hands_i, key="cold (lightning)", limit_to_mask=True)
lay_h1, _, _, _ = M["EFEffectLayer"]().extract(with_i, ref_i, False, 0.0, mask=hands_i, key="cold (lightning)", limit_to_mask=True, mask_hull=True)
assert lay_h0[1, 45, 70].max() < 1e-3 and lay_h1[1, 45, 70].max() > 0.2, (lay_h0[1, 45, 70], lay_h1[1, 45, 70])
print("effect layer mask hull ok")
_L3 = M["EFDepthLight"]
gen_n = torch.Generator().manual_seed(3)
vv_n, uu_n = torch.meshgrid(torch.arange(160, dtype=torch.float32), torch.arange(120, dtype=torch.float32), indexing="ij")
z_n = 2.0 + 0.004 * vv_n + 0.004 * torch.randn(160, 120, generator=gen_n)
z_n[40:100, 40:80] = 1.4
f_n = 100.0
P_n = torch.stack(((uu_n - 59.5) / f_n * z_n, (vv_n - 79.5) / f_n * z_n, z_n), -1)
n_raw = _L3.normals(P_n)
n_smo = _L3.normals_smooth(z_n, f_n, 80)
zc = 2.0 + 0.004 * vv_n
Pc = torch.stack(((uu_n - 59.5) / f_n * zc, (vv_n - 79.5) / f_n * zc, zc), -1)
n_ref = _L3.normals(Pc)
floor_n = torch.zeros(160, 120, dtype=torch.bool); floor_n[110:150, 10:110] = True
err = lambda n: float(torch.rad2deg(torch.acos((n * n_ref).sum(-1).clamp(-1, 1)))[floor_n].mean())
rim = lambda n: float(n[70, 81, 0].abs())
assert err(n_smo) < 0.35 * err(n_raw) and rim(n_smo) < 0.5 * rim(n_raw) + 0.05, (err(n_raw), err(n_smo), rim(n_raw), rim(n_smo))
print(f"smooth normals ok: floor error {err(n_raw):.1f} -> {err(n_smo):.1f} deg, edge tilt {rim(n_raw):.2f} -> {rim(n_smo):.2f}")
enc_n = torch.zeros(1, 24, 32, 3); enc_n[..., 0] = 0.5; enc_n[..., 1] = 0.5 + 0.5 * 0.8; enc_n[..., 2] = 0.5 + 0.5 * 0.6
_, _, nrm_out = _L3().light(torch.full((1, 48, 64, 3), 0.5), torch.zeros(1, 48, 64, 3), torch.rand(1, 48, 64, 3),
                            1.0, 2.0, 65.0, 0.15, 0.25, False, 0.8, 1.0, normals_image=enc_n)
assert torch.allclose(nrm_out[0, 20, 30], torch.tensor([0.5, 0.9, 0.8]), atol=1e-3), nrm_out[0, 20, 30]
print("normals image ok")
ref_w = torch.full((1, 64, 64, 3), 0.15)
fl_w = ref_w.clone(); fl_w[:, 20:50, 24:40] = torch.tensor([1.0, 0.55, 0.15]); fl_w[:, 30:40, 28:36] = 1.0
lay_w0, _, _, _ = M["EFEffectLayer"]().extract(fl_w, ref_w, True, 0.0, key="warm")
lay_w1, _, _, _ = M["EFEffectLayer"]().extract(fl_w, ref_w, True, 0.0, key="warm", warm_core=True)
assert lay_w0[0, 35, 32].max() < 1e-3 and lay_w1[0, 35, 32].min() > 0.5 and lay_w1[0, 5, 5].max() < 1e-4, (lay_w0[0, 35, 32], lay_w1[0, 35, 32])
print("effect layer warm core ok")
det_b = torch.full((5, 64, 96, 3), 0.2)
assert torch.equal(M["EFFreeVRAM"]().free(det_b)[0], det_b)
print("free vram ok")
xs_d = [100.0] * 5 + [100.0 + 300 * (i / 10) for i in range(1, 11)] + [400.0] * 25
tr_d = {"plate_size": [1920, 1080], "frames": len(xs_d), "point_track_px": [[x, 500.0] for x in xs_d]}
org_m = [[x - 128, 300.0] for x in xs_d]
tr_m = {**tr_d, "crop_origin_plate_px": org_m, "scale_roi_per_plate_px": 2.0, "roi_size": [512, 768]}
js_m, w_m, h_m, rep_m, cut_m = M["EFMotionTracks"]().tracks(tr_m, 45, 0.6, "track as is", 1.0, 0.6, 0.5, 80.0, fps=30.0, body_points="120, 230")
tk_m = __import__("json").loads(js_m)
assert (w_m, h_m) == (512, 768) and len(tk_m) == 4 and len(tk_m[0]) == len(xs_d)
assert max(abs(p["x"] - 256) for p in tk_m[0]) < 1e-6 and abs(tk_m[0][0]["y"] - 400) < 1e-6
assert tk_m[1][12]["x"] < 256 - 5 and abs(tk_m[1][-1]["x"] - 256) < 12, (tk_m[1][12], tk_m[1][-1])
assert abs(tk_m[2][5]["y"] - 520) < 1e-6
assert cut_m.shape == (len(xs_d), 768, 512) and cut_m[3, 390, 100] == 0 and cut_m[3, 420, 100] == 1
print("motion tracks ok:", rep_m)
short_tr = {"plate_size": [1920, 1080], "frames": 3, "point_track_px": [[100.0, 500.0], [200.0, 500.0], [300.0, 500.0]]}
assert len(__import__("json").loads(M["EFMotionTracks"]().tracks(short_tr, 45, 0.6, "object only (needs plate)", 1.0, 0.6, 0.5, 0.0, fps=2.0)[0])[0]) == 3
print("motion tracks short clip ok")
crop_m = {"plate_size": [1920, 1080], "frames": len(xs_d), "crop_origin_plate_px": [[0.0, 0.0]] * len(xs_d), "scale_roi_per_plate_px": 0.5, "roi_size": [960, 540]}
tk_c = __import__("json").loads(M["EFMotionTracks"]().tracks(tr_d, 45, 0.6, "track as is", 1.0, 0.6, 0.5, 80.0, fps=30.0, crop=crop_m)[0])
assert abs(tk_c[0][0]["x"] - 50) < 1e-6 and abs(tk_c[0][-1]["x"] - 200) < 1e-6, (tk_c[0][0], tk_c[0][-1])
print("motion tracks with crop ok")
ce = types.ModuleType("comfy_extras"); nm = types.ModuleType("comfy_extras.nodes_moge")
seen = {"inf": [], "geo": [], "emptied": 0}
class _Out:
    def __init__(self, *a): self.args = a
class _Inf:
    @classmethod
    def execute(cls, moge_model, image, resolution_level, fov_x_degrees, batch_size, force_projection, apply_mask, refine_steps):
        seen["inf"].append((image.shape[0], resolution_level, fov_x_degrees, batch_size, force_projection, apply_mask, refine_steps))
        assert seen["geo"] == [] or seen["geo"][-1] == {}, "previous batch still holds its geometry"
        g = {"image": image, "normal": image[..., :3] * 2 - 1, "points": torch.zeros(image.shape[0], 4, 6, 3)}
        seen["geo"].append(g)
        return _Out(g)
class _Ren:
    @classmethod
    def execute(cls, moge_geometry, output):
        seen["out"] = output
        return _Out(moge_geometry["normal"] * 0.5 + 0.5)
nm.MoGeInference, nm.MoGeRender = _Inf, _Ren
ce.nodes_moge = nm; sys.modules["comfy_extras"] = ce; sys.modules["comfy_extras.nodes_moge"] = nm
mm.soft_empty_cache = lambda *a, **k: seen.__setitem__("emptied", seen["emptied"] + 1)
img_mg = torch.rand(5, 4, 6, 3)
n_mg = M["EFMoGeNormals"]().run("model", img_mg, 9, 2, "normal_opengl")[0]
assert n_mg.shape == (5, 4, 6, 3) and torch.allclose(n_mg, img_mg, atol=1e-6)
assert seen["inf"] == [(2, 9, 0.0, 2, True, False, 0), (2, 9, 0.0, 2, True, False, 0), (1, 9, 0.0, 2, True, False, 0)]
assert seen["out"] == "normal_opengl" and all(g == {} for g in seen["geo"]) and seen["emptied"] == 3
print("moge normals ok")
rng_t = np.random.default_rng(3)
base_t = (cv2.GaussianBlur(rng_t.random((300, 500)).astype(np.float32), (0, 0), 2) * 255).astype(np.uint8)
g_t = []
for i in range(12):
    f = np.roll(base_t, 3 * i, axis=1).copy()
    if i >= 5:
        f[100:200, 200:320] = 128
    g_t.append(f)
rs_t = []
tr_t, _, _ = M["EFTrackROI"].follow(g_t, 250.0, 150.0, 30, rs_t)
assert rs_t and rs_t[0] == 5 and abs(tr_t[-1][0] - (250 + 33)) < 2.5 and abs(tr_t[-1][1] - 150) < 2.5, (rs_t, tr_t[-1])
rs_n = []
M["EFTrackROI"].follow([np.roll(base_t, 3 * i, axis=1) for i in range(6)], 250.0, 150.0, 30, rs_n)
assert rs_n == []
bg_o = (cv2.GaussianBlur(np.random.default_rng(5).random((300, 500)).astype(np.float32), (0, 0), 2) * 255).astype(np.uint8)
ob_o = (cv2.GaussianBlur(np.random.default_rng(6).random((140, 140)).astype(np.float32), (0, 0), 2) * 255).astype(np.uint8)
g_o = []
for i in range(14):
    f = bg_o.copy()
    f[80:220, 150 + 4 * i:290 + 4 * i] = 128 if 5 <= i <= 7 else ob_o
    g_o.append(f)
rs_o = []
tr_o, _, _ = M["EFTrackROI"].follow(g_o, 220.0, 150.0, 30, rs_o)
assert rs_o and rs_o[0] == 5, rs_o
assert abs((tr_o[13][0] - tr_o[8][0]) - 20) < 2 and abs(tr_o[13][1] - 150) < 2, tr_o[8:].round(1)
print("track roi fallback ok:", rs_t, tr_t[-1].round(1), "back on the object:", rs_o, tr_o[8:, 0].round(1))
import io
import av
def _mp4(path, n, start, steps, ticks=1000):
    with av.open(path, "w") as c:
        st = c.add_stream("libx264", rate=25)
        st.width, st.height, st.pix_fmt = 64, 48, "yuv420p"
        tb = st.codec_context.time_base = __import__("fractions").Fraction(1, ticks)
        t = start
        for k in range(n):
            f = av.VideoFrame.from_ndarray(np.full((48, 64, 3), k % 255, np.uint8), format="rgb24").reformat(format="yuv420p")
            f.pts, f.time_base = t, tb
            t += steps[k % len(steps)]
            for pk in st.encode(f):
                c.mux(pk)
        for pk in st.encode():
            c.mux(pk)
class _Vid:
    def __init__(self, src): self.src, self.cut = src, None
    def get_stream_source(self): return self.src
    def as_trimmed(self, start, dur, strict_duration=False):
        v = _Vid(self.src); v.cut = (start, dur); return v
def _count(path, end):
    with av.open(path) as c:
        st = c.streams.video[0]
        end_pts = int(end / float(st.time_base))
        return sum(1 for f in c.decode(st) if f.pts < end_pts)
_td = tempfile.mkdtemp()
for name, n, start, steps, ticks in (("cfr", 200, 0, [40], 1000), ("offset", 200, 1500, [40], 1000),
                                    ("vfr", 200, 700, [33, 50, 40], 1000), ("coarse", 200, 0, [1], 25)):
    fp = os.path.join(_td, name + ".mp4")
    _mp4(fp, n, start, steps, ticks)
    cut = M["EFClipFrames"]().clip(_Vid(fp), 121)[0]
    assert cut.cut and cut.cut[0] == 0.0 and _count(fp, cut.cut[1]) == 121, (name, cut.cut, _count(fp, cut.cut[1]))
    with open(fp, "rb") as fh:
        bio = io.BytesIO(fh.read())
    cut_b = M["EFClipFrames"]().clip(_Vid(bio), 121)[0]
    assert abs(cut_b.cut[1] - cut.cut[1]) < 1e-9 and bio.tell() == 0
fp_s = os.path.join(_td, "short.mp4")
_mp4(fp_s, 81, 0, [40])
short_v = _Vid(fp_s)
assert M["EFClipFrames"]().clip(short_v, 121)[0] is short_v
assert M["EFClipFrames"]().clip(short_v, 81)[0] is short_v
broken = _Vid(os.path.join(_td, "missing.mp4"))
assert M["EFClipFrames"]().clip(broken, 121)[0] is broken
print("clip frames ok")
