import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import * as R from "./ui/run.js";
import { icon } from "./ui/icons.js";

const SHARED = ["mode", "night", "sharper_2x"];
let fxOf = () => ({}), setAll = () => false;
let defaults = null;
let lastActive;

const own = (values) => Object.fromEntries(Object.entries(values || {}).filter(([k]) => !SHARED.includes(k)));

async function loadDefaults() {
  if (defaults) return defaults;
  const r = await fetch("/object_info/EFAppEffect");
  if (!r.ok) throw new Error(`object_info ${r.status}`);
  const node = (await r.json()).EFAppEffect || {};
  const d = {};
  for (const part of ["required", "optional"]) for (const [k, spec] of Object.entries(node.input?.[part] || {})) {
    if (spec?.[1] && "default" in spec[1]) d[k] = spec[1].default;
    else if (Array.isArray(spec?.[0]) && spec[0].length) d[k] = spec[0][0];
  }
  return (defaults = d);
}

function sync(reason) {
  const sh = S.getShot(), now = sh.active;
  if (now === lastActive) return;
  const prev = lastActive;
  lastActive = now;
  if (reason === "replace" || prev === undefined) return;
  const values = own(fxOf());
  if (prev && sh.effects.some((e) => e.id === prev)) S.applyContext((s) => { const e = s.effects.find((x) => x.id === prev); if (e) e.fx = values; });
  const next = sh.effects.find((e) => e.id === now);
  if (next?.fx) setAll(next.fx);
}

export function initEffects(a) {
  fxOf = a.fx;
  setAll = a.setAll;
  lastActive = S.getShot().active;
  S.subscribe(sync);
  loadDefaults().catch(() => {});
}

function keep() {
  const values = own(fxOf());
  S.applyContext((s) => { const e = s.effects.find((x) => x.id === s.active); if (e) e.fx = values; });
}
function showChosen(id) {
  const v = S.shownOf(id);
  S.setUI(v?.status === "done" && v.comp ? { media: { url: v.comp, live: v.preview || null, label: "Result" }, compare: false, pass: null }
    : { media: null, compare: false, pass: null });
}
function choose(x, id) {
  if (id === S.getShot().active) return;
  x.flush();
  keep();
  S.change((sh) => { sh.active = id; }, "select");
  showChosen(id);
}
async function add(x) {
  x.flush();
  let d;
  try { d = await loadDefaults(); } catch (err) { x.say(`A new effect needs the Effect node's defaults (${err.message}).`); return; }
  keep();
  const e = S.blankEffect(null, null);
  e.fresh = true;
  const { effect_style: _keep, ...rest } = own(d);
  e.fx = { ...rest, effect_style: fxOf().effect_style };
  S.change((sh) => { sh.effects.push(e); sh.active = e.id; }, "add-effect");
  S.setUI({ media: null, compare: false, pass: null });
}
function remove(x, id) {
  if (R.running(id)) { x.say("This effect is still being made. Stop it first."); return; }
  const sh = S.getShot(), i = sh.effects.findIndex((e) => e.id === id);
  if (i < 0 || sh.effects.length < 2) return;
  x.flush();
  keep();
  const next = sh.effects[i === 0 ? 1 : i - 1].id, was = sh.active === id;
  S.change((s) => { s.effects.splice(s.effects.findIndex((e) => e.id === id), 1); if (was) s.active = next; }, "remove-effect");
  if (was) showChosen(next);
}

export function effectStrip(x) {
  const { h } = x;
  const sh = S.getShot();
  if (!sh.clip) return [];
  const name = (e, i) => { const d = P.effectDef(e.kind); return d && !e.fresh ? `${i + 1} · ${d.name}` : `Effect ${i + 1}`; };
  return [h("div", { class: "fx-strip", role: "tablist", "aria-label": "Effects in this clip" },
    ...sh.effects.map((e, i) => {
      const on = e.id === sh.active, v = S.versionsOf(e.id), busy = R.running(e.id);
      return h("div", { class: "fx-chip" + (on ? " on" : ""), role: "presentation" },
        h("button", { role: "tab", "aria-selected": String(on), class: "fx-name", onclick: () => choose(x, e.id),
          title: `${name(e, i)}${v.length ? `: ${v.length} version${v.length > 1 ? "s" : ""}` : ""}` },
        busy ? h("span", { class: "dot run", title: "Working" }) : v.some((y) => y.unseen) ? h("span", { class: "new-dot", "aria-label": "new" }) : null, name(e, i)),
        sh.effects.length > 1 ? h("button", { class: "fx-x", title: `Remove ${name(e, i)}`, "aria-label": `Remove ${name(e, i)}`, onclick: () => remove(x, e.id) }, icon("close")) : null);
    }),
    h("button", { class: "fx-add", title: "Add another effect to this clip: a run of its own, laid over the others", onclick: () => add(x) }, icon("plus"), "Effect"))];
}
