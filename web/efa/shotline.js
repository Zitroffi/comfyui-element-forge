import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import { frameBox, genWindow, usesGuide } from "./ui/run.js";
import { bonsaiStatus, whyNotSeeing, describeShot } from "./ui/enhance.js";

const MIN_SIDE = 512;
let api = null;
let pending = null;
const hasBonsai = () => !whyNotSeeing();

export function initShotLine(a) { api = a; bonsaiStatus().then(() => S.setUI({ shotLine: S.ui.shotLine || null })).catch(() => {}); }
const sentence = () => String(api?.fx?.().shot_sentence || "").trim();

export function areaOf(e, sh = S.getShot()) {
  const c = sh.clip, st = P.styleDef(e.kind, e.style);
  const b = c && st ? frameBox(e, c) : null;
  if (!b) return null;
  const w0 = genWindow(st, b, usesGuide(st, e));
  const w = Math.min(c.width, Math.max(MIN_SIDE, w0.w)), h = Math.min(c.height, Math.max(MIN_SIDE, w0.h));
  const x = Math.min(Math.max(0, w0.x + w0.w / 2 - w / 2), c.width - w), y = Math.min(Math.max(0, w0.y + w0.h / 2 - h / 2), c.height - h);
  return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
}
export function keyOf(e, sh = S.getShot()) {
  const a = areaOf(e, sh);
  return JSON.stringify([sh.clip?.name || null, Math.round((e.timing?.start || 0) * 10) / 10, a ? [a.x, a.y, a.w, a.h].map((v) => Math.round(v / 16)) : null]);
}
export function wanted() {
  const e = S.activeEffect(), sh = S.getShot();
  return !!(e && sh.clip && P.canPaintIn(P.styleDef(e.kind, e.style)) && P.inScene(e));
}
export function lineState() {
  const sh = S.getShot(), e = S.activeEffect();
  const ui = S.ui.shotLine;
  const why = whyNotSeeing(), bonsai = !why;
  if (ui?.status === "busy" || ui?.status === "failed") return { ...ui, bonsai, why };
  const t = sentence();
  if (!t) return { status: "none", bonsai, why };
  if (sh.sceneLock) return { status: "own", bonsai, why };
  return { status: e && sh.sceneKey === keyOf(e, sh) ? "auto" : "stale", bonsai, why };
}
export function typedByHand() {
  if (!S.getShot().sceneLock) S.change((sh) => { sh.sceneLock = true; }, "scene-line");
}
export async function describe() {
  const e = S.activeEffect(), sh = S.getShot();
  if (!e || !sh.clip) throw new Error("pick a clip and an effect first");
  const key = keyOf(e, sh);
  if (pending?.key === key) return pending.promise;
  const a = areaOf(e, sh);
  S.setUI({ shotLine: { status: "busy" } });
  const promise = (async () => {
    try {
      await bonsaiStatus();
      if (!hasBonsai()) throw new Error(`Write the sentence yourself: ${whyNotSeeing()}.`);
      const t = await describeShot(sh.clip.name, e.timing?.start || 0, a ? [a.x, a.y, a.w, a.h] : null);
      api?.setFx("shot_sentence", t);
      S.change((x) => { x.sceneLock = false; x.sceneKey = key; }, "scene-line");
      S.setUI({ shotLine: null });
      return t;
    } catch (err) {
      S.setUI({ shotLine: { status: "failed", error: err.message } });
      throw err;
    } finally {
      pending = null;
    }
  })();
  pending = { key, promise };
  return promise;
}
export async function beforeRun(onWrite = () => {}) {
  if (!wanted()) return false;
  const sh = S.getShot(), e = S.activeEffect();
  if (sh.sceneLock && sentence()) return false;
  if (sh.sceneKey === keyOf(e, sh) && sentence()) return false;
  await bonsaiStatus();
  if (!hasBonsai()) return false;
  onWrite();
  try { await describe(); } catch { return false; }
  return true;
}
