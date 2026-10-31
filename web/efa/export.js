import * as S from "./ui/state.js";
import * as L from "./ui/look.js";
import { hasRtx } from "./ui/machine.js";
import { nextStep } from "./versions.js";

const FORMATS = [["mp4", "MP4", "H.264, 8 bit: plays everywhere"], ["prores", "ProRes", "ProRes 422 HQ (.mov), 10 bit: for editing, no banding in glow"],
  ["h265", "H.265", "H.265 (.mp4), 10 bit: small files without banding"], ["png", "PNG", "A PNG image per frame, 8 or 16 bit"], ["exr", "EXR", "An EXR image per frame: half float, linear Rec.709, for compositing"]];
const DEFAULT = { format: "mp4", png16: false, layers: false, passes: null, range: "all", hdr: false, hdrOn: "comp", upscale: "off" };
const PASSES = [["effects", "Effect passes", "Light, element, smoke and glow of every effect, as they go into the comp"],
  ["plate", "Plate", "The clip as graded in Scene & finish"], ["depth", "Depth", "Depth of the clip, near = white"],
  ["normals", "Normals", "Surface normals of the clip, for relighting"], ["mask", "Object mask", "The mask of the object you clicked, per frame"]];
const passesOf = (o) => (Array.isArray(o.passes) ? o.passes : o.layers ? ["effects", "plate", "depth"] : []);
const setExport = (fn) => S.change((sh) => { sh.output = { ...sh.output, export: { ...DEFAULT, ...sh.output?.export } }; fn(sh.output.export); }, "export");
let name = "";
let hooked = false;

function span(shot, effects) {
  const fps = shot.clip.fps, n = Math.round(shot.clip.seconds * fps);
  const t = effects.map((e) => L.timingFrames(e, fps));
  return [Math.max(0, Math.min(...t.map((x) => x.start))), Math.min(n - 1, Math.max(...t.map((x) => Math.min(x.end, n - 1))))];
}

export function exportRows(x) {
  const { h, seg, toggle, note, link } = x;
  if (!hooked) { L.onExport(() => x.render()); hooked = true; }
  const shot = S.getShot();
  const o = { ...DEFAULT, ...shot.output?.export };
  const ready = shot.effects.filter((e) => S.shownOf(e.id)?.status === "done");
  const job = L.runningExport();
  const fmt = o.format === "png" || o.format === "png8" || o.format === "png16" ? "png" : o.format;
  const kids = [h("p", { class: "muted small" }, !ready.length ? "The clip alone, as graded in Scene & finish, at full size: with the passes below, NVIDIA × 2 or HDR."
    : ready.length > 1 ? `All ${ready.length} effects together, as you see them, at full size.` : "The clip with the effect, as you see it, at full size.")];
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Format"),
    seg("Export format", FORMATS, fmt, (v) => setExport((y) => { y.format = v; if (v !== "h265") y.hdr = false; })),
    h("p", { class: "muted small" }, FORMATS.find(([k]) => k === fmt)?.[2] || "")));
  if (fmt === "png") kids.push(seg("PNG depth", [[false, "8 bit"], [true, "16 bit"]], !!o.png16, (v) => setExport((y) => { y.png16 = v; })));
  const sp = ready.length ? span(shot, ready) : null;
  const fps = shot.clip?.fps || 25;
  if (ready.length) kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Frames"),
    seg("Export frames", [["all", "Whole clip"], ["effects", "Where the effects are", sp ? `Frames ${sp[0] + 1}–${sp[1] + 1} (${(sp[0] / fps).toFixed(1)}–${((sp[1] + 1) / fps).toFixed(1)} s), from the timeline` : "From the effects' bars in the timeline"]],
      o.range, (v) => setExport((y) => { y.range = v; }))));
  const have = passesOf(o);
  const point = !!S.activeEffect()?.where?.a;
  const setPass = (k, on) => setExport((y) => { const p = new Set(passesOf(y)); if (on) p.add(k); else p.delete(k); y.passes = PASSES.map(([q]) => q).filter((q) => p.has(q)); y.layers = false; });
  const shown = PASSES.filter(([k]) => k !== "effects" || ready.length);
  kids.push(h("div", { class: "field stack" }, h("div", { class: "label" }, "Passes as EXR"),
    ...shown.map(([k, t, tip]) => toggle(t, have.includes(k) && (k !== "mask" || ready.length || point), (v) => {
      if (k === "mask" && v && !ready.length && !point) return;
      setPass(k, v);
    }, tip)),
    have.includes("mask") && !ready.length && !point ? h("p", { class: "muted small" }, "The object mask needs a point: click the object in Position.") : null,
    ready.length && have.some((k) => ["normals", "mask"].includes(k)) ? h("p", { class: "muted small" }, "Normals and the mask come from the shown versions: turn them on under Passes before the run.") : null,
    !ready.length && have.some((k) => ["depth", "normals"].includes(k)) ? h("p", { class: "muted small" }, "Without an analysis of the clip the export works depth and normals out first (a few minutes).") : null,
    h("p", { class: "muted small" }, "Half float, scene-linear, in layers/ of the export folder.")));
  const up = hasRtx() ? (ready.length ? o.upscale : (o.upscale === "off" ? "off" : "plate")) : "off";
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "NVIDIA × 2 (Super Resolution)"),
    seg("NVIDIA × 2", ready.length
      ? [["off", "Off"], ["plate", "Plate only", "Only the clip gets the new detail; the effects are scaled up as they are"], ["comp", "With the effects", "The finished comp, effects included"]]
      : [["off", "Off"], ["plate", "On", "The clip at twice the size, with new detail"]],
    up, (v) => { if (hasRtx() || v === "off") setExport((y) => { y.upscale = v; }); }),
    h("p", { class: "muted small" }, hasRtx() ? "Twice the size; the passes come at the same size." : "Needs an NVIDIA RTX card and ComfyUI's NVIDIA nodes.")));
  if (fmt === "h265") {
    kids.push(toggle("HDR (NVIDIA TrueHDR)", o.hdr && hasRtx(), (v) => { if (hasRtx()) setExport((y) => { y.hdr = v; }); },
      hasRtx() ? "HDR10 (PQ, BT.2020) through NVIDIA RTX TrueHDR" : "Needs an NVIDIA RTX card and ComfyUI's NVIDIA nodes"));
    if (!hasRtx()) kids.push(h("p", { class: "muted small" }, "HDR needs an NVIDIA RTX card and ComfyUI's NVIDIA nodes."));
    else if (o.hdr && ready.length) kids.push(seg("HDR on", [["comp", "With the effects", "TrueHDR expands the finished comp"],
      ["plate", "Plate only", "TrueHDR expands the clip; the effects keep their own brightness on top"]], o.hdrOn === "plate" ? "plate" : "comp",
    (v) => setExport((y) => { y.hdrOn = v; })));
  } else kids.push(h("p", { class: "muted small" }, "HDR: choose H.265."));
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Folder name (optional)"),
    h("input", { class: "text", type: "text", value: name, placeholder: shot.clip?.name.replace(/\.[^.]+$/, "") || "shot", "aria-label": "Export folder name",
      oninput: (ev) => { name = ev.target.value; } })));
  kids.push(h("div", { class: "row gap" }, h("button", { class: "btn" + (nextStep() === "export" ? " primary" : ""), disabled: !!job || !shot.clip,
    title: !shot.clip ? "Choose a clip first" : job ? "An export is running" : "Renders the comp at full size into ComfyUI's output folder",
    onclick: async () => {
      const kind = fmt === "png" ? (o.png16 ? "png16" : "png8") : fmt;
      const passes = have.filter((k) => (k !== "effects" || ready.length) && (k !== "mask" || ready.length || point));
      try { await L.exportShot(kind, { name, passes, range: ready.length && o.range === "effects" && sp ? sp : null, hdr: fmt === "h265" && o.hdr && hasRtx(),
        hdrOn: o.hdrOn, upscale: up }); }
      catch (err) { x.say(err.message, true); }
      x.render();
    } }, "Export")));
  for (const j of [...L.exports_].reverse().slice(0, 3)) {
    if (j.status === "running") {
      const pct = j.max ? Math.round((j.value / j.max) * 100) : null;
      kids.push(h("div", { class: "busy", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), h("span", {}, `Rendering the export${pct == null ? "…" : ` · ${pct} %`}`)));
    } else if (j.status === "done") {
      kids.push(note("ok", `Export ready: ComfyUI › output › ${j.out}/${j.file || "comp.mp4"}${j.layers ? ", the passes in layers/" : ""}. `,
        link("Play it", () => S.setUI({ media: { url: j.comp, label: "Export" }, compare: false, pass: null }))));
    } else {
      kids.push(note("err", `Export failed: ${j.error || j.status}`));
    }
  }
  return kids;
}
