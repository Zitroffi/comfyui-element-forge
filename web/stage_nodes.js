import { app } from "../../scripts/app.js";

const ACCENT = { color: "#5a3a14", bgcolor: "#80541e" };
const ACCENTED = new Set(["EFForgeElement", "EFForgeExport"]);

function source(node, input) {
  const link = node.inputs?.find((i) => i.name === input)?.link;
  const l = link != null ? (node.graph?.links?.get?.(link) ?? node.graph?.links?.[link]) : null;
  return l ? node.graph.getNodeById(l.origin_id) ?? node.graph.getNodeById(Number(l.origin_id)) : null;
}

function clipOf(track) {
  const shot = source(track, "shot");
  if (!shot) return null;
  const widget = (n, names) => n?.widgets?.find((w) => names.includes(w.name))?.value;
  const video = widget(source(shot, "video"), ["file", "video"]);
  if (typeof video === "string" && video) return { name: video, still: false };
  const picture = widget(source(shot, "picture"), ["image"]);
  if (typeof picture === "string" && picture) return { name: picture.replace(/ \[input\]$/, ""), still: true };
  return null;
}

function addPicker(node) {
  const box = document.createElement("div");
  Object.assign(box.style, { position: "relative", width: "100%", height: "100%", background: "#111", borderRadius: "6px", overflow: "hidden", cursor: "crosshair" });
  const video = document.createElement("video");
  Object.assign(video, { muted: true, preload: "auto", playsInline: true });
  const img = document.createElement("img");
  for (const el of [video, img]) Object.assign(el.style, { position: "absolute", inset: "0", width: "100%", height: "100%", objectFit: "contain", display: "none", pointerEvents: "none" });
  const hint = document.createElement("div");
  Object.assign(hint.style, { position: "absolute", left: "6px", bottom: "4px", font: "11px sans-serif", color: "#ddd", textShadow: "0 0 3px #000", pointerEvents: "none" });
  hint.textContent = "Click: point A · Shift+click: point B";
  const dot = (label, colour) => {
    const d = document.createElement("div");
    Object.assign(d.style, { position: "absolute", width: "14px", height: "14px", margin: "-7px 0 0 -7px", borderRadius: "50%", border: "2px solid #fff",
      background: colour, font: "bold 9px sans-serif", color: "#000", textAlign: "center", lineHeight: "10px", pointerEvents: "none", display: "none" });
    d.textContent = label;
    return d;
  };
  const da = dot("A", "#ffc83d"), db = dot("B", "#5ad1ff");
  box.append(video, img, da, db, hint);
  const meta = { key: null, w: 0, h: 0 };
  const w = (n) => node.widgets?.find((x) => x.name === n);
  const frame = () => {
    const bw = box.clientWidth, bh = box.clientHeight;
    if (!meta.w || !bw || !bh) return null;
    const s = Math.min(bw / meta.w, bh / meta.h);
    return { x: (bw - meta.w * s) / 2, y: (bh - meta.h * s) / 2, s };
  };
  const place = () => {
    const f = frame();
    for (const [d, px, py] of [[da, "point A x", "point A y"], [db, "point B x", "point B y"]]) {
      const x = w(px)?.value, y = w(py)?.value;
      const on = f && x >= 0 && y >= 0;
      d.style.display = on ? "block" : "none";
      if (on) { d.style.left = `${f.x + x * f.s}px`; d.style.top = `${f.y + y * f.s}px`; }
    }
  };
  const set = (n, v) => { const x = w(n); if (!x) return; x.value = v; x.callback?.(v); };
  box.addEventListener("pointerdown", (e) => {
    const f = frame();
    if (!f) return;
    e.preventDefault();
    e.stopPropagation();
    const r = box.getBoundingClientRect();
    const zoom = r.width / box.clientWidth || 1;
    const x = Math.round(((e.clientX - r.left) / zoom - f.x) / f.s), y = Math.round(((e.clientY - r.top) / zoom - f.y) / f.s);
    if (e.button === 2) { set("point B x", -1); set("point B y", -1); }
    else if (x >= 0 && y >= 0 && x < meta.w && y < meta.h) {
      const p = e.shiftKey ? "point B" : "point A";
      set(`${p} x`, x); set(`${p} y`, y);
    }
    place();
    node.setDirtyCanvas?.(true, true);
  });
  box.addEventListener("contextmenu", (e) => { e.preventDefault(); e.stopPropagation(); });
  const load = async (clip) => {
    const key = clip ? `${clip.still}:${clip.name}` : null;
    meta.key = key;
    meta.w = meta.h = 0;
    video.style.display = img.style.display = "none";
    if (!clip) { video.removeAttribute("src"); place(); return; }
    try {
      const m = await (await fetch(`/element-forge/api/clip-meta?name=${encodeURIComponent(clip.name)}`)).json();
      if (meta.key !== key || !m.width) return;
      meta.w = m.width; meta.h = m.height;
      const url = `/element-forge/media/input/${encodeURIComponent(clip.name)}`;
      if (clip.still) { img.src = url; img.style.display = "block"; }
      else { video.src = url; video.currentTime = 0; video.style.display = "block"; }
    } catch {  }
    place();
  };
  const widget = node.addDOMWidget("first_frame", "ef_points", box, { serialize: false, hideOnZoom: false, getValue: () => null, setValue: () => {} });
  widget.serialize = false;
  widget.computeLayoutSize = () => ({ minHeight: 220, minWidth: 240 });
  node.widgets.splice(node.widgets.indexOf(widget), 1);
  node.widgets.unshift(widget);
  const tick = () => {
    const c = clipOf(node);
    const key = c ? `${c.still}:${c.name}` : null;
    if (key !== meta.key) load(c); else place();
  };
  const timer = setInterval(tick, 400);
  const removed = node.onRemoved;
  node.onRemoved = function (...a) { clearInterval(timer); return removed?.apply(this, a); };
  tick();
}

function setup(node) {
  if (node.__efStage || !String(node.comfyClass || "").startsWith("EFForge")) return;
  node.__efStage = true;
  if (node.comfyClass === "EFForgeTrack") addPicker(node);
  if (ACCENTED.has(node.comfyClass) && !node.color) {
    Object.assign(node, ACCENT);
    node.setDirtyCanvas?.(true, true);
  }
}

app.registerExtension({
  name: "ElementForge.StageNodes",
  nodeCreated(node) { setup(node); },
  loadedGraphNode(node) { setup(node); },
});
