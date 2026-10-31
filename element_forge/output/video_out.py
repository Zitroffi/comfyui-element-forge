import os
from fractions import Fraction

import numpy as np
import torch

FORMATS = {
    "mp4": ("comp.mp4", "H.264 MP4, 8 bit"),
    "prores": ("comp.mov", "ProRes 422 HQ, 10 bit"),
    "h265": ("comp_h265.mp4", "H.265, 10 bit"),
    "png8": ("comp_#####.png", "PNG sequence, 8 bit"),
    "png16": ("comp_#####.png", "PNG sequence, 16 bit"),
    "exr": ("comp_#####.exr", "EXR sequence, half float, linear Rec.709"),
}
VIDEO = {"mp4", "prores", "h265"}


def srgb_encode(C):
    C = C.clamp(0, 1)
    return torch.where(C <= 0.0031308, C * 12.92, 1.055 * C.clamp(min=1e-12) ** (1 / 2.4) - 0.055)


def quantize(x, bits, seed):
    top = (1 << bits) - 1
    g = torch.Generator().manual_seed(int(seed))
    noise = torch.rand(x.shape, generator=g) - torch.rand(x.shape, generator=g)
    q = (x * top + noise).round().clamp(0, top)
    if bits == 8:
        return q.to(torch.uint8).numpy()
    return (q * (65535 / top)).round().to(torch.int32).numpy().astype(np.uint16)


class CompWriter:
    def __init__(self, folder, fmt, fps, w, h, hdr=False):
        if fmt not in FORMATS:
            raise ValueError(f"unknown format {fmt}: {', '.join(FORMATS)}")
        if hdr and fmt != "h265":
            raise ValueError("HDR is written as H.265 10 bit only")
        self.folder, self.fmt, self.fps, self.hdr = folder, fmt, fps, hdr
        self.w, self.h = (w // 2 * 2, h // 2 * 2) if fmt in VIDEO else (w, h)
        self.files = []
        self.c = self.st = None
        if fmt in VIDEO:
            import av
            name = FORMATS[fmt][0]
            self.c = av.open(os.path.join(folder, name), "w")
            self.files.append(name)
            if fmt == "mp4":
                from ..app.app_nodes import _mp4_stream
                self.st = _mp4_stream(self.c, fps, self.w, self.h)
                return
            codec, pix = ("prores_ks", "yuv422p10le") if fmt == "prores" else ("libx265", "yuv420p10le")
            st = self.c.add_stream(codec, rate=Fraction(fps).limit_denominator(1001))
            st.width, st.height, st.pix_fmt = self.w, self.h, pix
            cc = st.codec_context
            if hdr:
                cc.colorspace, cc.color_primaries, cc.color_trc, cc.color_range = 9, 9, 16, 1
            else:
                cc.colorspace, cc.color_primaries, cc.color_trc, cc.color_range = 1, 1, 1, 1
            if fmt == "prores":
                st.options = {"profile": "3", "vendor": "apl0"}
            else:
                p = "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc" if hdr else "colorprim=bt709:transfer=bt709:colormatrix=bt709"
                st.options = {"crf": "14", "preset": "medium", "x265-params": f"log-level=error:{p}:range=limited" + (":hdr10=1:hdr10-opt=1" if hdr else "")}
                try:
                    cc.codec_tag = "hvc1"
                except (AttributeError, ValueError):
                    pass
            self.st = st

    def add(self, C, frames):
        C = C[:, : self.h, : self.w, :3].float()
        if self.fmt == "exr":
            from ..app.app_nodes import _exr_layer
            for k, i in enumerate(frames):
                name = FORMATS["exr"][0].replace("#####", f"{int(i) + 1:05d}")
                _exr_layer(os.path.join(self.folder, name), C[k].numpy())
                self.files.append(name)
            return
        x = C.clamp(0, 1) if self.hdr else srgb_encode(C)
        seed = int(frames[0]) if len(frames) else 0
        if self.fmt in ("mp4", "png8"):
            q = quantize(x, 8, seed)
        else:
            q = quantize(x, 10 if self.fmt in VIDEO else 16, seed)
        if self.fmt in ("png8", "png16"):
            from PIL import Image
            for k, i in enumerate(frames):
                name = FORMATS[self.fmt][0].replace("#####", f"{int(i) + 1:05d}")
                path = os.path.join(self.folder, name)
                if self.fmt == "png8":
                    Image.fromarray(q[k], "RGB").save(path, compress_level=4)
                else:
                    _png16(path, q[k])
                self.files.append(name)
            return
        import av
        from av.video.reformatter import ColorRange, Colorspace
        for k in range(q.shape[0]):
            if self.fmt == "mp4":
                from ..app.app_nodes import _mp4_frame
                fr = _mp4_frame(q[k])
            else:
                fr = av.VideoFrame.from_ndarray(np.ascontiguousarray(q[k]), format="rgb48le").reformat(
                    format=self.st.pix_fmt, dst_colorspace=Colorspace.BT2020 if self.hdr else Colorspace.ITU709, dst_color_range=ColorRange.MPEG)
            for pkt in self.st.encode(fr):
                self.c.mux(pkt)

    def close(self):
        if self.c is not None:
            for pkt in self.st.encode():
                self.c.mux(pkt)
            self.c.close()
            self.c = None


def _png16(path, rgb16):
    import OpenImageIO as oiio
    spec = oiio.ImageSpec(rgb16.shape[1], rgb16.shape[0], 3, "uint16")
    o = oiio.ImageOutput.create(path)
    if not o or not o.open(path, spec):
        raise RuntimeError(f"PNG write failed: {oiio.geterror()}")
    o.write_image(np.ascontiguousarray(rgb16))
    o.close()


def true_hdr(srgb_chunk):
    import nodes as comfy_nodes
    cls = comfy_nodes.NODE_CLASS_MAPPINGS.get("RTXTrueHDR")
    if cls is None:
        raise ValueError("HDR needs NVIDIA's RTX nodes (ComfyUI_Nvidia_VFX_Nodes) and an RTX card")
    node = cls()
    fn = getattr(node, getattr(cls, "FUNCTION", "execute"))
    out = fn(images=srgb_chunk, contrast=100, saturation=100, middle_gray=50, luminance=2000, debanding=True, output_colorspace="HDR PQ")
    out = out[0] if isinstance(out, (tuple, list)) else getattr(out, "result", [out])[0]
    return out


def has_true_hdr():
    try:
        import nodes as comfy_nodes
        return "RTXTrueHDR" in comfy_nodes.NODE_CLASS_MAPPINGS
    except ImportError:
        return False


def srgb_decode(S):
    S = S.clamp(0, 1)
    return torch.where(S <= 0.04045, S / 12.92, ((S + 0.055) / 1.055) ** 2.4)


def rtx_sr(srgb_chunk, scale=2.0):
    import nodes as comfy_nodes
    cls = comfy_nodes.NODE_CLASS_MAPPINGS.get("RTXVideoSuperResolution")
    if cls is None:
        raise ValueError("NVIDIA x2 needs NVIDIA's RTX nodes (ComfyUI_Nvidia_VFX_Nodes) and an RTX card")
    fn = getattr(cls(), getattr(cls, "FUNCTION", "execute"))
    out = fn(images=srgb_chunk, resize_type={"resize_type": "scale by multiplier", "scale": float(scale)}, quality="ULTRA",
             strength=1.0, image_encoding="10-bit RGB (RGB10A2)")
    out = out[0] if isinstance(out, (tuple, list)) else getattr(out, "result", [out])[0]
    return out[..., :3].float().cpu()


def has_rtx_sr():
    try:
        import nodes as comfy_nodes
        return "RTXVideoSuperResolution" in comfy_nodes.NODE_CLASS_MAPPINGS
    except ImportError:
        return False


PQ_M1, PQ_M2, PQ_C1, PQ_C2, PQ_C3 = 2610 / 16384, 2523 / 4096 * 128, 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
REC709_TO_2020 = torch.tensor([[0.6274, 0.3293, 0.0433], [0.0691, 0.9195, 0.0114], [0.0164, 0.0880, 0.8956]])
LUMA_2020 = torch.tensor([0.2627, 0.6780, 0.0593])


def pq_nits(E):
    p = E.clamp(0, 1) ** (1 / PQ_M2)
    return 10000.0 * ((p - PQ_C1).clamp(min=0) / (PQ_C2 - PQ_C3 * p)) ** (1 / PQ_M1)


def nits_pq(L):
    y = (L.clamp(0, 10000) / 10000.0) ** PQ_M1
    return ((PQ_C1 + PQ_C2 * y) / (1 + PQ_C3 * y)) ** PQ_M2


def hdr_plate_only(plate_srgb, plate_lin, comp_lin, through):
    P = pq_nits(true_hdr(plate_srgb).float().cpu()[..., :3])
    lum = LUMA_2020.to(P)
    m = REC709_TO_2020.to(P)
    lin = plate_lin @ m.T
    out = []
    for k in range(P.shape[0]):
        y_in, y_out = (lin[k] * lum).sum(-1), (P[k] * lum).sum(-1)
        sel = (y_in > 0.05) & (y_in < 0.6)
        g = float((y_out[sel] / y_in[sel]).median()) if int(sel.sum()) > 256 else 203.0
        eff = ((comp_lin[k] - plate_lin[k] * through[k]) @ m.T).clamp(min=0) * g
        out.append(nits_pq(P[k] * through[k] + eff))
    return torch.stack(out)
