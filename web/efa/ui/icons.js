const P = {
  undo: "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  redo: "m15 14 5-5-5-5M20 9H9.5a5.5 5.5 0 0 0 0 11H13",
  close: "M18 6 6 18M6 6l12 12",
  help: "M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4.5M12 18h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20",
  versions: "M12 2 2 7l10 5 10-5-10-5ZM2 17l10 5 10-5M2 12l10 5 10-5",
  play: "M7 4v16l13-8L7 4Z",
  pause: "M7 4h3v16H7zM14 4h3v16h-3z",
  loop: "M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3",
  hand: "M18 11V6a2 2 0 0 0-4 0v5M14 10V4a2 2 0 0 0-4 0v6M10 10.5V6a2 2 0 0 0-4 0v8l-1.6-1.6a2 2 0 0 0-2.8 2.8L7 21h9a4 4 0 0 0 4-4v-5a2 2 0 0 0-4 0",
  point: "M12 2v4M12 18v4M2 12h4M18 12h4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z",
  frame: "M3 7V3h4M17 3h4v4M21 17v4h-4M7 21H3v-4M7 7h10v10H7z",
  arrow: "M5 19 19 5M9 5h10v10",
  brush: "M9.1 15.5c-1.6 0-3.1 1.3-3.1 3V21c-1.7 0-3-1-3-1 1.2-1 1.5-2.3 1.5-3.5a3.5 3.5 0 0 1 4.6-3.3M21 3 11 13l-1.8-1.8L19.2 1.2",
  zoomIn: "M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16ZM21 21l-4.3-4.3M11 8v6M8 11h6",
  zoomOut: "M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16ZM21 21l-4.3-4.3M8 11h6",
  fit: "M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7",
  check: "M20 6 9 17l-5-5",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  upload: "M12 3v12M7 8l5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4",
  chevron: "m9 6 6 6-6 6",
  plus: "M12 5v14M5 12h14",
  gear: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM12 5a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1",
  live: "M13 2 3 14h9l-1 8 10-12h-9l1-8Z",
  calc: "M12 6v6l4 2M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z",
  gen: "M12 3l1.9 5.8L20 10.7l-5 3.6 1.9 5.7-4.9-3.5-4.9 3.5L9 14.3l-5-3.6 6.1-1.9L12 3Z",
  sidebar: "M3 4h18v16H3zM9 4v16",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12ZM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z",
  eyeOff: "M9.9 5.2A9.8 9.8 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.4 3.3M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7c1.9 0 3.6-.6 5-1.4M3 3l18 18M9.9 9.9a3 3 0 0 0 4.2 4.2",
  pick: "m2 22 1-1h3l9-9M3 21v-3l9-9M15 6l3.4-3.4a2.1 2.1 0 0 1 3 3L18 9l.4.4a2.1 2.1 0 0 1-3 3l-3.8-3.8a2.1 2.1 0 0 1 3-3l.4.4",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
};

export function icon(name, cls = "") {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "1.8");
  s.setAttribute("stroke-linecap", "round");
  s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("aria-hidden", "true");
  if (cls) s.setAttribute("class", cls);
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", P[name] || "");
  s.append(p);
  return s;
}
