import importlib.util
import os
import sys

import torch

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("memory_guard", os.path.join(PACK, "memory_guard.py"))
mg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mg)
GB = mg.GB
n = bad = 0


def check(cond, name):
    global n, bad
    n += 1
    bad += not cond
    print("ok  " if cond else "FAIL", name)


class Fake:
    def __init__(self, total, limit, gives):
        self.total, self.limit, self.gives, self.calls = total * GB, limit * GB, gives, []

    def read(self):
        return self.total, self.limit

    def steps(self):
        def step(label, amount):
            def run(short):
                self.calls.append(label)
                self.total -= amount * GB
                return amount * GB
            return (label, run)
        return [step(label, a) for label, a in self.gives]


f = Fake(80, 94, [("pins", 10), ("old", 5), ("active", 5), ("models", 20)])
check(mg.ensure(4 * GB, "x", read=f.read, release=f.steps()) == [] and f.calls == [], "room left (80 + 4 + 3 < 94): nothing freed")
f = Fake(90, 94, [("pins", 10), ("old", 5), ("active", 5), ("models", 20)])
done = mg.ensure(4 * GB, "x", read=f.read, release=f.steps())
check(f.calls == ["pins"] and done == [("pins", 10 * GB)], "3 GB short: model pins first, then it stops")
f = Fake(92, 94, [("pins", 2), ("old", 1), ("active", 5), ("models", 20)])
mg.ensure(6 * GB, "x", read=f.read, release=f.steps())
check(f.calls == ["pins", "old", "active"], "pins and old outputs not enough: active outputs next, models stay loaded")


def boom(short):
    raise RuntimeError("no")


f = Fake(92, 94, [("old", 9)])
mg.ensure(4 * GB, "x", read=f.read, release=[("pins", boom)] + f.steps())
check(f.calls == ["old"], "a failing step is skipped, the next one runs")
check(mg.ensure(100 * GB, "x", read=lambda: None, release=[("pins", boom)]) == [], "off Windows (no commit numbers): nothing done")

t = torch.zeros(1024, 1024)
check(mg.tensor_bytes([t, t, {"a": t[:10]}, torch.zeros(10, device="meta")]) == 4 * 2 ** 20, "tensor bytes: each storage once, views and meta tensors not again")


class Node:
    FUNCTION = "go"

    def go(self, image, k=1):
        return (image * k,)


class NodeCM:
    FUNCTION = "go"

    @classmethod
    def go(cls, image):
        return (image + 1,)


seen = []
real = mg.ensure
mg.ensure = lambda need, name="", **kw: seen.append((name, need))
try:
    mg.guard_class(Node)
    mg.guard_class(Node)
    mg.guard_class(NodeCM)
    r = Node().go(t, k=2)
    r2 = NodeCM().go(t)
finally:
    mg.ensure = real
check(torch.equal(r[0], t * 2) and torch.equal(r2[0], t + 1), "wrapped nodes return the same result (method and classmethod)")
check(seen == [("Node", 8 * 2 ** 20), ("NodeCM", 8 * 2 ** 20)], f"the guard runs once per call with twice the input bytes: {seen}")
order = []


class VDA:
    FUNCTION = "process"

    def process(self, images):
        order.append("process")
        return (images + 1,)


class Other:
    FUNCTION = "go"

    def go(self, x):
        return (x,)


maps = {"VideoDepthAnythingProcess": VDA, "Other": Other}
mg.gpu_room_class(VDA, free=lambda: order.append("free"))
mg.gpu_room_class(VDA, free=lambda: order.append("free twice"))
r = VDA().process(t)
check(order == ["free", "process"] and torch.equal(r[0], t + 1), f"VDA: models off the GPU first, same result: {order}")
mg.gpu_room_foreign(maps)
check(not getattr(Other.go, "_ef_gpu_room", False) and getattr(VDA.process, "_ef_gpu_room", False), "only the foreign depth nodes are wrapped")
check(mg.on_prompt({"prompt": {}}) == {"prompt": {}}, "on_prompt leaves the prompt as it is (also without ComfyUI's nodes module)")
c = mg.commit()
check(c is None or (0 < c[0] < c[1]), f"commit numbers of this computer: {None if c is None else (round(c[0] / GB, 1), round(c[1] / GB, 1))} GB")
print(f"{n - bad}/{n} passed")
sys.exit(1 if bad else 0)
