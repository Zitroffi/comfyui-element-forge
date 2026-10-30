export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") for (const [sk, sv] of Object.entries(v)) sk.startsWith("--") ? el.style.setProperty(sk, sv) : (el.style[sk] = sv);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

export async function getJSON(url, opt = {}) {
  const r = await fetch(url, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.error || r.statusText || `HTTP ${r.status}`), { status: r.status });
  return j;
}
export const postJSON = (url, body) => getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const memory = new Map();
export const store = {
  get(k, d) { return memory.has(k) ? clone(memory.get(k)) : d; },
  set(k, v) { memory.set(k, clone(v)); },
};

export const fmtSize = (b) => (b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : (b / 1e6).toFixed(1) + " MB");
export const fmtSec = (s) => (s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")} min`);
export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const uid = () => Math.random().toString(36).slice(2, 10);
export const clone = (o) => (o === undefined ? o : JSON.parse(JSON.stringify(o)));
