import argparse
import hashlib
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

TAG = "prism-b10743-adfffbe"
BASE = f"https://github.com/PrismML-Eng/llama.cpp/releases/download/{TAG}/"
SHA = {
    f"llama-{TAG}-bin-win-cuda-12.4-x64.zip": "1b849f713bee42fda258de83770cd422e8f48dd631ce370eb0641f6458c69d87",
    "cudart-llama-bin-win-cuda-12.4-x64.zip": "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
    f"llama-{TAG}-bin-win-cpu-x64.zip": "d0b3016c9cc4bc1385de68be034adee570277ba952dd94292ba3888b7f18cc44",
    f"llama-{TAG}-bin-linux-cuda-12.8-x64.tar.gz": "43b73a24d5cd83c4482750ee52e59afac497c669c008a319e44e43a0033757e2",
    f"llama-{TAG}-bin-linux-cuda-13.3-x64.tar.gz": "bfa6e1e0af2f21295e863cf26444c49b5d0094221ea785836cd810325fca2159",
    f"llama-{TAG}-bin-ubuntu-x64.tar.gz": "1bb340929fddae8667c97ec6d4064a5768fe1dd08eeee0074b8d5e08f07dfc31",
    f"llama-{TAG}-bin-macos-arm64.tar.gz": "596d257973080ca5011a4be50477c5f93ed1d231fcccfc2afb44bb573bb9629a",
    f"llama-{TAG}-bin-macos-x64.tar.gz": "3527598651d783b66d525afbcdd0cbbba12a8d59c388bb0e13fa85715381969d",
}
SIZE = {
    f"llama-{TAG}-bin-win-cuda-12.4-x64.zip": 257322810, "cudart-llama-bin-win-cuda-12.4-x64.zip": 391443627,
    f"llama-{TAG}-bin-win-cpu-x64.zip": 19441568, f"llama-{TAG}-bin-linux-cuda-12.8-x64.tar.gz": 174402805,
    f"llama-{TAG}-bin-linux-cuda-13.3-x64.tar.gz": 153677617, f"llama-{TAG}-bin-ubuntu-x64.tar.gz": 17779725,
    f"llama-{TAG}-bin-macos-arm64.tar.gz": 11517506, f"llama-{TAG}-bin-macos-x64.tar.gz": 11559738,
}
MODEL_REPO = "https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf/resolve/main/"
MODEL_FILES = ["Ternary-Bonsai-2-27B-PTQ1_0.gguf", "Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf"]
MODEL_SHA = {
    "Ternary-Bonsai-2-27B-PTQ1_0.gguf": "53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3",
    "Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf": "6807ede61d570bb86ba34b756a0fa109edc33668604de867c6ea6d8f1d631903",
}
MODEL_SIZE = {"Ternary-Bonsai-2-27B-PTQ1_0.gguf": 5946648928, "Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf": 629246976}
HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(HERE, "runtime")


def torch_cuda():
    try:
        import torch
        return torch.version.cuda if torch.cuda.is_available() else None
    except Exception:
        return None


def pick(system=None, machine=None, cuda="auto", cpu=False):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if cuda == "auto":
        cuda = torch_cuda()
    if system == "win32":
        if machine not in ("amd64", "x86_64"):
            raise SystemExit(f"Windows on {machine}: no package of {TAG} for this pack, install it by hand.")
        if cpu or not cuda:
            return [f"llama-{TAG}-bin-win-cpu-x64.zip"]
        return [f"llama-{TAG}-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-12.4-x64.zip"]
    if system == "darwin":
        return [f"llama-{TAG}-bin-macos-{'arm64' if machine in ('arm64', 'aarch64') else 'x64'}.tar.gz"]
    if system.startswith("linux"):
        if machine not in ("x86_64", "amd64"):
            raise SystemExit(f"Linux on {machine}: no package of {TAG} for this pack, install it by hand.")
        if cpu or not cuda:
            return [f"llama-{TAG}-bin-ubuntu-x64.tar.gz"]
        major = str(cuda).split(".")[0]
        if major not in ("12", "13"):
            raise SystemExit(f"PyTorch uses CUDA {cuda}; {TAG} has packages for CUDA 12 and 13 only.")
        return [f"llama-{TAG}-bin-linux-cuda-{'13.3' if major == '13' else '12.8'}-x64.tar.gz"]
    raise SystemExit(f"{system}: no package of {TAG} for this pack.")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url, dest, progress=None):
    if progress is None:
        print(f"  download {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "comfyui-prism-bonsai-setup"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            f.write(block)
            done += len(block)
            if progress is not None:
                progress(done, total)
            elif total:
                print(f"\r  {done / 1e6:.0f} / {total / 1e6:.0f} MB", end="", flush=True)
    if progress is None:
        print()
    os.replace(dest + ".part", dest)


def unpack(archive, target):
    tmp = tempfile.mkdtemp(dir=os.path.dirname(target))
    try:
        if archive.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    p = os.path.realpath(os.path.join(tmp, name))
                    if not p.startswith(os.path.realpath(tmp) + os.sep):
                        raise SystemExit(f"unsafe path in {archive}: {name}")
                z.extractall(tmp)
        else:
            with tarfile.open(archive) as t:
                try:
                    t.extractall(tmp, filter="data")
                except TypeError:
                    for m in t.getmembers():
                        p = os.path.realpath(os.path.join(tmp, m.name))
                        if not p.startswith(os.path.realpath(tmp) + os.sep) or m.isdev():
                            raise SystemExit(f"unsafe path in {archive}: {m.name}")
                    t.extractall(tmp)
        entries = os.listdir(tmp)
        src = os.path.join(tmp, entries[0]) if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])) else tmp
        copy_tree(src, target)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def copy_tree(src, target):
    os.makedirs(target, exist_ok=True)
    for name in os.listdir(src):
        s, d = os.path.join(src, name), os.path.join(target, name)
        if os.path.isdir(s) and not os.path.islink(s):
            copy_tree(s, d)
        else:
            shutil.copy2(s, d, follow_symlinks=False)


def check_runtime(target):
    sys.path.insert(0, HERE)
    for mod in ("prism_rt", "bonsai_rt"):
        try:
            return __import__(mod).is_runtime(target)
        except ImportError:
            continue
    return any(f.startswith(("llama.", "libllama.")) for f in os.listdir(target))


def models_dir():
    return os.path.join(os.path.dirname(os.path.dirname(HERE)), "models", "LLM")


def check_runtime_quiet(target):
    return os.path.isdir(target) and check_runtime(target)


def plan(model=True, cpu=False, llm_dir=None, have=None, is_runtime=None):
    have = have or (lambda f: os.path.exists(os.path.join(llm_dir or models_dir(), f)))
    is_runtime = is_runtime or check_runtime_quiet
    out = [] if is_runtime(RUNTIME) else [(x, BASE + x, SIZE.get(x, 0), "runtime") for x in pick(cpu=cpu)]
    if model:
        out += [(f, MODEL_REPO + f, MODEL_SIZE[f], "model") for f in MODEL_FILES if not have(f)]
    return out


def install(model=True, cpu=False, llm_dir=None, have=None, progress=None, phase=None, is_runtime=None):
    phase = phase or (lambda t: None)
    llm_dir = llm_dir or models_dir()
    try:
        todo = plan(model, cpu, llm_dir, have, is_runtime)
    except SystemExit as e:
        raise RuntimeError(str(e)) from None
    need = sum(n for _, _, n, _ in todo)
    for folder in {HERE, llm_dir}:
        os.makedirs(folder, exist_ok=True)
        if shutil.disk_usage(folder).free < need * 1.2 + (1 << 30):
            raise RuntimeError(f"Not enough free space for {need / 1e9:.1f} GB on the drive of {folder}.")
    cache = os.path.join(HERE, "downloads")
    for name, url, _, kind in todo:
        path = os.path.join(cache if kind == "runtime" else llm_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        want = SHA[name] if kind == "runtime" else MODEL_SHA[name]
        if not (os.path.exists(path) and sha256(path) == want):
            phase(f"Downloading {name}")
            download(url, path, lambda d, t, n=name: progress and progress(n, d, t))
        phase(f"Checking {name}")
        if sha256(path) != want:
            os.replace(path, path + ".bad")
            raise RuntimeError(f"{name} does not match its published sha256; kept as {path}.bad, nothing installed from it.")
        if kind == "runtime":
            phase(f"Unpacking {name}")
            os.makedirs(RUNTIME, exist_ok=True)
            unpack(path, RUNTIME)
            os.remove(path)
    if not (is_runtime or check_runtime_quiet)(RUNTIME):
        raise RuntimeError(f"{RUNTIME} does not hold the libraries Bonsai loads; see the README.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", action="store_true", help="also download the model and the vision projector")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cpu", action="store_true", help="CPU package, no graphics card")
    ap.add_argument("--from", dest="src", help="archive or unpacked release folder to install from")
    ap.add_argument("--target", default=RUNTIME, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    assets = pick(cpu=a.cpu)
    print(f"system {sys.platform} {platform.machine()}, CUDA of PyTorch: {torch_cuda() or '-'}")
    print("package:", " + ".join(assets), "->", a.target)
    if a.model:
        print("model:", ", ".join(MODEL_FILES), "->", models_dir())
    if a.dry_run:
        for x in assets:
            print("  ", BASE + x)
        return 0
    os.makedirs(a.target, exist_ok=True)
    if a.src and os.path.isdir(a.src):
        copy_tree(a.src, a.target)
    elif a.src:
        if os.path.basename(a.src) in SHA and sha256(a.src) != SHA[os.path.basename(a.src)]:
            raise SystemExit(f"sha256 of {a.src} does not match the release")
        unpack(a.src, a.target)
    else:
        cache = os.path.join(HERE, "downloads")
        os.makedirs(cache, exist_ok=True)
        for x in assets:
            path = os.path.join(cache, x)
            if not (os.path.exists(path) and sha256(path) == SHA[x]):
                download(BASE + x, path)
            if sha256(path) != SHA[x]:
                raise SystemExit(f"sha256 of {x} does not match the release, file kept for inspection: {path}")
            unpack(path, a.target)
            os.remove(path)
    if not check_runtime(a.target):
        raise SystemExit(f"{a.target} does not hold the libraries this pack loads; see the README.")
    print("runtime ok:", a.target)
    if a.model:
        dst = models_dir()
        os.makedirs(dst, exist_ok=True)
        for f in MODEL_FILES:
            if os.path.exists(os.path.join(dst, f)):
                print("  already there:", f)
                continue
            download(MODEL_REPO + f, os.path.join(dst, f))
            if sha256(os.path.join(dst, f)) != MODEL_SHA[f]:
                raise SystemExit(f"sha256 of {f} does not match Hugging Face's, file kept for inspection.")
    print("done. Restart ComfyUI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
