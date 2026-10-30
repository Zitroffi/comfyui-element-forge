import ctypes
import os
import sys
import threading
import time
from ctypes import POINTER, c_bool, c_char_p, c_float, c_int, c_int8, c_int32, c_size_t, c_uint32, c_void_p

import numpy as np

c_token = c_int32


class ModelParams(ctypes.Structure):
    _fields_ = [("dspark_head_source", c_void_p), ("devices", c_void_p), ("tensor_buft_overrides", c_void_p),
                ("n_gpu_layers", c_int32), ("split_mode", c_int), ("load_mode", c_int), ("main_gpu", c_int32),
                ("tensor_split", c_void_p), ("progress_callback", c_void_p), ("progress_callback_user_data", c_void_p),
                ("kv_overrides", c_void_p), ("vocab_only", c_bool), ("check_tensors", c_bool), ("use_extra_bufts", c_bool),
                ("no_host", c_bool), ("no_alloc", c_bool), ("load_mtp", c_bool)]


class ContextParams(ctypes.Structure):
    _fields_ = [("n_ctx", c_uint32), ("n_batch", c_uint32), ("n_ubatch", c_uint32), ("n_seq_max", c_uint32), ("n_rs_seq", c_uint32),
                ("n_outputs_max", c_uint32), ("n_outputs_max_per_seq", c_uint32), ("n_threads", c_int32), ("n_threads_batch", c_int32),
                ("ctx_type", c_int), ("rope_scaling_type", c_int), ("pooling_type", c_int), ("attention_type", c_int),
                ("flash_attn_type", c_int), ("rope_freq_base", c_float), ("rope_freq_scale", c_float), ("yarn_ext_factor", c_float),
                ("yarn_attn_factor", c_float), ("yarn_beta_fast", c_float), ("yarn_beta_slow", c_float), ("yarn_orig_ctx", c_uint32),
                ("defrag_thold", c_float), ("cb_eval", c_void_p), ("cb_eval_user_data", c_void_p), ("type_k", c_int), ("type_v", c_int),
                ("path_kv_mean_center", c_void_p), ("abort_callback", c_void_p), ("abort_callback_data", c_void_p),
                ("embeddings", c_bool), ("offload_kqv", c_bool), ("no_perf", c_bool), ("op_offload", c_bool), ("swa_full", c_bool),
                ("kv_unified", c_bool), ("samplers", c_void_p), ("n_samplers", c_size_t), ("ctx_other", c_void_p)]


class Batch(ctypes.Structure):
    _fields_ = [("n_tokens", c_int32), ("token", POINTER(c_token)), ("embd", POINTER(c_float)), ("pos", POINTER(c_int32)),
                ("n_seq_id", POINTER(c_int32)), ("seq_id", POINTER(POINTER(c_int32))), ("logits", POINTER(c_int8))]


class ChainParams(ctypes.Structure):
    _fields_ = [("no_perf", c_bool)]


class MtmdParams(ctypes.Structure):
    _fields_ = [("use_gpu", c_bool), ("device", c_void_p), ("print_timings", c_bool), ("n_threads", c_int), ("image_marker", c_char_p),
                ("media_marker", c_char_p), ("flash_attn_type", c_int), ("warmup", c_bool), ("image_min_tokens", c_int),
                ("image_max_tokens", c_int), ("cb_eval", c_void_p), ("cb_eval_user_data", c_void_p), ("batch_max_tokens", c_int32),
                ("progress_callback", c_void_p), ("progress_callback_user_data", c_void_p)]


class MtmdText(ctypes.Structure):
    _fields_ = [("text", c_char_p), ("text_len", c_size_t), ("add_special", c_bool), ("parse_special", c_bool)]


LOG_CB = ctypes.CFUNCTYPE(None, c_int, c_char_p, c_void_p)
GGML_LOG_ERROR = 4

_lib_lock = threading.Lock()

if os.name == "nt":
    LIB_NAMES = ("ggml.dll", "llama.dll", "mtmd.dll")
elif sys.platform == "darwin":
    LIB_NAMES = ("libggml.dylib", "libllama.dylib", "libmtmd.dylib")
else:
    LIB_NAMES = ("libggml.so", "libllama.so", "libmtmd.so")


def is_runtime(folder):
    return bool(folder) and all(os.path.isfile(os.path.join(folder, n)) for n in LIB_NAMES)


def _preload_cuda(folder):
    if os.name == "nt":
        return [ctypes.CDLL(os.path.join(folder, d)) for d in ("cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll")
                if os.path.exists(os.path.join(folder, d))]
    if sys.platform == "darwin":
        return []
    dirs = [folder]
    for p in sys.path:
        nv = os.path.join(p, "nvidia")
        if os.path.isdir(nv):
            dirs += [os.path.join(nv, d, "lib") for d in sorted(os.listdir(nv)) if os.path.isdir(os.path.join(nv, d, "lib"))]
    loaded = []
    for major in ("13", "12"):
        for name in (f"libcudart.so.{major}", f"libcublasLt.so.{major}", f"libcublas.so.{major}"):
            for d in [None] + dirs:
                try:
                    loaded.append(ctypes.CDLL(name if d is None else os.path.join(d, name), mode=ctypes.RTLD_GLOBAL))
                    break
                except OSError:
                    continue
    return loaded


class Libraries:

    def __init__(self, folder):
        self.folder = folder
        self._dll_dir = os.add_dll_directory(folder) if os.name == "nt" else None
        self._cuda = _preload_cuda(folder)
        mode = {} if os.name == "nt" else {"mode": ctypes.RTLD_GLOBAL}
        self.ggml, self.llama, self.mtmd = (ctypes.CDLL(os.path.join(folder, n), **mode) for n in LIB_NAMES)
        self.errors = []
        self.cuda = False
        self._log = LOG_CB(self._on_log)
        L, G, M = self.llama, self.ggml, self.mtmd
        sig = lambda f, res, *args: (setattr(f, "restype", res), setattr(f, "argtypes", list(args)))
        sig(G.ggml_backend_load_all_from_path, None, c_char_p)
        sig(L.llama_log_set, None, LOG_CB, c_void_p)
        sig(L.llama_backend_init, None)
        sig(L.llama_model_default_params, ModelParams)
        sig(L.llama_context_default_params, ContextParams)
        sig(L.llama_sampler_chain_default_params, ChainParams)
        sig(L.llama_model_load_from_file, c_void_p, c_char_p, ModelParams)
        sig(L.llama_init_from_model, c_void_p, c_void_p, ContextParams)
        sig(L.llama_model_free, None, c_void_p)
        sig(L.llama_free, None, c_void_p)
        sig(L.llama_model_get_vocab, c_void_p, c_void_p)
        sig(L.llama_model_chat_template, c_char_p, c_void_p, c_char_p)
        sig(L.llama_model_size, ctypes.c_uint64, c_void_p)
        sig(L.llama_n_ctx, c_uint32, c_void_p)
        sig(L.llama_get_memory, c_void_p, c_void_p)
        sig(L.llama_memory_clear, None, c_void_p, c_bool)
        sig(L.llama_tokenize, c_int32, c_void_p, c_char_p, c_int32, POINTER(c_token), c_int32, c_bool, c_bool)
        sig(L.llama_token_to_piece, c_int32, c_void_p, c_token, c_char_p, c_int32, c_int32, c_bool)
        sig(L.llama_vocab_is_eog, c_bool, c_void_p, c_token)
        sig(L.llama_batch_get_one, Batch, POINTER(c_token), c_int32)
        sig(L.llama_decode, c_int32, c_void_p, Batch)
        sig(L.llama_sampler_chain_init, c_void_p, ChainParams)
        sig(L.llama_sampler_chain_add, None, c_void_p, c_void_p)
        sig(L.llama_sampler_init_grammar, c_void_p, c_void_p, c_char_p, c_char_p)
        sig(L.llama_sampler_init_top_k, c_void_p, c_int32)
        sig(L.llama_sampler_init_top_p, c_void_p, c_float, c_size_t)
        sig(L.llama_sampler_init_temp, c_void_p, c_float)
        sig(L.llama_sampler_init_dist, c_void_p, c_uint32)
        sig(L.llama_sampler_init_greedy, c_void_p)
        sig(L.llama_sampler_sample, c_token, c_void_p, c_void_p, c_int32)
        sig(L.llama_sampler_free, None, c_void_p)
        sig(M.mtmd_helper_log_set, None, LOG_CB, c_void_p)
        sig(M.mtmd_default_marker, c_char_p)
        sig(M.mtmd_context_params_default, MtmdParams)
        sig(M.mtmd_init_from_file, c_void_p, c_char_p, c_void_p, MtmdParams)
        sig(M.mtmd_free, None, c_void_p)
        sig(M.mtmd_support_vision, c_bool, c_void_p)
        sig(M.mtmd_bitmap_init, c_void_p, c_uint32, c_uint32, c_char_p)
        sig(M.mtmd_bitmap_free, None, c_void_p)
        sig(M.mtmd_input_chunks_init, c_void_p)
        sig(M.mtmd_input_chunks_free, None, c_void_p)
        sig(M.mtmd_tokenize, c_int32, c_void_p, c_void_p, POINTER(MtmdText), POINTER(c_void_p), c_size_t)
        sig(M.mtmd_helper_eval_chunks, c_int32, c_void_p, c_void_p, c_void_p, c_int32, c_int32, c_int32, c_bool, POINTER(c_int32))
        L.llama_log_set(self._log, None)
        M.mtmd_helper_log_set(self._log, None)
        G.ggml_backend_load_all_from_path(folder.encode())
        L.llama_backend_init()
        self.check_layout()

    def _on_log(self, level, text, _):
        if text and b"loaded CUDA backend" in text:
            self.cuda = True
        if level == GGML_LOG_ERROR and text:
            self.errors = (self.errors + [text.decode("utf-8", "replace").strip()])[-20:]

    def check_layout(self):
        m = self.llama.llama_model_default_params()
        c = self.llama.llama_context_default_params()
        p = self.mtmd.mtmd_context_params_default()
        ok = (m.n_gpu_layers == -1 and m.split_mode == 1 and m.load_mode == -1 and m.main_gpu == 0 and m.use_extra_bufts
              and not m.vocab_only and c.n_batch == 2048 and c.n_ubatch == 512 and c.n_seq_max == 1 and c.flash_attn_type == -1
              and c.type_k == 1 and c.type_v == 1 and c.offload_kqv and c.op_offload and c.swa_full and not c.kv_unified
              and p.media_marker == b"<__media__>" and p.batch_max_tokens == 1024)
        if not ok:
            raise RuntimeError(f"The libraries in {self.folder} do not match this pack (struct layout check failed); use the PrismML "
                               "release prism-b10743-adfffbe.")


def libraries(folder):
    with _lib_lock:
        shared = sys.__dict__.setdefault("_prism_llama_libraries", {})
        lib = shared.get("lib")
        if lib is None:
            lib = shared["lib"] = Libraries(folder)
        elif os.path.normcase(lib.folder) != os.path.normcase(folder):
            raise RuntimeError(f"Another runtime folder is already loaded in this ComfyUI ({lib.folder}); restart ComfyUI to change it.")
        return lib


class Model:

    def __init__(self, lib, path, mmproj=None, n_ctx=4096, gpu=True, mmproj_gpu=False, image_max_tokens=1024):
        self.lib, L = lib, lib.llama
        mp = L.llama_model_default_params()
        self._no_devices = (c_void_p * 1)()
        if gpu:
            mp.n_gpu_layers = -1
            if not lib.cuda and sys.platform != "darwin":
                print(f"[Bonsai] no CUDA backend in {lib.folder}, the model runs on the CPU (slow).")
        else:
            mp.n_gpu_layers, mp.devices = 0, ctypes.cast(self._no_devices, c_void_p)
        t0 = time.time()
        lib.errors = []
        self.model = L.llama_model_load_from_file(path.encode(), mp)
        if not self.model:
            raise RuntimeError("Could not load the model: " + ("; ".join(lib.errors[-3:]) or path))
        cp = L.llama_context_default_params()
        cp.n_ctx, cp.n_batch, cp.n_ubatch, cp.flash_attn_type = int(n_ctx), 1024, 512, (1 if gpu else 0)
        cp.n_threads = cp.n_threads_batch = max(1, (os.cpu_count() or 4) // 2)
        cp.offload_kqv = cp.op_offload = bool(gpu)
        self.ctx = L.llama_init_from_model(self.model, cp)
        if not self.ctx:
            L.llama_model_free(self.model)
            raise RuntimeError("Could not create the context (too little memory?): " + "; ".join(lib.errors[-3:]))
        self.vocab = L.llama_model_get_vocab(self.model)
        tpl = L.llama_model_chat_template(self.model, None)
        self.template = tpl.decode("utf-8") if tpl else None
        self.mtmd = None
        if mmproj:
            pp = lib.mtmd.mtmd_context_params_default()
            pp.use_gpu, pp.print_timings, pp.warmup = bool(gpu and mmproj_gpu), False, False
            pp.n_threads = cp.n_threads
            pp.image_max_tokens = int(image_max_tokens)
            pp.flash_attn_type = cp.flash_attn_type
            self.mtmd = lib.mtmd.mtmd_init_from_file(mmproj.encode(), self.model, pp)
            if not self.mtmd:
                self.free()
                raise RuntimeError("Could not load the vision projector: " + "; ".join(lib.errors[-3:]))
        self.load_seconds = round(time.time() - t0, 2)
        self.size_bytes = int(L.llama_model_size(self.model))

    @property
    def marker(self):
        return self.lib.mtmd.mtmd_default_marker().decode()

    def free(self):
        L = self.lib.llama
        if getattr(self, "mtmd", None):
            self.lib.mtmd.mtmd_free(self.mtmd)
            self.mtmd = None
        if getattr(self, "ctx", None):
            L.llama_free(self.ctx)
            self.ctx = None
        if getattr(self, "model", None):
            L.llama_model_free(self.model)
            self.model = None

    def _decode_tokens(self, tokens, n_batch=1024):
        L = self.lib.llama
        for i in range(0, len(tokens), n_batch):
            part = (c_token * len(tokens[i:i + n_batch]))(*tokens[i:i + n_batch])
            if L.llama_decode(self.ctx, L.llama_batch_get_one(part, len(part))) != 0:
                raise RuntimeError("The prompt does not fit into the context (raise the context size).")

    def _tokenize(self, text):
        L = self.lib.llama
        raw = text.encode("utf-8")
        buf = (c_token * (len(raw) + 16))()
        n = L.llama_tokenize(self.vocab, raw, len(raw), buf, len(buf), False, True)
        if n < 0:
            raise RuntimeError("tokenizing failed")
        return list(buf[:n])

    def generate(self, prompt, image=None, grammar=None, max_tokens=400, temperature=0.7, top_p=0.8, top_k=20, seed=0):
        L, M = self.lib.llama, self.lib.mtmd
        L.llama_memory_clear(L.llama_get_memory(self.ctx), True)
        t0 = time.time()
        if image is not None:
            if not self.mtmd:
                raise RuntimeError("This model was loaded without a vision projector.")
            img = np.ascontiguousarray(image, dtype=np.uint8)
            bmp = M.mtmd_bitmap_init(img.shape[1], img.shape[0], img.tobytes())
            chunks = M.mtmd_input_chunks_init()
            try:
                raw = prompt.encode("utf-8")
                txt = MtmdText(raw, len(raw), False, True)
                arr = (c_void_p * 1)(bmp)
                if M.mtmd_tokenize(self.mtmd, chunks, ctypes.byref(txt), arr, 1) != 0:
                    raise RuntimeError("The image could not be read into the prompt.")
                n_past = c_int32(0)
                if M.mtmd_helper_eval_chunks(self.mtmd, self.ctx, chunks, 0, 0, 1024, True, ctypes.byref(n_past)) != 0:
                    raise RuntimeError("The prompt with the image does not fit into the context.")
                n_prompt = n_past.value
            finally:
                M.mtmd_input_chunks_free(chunks)
                M.mtmd_bitmap_free(bmp)
        else:
            tokens = self._tokenize(prompt)
            n_prompt = len(tokens)
            self._decode_tokens(tokens)
        t1 = time.time()
        chain = L.llama_sampler_chain_init(L.llama_sampler_chain_default_params())
        if grammar:
            g = L.llama_sampler_init_grammar(self.vocab, grammar.encode(), b"root")
            if not g:
                L.llama_sampler_free(chain)
                raise RuntimeError("The JSON schema could not be turned into a grammar: " + "; ".join(self.lib.errors[-2:]))
            L.llama_sampler_chain_add(chain, g)
        if temperature <= 0:
            L.llama_sampler_chain_add(chain, L.llama_sampler_init_greedy())
        else:
            L.llama_sampler_chain_add(chain, L.llama_sampler_init_top_k(int(top_k)))
            L.llama_sampler_chain_add(chain, L.llama_sampler_init_top_p(float(top_p), 1))
            L.llama_sampler_chain_add(chain, L.llama_sampler_init_temp(float(temperature)))
            L.llama_sampler_chain_add(chain, L.llama_sampler_init_dist(int(seed) & 0xFFFFFFFF))
        out, piece, cut, n_gen = bytearray(), ctypes.create_string_buffer(256), True, 0
        one = (c_token * 1)()
        try:
            for _ in range(int(max_tokens)):
                tok = L.llama_sampler_sample(chain, self.ctx, -1)
                if L.llama_vocab_is_eog(self.vocab, tok):
                    cut = False
                    break
                n = L.llama_token_to_piece(self.vocab, tok, piece, len(piece), 0, False)
                out += piece.raw[:max(n, 0)]
                n_gen += 1
                one[0] = tok
                if L.llama_decode(self.ctx, L.llama_batch_get_one(one, 1)) != 0:
                    raise RuntimeError("The answer ran out of context (raise the context size).")
        finally:
            L.llama_sampler_free(chain)
        t2 = time.time()
        stats = {"prompt_tokens": n_prompt, "prompt_seconds": round(t1 - t0, 2), "generated_seconds": round(t2 - t1, 2),
                 "tokens_per_second": round(n_gen / max(t2 - t1, 1e-6), 2), "cut": cut}
        return out.decode("utf-8", "replace"), stats
