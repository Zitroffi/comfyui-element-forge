import { getJSON, store } from "./ui/lib.js";
import * as M from "./ui/machine.js";
import { enhancers, enhancer, setEnhancer, hasBonsai } from "./ui/enhance.js";

let models = null, failed = null, loading = false;
const SETTINGS = { ltx: "ElementForge.Machine.LTX", enhancer: "ElementForge.Machine.TextModel" };

async function loadSettings() {
  for (const [k, id] of Object.entries(SETTINGS)) {
    const r = await fetch(`/api/settings/${id}`).catch(() => null);
    const v = r?.ok ? await r.json().catch(() => null) : null;
    if (v != null) store.set(k, v);
  }
}
function keep(k) {
  if (k === "ltx" && M.hasModelsNode()) return;
  fetch(`/api/settings/${SETTINGS[k]}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(store.get(k, null)) }).catch(() => {});
}
const NEED = { yes: "needed", some: "for some styles", option: "optional" };

export function loadGear(render) {
  if (loading || models) return;
  loading = true;
  Promise.all([getJSON("/element-forge/app/models"), M.loadLtxFiles(), M.loadTeFiles(), M.loadRtx(), loadSettings()])
    .then(([m]) => { models = m.models || []; }, (err) => { failed = err.message; })
    .finally(() => { loading = false; render(); });
}

const gb = (x) => (x == null ? "size unknown" : x >= 1 ? `${x.toFixed(1)} GB` : `${Math.round(x * 1000)} MB`);
const short = (f) => f.replace(/\.(safetensors|gguf|pth)$/i, "");

export function gearRows(x) {
  const { h, seg, toggle, note, link } = x;
  loadGear(x.render);
  if (!models && !failed) return [h("p", { class: "muted" }, "Looking at the models of this ComfyUI…")];
  const c = M.ltxChoice();
  const set = (patch) => { M.setLtx({ ...c, ...patch }); keep("ltx"); x.render(); };
  const kids = [h("p", { class: "muted small" }, M.hasModelsNode()
    ? "LTX model, INT8 attention, text encoder and depth model are saved in the workflow (the Element Forge · Models node): another PC that opens it uses the same files, and ComfyUI offers the ones it does not have. The text model is a setting of this computer."
    : "Settings of this computer, not of the shot: another PC that opens the workflow uses its own.")];

  const ltxOpts = [["", `${short(M.LTX_DEFAULT)} (default)`], ...M.ltxFiles().map((f) => [f, short(f) + (M.isGguf(f) ? " (GGUF)" : "")])];
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "LTX model"),
    h("select", { class: "text", "aria-label": "LTX model", onchange: (ev) => set({ file: ev.target.value }) },
      ...ltxOpts.map(([v, t]) => h("option", { value: v, selected: v === c.file }, t))),
    M.ltxDefaultMissing() ? note("err", "The default LTX file is not installed: the first other LTX file is used.") : null,
    h("p", { class: "muted small" }, "INT8 is the default. GGUF Q4 needs about 8 GB less memory and is slower on RTX 20 cards.")));
  kids.push(toggle("INT8 attention", c.attention === M.KITCHEN && !M.isGguf(c.file), (v) => set({ attention: v ? M.KITCHEN : "" }),
    M.isGguf(c.file) ? "Not with GGUF: slower there" : "Faster on cards like the RTX 2080 Ti (about a quarter off the LTX time)"));
  if (M.isGguf(c.file)) kids.push(h("p", { class: "muted small" }, "INT8 attention is off with GGUF (it is slower there)."));
  const te = M.teFilesList();
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Text encoder"),
    te.length ? h("select", { class: "text", "aria-label": "Text encoder", onchange: (ev) => set({ te: ev.target.value }) },
      h("option", { value: "", selected: !c.te }, `${short(M.TE_DEFAULT)} (default)`), ...te.map((f) => h("option", { value: f, selected: f === c.te }, short(f))))
      : h("p", { class: "muted small" }, `${short(M.TE_DEFAULT)}: reads the prompt for LTX. Another Gemma 12B file shows here when it is installed.`)));
  M.loadDepthCrafter().then((had) => { if (had && !M.hasDepthCrafter()) x.render(); });
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Depth model"),
    M.hasDepthCrafter() ? seg("Depth model", [["", "Video Depth Anything (default)"], ["depthcrafter", "DepthCrafter"]], c.depth || "", (v) => set({ depth: v }))
      : null,
    h("p", { class: "muted small" }, M.hasDepthCrafter()
      ? "DepthCrafter: clean edges without a fringe, much slower (about 15 more minutes for 81 frames on an RTX 2080 Ti); non-commercial licence. A run works the depth out again when the clip was analysed with the other model."
      : "Video Depth Anything. DepthCrafter (sharper edges, non-commercial licence) shows here when ComfyUI-DepthCrafter-Nodes is installed.")));
  const lms = enhancers();
  kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Text model (Enhance, inpaint sentence, Describe what you want)"),
    seg("Text model", lms.map((m) => [m.id, m.label]), enhancer().id, (v) => { setEnhancer(v); keep("enhancer"); x.render(); }),
    h("p", { class: "muted small" }, hasBonsai() ? "Bonsai 2 runs beside ComfyUI's queue and can look at the clip; Gemma 4 E2B is a short ComfyUI job."
      : "Bonsai 2 is not set up in this ComfyUI (setup_bonsai.py in the pack); Gemma 4 E2B is used.")));
  kids.push(h("div", { class: "field" + (M.hasRtx() ? "" : " off") }, h("div", { class: "label" }, "NVIDIA Super Resolution and TrueHDR"),
    h("p", { class: "muted small" }, M.hasRtx() ? "Available: Upscale NVIDIA × 2 in Output, HDR export as H.265."
      : "Not available here: they need an NVIDIA RTX card and ComfyUI's NVIDIA nodes. Upscale NVIDIA × 2 and the HDR export stay greyed out.")));
  if (failed) { kids.push(note("err", `The list of models could not be read (${failed}).`)); return kids; }
  const missing = models.filter((m) => !(m.covered ?? m.present) && m.need === "yes");
  kids.push(h("div", { class: "label" }, "Models"),
    missing.length ? note("err", `${missing.length} needed model${missing.length > 1 ? "s are" : " is"} missing. ComfyUI offers the download when the workflow opens; or put the file into the folder named below.`)
      : note("ok", "Every needed model is there."));
  kids.push(h("div", { class: "models", role: "list" }, ...models.map((m) => h("div", { class: "model" + (m.present ? " on" : ""), role: "listitem" },
    h("div", { class: "model-top" }, h("span", { class: "dot " + (m.present ? "ok" : m.need === "yes" && !m.covered ? "err" : "off"), "aria-hidden": "true" }),
      h("span", { class: "model-name", title: m.file }, short(m.file)), h("span", { class: "muted small" }, gb(m.size_gb))),
    h("div", { class: "muted small" }, `${m.for} · ${NEED[m.need] || ""} · ${m.present ? "installed" : m.covered ? "not installed, the other choice is" : "missing"} · models/${m.folder}`,
      " · ", h("a", { href: m.source, target: "_blank", rel: "noopener" }, "source"))))));
  return kids;
}
