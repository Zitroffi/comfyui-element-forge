import { getJSON, postJSON, uid } from "./lib.js";

const clientId = (() => {
  const fresh = "element-forge-" + uid() + uid();
  try { const id = sessionStorage.getItem("ef.clientId") || fresh; sessionStorage.setItem("ef.clientId", id); return id; } catch { return fresh; }
})();
const handlers = new Map();
const early = new Map();
const listeners = new Set();
let ws = null;
let connected = false;
let retry = 0;

export const isConnected = () => connected;
export function onConnection(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function setConnected(v) { if (connected === v) return; connected = v; for (const fn of listeners) fn(v); }

function connect() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?clientId=${encodeURIComponent(clientId)}`;
  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { const again = everOpen; everOpen = true; retry = 0; setConnected(true); if (again) settleLost(); };
  ws.onclose = () => {
    setConnected(false);
    setTimeout(connect, Math.min(10000, 500 * 2 ** retry++));
  };
  ws.onmessage = (m) => {
    if (typeof m.data !== "string") return;
    let msg;
    try { msg = JSON.parse(m.data); } catch { return; }
    const d = msg.data || {};
    if (!d.prompt_id) return;
    if (!handlers.has(d.prompt_id)) {
      early.set(d.prompt_id, [...(early.get(d.prompt_id) || []), msg]);
      if (early.size > 40) early.delete(early.keys().next().value);
      return;
    }
    dispatch(msg);
  };
}
let everOpen = false;

function dispatch(msg) {
  const d = msg.data || {};
  const h = handlers.get(d.prompt_id);
  if (!h) return;
  switch (msg.type) {
      case "execution_start": h.onStart?.(); break;
      case "executing": if (d.node) h.onNode?.(d.node); break;
      case "progress": h.onProgress?.(d.value, d.max, d.node); break;
      case "executed": h.onOutput?.(d.node, d.output); break;
      case "execution_cached": h.onCached?.(d.nodes || []); break;
      case "execution_success": finish(d.prompt_id, { status: "done" }); break;
      case "execution_interrupted": finish(d.prompt_id, { status: "stopped" }); break;
      case "execution_error": finish(d.prompt_id, { status: "failed", error: d.exception_message, node: d.node_type, oom: /out of memory|OutOfMemory|CUDA error: out of memory/i.test(d.exception_message || "") }); break;
  }
}
function attach(id, on) {
  handlers.set(id, on);
  const msgs = early.get(id) || [];
  early.delete(id);
  for (const m of msgs) dispatch(m);
}
async function settleLost() {
  if (!handlers.size) return;
  try {
    const q = await getJSON("/queue");
    const queued = new Set([...q.queue_running, ...q.queue_pending].map((x) => x[1]));
    for (const [id, on] of [...handlers]) {
      if (queued.has(id) || handlers.get(id) !== on) continue;
      handlers.delete(id);
      await follow(id, on).catch(() => handlers.set(id, on));
    }
  } catch {  }
}
setInterval(() => { if (connected) settleLost(); }, 15000);

function finish(id, result) {
  const h = handlers.get(id);
  handlers.delete(id);
  h?.onDone?.(result);
}

export async function queue(graph, on = {}) {
  const r = await fetch("/prompt", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: graph, client_id: clientId, extra_data: { source: "element-forge-app" } }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.error) {
    const nodeErr = j.node_errors && Object.values(j.node_errors)[0];
    const detail = nodeErr?.errors?.[0] ? `${nodeErr.class_type}: ${nodeErr.errors[0].message} ${nodeErr.errors[0].details || ""}` : "";
    throw Object.assign(new Error(j.error?.message || j.error || `ComfyUI refused the job (HTTP ${r.status})`), { detail, nodeErrors: j.node_errors });
  }
  attach(j.prompt_id, on);
  return j.prompt_id;
}

export async function follow(id, on = {}) {
  const q = await getJSON("/queue");
  const inQueue = [...q.queue_running, ...q.queue_pending].some((x) => x[1] === id);
  if (inQueue) { attach(id, on); return "following"; }
  const hist = await getJSON(`/history/${encodeURIComponent(id)}`);
  const st = hist[id]?.status;
  if (!st) { on.onDone?.({ status: "lost" }); return "lost"; }
  const interrupted = st.messages?.some((m) => m[0] === "execution_interrupted");
  on.onDone?.({ status: st.status_str === "success" ? "done" : interrupted ? "stopped" : "failed", outputs: hist[id].outputs,
    error: st.messages?.find((m) => m[0] === "execution_error")?.[1]?.exception_message });
  return "finished";
}

export async function position(id) {
  const q = await getJSON("/queue");
  if (q.queue_running.some((x) => x[1] === id)) return 0;
  const pend = [...q.queue_pending].sort((a, b) => a[0] - b[0]);
  const i = pend.findIndex((x) => x[1] === id);
  return i < 0 ? -1 : i + 1 + q.queue_running.length;
}

export async function cancel(id) {
  const q = await getJSON("/queue");
  if (q.queue_pending.some((x) => x[1] === id)) {
    await postJSON("/queue", { delete: [id] });
    finish(id, { status: "stopped" });
    return "removed";
  }
  if (q.queue_running.some((x) => x[1] === id)) {
    await postJSON("/interrupt", { prompt_id: id });
    return "interrupting";
  }
  return "not-ours";
}

export const build = (variant, values, run, recipe, ltx = null, extra = {}) => postJSON("/element-forge/api/build", { variant, values, run, recipe, ...(ltx ? { ltx } : {}), ...extra });

export const connectSocket = () => { if (!ws) connect(); };
