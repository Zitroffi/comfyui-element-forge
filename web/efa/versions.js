import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import * as R from "./ui/run.js";

const pending = [];
const ROLL = ["box", "adv", "depth", "dir", "where", "paint", "groups"];

export function noteQueued(fx, e, shot) {
  if (!e) return;
  const { mode: _ui, ...values } = fx || {};
  pending.push({ id: e.id, fx: values, effect: JSON.parse(JSON.stringify(e)), night: !!shot?.night });
  if (pending.length > 12) pending.shift();
}
export function takeRecipe(effectId) {
  const i = pending.findIndex((p) => p.id === effectId);
  return i < 0 ? null : pending.splice(i, 1)[0];
}

function changed(v, fx, e) {
  const r = v.recipe;
  if (!r?.fx) return false;
  const { mode: _ui, ...now } = fx;
  if (Object.entries(r.fx).some(([k, val]) => JSON.stringify(now[k]) !== JSON.stringify(val))) return true;
  return ROLL.some((k) => JSON.stringify(e[k] ?? null) !== JSON.stringify(r.effect?.[k] ?? null));
}
function useSettings(x, e, v, n) {
  const r = v.recipe;
  const [kind, style] = String(r.fx.effect_style || "").split("/");
  if (!P.styleDef(kind, style)) { x.say(`Version ${n} was made with ${r.fx.effect_style}, which this version does not have.`); return; }
  if (e.kind !== kind || e.style !== style) x.chooseStyle(kind, style);
  for (const [k, val] of Object.entries(r.fx)) if (k !== "effect_style") x.setFx(k, val);
  S.change((sh) => {
    const y = sh.effects.find((z) => z.id === e.id);
    if (!y) return;
    for (const k of ROLL) if (k in r.effect) y[k] = JSON.parse(JSON.stringify(r.effect[k]));
    y.timing = { ...y.timing, start: r.effect.timing?.start ?? y.timing.start };
    if (P.styleDef(kind, style)?.dir === "dissolve" && r.effect.timing && "end" in r.effect.timing) y.timing.end = r.effect.timing.end;
  }, "use-version");
  x.say(v.clip !== S.getShot().clip?.name ? `Settings of version ${n} are back; it was made from another clip (${v.clip}). Ctrl+Z undoes it.`
    : `Settings of version ${n} are back. Ctrl+Z undoes it.`);
}
function show(e, v) {
  if (v.status !== "done") return;
  if (S.ui.compare === v.id) S.setUI({ compare: false });
  S.showVersion(e.id, v.id);
  if (v.unseen) S.updateVersion(e.id, v.id, { unseen: false });
  if (v.comp) S.setUI({ media: { url: v.comp, live: v.preview || null, label: "Result" }, compare: false, pass: null });
}
const PASS_NAME = { light: "Light pass", glow: "Glow pass", normals: "Normals" };
const PASS_TIP = { light: "The light the effect throws onto the scene: needed for Light on the scene (about a minute, no AI)",
  glow: "The glow as its own EXR layer for compositing (the live glow works without it)", normals: "Surface normals of the clip as EXR, for relighting in compositing" };

export function nextStep() {
  const e = S.activeEffect();
  if (!e) return "export";
  if (S.versionsOf(e.id).some((v) => v.unseen)) return "show";
  const shown = S.shownOf(e.id);
  return shown?.status === "done" && shown.quality === "preview" ? "final" : "export";
}

export function versionRows(x) {
  const { h, link } = x;
  const e = S.activeEffect();
  if (!e) return [];
  const vs = S.versionsOf(e.id);
  if (!vs.length) return [];
  const shown = S.shownOf(e.id);
  const busy = R.running(e.id);
  const kids = [h("div", { class: "versions" }, h("span", { class: "label" }, "Versions"),
    ...vs.map((v, i) => h("button", { class: `ver ${v.status}` + (shown?.id === v.id ? " on" : ""), "aria-pressed": String(shown?.id === v.id),
      title: `${v.status === "done" ? "Show" : v.status} version ${i + 1}${v.quality === "preview" ? " (preview)" : ""}${v.error ? `: ${v.error}` : ""}`,
      onclick: () => show(e, v) }, String(i + 1) + (v.quality === "preview" ? "·p" : ""), v.unseen ? h("span", { class: "new-dot", "aria-label": "new" }) : null)),
    ...vs.filter((v) => v.unseen).slice(-1).map((v) => h("button", { class: "btn small primary", onclick: () => show(e, v) }, `Version ${vs.indexOf(v) + 1} is ready · Show`)))];
  if (busy) kids.push(h("div", { class: "busy" }, h("span", { class: "spinner", "aria-hidden": "true" }), h("span", { role: "status" }, busy.step || busy.phase || "Working…"),
    link("Stop", () => R.stop(e.id))));
  if (!shown || shown.status !== "done") return kids;
  const n = vs.indexOf(shown) + 1;
  const acts = [];
  if (shown.quality === "preview") acts.push(h("button", { class: "btn small" + (nextStep() === "final" ? " primary" : ""), disabled: !!busy,
    title: "Goes on from this preview with LTX's second pass (latent upscaler × 2): twice the size, sharper, same motion. Comes as a new version with all passes.",
    onclick: async () => {
      try { if (await R.generate(e, { from: shown })) x.say(`Making version ${n} final. It comes as a new version.`); } catch (err) { x.say(`ComfyUI did not take the job: ${err.message}`, true); }
      x.render();
    } }, `Make version ${n} final (× 2)`));
  const miss = R.missingPasses(shown);
  const add = async (passes) => { try { await R.addPasses(e, shown, passes); } catch (err) { x.say(`The passes could not be added (${err.message}).`, true); } x.render(); };
  if (miss.length) acts.push(h("span", { class: "muted small" }, "Add"), ...miss.map((p) => h("button", { class: "btn small", disabled: !!busy || !!shown.adding,
    title: PASS_TIP[p], onclick: () => add([p]) }, PASS_NAME[p])), miss.length > 1 ? h("button", { class: "btn small", disabled: !!busy || !!shown.adding, onclick: () => add(miss) }, "All") : null);
  if (shown.addError) acts.push(h("span", { class: "muted small", role: "alert" }, `Adding passes failed: ${shown.addError}`));
  if (changed(shown, x.fx(), e)) acts.push(h("button", { class: "btn small", onclick: () => useSettings(x, e, shown, n),
    title: "Brings back the style, the words, the seed and the place this version was made with. Light, glow, colour and placement in Scene & finish stay." },
  `Use the settings of version ${n}`));
  const others = vs.filter((v) => v.status === "done" && v.id !== shown.id);
  if (others.length) {
    acts.push(h("span", { class: "muted small" }, `Compare ${n} with`), ...others.map((v) => {
      const on = S.ui.compare === v.id;
      return h("button", { class: "ver" + (on ? " on" : ""), "aria-pressed": String(on), disabled: !shown.preview,
        title: !shown.preview ? "Wait for the live view" : on ? "Stop comparing" : `Version ${vs.indexOf(v) + 1} left of the line, version ${n} right of it`,
        onclick: () => S.setUI(on ? { compare: false } : { media: { url: shown.comp, live: shown.preview, label: "Result" }, compare: v.id, pass: null }) }, String(vs.indexOf(v) + 1));
    }));
    if (typeof S.ui.compare === "string") acts.push(link("Stop comparing", () => S.setUI({ compare: false })));
  }
  if (acts.length) kids.push(h("div", { class: "ver-actions" }, ...acts));
  return kids;
}
