import ast
import importlib.util
import os
import sys
import tempfile
import types

import av
import numpy as np
import torch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tempfile.tempdir = os.environ.get("TEMP") or tempfile.gettempdir()

for name, sub in (("efpack", ""), ("efpack.app", "app"), ("efpack.output", "output")):
    pkg = types.ModuleType(name)
    pkg.__path__ = [os.path.join(HERE, "element_forge", sub) if sub else os.path.join(HERE, "element_forge")]
    sys.modules[name] = pkg
src = open(os.path.join(HERE, "element_forge/app/app_nodes.py"), encoding="utf-8").read()
an = types.ModuleType("efpack.app.app_nodes")
an.__dict__.update({"np": np, "Fraction": __import__("fractions").Fraction})
exec(compile(ast.Module([n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in ("_mp4_stream", "_mp4_frame", "_exr_layer")], []),
             "app_nodes", "exec"), an.__dict__)
sys.modules["efpack.app.app_nodes"] = an
spec = importlib.util.spec_from_file_location("efpack.output.video_out", os.path.join(HERE, "element_forge/output/video_out.py"))
vo = importlib.util.module_from_spec(spec)
sys.modules["efpack.output.video_out"] = vo
spec.loader.exec_module(vo)

n = bad = 0


def check(ok, msg):
    global n, bad
    n += 1
    bad += 0 if ok else 1
    print("ok  " if ok else "FAIL", msg)


def levels(path, fmt="rgb48le"):
    with av.open(path) as c:
        s = c.streams.video[0]
        f = next(c.decode(s))
        return f, f.to_ndarray(format=fmt)


h, w = 32, 2048
ramp = torch.linspace(0.18, 0.22, w).view(1, 1, w, 1).expand(3, h, w, 3).contiguous()
with tempfile.TemporaryDirectory() as d:
    for fmt in ("prores", "h265", "mp4"):
        wr = vo.CompWriter(d, fmt, 24, w, h)
        wr.add(ramp, [0, 1, 2])
        wr.close()
        f, a = levels(os.path.join(d, wr.files[0]))
        u = len(np.unique(a[h // 2, 8:-8, 1] >> 6))
        if fmt == "mp4":
            check(f.format.name == "yuv420p" and u <= 16, f"mp4: H.264 8 bit ({f.format.name}, {u} levels on the gradient)")
        else:
            want = "yuv422p10le" if fmt == "prores" else "yuv420p10le"
            check(f.format.name == want and u >= 30, f"{fmt}: {want}, {u} levels on the gradient (8 bit: about 11)")
    with av.open(os.path.join(d, "comp.mov")) as c:
        cc = c.streams.video[0].codec_context
        check(cc.name == "prores" and cc.color_primaries == 1 and cc.color_trc == 1, f"ProRes tagged BT.709 ({cc.color_primaries}, {cc.color_trc})")
    wr = vo.CompWriter(d, "png16", 24, 64, 16)
    wr.add(torch.full((2, 16, 64, 3), 0.5), [9, 10])
    wr.close()
    import OpenImageIO as oiio
    inp = oiio.ImageInput.open(os.path.join(d, "comp_00010.png"))
    px = inp.read_image(format="uint16")
    inp.close()
    srgb = float(vo.srgb_encode(torch.tensor(0.5))) * 65535
    check(wr.files == ["comp_00010.png", "comp_00011.png"] and abs(float(np.asarray(px).mean()) - srgb) < 64, f"png16: numbered by frame, 16 bit sRGB ({float(np.asarray(px).mean()):.0f} ~ {srgb:.0f})")
    wr = vo.CompWriter(d, "exr", 24, 64, 16)
    wr.add(torch.full((1, 16, 64, 3), 3.0), [0])
    wr.close()
    inp = oiio.ImageInput.open(os.path.join(d, "comp_00001.exr"))
    ex = np.asarray(inp.read_image(format="float"))
    inp.close()
    check(abs(float(ex.mean()) - 3.0) < 1e-2, "exr: linear values above 1 stay (3.0)")
    wr = vo.CompWriter(d, "prores", 24, 65, 33)
    check((wr.w, wr.h) == (64, 32), "video formats: even sizes")
    wr.close()
    try:
        vo.CompWriter(d, "prores", 24, 64, 32, hdr=True)
        check(False, "HDR only as H.265")
    except ValueError:
        check(True, "HDR only as H.265")
print(f"{n - bad}/{n} checks passed")
sys.exit(1 if bad else 0)
