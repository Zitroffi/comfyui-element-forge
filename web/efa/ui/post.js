export const DEFAULTS = {
  plate: { exposure: 0, contrast: 1, saturation: 1, temperature: 0, tint: 0 },
  element: { mode: "add", gain: 0, opacity: 1, saturation: 1, color: "#ffffff", color_amount: 0, offset_x: 0, offset_y: 0, scale: 1, stretch: 1, rotation: 0, pivot_x: null, pivot_y: null, time_offset: 0, visible: true },
  light: { strength: 1, color: "#ffffff", color_amount: 0 },
  glow: { exposure: -1, radius: 200, falloff: 2, threshold: 0.1, core: 2, color: "", color_amount: 1 },
  smoke: { opacity: 1 },
  lit: { others: 0 },
  haze: { amount: 0, color: "#8090a0", near: 0.3 },
  dof: { amount: 0, range: 0.15, focus: -1 },
  finish: { exposure: 0, rolloff: 0, vignette: 0, grain: 0, saturation: 1 },
};
export const clone = (o) => JSON.parse(JSON.stringify(o));
export function merge(s) {
  const out = clone(DEFAULTS);
  for (const [g, v] of Object.entries(s || {})) if (out[g] && v && typeof v === "object") for (const k of Object.keys(out[g])) if (k in v) out[g][k] = v[k];
  return out;
}

const VS = `#version 300 es
void main(){ vec2 p = vec2[3](vec2(-1.,-1.), vec2(3.,-1.), vec2(-1.,3.))[gl_VertexID]; gl_Position = vec4(p, 0., 1.); }`;

const COMMON = `#version 300 es
precision highp float;
uniform vec2 uSize;            // size of the target in px
uniform sampler2D uAtlas, uAtlasB;   // uFull: tiles 0-3 in uAtlas, 4-7 in uAtlasB (2 x 2 each); else all in uAtlas (4 x 2)
uniform bool uFull;
uniform vec2 uTile;            // tile size in px
uniform float uLogA, uLogMax;
out vec4 outColor;
vec2 img() { return vec2(gl_FragCoord.x / uSize.x, 1.0 - gl_FragCoord.y / uSize.y); }   // y = 0 at the top
vec4 tile(int k, vec2 p) {
  vec2 half_ = 0.75 / uTile;  // stay inside the tile: no bleeding from the neighbour (chroma subsampling)
  p = clamp(p, half_, 1.0 - half_);
  if (uFull) {
    int j = k % 4;
    vec2 uv = (vec2(float(j % 2), float(j / 2)) + p) / 2.0;
    return k < 4 ? texture(uAtlas, uv) : texture(uAtlasB, uv);
  }
  vec2 cr = vec2(float(k % 4), float(k / 4));
  return texture(uAtlas, (cr + p) / vec2(4.0, 2.0));
}
vec3 dec(vec3 v) { return (exp2(v * log2(1.0 + uLogA * uLogMax)) - 1.0) / uLogA; }
vec3 s2l(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
vec3 l2s(vec3 c) { c = max(c, 0.0); return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
`;

const FS_ELEMENT = COMMON + `
uniform vec2 uPlate; uniform vec2 uOff, uPivot, uScale; uniform float uRot, uGain, uOpacity, uSat, uColAmt; uniform vec3 uCol;
void main() {
  vec2 p = img();
  vec2 q = uPivot - 0.5 * uPlate;                    // pivot from the plate centre, px (y down)
  float c = cos(radians(uRot)), sn = sin(radians(uRot));
  vec2 s = (mat2(c, -sn, sn, c) * ((p - 0.5) * uPlate - q - uOff) / uScale + q) / uPlate + 0.5;   // inverse of: scale (x, y in its own axes), turn, move
  if (any(lessThan(s, vec2(0.0))) || any(greaterThan(s, vec2(1.0)))) { outColor = vec4(0.0); return; }
  vec3 e = dec(tile(1, s).rgb) * exp2(uGain) * uOpacity;
  float a = clamp(tile(4, s).r * uOpacity, 0.0, 1.0);
  float l = dot(e, LUMA);
  e = l + (e - l) * uSat;
  if (uColAmt > 0.0) e = e * (1.0 - uColAmt) + dot(e, LUMA) * uCol * uColAmt;
  outColor = vec4(max(e, 0.0), a);
}`;

const FS_THRESH = `#version 300 es
precision highp float;
uniform sampler2D uSrc; uniform vec2 uSize; uniform float uThr;
out vec4 outColor;
void main() {
  vec3 c = texture(uSrc, gl_FragCoord.xy / uSize).rgb;
  if (uThr > 0.0) {
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722)), knee = uThr * 0.5;
    float soft = pow(clamp(lum - uThr + knee, 0.0, 2.0 * knee), 2.0) / (4.0 * knee + 1e-8);
    c *= clamp(max(soft, lum - uThr) / max(lum, 1e-8), 0.0, 1.0);
  }
  outColor = vec4(c, 1.0);
}`;

const FS_DOWN = `#version 300 es
precision highp float;
uniform sampler2D uSrc; uniform vec2 uSrcSize, uSize;
out vec4 outColor;
vec3 T(vec2 tc, float x, float y) { return texture(uSrc, tc + vec2(x, y) / uSrcSize).rgb; }
void main() {   // 13-tap downsample (Jimenez 2014): a soft gaussian-like step per level
  vec2 tc = gl_FragCoord.xy / uSize;
  vec3 a = T(tc,-2.,-2.), b = T(tc,0.,-2.), c = T(tc,2.,-2.), d = T(tc,-1.,-1.), e = T(tc,1.,-1.), f = T(tc,-2.,0.), g = T(tc,0.,0.),
       h = T(tc,2.,0.), i = T(tc,-1.,1.), j = T(tc,1.,1.), k = T(tc,-2.,2.), l = T(tc,0.,2.), m = T(tc,2.,2.);
  vec3 r = (d + e + i + j) * 0.125 + (a + b + g + f) * 0.03125 + (b + c + h + g) * 0.03125 + (f + g + l + k) * 0.03125 + (g + h + m + l) * 0.03125;
  outColor = vec4(r, 1.0);
}`;

const MAXL = 11;
const LIT_DOWN = 5;
const GLOW = `
uniform sampler2D uL[${MAXL}];       // glow pyramid (level 0 = thresholded element)
uniform vec2 uLs[${MAXL}];
uniform int uLevels;
uniform float uSig[24]; uniform float uW[24]; uniform int uNSig;   // glow: sigmas in tile px and weights
uniform float uGlowExp, uGlowTintAmt; uniform vec3 uGlowTint; uniform bool uGlowTintOn;
vec4 flipT(sampler2D t, vec2 p) { return texture(t, vec2(p.x, 1.0 - p.y)); }
vec4 cubic(float v) { vec4 n = vec4(1.0, 2.0, 3.0, 4.0) - v; vec4 s = n * n * n; float x = s.x, y = s.y - 4.0 * s.x, z = s.z - 4.0 * s.y + 6.0 * s.x;
  return vec4(x, y, z, 6.0 - x - y - z) * (1.0 / 6.0); }
vec3 bspline(sampler2D t, vec2 size, vec2 tc) {   // smooth (cubic B-spline) upsampling of a small level, 4 taps
  tc = tc * size - 0.5; vec2 f = fract(tc); tc -= f;
  vec4 xc = cubic(f.x), yc = cubic(f.y);
  vec4 c = tc.xxyy + vec2(-0.5, 1.5).xyxy; vec4 s = vec4(xc.xz + xc.yw, yc.xz + yc.yw);
  vec4 o = c + vec4(xc.yw, yc.yw) / s; o /= size.xxyy;
  vec3 s0 = texture(t, o.xz).rgb, s1 = texture(t, o.yz).rgb, s2 = texture(t, o.xw).rgb, s3 = texture(t, o.yw).rgb;
  float sx = s.x / (s.x + s.y), sy = s.z / (s.z + s.w);
  return mix(mix(s3, s2, sx), mix(s1, s0, sx), sy);
}
vec3 level(int k, vec2 tc) {
  ${Array.from({ length: MAXL }, (_, k) => `if (k == ${k}) return ${k === 0 ? "texture(uL[0], tc).rgb" : `bspline(uL[${k}], uLs[${k}], tc)`};`).join("\n  ")}
  return vec3(0.0);
}
vec3 glowAt(vec2 p) {
  vec2 tc = vec2(p.x, 1.0 - p.y);
  vec3 g = vec3(0.0);
  for (int i = 0; i < 24; i++) {
    if (i >= uNSig) break;
    float lv = uSig[i] < 0.8 ? uSig[i] / 0.8 : 1.0 + log2(uSig[i] / 0.8);   // level k ~ gaussian sigma 0.8 * 2^k
    lv = clamp(lv, 0.0, float(uLevels - 1));
    int k0 = int(floor(lv)); int k1 = min(k0 + 1, uLevels - 1);
    g += uW[i] * mix(level(k0, tc), level(k1, tc), lv - float(k0));
  }
  g *= exp2(uGlowExp);
  if (uGlowTintOn) g = g * (1.0 - uGlowTintAmt) + dot(g, LUMA) * uGlowTint * uGlowTintAmt;
  return g;
}
uniform float uLStr, uLColAmt; uniform vec3 uLCol; uniform bool uHasLight, uHasSmoke, uOver;
uniform float uSmokeOp;
vec3 lightAt(vec2 p) {
  if (!uHasLight) return vec3(0.0);
  vec3 L = dec(tile(2, p).rgb) * uLStr;
  if (uLColAmt > 0.0) L = L * (1.0 - uLColAmt) + dot(L, LUMA) * uLCol * uLColAmt;
  return L;
}
`;
const FS_PLATE = COMMON + `
uniform float uPExp, uPCon, uPSat, uPTemp, uPTint;
void main() {
  vec3 P = s2l(tile(0, img()).rgb) * exp2(uPExp);
  P *= vec3(1.0 + 0.1 * uPTemp - 0.05 * uPTint, 1.0 + 0.1 * uPTint, 1.0 - 0.1 * uPTemp - 0.05 * uPTint);
  float pl = dot(P, LUMA); P = pl + (P - pl) * uPSat;
  P = 0.18 * pow(max(P, 0.0) / 0.18, vec3(uPCon));
  outColor = vec4(P, 1.0);
}`;
const FS_ADD = COMMON + GLOW + `
uniform sampler2D uC;                 // comp so far (same size as this target)
uniform sampler2D uE;                 // element pass of this layer (premultiplied linear + alpha), FBO
uniform float uK;                     // fade weight of the whole layer (fade_weight in app_nodes.py)
uniform bool uShowE;                  // element muted: its light and glow stay (element.visible)
uniform sampler2D uIrr;               // F6: light falling here from the other layers (FS_IRR); unit 3, the 16th sampler
uniform float uLit;                   // lit.others; 0 = off
void main() {
  vec2 p = img();
  vec2 fc = gl_FragCoord.xy / uSize;
  vec3 own = lightAt(p) * uK;
  vec3 C = texture(uC, fc).rgb + own;
  vec3 g = vec3(1.0);
  if (uLit > 0.0) g = 1.0 + uLit * texture(uIrr, fc).rgb;   // as lit_by() in app_nodes.py
  vec4 E = uShowE ? flipT(uE, p) * uK : vec4(0.0);
  E.rgb *= g;
  C = uOver ? C * (1.0 - E.a) + E.rgb : C + E.rgb;
  if (uHasSmoke) { float sa = clamp(tile(6, p).r * uSmokeOp, 0.0, 1.0) * uK; C = C * (1.0 - sa) + dec(tile(3, p).rgb) * g * uSmokeOp * uK; }
  outColor = vec4(C + glowAt(p) * uK, 1.0);
}`;
const FS_LSUM = COMMON + GLOW + `
uniform sampler2D uC;
uniform float uK;
void main() { outColor = vec4(texture(uC, gl_FragCoord.xy / uSize).rgb + lightAt(img()) * uK, 1.0); }`;
const FS_FINAL = COMMON + GLOW + `
uniform sampler2D uC, uP, uE;          // comp of all layers, graded plate, element of the main layer
uniform bool uHasDepth;
uniform float uHaze, uHazeNear; uniform vec3 uHazeCol;
uniform float uFExp, uRoll, uVig, uGrain, uFSat, uFrame;
uniform int uView; uniform float uWipe;
float hash(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
void main() {
  vec2 p = img();
  vec3 raw = tile(0, p).rgb;
  if (uWipe >= 0.0 && p.x < uWipe) { outColor = vec4(raw, 1.0); return; }   // before/after: left of the wipe the untouched plate
  vec2 fc = gl_FragCoord.xy / uSize;
  vec3 C = texture(uC, fc).rgb;
  float depth = tile(5, p).r;
  if (uHaze > 0.0 && uHasDepth) {
    float far = 1.0 - depth;
    float k = clamp(uHaze * clamp((far - (1.0 - uHazeNear)) / max(1e-3, uHazeNear), 0.0, 1.0), 0.0, 1.0);
    C = C * (1.0 - k) + uHazeCol * k;
  }
  C *= exp2(uFExp);
  float cl = dot(C, LUMA); C = cl + (C - cl) * uFSat;
  if (uRoll > 0.0) { float k = 1.0 - 0.6 * uRoll; vec3 over = max(C - k, 0.0); C = mix(C, k + over / (1.0 + over / (1.0 - k + 1e-6)), step(k, C)); }
  if (uVig > 0.0) { vec2 q = p * 2.0 - 1.0; float r2 = dot(q, q) / 2.0; C *= 1.0 - uVig * pow(r2, 1.5); }
  if (uGrain > 0.0) {
    vec2 px = floor(p * uSize) + uFrame * 17.0;
    float n = (hash(px) + hash(px + 31.7) + hash(px + 71.3) - 1.5) * 2.0;
    C += n * uGrain * 0.04 * sqrt(clamp(C, 0.0, 1.0));
  }
  C = max(C, 0.0);
  vec4 E = flipT(uE, p);
  if (uView == 2) C = texture(uP, fc).rgb;
  else if (uView == 3) C = E.rgb;
  else if (uView == 4) C = lightAt(p);
  else if (uView == 5) C = glowAt(p);
  else if (uView == 6) C = vec3(E.a);
  else if (uView == 7) C = uHasDepth ? vec3(depth) : vec3(0.0);
  else if (uView == 8) { float sa = uHasSmoke ? clamp(tile(6, p).r * uSmokeOp, 0.0, 1.0) : 0.0;   // smoke over mid grey: dark smoke shows too
    C = vec3(0.18) * (1.0 - sa) + (uHasSmoke ? dec(tile(3, p).rgb) * uSmokeOp : vec3(0.0)); }
  vec3 o = uView == 6 || uView == 7 ? C : l2s(clamp(C, 0.0, 1.0));
  o += (hash(gl_FragCoord.xy + uFrame) - 0.5) / 255.0;   // dither against banding
  outColor = vec4(o, 1.0);
}`;

const DOFL = 5;
const FS_DOF = COMMON + `
uniform sampler2D uC; uniform sampler2D uD[${DOFL}];
uniform float uSmax, uRange, uFocus;
void main() {
  vec2 p = img(), fc = gl_FragCoord.xy / uSize;
  float depth = tile(5, p).r;
  float coc = clamp((abs(depth - uFocus) - 0.02) / max(1e-3, uRange), 0.0, 1.0);
  float lv = clamp(log2(max(coc * uSmax, 1.0)), 0.0, float(${DOFL}));
  vec3 C = texture(uC, fc).rgb * max(0.0, 1.0 - lv);
  ${Array.from({ length: DOFL }, (_, k) => `C += texture(uD[${k}], fc).rgb * max(0.0, 1.0 - abs(lv - ${k + 1}.0));`).join(" ")}
  outColor = vec4(C, 1.0);
}`;

const FS_IRR = `#version 300 es
precision highp float;
uniform sampler2D uA, uB; uniform vec2 uSize;
out vec4 outColor;
void main() { vec2 fc = gl_FragCoord.xy / uSize;
  float pl = dot(texture(uB, fc).rgb, vec3(0.2126, 0.7152, 0.0722));
  outColor = vec4(clamp(max(texture(uA, fc).rgb, 0.0) / (pl + 0.05), 0.0, 8.0), 1.0); }`;

const FS_MERGE = `#version 300 es
precision highp float;
uniform sampler2D uA, uB; uniform vec2 uSize; uniform float uWipe;
out vec4 outColor;
void main() { vec2 fc = gl_FragCoord.xy / uSize; outColor = vec4(fc.x < uWipe ? texture(uB, fc).rgb : texture(uA, fc).rgb, 1.0); }`;

export const VIEWS = ["comp", "before", "plate", "element", "light", "glow", "alpha", "depth", "smoke", "versions"];

function hexLin(h) {
  h = (h || "#ffffff").replace("#", "");
  const c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return c;
}
function lumNorm(c) { const l = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; return c.map((v) => v / Math.max(l, 1e-6)); }

export class PostRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext("webgl2", { antialias: false, premultipliedAlpha: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error("WebGL2 is not available in this browser.");
    if (!gl.getExtension("EXT_color_buffer_float")) throw new Error("This GPU/browser cannot render to float textures (EXT_color_buffer_float).");
    gl.getExtension("OES_texture_float_linear");
    this.gl = gl;
    this.settings = clone(DEFAULTS);
    this.view = "comp";
    this.wipe = 0.5;
    this.frame = 0;
    this.onframe = null;
    this.under = []; this.over = [];
    this.cmp = null;
    this.prog = {
      element: this.program(FS_ELEMENT), thresh: this.program(FS_THRESH), down: this.program(FS_DOWN),
      plate: this.program(FS_PLATE), add: this.program(FS_ADD), final: this.program(FS_FINAL), merge: this.program(FS_MERGE),
      dof: this.program(FS_DOF), lsum: this.program(FS_LSUM), irr: this.program(FS_IRR),
    };
    this.vao = gl.createVertexArray();
    this.main = this.layer();
    this.video = this.main.video;
    this.video.addEventListener("pause", () => { for (const L of this.extras) L.video.pause(); setTimeout(() => this.showFull(), 60); });
    this.video.addEventListener("play", () => { for (const L of this.extras) L.video.play().catch(() => {}); this.onfull?.(false); });
    this.video.addEventListener("seeked", () => { if (!this.playing) setTimeout(() => this.showFull(), 30); });
  }

  destroy() {
    this.ready = false;
    for (const L of [this.main, ...this.under, ...this.over, ...(this.cmp ? [this.cmp] : [])]) { L.dropped = true; L.ready = false; L.abort?.(); L.video.pause(); L.video.removeAttribute("src"); L.video.load();
      for (const x of L.full ? [L.full.a, L.full.b] : []) if (x.vid) { x.vid.removeAttribute("src"); x.vid.load(); x.vid = null; } }
    this.under = []; this.over = [];
    this.gl.getExtension("WEBGL_lose_context")?.loseContext();
  }

  layer() {
    const gl = this.gl;
    const atlas = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, atlas);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    const video = document.createElement("video");
    Object.assign(video, { muted: true, loop: true, playsInline: true, preload: "auto" });
    return { atlas, video, man: null, tile: null, E: null, levels: [], ready: false, settings: clone(DEFAULTS), adjust: null, full: null };
  }

  program(fs) {
    const gl = this.gl;
    const mk = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, VS)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const loc = new Map();
    return { p, u: (n) => { if (!loc.has(n)) loc.set(n, gl.getUniformLocation(p, n)); return loc.get(n); } };
  }

  target(w, h) {
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return { tex, fbo, w, h };
  }
  freeTarget(t) { if (t) { this.gl.deleteTexture(t.tex); this.gl.deleteFramebuffer(t.fbo); } }

  async loadLayer(L, manifestUrl) {
    const res = await fetch(manifestUrl, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status === 404 ? "its preview files are missing" : `HTTP ${res.status}`);
    const man = await res.json();
    if (L.dropped) throw new Error("dropped");
    L.man = man;
    const [tw, th] = man.tile_size;
    L.tile = [tw, th];
    const [rw, rh] = man.full?.tile_size || man.tile_size;
    L.size = [rw, rh];
    L.E = this.target(rw, rh);
    L.levels = [];
    let w = rw, h = rh;
    for (let k = 0; k < MAXL && w >= 2 && h >= 2; k++) { L.levels.push(this.target(w, h)); w = Math.max(1, w >> 1); h = Math.max(1, h >> 1); }
    const base = manifestUrl.slice(0, manifestUrl.lastIndexOf("/") + 1);
    const v = L.video;
    v.pause();
    v.src = base + man.video + "?t=" + Date.now();
    await new Promise((res, rej) => { v.onloadeddata = res; v.onerror = () => rej(new Error("Cannot load the preview video."));
      L.abort = () => rej(new Error("dropped")); });
    L.abort = null;
    if (L.dropped) throw new Error("dropped");
    if (man.full) {
      const mk = (name) => { const t = this.gl.createTexture(); this.gl.bindTexture(this.gl.TEXTURE_2D, t);
        for (const [k, val] of [[this.gl.TEXTURE_MIN_FILTER, this.gl.LINEAR], [this.gl.TEXTURE_MAG_FILTER, this.gl.LINEAR], [this.gl.TEXTURE_WRAP_S, this.gl.CLAMP_TO_EDGE], [this.gl.TEXTURE_WRAP_T, this.gl.CLAMP_TO_EDGE]]) this.gl.texParameteri(this.gl.TEXTURE_2D, k, val);
        return { tex: t, url: base + name + "?t=" + Date.now(), vid: null }; };
      const [a, b] = man.full.videos.map(mk);
      L.full = { a, b, tile: man.full.tile_size, frame: -1 };
    }
    L.ready = true;
    this.upload(L);
    return man;
  }

  showFull() {
    if (!this.ready || this.playing) return;
    if (this._fullBusy) { this._fullAgain = true; return; }
    this._fullBusy = true;
    this._showFull().catch(() => {}).finally(() => {
      this._fullBusy = false;
      if (this._fullAgain) { this._fullAgain = false; this.showFull(); }
    });
  }
  async _showFull() {
    const f = this.frame;
    const layers = [this.main, ...this.extras].filter((L) => L.full && L.ready && !L.dropped);
    if (!layers.length) return;
    const t = (f + 0.5) / this.man.fps;
    const open = (x) => new Promise((res) => {
      const v = document.createElement("video");
      Object.assign(v, { muted: true, playsInline: true, preload: "auto" });
      x.vid = v;
      const end = (ok) => { clearTimeout(timer); v.onloadeddata = v.onseeked = v.onerror = null;
        res(ok && x.vid === v && !v.seeking && v.readyState >= 2 && !v.error); };
      const timer = setTimeout(() => end(false), 6000);
      v.onerror = () => end(false);
      v.onloadeddata = () => { v.onloadeddata = null; v.onseeked = () => end(true); v.currentTime = t; };
      v.src = x.url;
    });
    const close = () => { for (const L of layers) for (const x of [L.full.a, L.full.b]) if (x.vid) { x.vid.removeAttribute("src"); x.vid.load(); x.vid = null; } };
    this.fullFailed = false;
    const ok = await Promise.all(layers.flatMap((L) => [open(L.full.a), open(L.full.b)]));
    if (!this.ready || this.playing || this.frame !== f) { close(); this.onfull?.(false); return; }
    const gl = this.gl;
    layers.forEach((L, i) => {
      if (L.dropped) return;
      if (!ok[2 * i] || !ok[2 * i + 1]) { L.full.frame = -1; if (L === this.main) this.fullFailed = true; return; }
      for (const x of [L.full.a, L.full.b]) { gl.bindTexture(gl.TEXTURE_2D, x.tex); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, x.vid); }
      L.full.frame = f;
    });
    close();
    this.render();
    this.onfull?.(this.fullShown());
  }
  fullShown() { return !!this.main.full && this.main.full.frame === this.frame && !this.playing; }

  async load(manifestUrl) {
    const L = this.main;
    const man = await this.loadLayer(L, manifestUrl);
    this.man = man;
    this.tile = L.size;
    this.canvas.width = L.size[0]; this.canvas.height = L.size[1];
    for (const t of [this.P, this.CA, this.CB, this.CC, this.CD, this.CW]) this.freeTarget(t);
    this.P = this.target(...L.size); this.CA = this.target(...L.size); this.CB = this.target(...L.size);
    this.CC = this.CD = this.CW = null;
    this.ready = true;
    const v = L.video;
    const tick = (now, meta) => {
      if (!this.ready || v.src !== this._src) return;
      const t = meta?.mediaTime ?? v.currentTime;
      this.frame = Math.min(man.frames - 1, Math.floor(t * man.fps + 1e-3));
      this.follow(t);
      this.upload(L); this.render(); this.onframe?.(this.frame);
      v.requestVideoFrameCallback(tick);
    };
    this._src = v.src;
    if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(tick);
    v.onseeked = () => { this.frame = Math.min(man.frames - 1, Math.floor(v.currentTime * man.fps + 1e-3)); this.upload(L); this.render(); this.onframe?.(this.frame); };
    this.render();
    return man;
  }

  async setLayers(list) {
    const old = new Map([...this.under, ...this.over].map((L) => [L.key, L]));
    const under = [], over = [];
    const loads = [];
    for (const it of list) {
      let L = old.get(it.key);
      if (L && L.url !== it.url) { this.dropLayer(L); old.delete(it.key); L = null; }
      if (!L) {
        L = this.layer(); L.key = it.key; L.url = it.url;
        loads.push(this.loadLayer(L, it.url).then(() => { if (L.dropped) return; L.video.currentTime = this.video.currentTime; L.video.onseeked = () => { this.upload(L); this.render(); };
          if (this.playing) L.video.play().catch(() => {}); else this.showFull(); this.render(); }).catch(() => { L.failed = true; }));
      }
      old.delete(it.key);
      L.settings = merge(it.settings); L.adjust = it.adjust || null;
      (it.below ? under : over).push(L);
    }
    for (const L of old.values()) this.dropLayer(L);
    this.under = under; this.over = over;
    this.render();
    await Promise.all(loads);
  }
  async setCompare(url) {
    if ((this.cmp?.url || null) === (url || null)) return true;
    if (this.cmp) { this.dropLayer(this.cmp); this.cmp = null; }
    if (!url) { this.render(); return true; }
    const L = this.layer(); L.url = url; this.cmp = L;
    try { await this.loadLayer(L, url); } catch {
      if (this.cmp === L) { this.dropLayer(L); this.cmp = null; }
      return false;
    }
    if (L.dropped) return false;
    L.video.currentTime = this.video.currentTime;
    L.video.onseeked = () => { this.upload(L); this.render(); };
    if (this.playing) L.video.play().catch(() => {}); else this.showFull();
    this.render();
    return true;
  }
  dropLayer(L) {
    L.dropped = true; L.ready = false;
    L.abort?.();
    L.video.pause(); L.video.removeAttribute("src"); L.video.load();
    this.freeTarget(L.E); L.levels.forEach((t) => this.freeTarget(t)); this.gl.deleteTexture(L.atlas);
    for (const x of L.full ? [L.full.a, L.full.b] : []) { if (x.vid) { x.vid.removeAttribute("src"); x.vid.load(); x.vid = null; } this.gl.deleteTexture(x.tex); }
  }
  get extras() { return [...this.under, ...this.over, ...(this.cmp ? [this.cmp] : [])].filter((L) => L.ready); }
  follow(t) {
    const main = this.video;
    for (const L of this.extras) {
      const v = L.video, fps = L.man.fps || this.man.fps;
      if (main.paused && !v.paused) v.pause();
      if (!main.paused && v.paused) v.play().catch(() => {});
      if (Math.abs(v.currentTime - t) > 1.5 / fps) v.currentTime = t;
      this.upload(L);
    }
  }

  upload(L = this.main) {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, L.atlas);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, L.video);
  }

  play() { this.video.play(); for (const L of this.extras) L.video.play().catch(() => {}); }
  pause() { this.video.pause(); for (const L of this.extras) L.video.pause(); }
  get playing() { return !this.video.paused; }
  seek(f) { const t = (f + 0.5) / this.man.fps; this.video.currentTime = t; for (const L of this.extras) L.video.currentTime = t; }
  set(settings) { this.settings = merge(settings); this.render(); }
  setView(v) { this.view = v; this.render(); }
  setWipe(x) { this.wipe = x; this.render(); }

  draw(prog, target, uniforms) {
    const gl = this.gl;
    gl.useProgram(prog.p);
    gl.bindVertexArray(this.vao);
    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.fbo : null);
    const [w, h] = target ? [target.w, target.h] : [this.canvas.width, this.canvas.height];
    gl.viewport(0, 0, w, h);
    gl.uniform2f(prog.u("uSize"), w, h);
    uniforms(prog);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  bindTex(prog, name, tex, unit) {
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.uniform1i(prog.u(name), unit);
  }

  atlasUniforms(prog, L) {
    const gl = this.gl;
    const full = L.full && L.full.frame === this.frame && !this.playing;
    gl.uniform1i(prog.u("uFull"), full ? 1 : 0);
    if (full) {
      this.bindTex(prog, "uAtlas", L.full.a.tex, 0); this.bindTex(prog, "uAtlasB", L.full.b.tex, 15);
      gl.uniform2f(prog.u("uTile"), L.full.tile[0], L.full.tile[1]);
    } else {
      this.bindTex(prog, "uAtlas", L.atlas, 0); gl.uniform1i(prog.u("uAtlasB"), 0);
      gl.uniform2f(prog.u("uTile"), L.tile[0], L.tile[1]);
    }
    gl.uniform1f(prog.u("uLogA"), L.man.encoding.hdr.a);
    gl.uniform1f(prog.u("uLogMax"), L.man.encoding.hdr.max);
  }

  layerPasses(L, s) {
    const gl = this.gl, e = s.element, man = L.man;
    this.draw(this.prog.element, L.E, (pr) => {
      this.atlasUniforms(pr, L);
      gl.uniform2f(pr.u("uPlate"), man.plate_size[0], man.plate_size[1]);
      gl.uniform2f(pr.u("uOff"), e.offset_x, e.offset_y);
      gl.uniform2f(pr.u("uScale"), e.scale || 1, (e.scale || 1) * (e.stretch || 1));
      gl.uniform1f(pr.u("uRot"), e.rotation || 0);
      gl.uniform2f(pr.u("uPivot"), e.pivot_x ?? man.plate_size[0] / 2, e.pivot_y ?? man.plate_size[1] / 2);
      gl.uniform1f(pr.u("uGain"), e.gain); gl.uniform1f(pr.u("uOpacity"), e.opacity); gl.uniform1f(pr.u("uSat"), e.saturation);
      gl.uniform1f(pr.u("uColAmt"), e.color_amount); gl.uniform3fv(pr.u("uCol"), lumNorm(hexLin(e.color)));
    });
    const Lv = L.levels;
    this.draw(this.prog.thresh, Lv[0], (pr) => { this.bindTex(pr, "uSrc", L.E.tex, 0); gl.uniform1f(pr.u("uThr"), s.glow.threshold); });
    for (let k = 1; k < Lv.length; k++) {
      this.draw(this.prog.down, Lv[k], (pr) => { this.bindTex(pr, "uSrc", Lv[k - 1].tex, 0); gl.uniform2f(pr.u("uSrcSize"), Lv[k - 1].w, Lv[k - 1].h); });
    }
  }

  layerUniforms(pr, L, s) {
    const gl = this.gl, man = L.man, g = s.glow;
    this.atlasUniforms(pr, L);
    const scale = L.size[0] / man.plate_size[0];
    const sig = []; let sg = Math.min(Math.max(0.5, g.core), Math.max(2, g.radius) / 2);
    while (sg <= Math.max(2, g.radius) / 2 + 1e-6 && sig.length < 24) { sig.push(sg); sg *= Math.SQRT2; }
    const ws = sig.map((x) => x ** (2 - g.falloff)); const sum = ws.reduce((a, b) => a + b, 0);
    const units = [], sizes = [];
    for (let k = 0; k < MAXL; k++) { const lv = L.levels[Math.min(k, L.levels.length - 1)]; units.push(4 + k); sizes.push(lv.w, lv.h);
      gl.activeTexture(gl.TEXTURE4 + k); gl.bindTexture(gl.TEXTURE_2D, lv.tex); }
    gl.uniform1iv(pr.u("uL"), units); gl.uniform2fv(pr.u("uLs"), sizes); gl.uniform1i(pr.u("uLevels"), L.levels.length);
    const sg24 = new Float32Array(24), w24 = new Float32Array(24);
    sig.forEach((x, i) => { sg24[i] = x * scale; w24[i] = ws[i] / sum; });
    gl.uniform1fv(pr.u("uSig"), sg24); gl.uniform1fv(pr.u("uW"), w24); gl.uniform1i(pr.u("uNSig"), sig.length);
    gl.uniform1f(pr.u("uGlowExp"), g.exposure);
    gl.uniform1i(pr.u("uGlowTintOn"), g.color ? 1 : 0); gl.uniform1f(pr.u("uGlowTintAmt"), g.color_amount);
    gl.uniform3fv(pr.u("uGlowTint"), lumNorm(hexLin(g.color || "#ffffff")));
    gl.uniform1f(pr.u("uLStr"), s.light.strength); gl.uniform1f(pr.u("uLColAmt"), s.light.color_amount);
    gl.uniform3fv(pr.u("uLCol"), lumNorm(hexLin(s.light.color)));
    gl.uniform1i(pr.u("uHasLight"), man.passes.light ? 1 : 0); gl.uniform1i(pr.u("uHasSmoke"), man.passes.smoke ? 1 : 0);
    gl.uniform1i(pr.u("uOver"), s.element.mode === "over" ? 1 : 0);
    gl.uniform1f(pr.u("uSmokeOp"), s.smoke.opacity);
    gl.uniform1f(pr.u("uK"), s.weight ?? 1);
    gl.uniform1i(pr.u("uShowE"), s.element.visible === false ? 0 : 1);
  }

  depthBlur(src, dof, M) {
    const gl = this.gl;
    const [w, h] = M.size;
    const smax = dof.amount * 0.01 * Math.max(w, h);
    if (smax < 1) return src;
    if (!this.DL || this.DL.w !== w || this.DL.h !== h) {
      if (this.DL) for (const t of [this.DL.out, ...this.DL.lv]) this.freeTarget(t);
      const lv = [];
      for (let k = 0, lw = w, lh = h; k < DOFL; k++) { lw = Math.max(1, Math.ceil(lw / 2)); lh = Math.max(1, Math.ceil(lh / 2)); lv.push(this.target(lw, lh)); }
      this.DL = { w, h, lv, out: this.target(w, h) };
    }
    let prev = src;
    for (const t of this.DL.lv) {
      this.draw(this.prog.down, t, (pr) => { this.bindTex(pr, "uSrc", prev.tex, 0); gl.uniform2f(pr.u("uSrcSize"), prev.w, prev.h); });
      prev = t;
    }
    const fl = this.man.focus || [];
    const focus = dof.focus >= 0 ? dof.focus : fl.length ? fl[Math.min(this.frame, fl.length - 1)] : 0.5;
    this.draw(this.prog.dof, this.DL.out, (pr) => {
      this.atlasUniforms(pr, M);
      this.bindTex(pr, "uC", src.tex, 1);
      this.DL.lv.forEach((t, k) => { gl.activeTexture(gl.TEXTURE2 + k); gl.bindTexture(gl.TEXTURE_2D, t.tex); });
      gl.uniform1iv(pr.u("uD"), this.DL.lv.map((_, k) => 2 + k));
      gl.uniform1f(pr.u("uSmax"), smax); gl.uniform1f(pr.u("uRange"), dof.range); gl.uniform1f(pr.u("uFocus"), focus);
    });
    return this.DL.out;
  }

  render() {
    if (!this.ready) return;
    const gl = this.gl;
    const M = this.main;
    const sm = this.adjust ? this.adjust(this.settings, this.frame) : this.settings;
    const eff = (L) => (L === M ? sm : L.adjust ? L.adjust(L.settings, this.frame) : L.settings);
    const stack = [...this.under.filter((L) => L.ready), M, ...this.over.filter((L) => L.ready)];
    const p = sm.plate;
    this.draw(this.prog.plate, this.P, (pr) => {
      this.atlasUniforms(pr, stack[0]);
      gl.uniform1f(pr.u("uPExp"), p.exposure); gl.uniform1f(pr.u("uPCon"), p.contrast); gl.uniform1f(pr.u("uPSat"), p.saturation);
      gl.uniform1f(pr.u("uPTemp"), p.temperature); gl.uniform1f(pr.u("uPTint"), p.tint);
    });
    const base = sm.dof?.amount > 0 && this.man.passes.depth ? this.depthBlur(this.P, sm.dof, M) : this.P;
    const lit = stack.length > 1 && stack.some((L) => (eff(L).lit?.others ?? 0) > 0);
    const soft = (src, chain) => {
      let s = src;
      for (const t of chain) { this.draw(this.prog.down, t, (pr) => { this.bindTex(pr, "uSrc", s.tex, 0); gl.uniform2f(pr.u("uSrcSize"), s.w, s.h); }); s = t; }
      return s;
    };
    let plSoft = null;
    if (lit) {
      if (!this.LA || this.LA.w !== M.size[0] || this.LA.h !== M.size[1]) {
        for (const t of [this.LA, this.LB, ...(this.LSC || []), ...(this.PLC || [])]) this.freeTarget(t);
        this.LA = this.target(...M.size); this.LB = this.target(...M.size);
        const chain = () => { const c = []; let [w, h] = M.size;
          for (let k = 0; k < LIT_DOWN; k++) { w = Math.max(1, Math.ceil(w / 2)); h = Math.max(1, Math.ceil(h / 2)); c.push(this.target(w, h)); }
          return c; };
        this.LSC = chain(); this.PLC = chain();
      }
      plSoft = soft(base, this.PLC);
    }
    const othersSoft = (me) => {
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.LA.fbo); gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
      let ls = this.LA, ld = this.LB;
      for (const L of stack) {
        const s = eff(L);
        if (L === me || (L !== M && (s.weight ?? 1) <= 0)) continue;
        this.draw(this.prog.lsum, ld, (pr) => { this.layerUniforms(pr, L, s); this.bindTex(pr, "uC", ls.tex, 1); });
        [ls, ld] = [ld, ls];
      }
      const lo = soft(ls, this.LSC);
      this.draw(this.prog.irr, this.LA, (pr) => { this.bindTex(pr, "uA", lo.tex, 1); this.bindTex(pr, "uB", plSoft.tex, 2); });
      return this.LA;
    };
    let src = base, dst = this.CA;
    for (const L of stack) {
      const s = eff(L);
      if (L !== M && (s.weight ?? 1) <= 0) continue;
      this.layerPasses(L, s);
      const lo = lit && (s.lit?.others ?? 0) > 0 ? othersSoft(L) : null;
      this.draw(this.prog.add, dst, (pr) => {
        this.layerUniforms(pr, L, s);
        this.bindTex(pr, "uC", src.tex, 1);
        this.bindTex(pr, "uE", L.E.tex, 2);
        gl.uniform1f(pr.u("uLit"), lo ? s.lit.others : 0);
        if (lo) this.bindTex(pr, "uIrr", lo.tex, 3);
      });
      src = dst; dst = dst === this.CA ? this.CB : this.CA;
    }
    if (this.view === "versions" && this.cmp?.ready) {
      if (!this.CC) { this.CC = this.target(...M.size); this.CD = this.target(...M.size); this.CW = this.target(...M.size); }
      let s2 = base, d2 = this.CC;
      for (const L of stack.map((x) => (x === M ? this.cmp : x))) {
        const s = L === this.cmp ? sm : eff(L);
        if (L !== this.cmp && (s.weight ?? 1) <= 0) continue;
        this.layerPasses(L, s);
        this.draw(this.prog.add, d2, (pr) => { this.layerUniforms(pr, L, s); this.bindTex(pr, "uC", s2.tex, 1); this.bindTex(pr, "uE", L.E.tex, 2); });
        s2 = d2; d2 = d2 === this.CC ? this.CD : this.CC;
      }
      this.draw(this.prog.merge, this.CW, (pr) => { this.bindTex(pr, "uA", src.tex, 1); this.bindTex(pr, "uB", s2.tex, 2); gl.uniform1f(pr.u("uWipe"), this.wipe); });
      src = this.CW;
    }
    this.draw(this.prog.final, null, (pr) => {
      this.layerUniforms(pr, M, sm);
      this.bindTex(pr, "uC", src.tex, 1);
      this.bindTex(pr, "uP", this.P.tex, 2);
      this.bindTex(pr, "uE", M.E.tex, 3);
      gl.uniform1i(pr.u("uHasDepth"), this.man.passes.depth ? 1 : 0);
      gl.uniform1f(pr.u("uHaze"), sm.haze.amount); gl.uniform1f(pr.u("uHazeNear"), sm.haze.near); gl.uniform3fv(pr.u("uHazeCol"), hexLin(sm.haze.color));
      const f = sm.finish;
      gl.uniform1f(pr.u("uFExp"), f.exposure); gl.uniform1f(pr.u("uRoll"), f.rolloff); gl.uniform1f(pr.u("uVig"), f.vignette);
      gl.uniform1f(pr.u("uGrain"), f.grain); gl.uniform1f(pr.u("uFSat"), f.saturation); gl.uniform1f(pr.u("uFrame"), this.frame);
      gl.uniform1i(pr.u("uView"), VIEWS.indexOf(this.view));
      gl.uniform1f(pr.u("uWipe"), this.view === "before" ? this.wipe : -1);
    });
  }
}
