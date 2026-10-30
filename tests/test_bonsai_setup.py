import functools
import hashlib
import http.server
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import threading
import zipfile

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("setup_bonsai", os.path.join(PACK, "element_forge/bonsai/setup_bonsai.py"))
SB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SB)
n = bad = 0


def check(cond, name):
    global n, bad
    n += 1
    bad += not cond
    print("ok  " if cond else "FAIL", name)


LIBS = ("ggml.dll", "llama.dll", "mtmd.dll") if os.name == "nt" else ("libggml.so", "libllama.so", "libmtmd.so")
is_runtime = lambda d: all(os.path.isfile(os.path.join(d, x)) for x in LIBS)


def zip_bytes(files, top="release"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, data in files.items():
            z.writestr(f"{top}/{name}", data)
    return b.getvalue()


root = tempfile.mkdtemp(prefix="ef_bonsai_setup_")
served, pack, llm = os.path.join(root, "served"), os.path.join(root, "pack"), os.path.join(root, "LLM")
os.makedirs(served)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


handler = functools.partial(Quiet, directory=served)
httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{httpd.server_address[1]}/"

assets = SB.pick(system="win32" if os.name == "nt" else "linux", machine="x86_64", cuda="12.4")
blobs = {a: zip_bytes({x: b"lib" for x in LIBS} if i == 0 else {"cudart64_12.dll": b"rt"}) for i, a in enumerate(assets)}
blobs.update({f: f.encode() * 1000 for f in SB.MODEL_FILES})
for name, data in blobs.items():
    with open(os.path.join(served, name), "wb") as f:
        f.write(data)
SB.BASE = SB.MODEL_REPO = url
SB.HERE, SB.RUNTIME = pack, os.path.join(pack, "runtime")
SB.pick = lambda cpu=False: list(assets)
for name, data in blobs.items():
    (SB.SHA if name in assets else SB.MODEL_SHA)[name] = hashlib.sha256(data).hexdigest()
    (SB.SIZE if name in assets else SB.MODEL_SIZE)[name] = len(data)

try:
    have = lambda f: os.path.exists(os.path.join(llm, f))
    todo = SB.plan(True, False, llm, have, is_runtime)
    check([t[0] for t in todo] == assets + SB.MODEL_FILES, f"plan lists runtime and model: {[t[0] for t in todo]}")
    check(sum(t[2] for t in todo) == sum(len(b) for b in blobs.values()), "plan sizes add up")

    with open(os.path.join(served, assets[0]), "wb") as f:
        f.write(blobs[assets[0]] + b"x")
    try:
        SB.install(True, False, llm, have, None, None, is_runtime)
        check(False, "wrong sha256 stops the install")
    except RuntimeError as e:
        check("sha256" in str(e), f"wrong sha256 stops the install: {e}")
    check(os.path.exists(os.path.join(pack, "downloads", assets[0] + ".bad")), "the wrong file is kept as .bad")
    check(not is_runtime(SB.RUNTIME), "nothing unpacked from it")

    with open(os.path.join(served, assets[0]), "wb") as f:
        f.write(blobs[assets[0]])
    seen, phases = [], []
    SB.install(True, False, llm, have, lambda name, d, t: seen.append((name, d, t)), phases.append, is_runtime)
    check(is_runtime(SB.RUNTIME), "runtime unpacked into runtime/ (top folder of the archive dropped)")
    check(all(have(f) for f in SB.MODEL_FILES), "model files in the LLM folder")
    check({s[0] for s in seen} == set(blobs), "progress for every file")
    check(all(d <= t for _, d, t in seen) and seen[-1][1] == seen[-1][2], "progress ends at the size")
    check(any(p.startswith("Checking") for p in phases) and any(p.startswith("Unpacking") for p in phases), f"phases: {phases[:4]} …")
    check(not [f for f in os.listdir(os.path.join(pack, "downloads")) if not f.endswith(".bad")], "the archives are removed after unpacking")
    check(SB.plan(True, False, llm, have, is_runtime) == [], "nothing left to fetch afterwards")
finally:
    httpd.shutdown()
    shutil.rmtree(root, ignore_errors=True)

print(f"{n - bad}/{n} passed")
sys.exit(1 if bad else 0)
