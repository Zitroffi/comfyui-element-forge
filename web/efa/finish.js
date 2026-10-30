import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import * as L from "./ui/look.js";
import { uid, getJSON } from "./ui/lib.js";
import { icon } from "./ui/icons.js";
import { playhead } from "./ui/stage.js";

const RUN_DIR = /^element-forge\/([^/]+)$/;
const ALL_PASSES = ["plate", "element", "light", "glow", "depth", "normals", "mask"], PREVIEW_PASSES = ["plate", "element", "depth", "mask"];

export function addRun(info, light = true, recipe = null, e = S.activeEffect(), known = null) {
  const sh = S.getShot();
  const m = RUN_DIR.exec(info?.run || "");
  if (!e || !sh.clip || !m || !info.filename) return null;
  const run = m[1];
  const old = S.allVersionsOf(e.id).find((v) => v.run === run);
  if (old) return old;
  const comp = `/element-forge/media/output/element-forge/${encodeURIComponent(run)}/${encodeURIComponent(info.filename)}`;
  const v = { id: uid(), run, status: "done", clip: sh.clip.name, at: Date.now(), comp, kind: e.kind, style: e.style, light,
    variant: "app", recipe, seed: recipe?.fx?.seed ?? null, prompt: null, ...(P.inScene(e) ? { paint: true } : {}) };
  S.addVersion(e.id, v);
  (known ? Promise.resolve(known) : getJSON(`/element-forge/media/output/element-forge/${encodeURIComponent(run)}/app_recipe.json`)).then((rec) => {
    const skip = new Set([...(rec.skipped || []), ...(rec.skip || [])]);
    if (light === false) { skip.add("light"); skip.add("normals"); }
    if (rec.values?.Glow === false) skip.add("glow");
    const passes = (rec.mode === "preview" ? PREVIEW_PASSES : ALL_PASSES).filter((p) => !skip.has(p));
    S.updateVersion(e.id, v.id, { quality: rec.mode === "preview" ? "preview" : "full", variant: rec.variant || "app", exact: true, passes });
  }).catch(() => {});
  S.showVersion(e.id, v.id);
  const chosen = e.id === sh.active;
  if (chosen) S.setUI({ media: { url: comp, live: null, label: "Result" }, compare: false, pass: null });
  L.ensurePreview(e.id, v).then((url) => {
    if (chosen && url && S.shownOf(e.id)?.id === v.id && S.ui.media?.url === comp) S.setUI({ media: { url: comp, live: url, label: "Result" } });
  });
  return v;
}

const edit = (fn, label) => S.change((sh) => { const x = sh.effects.find((y) => y.id === sh.active); if (x) fn(x); }, label);
const GRADE = { exposure: 0, temperature: 0, saturation: 1, blur: 0, blurRange: 0.15 };
const grade = (fn) => S.change((sh) => { sh.grade = { ...GRADE, ...sh.grade }; fn(sh.grade); }, "grade");

function range(x, label, value, min, max, step, onchange, fmt, rest = min < 0 ? 0 : 1) {
  const { h } = x;
  return h("div", { class: "field" }, h("div", { class: "label" }, label, h("span", { class: "muted small" }, ` · ${fmt(value)}`)),
    h("div", { class: "row gap" }, h("input", { type: "range", min: String(min), max: String(max), step: String(step), value: String(value),
      "aria-label": label, onchange: (ev) => onchange(+ev.target.value) }),
    value !== rest ? x.link("Reset", () => onchange(rest)) : null));
}

export function finishRows(x) {
  const { h, seg, note, link } = x;
  const e = S.activeEffect(), st = e && P.styleDef(e.kind, e.style);
  const v = e ? S.shownOf(e.id) : null;
  const adv = x.fx().mode === "advanced";
  if (!e || !st || v?.status !== "done") return [h("p", { class: "muted small" }, "After a run, light, glow, colour and the look of the clip change here at once, without a new run.")];
  const kids = [];
  if (!v.preview && !v.previewError) kids.push(h("div", { class: "busy" }, h("span", { class: "spinner", "aria-hidden": "true" }),
    h("span", { role: "status" }, "Preparing the live view of the run…")));
  if (v.previewError) kids.push(note("err", `The live view could not be made (${v.previewError}). `,
    link("Try again", () => { S.updateVersion(e.id, v.id, { previewError: null }); L.ensurePreview(e.id, { ...v, previewError: null }); })));
  if (v.preview && !S.ui.media?.live) kids.push(h("div", { class: "row gap" }, h("button", { class: "btn small", onclick: () =>
    S.setUI({ media: { url: v.comp, live: v.preview, label: "Result" }, compare: false, pass: null }) }, "Show the result live")));
  if (P.inScene(e)) kids.push(note("ok", "Inpaint: its light on the scene is part of the picture." + (v.light !== false ? " Light on the scene adds more on top." : "")));
  else if (v.light === false) kids.push(note("ok", "This run made no light pass, so Light on the scene shows nothing. Turn on Light under Passes in Output and run again."));
  const levels = L.LEVELS.map((t, i) => [i, t]);
  kids.push(
    h("div", { class: "field" }, h("div", { class: "label", title: "Light the effect throws onto the scene" }, "Light on the scene"),
      seg("Light on the scene", levels, e.look.light, (n) => edit((y) => { y.look.light = n; }, "light"))),
    h("div", { class: "field" }, h("div", { class: "label", title: "Soft glow around bright parts of the effect" }, "Glow"),
      seg("Glow", levels, e.look.glow, (n) => edit((y) => { y.look.glow = n; }, "glow"))),
    S.getShot().effects.length > 1 ? h("div", { class: "field" },
      h("div", { class: "label", title: "The light of the other effects brightens this one where it falls, e.g. smoke near a flame" }, "Lit by the other effects"),
      seg("Lit by the other effects", levels, e.look.lit ?? 0, (n) => edit((y) => { y.look.lit = n; }, "lit"))) : null,
    h("div", { class: "field" }, h("div", { class: "label", title: "Tints the effect, its light and its glow" }, "Colour"),
      h("div", { class: "swatches", role: "radiogroup", "aria-label": "Colour" },
        h("button", { class: "swatch none" + (!e.look.tint ? " on" : ""), role: "radio", "aria-checked": String(!e.look.tint), title: "The colours it was made with",
          onclick: () => edit((y) => { y.look.tint = null; }, "tint") }, "Original"),
        ...L.TINTS.map((c) => h("button", { class: "swatch" + (e.look.tint === c ? " on" : ""), role: "radio", "aria-checked": String(e.look.tint === c), title: c,
          "aria-label": `Colour ${c}`, style: { background: c }, onclick: () => edit((y) => { y.look.tint = c; }, "tint") })),
        e.look.tint && !L.TINTS.includes(e.look.tint) ? h("button", { class: "swatch on", role: "radio", "aria-checked": "true", title: `Your colour ${e.look.tint}`,
          "aria-label": `Your colour ${e.look.tint}`, style: { background: e.look.tint } }) : null,
        h("button", { class: "swatch pick" + (S.ui.tool === "pick" ? " on" : ""), title: "Take a colour from your clip (E)", "aria-label": "Take a colour from your clip",
          "aria-pressed": String(S.ui.tool === "pick"), onclick: () => S.setUI({ tool: S.ui.tool === "pick" ? "move" : "pick" }) }, icon("pick")),
        h("label", { class: "swatch pick", title: "Any colour" }, icon("plus"), h("input", { type: "color", value: e.look.tint || "#ffb347", "aria-label": "Any colour",
          onchange: (ev) => edit((y) => { y.look.tint = ev.target.value; }, "tint") })))));
  if (adv) {
    const autoBlend = st.dir === "dissolve" || st.settings?.["Blend on black (add = light, over = solid)"] === "over" ? "over" : "add";
    kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Glow reach"),
      seg("Glow reach", [[0, "Tight"], [1, "Normal"], [2, "Wide"]], e.look.size ?? 1, (n) => edit((y) => { y.look.size = n; }, "glow-size"))),
    h("div", { class: "field" }, h("div", { class: "label", title: "Add: the effect brightens the clip like light (fire, sparks). Normal: it covers the clip (smoke, debris)." }, "Blend mode"),
      seg("Blend mode", [["add", "Add (light)"], ["over", "Normal (solid)"]], e.look.blend || autoBlend, (b) => edit((y) => { y.look.blend = b === autoBlend ? null : b; }, "blend"))));
    if (st.dir !== "dissolve") {
      const fps = S.getShot().clip?.fps || 25;
      const bright = (k) => edit((y) => L.setBright(y, +Math.min(3, Math.max(0, L.brightAt(y, playhead()) * k)).toFixed(3), playhead(), fps), "bright");
      kids.push(h("div", { class: "field" }, h("div", { class: "label", title: "Brightness of the effect with its light and glow (with brightness keys: at the playhead)" }, "Brightness"),
        h("div", { class: "row gap" }, h("button", { class: "icon-btn", title: "Darker", "aria-label": "Darker", onclick: () => bright(1 / 1.2) }, "−"),
          h("span", { class: "muted small" }, `${Math.round(L.brightAt(e, playhead()) * 100)} %`),
          h("button", { class: "icon-btn", title: "Brighter", "aria-label": "Brighter", onclick: () => bright(1.2) }, "+"))));
    }
  }
  const p = L.placeAt(e, playhead());
  if (p.dx || p.dy || p.scale !== 1 || p.stretch !== 1 || p.rot || L.animated(e, "place")) kids.push(h("div", { class: "row gap" },
    h("span", { class: "muted small" }, "Moved, sized or turned in the canvas"),
    h("button", { class: "btn ghost small", title: L.animated(e, "place") ? "Also removes its position keys (Ctrl+Z brings them back)" : "",
      onclick: () => edit((y) => { y.place = { dx: 0, dy: 0, scale: 1, stretch: 1, rot: 0 }; y.keys = { ...y.keys, place: [] }; }, "place") }, "Back to where it was made")));
  const g = { ...GRADE, ...S.getShot().grade };
  kids.push(h("div", { class: "label sub" }, "The clip (all effects)"),
    range(x, "Brightness of the clip", g.exposure, -2, 2, 0.1, (n) => grade((y) => { y.exposure = n; }), (n) => (n ? `${n > 0 ? "+" : ""}${n.toFixed(1)} stops` : "as filmed")),
    range(x, "Warmth", g.temperature, -1, 1, 0.05, (n) => grade((y) => { y.temperature = n; }), (n) => (n ? (n > 0 ? "warmer" : "cooler") : "as filmed")));
  if (adv) kids.push(range(x, "Colour strength", g.saturation, 0, 2, 0.05, (n) => grade((y) => { y.saturation = n; }), (n) => (n === 1 ? "as filmed" : `${Math.round(n * 100)} %`)));
  kids.push(range(x, "Depth blur", g.blur, 0, 1, 0.05, (n) => grade((y) => { y.blur = n; }), (n) => (n ? `${Math.round(n * 100)} %` : "off"), 0));
  if (adv && g.blur > 0) kids.push(range(x, "Sharp around the effect", g.blurRange, 0.03, 0.5, 0.01, (n) => grade((y) => { y.blurRange = n; }),
    (n) => (n < 0.1 ? "narrow" : n > 0.3 ? "wide" : "medium"), 0.15));
  if (g.blur > 0) kids.push(h("p", { class: "muted small" }, "The focus stays on the effect as it moves; the farther something is in depth from it, the softer."));
  kids.push(h("p", { class: "muted small" }, "All of this shows at once. Drag the effect in the canvas to move it, its corners to size it, just outside a corner to turn it. Output exports it as you see it."));
  return kids;
}
