import * as C from "./comfy.js";
import { getJSON, postJSON, store } from "./lib.js";
import { inScene } from "./presets.js";

let bonsai = null;
let encoders = [];
export async function bonsaiStatus() {
  if (!bonsai) {
    const [b, info] = await Promise.all([getJSON("/element-forge/api/bonsai").catch(() => ({})), getJSON("/object_info/CLIPLoader").catch(() => ({}))]);
    const names = info?.CLIPLoader?.input?.required?.clip_name;
    encoders = Array.isArray(names?.[0]) ? names[0] : (names?.[1]?.options || []);
    bonsai = b;
  }
  return bonsai;
}
export const bonsaiSetup = () => getJSON("/element-forge/api/bonsai/setup");
export const startBonsaiSetup = () => postJSON("/element-forge/api/bonsai/setup", {});
export const resetBonsai = () => { bonsai = null; };
export const hasBonsai = () => !!(bonsai && (bonsai.running || bonsai.can_start));
export const bonsaiSees = () => hasBonsai() && !!bonsai.vision;
export function whyNotSeeing() {
  if (!hasBonsai()) return "Bonsai 2 is not set up in this ComfyUI";
  if (enhancer().id !== "bonsai") return "it needs Bonsai 2 as the language model";
  if (!bonsai.vision) return "Bonsai 2 needs its image part (the mmproj file in bonsai.json) to see the clip";
  return "";
}

const LMS = [
  { id: "e2b", file: "gemma4_e2b_it_int8_convrot.safetensors", label: "Gemma 4 E2B (fast)" },
];
export function enhancers() {
  const out = hasBonsai() ? [{ id: "bonsai", label: "Bonsai 2 (local)" }] : [];
  for (const m of LMS) if (encoders.includes(m.file)) out.push(m);
  return out.length ? out : [LMS[0]];
}
export function enhancer() {
  const list = enhancers(), want = store.get("enhancer", null);
  return list.find((m) => m.id === want) || list[0];
}
export const setEnhancer = (id) => store.set("enhancer", id);

const ON_BLACK = `You improve a short prompt for the LTX video model. The prompt describes ONE visual effect element that is filmed alone on a pure black background with a static camera; it will later be composited into another video.
Rules:
- Keep the kind of element, its colours, its size, its direction of motion and what it touches exactly as given. Do not add other elements, people, places, scenery, camera moves, lighting setups or sound.
- Keep every sentence about the black background word for word, at the end.
- Write one paragraph in present tense. Put the main action first. Add concrete physical detail about shape, texture, speed and how it changes over time.
- Stay under 120 words. Output only the prompt, nothing else.`;
const IN_SCENE = `You improve a short prompt for the LTX video model. The prompt describes ONE visual effect that is added into an existing video and touches the scene (for example fire on an object, or smoke rising from the ground).
Rules:
- Keep the kind of effect, its colours, its size, its direction of motion and what it touches exactly as given. Do not change or describe the rest of the scene, add people or camera moves, or mention sound.
- Write one paragraph in present tense. Put the main action first. Add concrete physical detail about shape, texture, speed and how it interacts with the surface it touches.
- Stay under 120 words. Output only the prompt, nothing else.`;


export function enhanceGraph(effect, prompt, file = LMS[0].file) {
  return {
    "1": { class_type: "CLIPLoader", inputs: { clip_name: file, type: "ltxv", device: "default" } },
    "2": { class_type: "TextGenerateLTX2Prompt", inputs: { clip: ["1", 0], prompt, max_length: 320, sampling_mode: "off", thinking: false,
      use_default_template: true, mtp: "auto", system_prompt: inScene(effect) ? IN_SCENE : ON_BLACK } },
    "3": { class_type: "PreviewAny", inputs: { source: ["2", 0] } },
  };
}

export function cleanEnhanced(text) {
  let t = String(text || "").replace(/<think>[\s\S]*?<\/think>/g, "");
  const open = t.indexOf("<think>");
  if (open >= 0) t = t.slice(0, open);
  t = t.trim();
  const words = (s) => s.toLowerCase().match(/[a-z0-9']+/g) || [];
  const sentences = t.match(/[^.!?]+(?:[.!?]+["')\]]*|$)\s*/g) || [];
  const firstWords = words(sentences[0] || "").slice(0, 5).join(" ");
  const seen = new Set();
  const kept = [];
  for (const s of sentences) {
    const w = words(s), key = w.join(" ");
    if (!key) continue;
    const restart = kept.length && firstWords.split(" ").length === 5 && w.slice(0, 5).join(" ") === firstWords;
    if (seen.has(key) || restart) break;
    seen.add(key);
    kept.push(s);
  }
  let out = kept.join("").trim();
  if (firstWords.split(" ").length === 5) {
    const again = out.toLowerCase().indexOf(firstWords, firstWords.length);
    if (again > 0) out = out.slice(0, again).trim();
  }
  const done = out.match(/^[\s\S]*[.!?]["')\]]*/);
  return (done && done[0].length > out.length / 2 ? done[0] : out).trim();
}

export async function enhance(effect, prompt, on = {}) {
  await bonsaiStatus();
  const lm = enhancer();
  if (lm.id === "bonsai") {
    on.phase?.(bonsai.running ? "Bonsai is writing" : "Loading Bonsai");
    const r = await postJSON("/element-forge/api/bonsai", { system: inScene(effect) ? IN_SCENE : ON_BLACK, text: prompt, max_tokens: 320, temperature: 0.7, keep: true });
    bonsai.running = true;
    const t = cleanEnhanced(r.text);
    if (!t) throw new Error("no text came back");
    return t;
  }
  return new Promise((resolve, reject) => {
    let text = null;
    C.connectSocket();
    C.queue(enhanceGraph(effect, prompt, lm.file), {
      onStart: () => on.phase?.("Loading the language model"),
      onNode: (n) => { if (n === "2") on.phase?.("Writing"); },
      onOutput: (node, out) => { if (node === "3") text = cleanEnhanced([].concat(out.text || out.value || []).join("")); },
      onDone: (r) => (r.status === "done" && text ? resolve(text) : reject(new Error(r.error || (r.status === "done" ? "no text came back" : r.status)))),
    }).then((id) => on.queued?.(id)).catch(reject);
  });
}

const SHOT = `You describe a video frame for the LTX video model, which will repaint part of this video. Write ONE sentence in present tense: what kind of shot it is (live-action, day or night, indoors or outdoors), the place, the main person or object and the light. No camera words, no effects, no guesses about what happens next. Output only the sentence.`;
export async function describeShot(clip, seconds = 0, box = null) {
  const r = await postJSON("/element-forge/api/bonsai", { system: SHOT, text: box ? "Describe this part of the frame." : "Describe this frame.", clip,
    time: seconds, ...(box ? { box } : {}), max_tokens: 90, temperature: 0.3, keep: true });
  if (bonsai) bonsai.running = true;
  const t = cleanEnhanced(r.text).replace(/^["']|["']$/g, "").trim();
  if (!t) throw new Error("no text came back");
  return t;
}

export function wordDiff(a, b) {
  const A = a.split(/(\s+)/).filter(Boolean), B = b.split(/(\s+)/).filter(Boolean);
  const n = A.length, m = B.length;
  if (n * m > 400000) return [{ t: a, kind: "del" }, { t: " ", kind: "same" }, { t: b, kind: "add" }];
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  const push = (t, kind) => { const last = out.at(-1); if (last?.kind === kind) last.t += t; else out.push({ t, kind }); };
  while (i < n && j < m) {
    if (A[i] === B[j]) { push(A[i], "same"); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) push(A[i++], "del");
    else push(B[j++], "add");
  }
  while (i < n) push(A[i++], "del");
  while (j < m) push(B[j++], "add");
  return out;
}
