import * as S from "./ui/state.js";
import * as L from "./ui/look.js";
import { hasRtx } from "./ui/machine.js";
import { nextStep } from "./versions.js";

const FORMATS = [["mp4", "MP4", "H.264, 8 bit: plays everywhere"], ["prores", "ProRes", "ProRes 422 HQ (.mov), 10 bit: for editing, no banding in glow"],
  ["h265", "H.265", "H.265 (.mp4), 10 bit: small files without banding"], ["png", "PNG", "A PNG image per frame, 8 or 16 bit"], ["exr", "EXR", "An EXR image per frame: half float, linear Rec.709, for compositing"]];
const DEFAULT = { format: "mp4", png16: false, layers: false, range: "all", hdr: false };
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
  const kids = [h("p", { class: "muted small" }, !ready.length ? "After a run: the clip with its effects, as you see it, at full size."
    : ready.length > 1 ? `All ${ready.length} effects together, as you see them, at full size.` : "The clip with the effect, as you see it, at full size.")];
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Format"),
    seg("Export format", FORMATS, fmt, (v) => setExport((y) => { y.format = v; if (v !== "h265") y.hdr = false; })),
    h("p", { class: "muted small" }, FORMATS.find(([k]) => k === fmt)?.[2] || "")));
  if (fmt === "png") kids.push(seg("PNG depth", [[false, "8 bit"], [true, "16 bit"]], !!o.png16, (v) => setExport((y) => { y.png16 = v; })));
  const sp = ready.length ? span(shot, ready) : null;
  const fps = shot.clip?.fps || 25;
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Frames"),
    seg("Export frames", [["all", "Whole clip"], ["effects", "Where the effects are", sp ? `Frames ${sp[0] + 1}–${sp[1] + 1} (${(sp[0] / fps).toFixed(1)}–${((sp[1] + 1) / fps).toFixed(1)} s), from the timeline` : "From the effects' bars in the timeline"]],
      o.range, (v) => setExport((y) => { y.range = v; }))));
  kids.push(toggle("Also every pass as EXR", o.layers, (v) => setExport((y) => { y.layers = v; }),
    "Plate, depth and per effect its light, element, smoke and glow as they go into the comp (half float, linear), for compositing"));
  if (fmt === "h265") {
    kids.push(toggle("HDR (NVIDIA TrueHDR)", o.hdr && hasRtx(), (v) => { if (hasRtx()) setExport((y) => { y.hdr = v; }); },
      hasRtx() ? "HDR10 (PQ, BT.2020) from the comp through NVIDIA RTX TrueHDR" : "Needs an NVIDIA RTX card and ComfyUI's NVIDIA nodes"));
    if (!hasRtx()) kids.push(h("p", { class: "muted small" }, "HDR needs an NVIDIA RTX card and ComfyUI's NVIDIA nodes."));
  }
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Folder name (optional)"),
    h("input", { class: "text", type: "text", value: name, placeholder: shot.clip?.name.replace(/\.[^.]+$/, "") || "shot", "aria-label": "Export folder name",
      oninput: (ev) => { name = ev.target.value; } })));
  kids.push(h("div", { class: "row gap" }, h("button", { class: "btn" + (nextStep() === "export" ? " primary" : ""), disabled: !!job || !ready.length,
    title: !ready.length ? "Make a run first" : job ? "An export is running" : "Renders the comp at full size into ComfyUI's output folder",
    onclick: async () => {
      const kind = fmt === "png" ? (o.png16 ? "png16" : "png8") : fmt;
      try { await L.exportShot(kind, { name, layers: o.layers, range: o.range === "effects" && sp ? sp : null, hdr: fmt === "h265" && o.hdr && hasRtx() }); }
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
