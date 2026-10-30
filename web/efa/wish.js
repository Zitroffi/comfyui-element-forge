import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import { suggest, changes, stillToDo } from "./ui/assist.js";
import { bonsaiStatus, whyNotSeeing } from "./ui/enhance.js";

const SUPPORTED = ["style", "strength", "look", "motion", "contact", "direction", "depth", "start", "end", "object", "light", "glow"];
const WORDS = { look: "look_words", motion: "motion_words", contact: "contact_words" };
const DIRS = { preset: null, up: 0, "up-right": 45, right: 90, "down-right": 135, down: 180, "down-left": 225, left: 270, "up-left": 315 };
const DEPTHS = { "far back": -0.3, back: -0.15, "as placed": 0, front: 0.15, "far front": 0.3 };
let state = null;
let wish = "";

export const canWish = () => !whyNotSeeing();
export function initWish(render) { bonsaiStatus().then(render).catch(() => {}); }

function effectNow() {
  const e = S.activeEffect();
  if (e) return e;
  return { kind: "", style: "", where: { a: null, b: null, word: "" }, dir: null, depth: 0, strength: "normal",
    text: { what: "", look: "", motion: "", contact: "" }, timing: { start: 0, end: null }, look: { light: 2, glow: 2, tint: null } };
}

async function ask(x) {
  const sh = S.getShot();
  state = { status: "busy", wish };
  x.render();
  try {
    const e = effectNow();
    const { proposal } = await suggest(e, sh.clip, wish, () => true);
    const list = changes(e, proposal, sh.clip).filter((c) => SUPPORTED.includes(c.key));
    state = { status: "ready", wish, proposal, list, note: String(proposal.note || "").slice(0, 200) };
  } catch (err) {
    state = { status: "failed", wish, error: err.message };
  }
  x.render();
}

function apply(x) {
  const { proposal: p, list } = state;
  const keys = new Set(list.map((c) => c.key));
  const to = Object.fromEntries(list.map((c) => [c.key, c.to]));
  if (keys.has("style")) { const [kind, style] = p.style.split("/"); x.chooseStyle(kind, style); }
  if (keys.has("strength")) x.setFx("strength", to.strength);
  for (const k of ["look", "motion", "contact"]) if (keys.has(k)) x.setFx(WORDS[k], to[k]);
  if (keys.has("object")) x.setFx("object_word", to.object);
  S.change((sh) => {
    const e = sh.effects.find((y) => y.id === sh.active);
    if (!e) return;
    if (keys.has("direction")) e.dir = DIRS[to.direction];
    if (keys.has("depth")) e.depth = DEPTHS[to.depth];
    if (keys.has("start")) e.timing.start = to.start;
    if (keys.has("end")) e.timing.end = to.end;
    if (keys.has("light")) e.adv = { ...e.adv, Light: to.light !== "off" };
    if (keys.has("glow")) e.adv = { ...e.adv, Glow: to.glow !== "off" };
  }, "wish");
  const e = S.activeEffect();
  state = { status: "done", todo: e ? stillToDo(e) : "" };
  x.render();
}

export function suggestButton(x, text) {
  if (!canWish()) return null;
  const t = String(text || "").trim();
  return x.h("button", { class: "btn small", disabled: state?.status === "busy" || !t, title: "Bonsai reads your words and the clip and proposes a style and its words",
    onclick: () => { wish = t; ask(x); } }, state?.status === "busy" ? "Thinking…" : "Suggest");
}
export function wishResults(x) {
  const { h, link, note } = x;
  const rows = [];
  if (state?.status === "failed") rows.push(note("err", state.error));
  if (state?.status === "ready") {
    rows.push(h("div", { class: "field" }, h("div", { class: "label" }, "This is what I would set"),
      state.list.length ? h("ul", { class: "small" }, ...state.list.map((c) => h("li", {}, h("span", { class: "strong" }, c.label), ": ",
        h("span", { class: "muted" }, String(c.from ?? "–")), " → ", String(c.to ?? "until the end")))) : h("p", { class: "muted small" }, "Nothing to change."),
      state.note ? h("p", { class: "muted small" }, state.note) : null,
      h("div", { class: "row gap" },
        state.list.length ? h("button", { class: "btn small", onclick: () => apply(x) }, "Apply") : null,
        h("button", { class: "btn ghost small", onclick: () => { state = null; x.render(); } }, "Discard"))));
  }
  if (state?.status === "done") rows.push(h("p", { class: "muted small" }, state.todo || "Applied.", " ", link("OK", () => { state = null; x.render(); })));
  return rows;
}
export function wishRows(x) {
  const { h, link, note } = x;
  const ok = canWish();
  const input = h("input", { class: "text", placeholder: "e.g. blue sparks flying off the skateboard", "aria-label": "Describe what you want",
    value: wish, disabled: !ok, oninput: (ev) => { wish = ev.target.value; },
    onkeydown: (ev) => { if (ev.key === "Enter" && wish.trim()) { ev.preventDefault(); ask(x); } } });
  const rows = [h("div", { class: "field" }, h("div", { class: "label" }, "Describe what you want"),
    h("div", { class: "row gap" }, input,
      h("button", { class: "btn small", disabled: !ok || state?.status === "busy" || !wish.trim(), onclick: () => ask(x) },
        state?.status === "busy" ? "Thinking…" : "Suggest")),
    !ok ? h("p", { class: "muted small" }, `Off: ${whyNotSeeing()}. Pick a tile instead.`) : null)];
  if (state?.status === "failed") rows.push(note("err", state.error));
  if (state?.status === "ready") {
    rows.push(h("div", { class: "field" }, h("div", { class: "label" }, "This is what I would set"),
      state.list.length ? h("ul", { class: "small" }, ...state.list.map((c) => h("li", {}, h("span", { class: "strong" }, c.label), ": ",
        h("span", { class: "muted" }, String(c.from ?? "–")), " → ", String(c.to ?? "until the end")))) : h("p", { class: "muted small" }, "Nothing to change."),
      state.note ? h("p", { class: "muted small" }, state.note) : null,
      h("div", { class: "row gap" },
        state.list.length ? h("button", { class: "btn small", onclick: () => apply(x) }, "Apply") : null,
        h("button", { class: "btn ghost small", onclick: () => { state = null; x.render(); } }, "Discard"))));
  }
  if (state?.status === "done") rows.push(h("p", { class: "muted small" }, state.todo || "Applied.", " ", link("OK", () => { state = null; x.render(); })));
  return rows;
}
