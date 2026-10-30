import * as S from "./state.js";
import * as C from "./comfy.js";
import { styleDef, effectDef } from "./presets.js";
import { uid } from "./lib.js";
import { frameBox, genWindow, usesGuide, inWindow } from "./run.js";

export const LEVELS = ["Off", "Low", "Medium", "High"];
const LIGHT = [0, 0.5, 1, 1.6];
const GLOW = [-30, -2, -1, 0];
const LIT = [0, 0.5, 1, 2];
const GLOW_SIZE = [90, 200, 420];
export const TINTS = ["#ffb347", "#ff6a3d", "#ffe9a8", "#9fd0ff", "#b48cff", "#7dffb0"];

const runFolder = (v) => `element-forge/${v.run}`;

export function postSettings(e) {
  const st = styleDef(e.kind, e.style);
  const clip = S.getShot().clip;
  const pv = clip ? pivotOf(e, clip) : { x: null, y: null };
  const over = e.look.blend ? e.look.blend === "over" : st?.dir === "dissolve" || st?.settings?.["Blend on black (add = light, over = solid)"] === "over";
  const t = e.look.tint;
  const mute = e.look.mute || {};
  return {
    element: { mode: over ? "over" : "add", offset_x: e.place.dx, offset_y: e.place.dy, scale: e.place.scale, stretch: e.place.stretch ?? 1, rotation: e.place.rot || 0,
      pivot_x: pv.x, pivot_y: pv.y, visible: !mute.element,
      ...(t ? { color: t, color_amount: 0.6 } : {}) },
    light: { strength: mute.light ? 0 : LIGHT[e.look.light] ?? 1, ...(t ? { color: t, color_amount: 0.6 } : {}) },
    glow: { exposure: mute.glow ? -30 : GLOW[e.look.glow] ?? -1, radius: GLOW_SIZE[e.look.size ?? 1] ?? 200, ...(t ? { color: t, color_amount: 0.8 } : {}) },
    lit: { others: LIT[e.look.lit] ?? 0 },
  };
}
export function commonSettings(shot = S.getShot()) {
  const g = shot?.grade || {};
  return { plate: { exposure: +g.exposure || 0, temperature: +g.temperature || 0, saturation: Number.isFinite(+g.saturation) ? +g.saturation : 1 },
    dof: { amount: +g.blur || 0, range: +g.blurRange || 0.15, focus: -1 } };
}
export function timingFrames(e, fps) {
  const T = e.timing;
  return { start: Math.round(T.start * fps), end: T.end == null ? 1e9 : Math.round(T.end * fps),
    fade_in: Math.round(T.fadeIn * fps), fade_out: Math.round(T.fadeOut * fps) };
}
export function weightAt(e, fps, f) {
  const { start: a, end: b, fade_in: fi, fade_out: fo } = timingFrames(e, fps);
  if (f < a || f > b) return 0;
  let w = 1;
  if (fi > 0) w = Math.min(w, (f - a + 1) / fi);
  if (fo > 0) w = Math.min(w, (b - f + 1) / fo);
  return Math.max(0, Math.min(1, w));
}

export const EASES = { even: (u) => u, in: (u) => u * u, out: (u) => 1 - (1 - u) ** 2, smooth: (u) => u * u * (3 - 2 * u) };
export const EASE_NAMES = [["even", "Linear", "Same speed all the way to the next key (Linear in After Effects)"],
  ["in", "Slow start", "Starts slowly, then speeds up (like Easy Ease Out on this key in After Effects)"],
  ["out", "Slow end", "Slows down towards the next key (like Easy Ease In on the next key in After Effects)"],
  ["smooth", "Easy ease", "Slow start and slow end (Easy Ease in After Effects)"]];
export function keyAt(keys, t, get) {
  const ks = [...keys].sort((a, b) => a.t - b.t);
  if (t <= ks[0].t) return get(ks[0]);
  for (let i = 0; i < ks.length - 1; i++) {
    const k0 = ks[i], k1 = ks[i + 1];
    if (t < k1.t) return get(k0) + (get(k1) - get(k0)) * (EASES[k0.ease] || EASES.even)((t - k0.t) / Math.max(1e-9, k1.t - k0.t));
  }
  return get(ks.at(-1));
}
export const animated = (e, lane) => !!e.keys?.[lane]?.length;
export function placeAt(e, tAbs) {
  if (!animated(e, "place")) return { dx: e.place.dx, dy: e.place.dy, scale: e.place.scale || 1, stretch: e.place.stretch ?? 1, rot: e.place.rot || 0 };
  const ks = e.keys.place, t = tAbs - e.timing.start;
  return { dx: keyAt(ks, t, (k) => k.dx), dy: keyAt(ks, t, (k) => k.dy), scale: keyAt(ks, t, (k) => k.scale), stretch: keyAt(ks, t, (k) => k.stretch ?? 1),
    rot: keyAt(ks, t, (k) => k.rot) };
}
export const brightAt = (e, tAbs) => (animated(e, "bright") ? Math.max(0, keyAt(e.keys.bright, tAbs - e.timing.start, (k) => k.v)) : e.look.bright ?? 1);
export function resultBox(e, clip) {
  const rec = S.shownOf(e.id)?.recipe;
  const r = (rec?.where ? rec : rec?.effect?.where ? rec.effect : null) || e;
  const b = frameBox(r, clip);
  if (!b) return { x: 0, y: 0, w: clip.width, h: clip.height };
  const st = styleDef(r.kind, r.style);
  return st && (st.placement !== "point" || inWindow(st, r)) ? genWindow(st, b, usesGuide(st, r)) : b;
}
export function pivotOf(e, clip) { const b = resultBox(e, clip); return { x: b.x + b.w / 2, y: b.y + b.h / 2 }; }
function keyTime(e, tAbs, fps) {
  const c = S.getShot().clip;
  const end = (e.timing.end ?? (c ? Math.min(c.seconds, 161 / c.fps) : Infinity)) - e.timing.start;
  return Math.min(Math.max(0, Math.round((tAbs - e.timing.start) * fps) / fps), Math.max(0, end));
}
export function keyHere(e, lane, tAbs, fps) {
  const t = keyTime(e, tAbs, fps);
  return (e.keys?.[lane] || []).find((k) => Math.abs(k.t - t) < 0.5 / fps) || null;
}
function upsert(e, lane, tAbs, fps, vals) {
  const k = keyHere(e, lane, tAbs, fps);
  if (k) { Object.assign(k, vals); return; }
  e.keys[lane].push({ id: uid(), t: +keyTime(e, tAbs, fps).toFixed(4), ease: "even", ...vals });
  e.keys[lane].sort((a, b) => a.t - b.t);
}
export function setPlace(e, p, tAbs, fps) {
  if (animated(e, "place")) upsert(e, "place", tAbs, fps, { ...placeAt(e, tAbs), ...p });
  else e.place = { ...e.place, ...p };
}
export function setBright(e, v, tAbs, fps) {
  if (animated(e, "bright")) upsert(e, "bright", tAbs, fps, { v });
  else e.look.bright = v;
}
export function keysFrames(e, fps) {
  const f = (k) => Math.round((e.timing.start + k.t) * fps);
  const out = {};
  if (animated(e, "place")) {
    for (const [name, get] of [["offset_x", (k) => k.dx], ["offset_y", (k) => k.dy], ["scale", (k) => k.scale], ["stretch", (k) => k.stretch ?? 1], ["rotation", (k) => k.rot]]) {
      out[name] = e.keys.place.map((k) => [f(k), get(k), k.ease || "even"]);
    }
  }
  if (animated(e, "bright")) out.brightness = e.keys.bright.map((k) => [f(k), k.v, k.ease || "even"]);
  else if ((e.look.bright ?? 1) !== 1) out.brightness = [[0, e.look.bright, "even"]];
  return out;
}

const previews = new Map();
export function ensurePreview(effectId, v) {
  if (v.preview || v.status !== "done") return Promise.resolve(v.preview || null);
  if (previews.has(v.id)) return previews.get(v.id);
  const p = new Promise((resolve) => {
    const graph = { "1": { class_type: "EFPassPreview", inputs: { run_folder: runFolder(v), long_side: 768, fps: 0, full_size: true } } };
    C.connectSocket();
    C.queue(graph, {
      onDone: (r) => {
        previews.delete(v.id);
        if (r.status !== "done") { S.updateVersion(effectId, v.id, { previewError: r.error || r.status }); resolve(null); return; }
        const url = `/element-forge/media/output/element-forge/${encodeURIComponent(v.run)}/app_preview/manifest.json?v=${Date.now().toString(36)}`;
        S.updateVersion(effectId, v.id, { preview: url, previewError: null });
        resolve(url);
      },
    }).catch((err) => { previews.delete(v.id); S.updateVersion(effectId, v.id, { previewError: err.message }); resolve(null); });
  });
  previews.set(v.id, p);
  return p;
}

export const exports_ = [];
let notify = () => {};
export const onExport = (fn) => (notify = fn);
export const runningExport = () => exports_.find((x) => x.status === "running") || null;

export const EXPORT_FILES = { mp4: "comp.mp4", prores: "comp.mov", h265: "comp_h265.mp4", png8: "comp_#####.png", png16: "comp_#####.png", exr: "comp_#####.exr" };
export async function exportShot(kind, { name = "", exr = false, layers: withLayers = false, range = null, hdr = false } = {}) {
  const shot = S.getShot();
  const fps = shot.clip.fps;
  const layers = shot.effects.map((e) => ({ e, v: S.shownOf(e.id) })).filter((x) => x.v?.status === "done")
    .map(({ e, v }) => ({ run_folder: runFolder(v), settings: postSettings(e), ...timingFrames(e, fps), keys: keysFrames(e, fps),
      name: effectDef(e.kind)?.name || e.kind || "effect" }));
  if (!layers.length) throw new Error("Make at least one effect first.");
  const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(4, 12);
  const safe = (name || shot.clip.name.replace(/\.[^.]+$/, "")).replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 40) || "shot";
  const out = `element-forge/app-export-${safe}-${stamp}-${uid().slice(0, 3)}`;
  const format = kind;
  const graph = { "1": { class_type: "EFFinishStack", inputs: { layers: JSON.stringify(layers), common: JSON.stringify(commonSettings()), out_folder: out,
    write_exr: exr, fps: 0, chunk: 8, write_layers: withLayers, comp_name: safe.replaceAll("_", " "),
    format, frame_start: range?.[0] ?? 0, frame_end: range?.[1] ?? -1, hdr: !!hdr && format === "h265" } } };
  const job = { id: uid(), kind, status: "running", started: Date.now(), out, error: null, value: 0, max: 0, file: EXPORT_FILES[format], layers: withLayers, hdr: !!hdr };
  exports_.push(job);
  notify();
  try {
    C.connectSocket();
    job.promptId = await C.queue(graph, {
      onProgress: (val, max) => { job.value = val; job.max = max; notify(); },
      onDone: (r) => {
        job.status = r.status === "done" ? "done" : r.status;
        job.error = r.error || null;
        job.comp = `/element-forge/media/output/${out.split("/").map(encodeURIComponent).join("/")}/comp.mp4`;
        notify();
      },
    });
  } catch (err) {
    job.status = "failed";
    job.error = err.message + (err.detail ? ` (${err.detail})` : "");
    notify();
  }
  return job;
}
