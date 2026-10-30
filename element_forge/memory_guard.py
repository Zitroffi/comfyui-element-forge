import ctypes
import functools
import gc
import inspect
import logging
import sys

GB = 2 ** 30
MARGIN = 3 * GB
MAX_SCAN = 64


class _PERF(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("CommitTotal", ctypes.c_size_t), ("CommitLimit", ctypes.c_size_t), ("CommitPeak", ctypes.c_size_t),
                ("PhysicalTotal", ctypes.c_size_t), ("PhysicalAvailable", ctypes.c_size_t), ("SystemCache", ctypes.c_size_t),
                ("KernelTotal", ctypes.c_size_t), ("KernelPaged", ctypes.c_size_t), ("KernelNonpaged", ctypes.c_size_t),
                ("PageSize", ctypes.c_size_t), ("HandleCount", ctypes.c_ulong), ("ProcessCount", ctypes.c_ulong), ("ThreadCount", ctypes.c_ulong)]


def commit():
    if sys.platform != "win32":
        return None
    p = _PERF()
    p.cb = ctypes.sizeof(p)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p), p.cb):
        return None
    return p.CommitTotal * p.PageSize, p.CommitLimit * p.PageSize


def tensor_bytes(v, depth=0):
    seen = set()

    def walk(x, d):
        if d > 3:
            return 0
        if hasattr(x, "untyped_storage") and getattr(x, "device", None) is not None and x.device.type == "cpu":
            s = x.untyped_storage()
            k = (s.data_ptr(), s.nbytes())
            if k in seen:
                return 0
            seen.add(k)
            return s.nbytes()
        if isinstance(x, dict):
            return sum(walk(y, d + 1) for y in list(x.values())[:MAX_SCAN])
        if isinstance(x, (list, tuple)):
            return sum(walk(y, d + 1) for y in x[:MAX_SCAN])
        return 0
    return walk(v, depth)


def _shortfall(need, read):
    c = read()
    if c is None:
        return 0
    total, limit = c
    return total + need + MARGIN - limit


def ensure(need, name="", read=commit, release=None):
    short = _shortfall(need, read)
    if short <= 0:
        return []
    steps = release if release is not None else _comfy_release()
    done = []
    gc.collect()
    for label, fn in steps:
        short = _shortfall(need, read)
        if short <= 0:
            break
        try:
            freed = fn(short)
        except Exception as e:
            logging.warning("[Element Forge] memory guard: %s failed: %s", label, e)
            continue
        done.append((label, int(freed or 0)))
    left = _shortfall(need, read)
    c = read()
    logging.info("[Element Forge] memory guard before %s: commit %.1f of %.1f GB, need ~%.1f GB; %s%s", name,
                 c[0] / GB if c else 0, c[1] / GB if c else 0, need / GB,
                 ", ".join(f"{label} {f / GB:.1f} GB" for label, f in done) or "nothing to free",
                 f"; still {left / GB:.1f} GB short" if left > 0 else "")
    return done


def _comfy_release():
    import comfy.memory_management as mm
    import comfy.model_management as m
    import comfy.system_memory as sm

    def pins(short):
        return m.free_pins(short + 512 * 2 ** 20, evict_active=True)

    def cache(active):
        def run(short):
            return mm.extra_ram_release(sm.virtual_memory_available() + short, free_active=active)
        return run

    def models(short):
        m.unload_all_models()
        m.soft_empty_cache()
        gc.collect()
        return 0
    return [("model pins", pins), ("old cached outputs", cache(False)), ("cached outputs", cache(True)), ("unload models", models)]


def guard_class(cls):
    fn_name = getattr(cls, "FUNCTION", None)
    if not fn_name or getattr(getattr(cls, fn_name, None), "_ef_guarded", False):
        return cls
    static = inspect.getattr_static(cls, fn_name, None)
    kind = classmethod if isinstance(static, classmethod) else staticmethod if isinstance(static, staticmethod) else None
    raw = static.__func__ if kind else static
    if not callable(raw) or inspect.iscoroutinefunction(raw):
        return cls

    @functools.wraps(raw)
    def run(*args, **kwargs):
        try:
            ensure(2 * (sum(tensor_bytes(v) for v in kwargs.values()) + sum(tensor_bytes(v) for v in args)), cls.__name__)
        except Exception as e:
            logging.warning("[Element Forge] memory guard skipped for %s: %s", cls.__name__, e)
        return raw(*args, **kwargs)
    run._ef_guarded = True
    setattr(cls, fn_name, kind(run) if kind else run)
    return cls


FOREIGN_GPU = ("VideoDepthAnythingProcess", "DepthCrafter")


def _free_vram():
    import comfy.model_management as mm
    mm.unload_all_models()
    mm.soft_empty_cache()
    gc.collect()


def gpu_room_class(cls, free=None):
    fn_name = getattr(cls, "FUNCTION", None)
    if not fn_name or getattr(getattr(cls, fn_name, None), "_ef_gpu_room", False):
        return cls
    static = inspect.getattr_static(cls, fn_name, None)
    kind = classmethod if isinstance(static, classmethod) else staticmethod if isinstance(static, staticmethod) else None
    raw = static.__func__ if kind else static
    if not callable(raw) or inspect.iscoroutinefunction(raw):
        return cls

    @functools.wraps(raw)
    def run(*args, **kwargs):
        try:
            (free or _free_vram)()
            logging.info("[Element Forge] models off the GPU before %s", cls.__name__)
        except Exception as e:
            logging.warning("[Element Forge] freeing the GPU before %s failed: %s", cls.__name__, e)
        return raw(*args, **kwargs)
    run._ef_gpu_room = True
    setattr(cls, fn_name, kind(run) if kind else run)
    return cls


def gpu_room_foreign(mappings):
    for name in FOREIGN_GPU:
        if name in mappings:
            gpu_room_class(mappings[name])


def on_prompt(json_data):
    try:
        import nodes
        gpu_room_foreign(nodes.NODE_CLASS_MAPPINGS)
    except Exception as e:
        logging.warning("[Element Forge] GPU room for foreign depth nodes not set: %s", e)
    return json_data
