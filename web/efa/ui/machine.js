import { getJSON, store } from "./lib.js";

export const KITCHEN = "comfy kitchen attention";
export const LTX_DEFAULT = "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors";
export const TE_DEFAULT = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors";
let files = null;
let hasDefault = true;
let teFiles = null;
let hasTeDefault = true;

const options = (info, cls, input) => {
  const names = info?.[cls]?.input?.required?.[input];
  return Array.isArray(names?.[0]) ? names[0] : (names?.[1]?.options || []);
};
export const isGguf = (f) => /\.gguf$/i.test(f || "");

export async function loadLtxFiles() {
  if (files) return files;
  const unet = options(await getJSON("/object_info/UNETLoader").catch(() => ({})), "UNETLoader", "unet_name");
  const gguf = options(await getJSON("/object_info/UnetLoaderGGUF").catch(() => ({})), "UnetLoaderGGUF", "unet_name");
  hasDefault = unet.includes(LTX_DEFAULT);
  files = [...unet.filter((f) => /ltx/i.test(f) && /\.safetensors$/i.test(f) && f !== LTX_DEFAULT),
    ...gguf.filter((f) => /ltx/i.test(f) && isGguf(f))];
  return files;
}
export const ltxFiles = () => files || [];
export const ltxDefaultMissing = () => !!files && !hasDefault;
export async function loadTeFiles() {
  if (teFiles) return teFiles;
  const all = options(await getJSON("/object_info/CLIPLoader").catch(() => ({})), "CLIPLoader", "clip_name");
  hasTeDefault = all.includes(TE_DEFAULT);
  teFiles = all.filter((f) => /gemma4-12b/i.test(f) && f !== TE_DEFAULT);
  return teFiles;
}
export const teFilesList = () => teFiles || [];
let rtx = null;
export async function loadRtx() {
  if (rtx === null) rtx = !!(await getJSON("/object_info/RTXVideoSuperResolution").catch(() => ({})))?.RTXVideoSuperResolution;
  return rtx;
}
export const hasRtx = () => rtx === true;
let sys = null;
export async function loadSystem() {
  if (sys === null) sys = await getJSON("/element-forge/api/status").catch(() => ({}));
  return sys;
}
const GIB = 1024 ** 3;
export function systemNotes() {
  if (!sys?.ok) return [];
  const out = [];
  const cuda = /^cuda/i.test(String(sys.device || ""));
  if (!cuda) out.push({ kind: "err", text: `The AI styles were tested on NVIDIA GPUs (CUDA) only. This computer runs on ${sys.device || "another device"}: not tested.` });
  else if (sys.vram_total && sys.vram_total < 10.5 * GIB) out.push({ kind: "err", text: `This GPU has ${(sys.vram_total / GIB).toFixed(1)} GB. The AI styles were tested with 11 GB and more.` });
  if (sys.ram_total && sys.ram_total < 75 * GIB) out.push({ kind: "info", text: `This computer has ${Math.round(sys.ram_total / GIB)} GB RAM; Element Forge was tested with 80 GB. If ComfyUI stops during a run, start it with --cache-none; on Windows a page file of 32 GB or more helps.` });
  return out;
}
let dc = null;
export async function loadDepthCrafter() {
  if (dc === null) dc = !!(await getJSON("/object_info/DepthCrafter").catch(() => ({})))?.DepthCrafter;
  return dc;
}
export const hasDepthCrafter = () => dc === true;

let modelsIO = null;
export const useModelsNode = (io) => { modelsIO = io || null; };
export const hasModelsNode = () => !!modelsIO?.get?.();
const wname = (f) => f.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 48);
export const MODEL_WIDGETS = { file: wname(LTX_DEFAULT), te: wname(TE_DEFAULT), attention: "attention", depth: "depth_model" };
function fromNode() {
  const v = modelsIO?.get?.();
  if (!v) return null;
  const W = MODEL_WIDGETS, file = v[W.file], te = v[W.te];
  return { file: file && file !== LTX_DEFAULT ? file : "", te: te && te !== TE_DEFAULT ? te : "",
    attention: v[W.attention] === KITCHEN ? KITCHEN : "", depth: v[W.depth] === "DepthCrafter" ? "depthcrafter" : "" };
}

export function ltxChoice() {
  const c = fromNode() || store.get("ltx", {}) || {};
  let file = ltxFiles().includes(c.file) ? c.file : "";
  if (!file && files && !hasDefault && ltxFiles().length) file = ltxFiles()[0];
  let te = teFilesList().includes(c.te) ? c.te : "";
  if (!te && teFiles && !hasTeDefault && teFilesList().length) te = teFilesList()[0];
  return { file, attention: !isGguf(file) && c.attention === KITCHEN ? KITCHEN : "", te,
    depth: c.depth === "depthcrafter" && dc !== false ? "depthcrafter" : "" };
}
export function setLtx(c) {
  store.set("ltx", { file: c.file || "", attention: c.attention || "", te: c.te || "", depth: c.depth || "" });
  const W = MODEL_WIDGETS;
  modelsIO?.set?.({ [W.file]: c.file || LTX_DEFAULT, [W.te]: c.te || TE_DEFAULT,
    [W.attention]: c.attention === KITCHEN ? KITCHEN : "pytorch attention", [W.depth]: c.depth === "depthcrafter" ? "DepthCrafter" : "Video Depth Anything" });
}

export function ltxForBuild() {
  const c = ltxChoice();
  return c.file || c.te || c.attention || c.depth ? c : null;
}
