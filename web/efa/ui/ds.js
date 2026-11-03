import { h } from "./lib.js";
import { icon } from "./icons.js";

export const PADX = 10;
export const VAL_W = 116;

export function seg(label, options, value, onpick, { wide = true } = {}) {
  if (options.length >= 6) {
    return h("select", { class: "text", "aria-label": label, onchange: (ev) => onpick(options[ev.target.selectedIndex][0]) },
      ...options.map(([v, t, tip]) => h("option", { selected: value === v, title: tip || null }, t)));
  }
  return h("div", { class: "seg" + (wide ? " wide" : ""), role: "radiogroup", "aria-label": label },
    ...options.map(([v, t, tip]) => h("button", { type: "button", role: "radio", "aria-checked": String(value === v), "aria-pressed": String(value === v),
      title: tip || null, onclick: () => onpick(v) }, h("span", { "data-t": t }, t))));
}
const needOf = (b) => Math.ceil((b.firstElementChild || b).getBoundingClientRect().width) + 2 * PADX;
export function fitSegs(root) {
  for (const s of root.querySelectorAll(".seg.wide")) {
    s.classList.remove("natural", "g22", "g32", "wrap");
    const line = s.parentElement?.matches(".cline, .em-row.choice:not(.wide)") ? s.parentElement : null;
    line?.classList.remove("stacked");
    if (!s.clientWidth || !s.children.length) continue;
    const cs = getComputedStyle(s), gap = parseFloat(cs.columnGap) || 0;
    const roomOf = () => s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) + 0.5;
    let room = roomOf();
    const need = [...s.children].map(needOf);
    const even = (xs) => xs.length * Math.max(...xs) + gap * (xs.length - 1) <= room;
    if (even(need)) continue;
    if (line) { line.classList.add("stacked"); room = roomOf(); if (even(need)) continue; }
    if (need.reduce((a, b) => a + b, 0) + gap * (need.length - 1) <= room) s.classList.add("natural");
    else if (need.length === 4 && even(need.slice(0, 2)) && even(need.slice(2))) s.classList.add("g22");
    else if (need.length === 5 && even(need.slice(0, 3)) && even(need.slice(3))) s.classList.add("g32");
    else s.classList.add("wrap");
  }
}

export function toggle(label, value, onchange, tip) {
  return h("label", { class: "toggle" }, h("input", { type: "checkbox", role: "switch", checked: !!value, onchange: (ev) => onchange(ev.target.checked) }),
    h("span", { class: "track", "aria-hidden": "true" }), h("span", { class: "toggle-text" }, label, tip ? info(label, tip) : null));
}
export const link = (text, onclick) => h("button", { type: "button", class: "link", onclick }, text);
export const note = (kind, text, ...more) => h("p", { class: "note " + kind },
  icon(kind === "err" ? "alert" : kind === "hint" ? "info" : "check"), h("span", {}, text, ...more));

const openInfo = new Set();
const HOSTS = ".em-row, .em-curve-head, .cline, .toggle, .label, .sec-head, .preview, .info-host";
export function info(label, text) {
  const key = String(label), on = openInfo.has(key);
  return h("button", { type: "button", class: "info", "aria-label": `About ${key}`, title: text, "aria-expanded": String(on), "data-info": key, "data-text": text,
    onclick: (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      const b = ev.currentTarget, now = !openInfo.has(key);
      if (now) openInfo.add(key); else openInfo.delete(key);
      b.setAttribute("aria-expanded", String(now));
      placeInfo(b);
    } }, icon("info"));
}
function placeInfo(b) {
  const host = b.closest(HOSTS) || b.parentElement, next = host.nextElementSibling;
  const has = next?.classList.contains("info-text") && next.dataset.for === b.dataset.info;
  if (b.getAttribute("aria-expanded") === "true" && !has) host.after(h("p", { class: "info-text", "data-for": b.dataset.info }, b.dataset.text));
  else if (b.getAttribute("aria-expanded") !== "true" && has) next.remove();
}

const decimals = (x) => { const s = String(+(+x).toFixed(6)); return s.includes(".") ? s.length - s.indexOf(".") - 1 : 0; };
export function valField({ label, value, base, min, max, step = 0.01, int = false, unit = "", scale = 1, onlive, onset, disabled = false }) {
  value = +value; base = +(base ?? value);
  const lo = Math.min(min, value, base), hi = Math.max(max, value, base);
  const at = (x) => (hi > lo ? Math.min(1, Math.max(0, (x - lo) / (hi - lo))) : 0);
  const dec = Math.min(4, decimals(step * scale));
  const show = (x) => String(+(x * scale).toFixed(dec)).replace(/^-0$/, "0");
  const snap = (x) => { let v = Math.round(Math.min(hi, Math.max(lo, x)) / step) * step; if (int) v = Math.round(v); return +v.toFixed(6); };
  const num = h("input", { class: "val-num", type: "number", step: String(+(step * scale).toFixed(6)), value: show(value), "aria-label": label, disabled,
    onchange: (ev) => { const v = +String(ev.target.value).replace(",", ".") / scale; if (Number.isFinite(v)) onset(int ? Math.round(v) : +v.toFixed(6)); } });
  const el = h("div", { class: "val", title: `Drag sideways or type. The line is the style's ${show(base)}${unit ? " " + unit : ""}` },
    h("span", { class: "val-bar", "aria-hidden": "true" }, h("i", { class: "val-fill" }), h("i", { class: "val-tick" })),
    num, unit ? h("span", { class: "val-unit" }, unit) : null);
  const paint = (v) => {
    el.style.setProperty("--px", `${Math.round(at(v) * VAL_W)}px`);
    el.style.setProperty("--bx", `${Math.round(3 + at(base) * (VAL_W - 8))}px`);
  };
  paint(value);
  el.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0 || disabled || document.activeElement === num) return;
    ev.preventDefault();
    const x0 = ev.clientX, v0 = value;
    let v = v0, moved = false;
    el.setPointerCapture(ev.pointerId);
    const move = (m) => {
      const dx = m.clientX - x0;
      if (!moved && Math.abs(dx) < 3) return;
      if (!moved) { moved = true; el.classList.add("drag"); }
      v = snap(v0 + dx * (hi - lo) / VAL_W * (m.shiftKey ? 0.1 : 1));
      num.value = show(v); paint(v); onlive?.(v);
    };
    const up = () => {
      el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up);
      el.classList.remove("drag");
      if (moved) { if (v !== v0) onset(v); } else { num.focus(); num.select(); }
    };
    el.addEventListener("pointermove", move); el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
  });
  return el;
}
export const resetBtn = (title, onclick) => h("button", { type: "button", class: "reset", title, "aria-label": title, onclick }, icon("reset"));
const gap = () => h("span", { class: "reset-gap", "aria-hidden": "true" });
export function valRow({ key, label, tip, unit = "", value, base, min, max, step, int, scale, changed, onlive, onset, onreset, resetTitle, extra, disabled }) {
  changed = changed ?? Math.abs(+value - +base) > 1e-9;
  const shown = (x) => String(+(+x * (scale || 1)).toFixed(4));
  return h("div", { class: "em-row" + (changed ? " changed" : ""), "data-key": key },
    h("span", { class: "em-label" }, label, tip ? info(label, tip) : null, extra || null),
    valField({ label, value, base, min, max, step, int, unit, scale, onlive, onset, disabled }),
    changed ? resetBtn(resetTitle || `Back to the style's value (${shown(base)}${unit ? " " + unit : ""})`, onreset) : gap());
}
export function choiceRow({ key, label, tip, control, changed, onreset, resetTitle, wide = true }) {
  return h("div", { class: "em-row choice" + (wide ? " wide" : "") + (changed ? " changed" : ""), "data-key": key },
    h("span", { class: "em-label" }, label, tip ? info(label, tip) : null), control,
    changed && onreset ? resetBtn(resetTitle || "Back to the style's choice", onreset) : gap());
}

export function inlineChoice(label, control, tip) {
  return h("div", { class: "cline" }, h("span", { class: "em-label" }, label, tip ? info(label, tip) : null), control);
}

export const secHead = (title, ...right) => h("div", { class: "sec-head" }, h("span", { class: "sec-title" }, title), ...right.filter(Boolean));
export function secFold({ key, title, open, sum = "", onflip, flipTitle = null }, ...right) {
  const own = open ? right.filter(Boolean) : [];
  return h("div", { class: "sec-head fold" + (open ? " open" : ""), "data-sec": key },
    h("button", { type: "button", class: "sec-flip", "aria-expanded": String(open), onclick: onflip, title: flipTitle },
      h("span", { class: "sec-title" }, title), sum && !own.length ? h("span", { class: "sec-sum", title: sum }, sum) : null),
    ...own);
}
const asRow = (k) => (k.matches?.(".seg, select, input, textarea, .bar") ? h("div", {}, k) : k);
export const blk = (...kids) => h("div", { class: "blk" }, ...kids.flat().filter(Boolean).map(asRow));
export function surfaces(kids) {
  const out = [];
  let cur = null;
  for (const k of kids.flat().filter(Boolean)) {
    if (k.classList?.contains("blk") || k.classList?.contains("sec-head")) { cur = null; out.push(k); continue; }
    if (!cur) { cur = h("div", { class: "blk" }); out.push(cur); }
    cur.append(asRow(k));
  }
  const full = out.filter((x) => !x.classList.contains("blk") || x.childElementCount);
  return full.filter((x, i) => !x.classList.contains("sec-head") || x.classList.contains("fold") || full[i + 1]?.classList.contains("blk"));
}

export function groupEl({ key, title, open, desc = "", state = "", badge = "", cls = "", onflip, flipTitle = null, body }) {
  const text = state || desc;
  return h("div", { class: "group" + (open ? " open" : "") + (cls ? ` ${cls}` : ""), "data-group": key },
    h("button", { type: "button", class: "group-head", "aria-expanded": String(open), onclick: onflip, title: flipTitle },
      h("span", { class: "group-title" }, title),
      badge ? h("span", { class: "group-badge" }, badge) : null,
      text ? h("span", { class: "group-hint", "data-full": text, title: text }, text) : null,
      icon("chevron", "chev")),
    open ? h("div", { class: "group-body" }, ...[].concat(body()).filter(Boolean)) : null);
}
function fitHints(root) {
  for (const g of root.querySelectorAll(".group-hint[data-full]")) {
    g.textContent = g.dataset.full;
    if (g.clientWidth && g.scrollWidth > g.clientWidth + 1) g.textContent = "";
  }
}

export function settle(root) {
  if (!root?.isConnected) return;
  fitSegs(root);
  fitHints(root);
  root.querySelectorAll("button.info[aria-expanded='true']").forEach(placeInfo);
}
