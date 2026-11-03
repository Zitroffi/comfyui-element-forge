import { h, fmtSec } from "./ui/lib.js";
import { valRow, choiceRow as dsChoice, info, resetBtn } from "./ui/ds.js";
import * as S from "./ui/state.js";
import { previewSimLook } from "./ui/stage.js";
import { fillRows } from "./fill.js";
import { styleDef, styleOf, startPreset, DIRECT_LOOK } from "./ui/presets.js";

export const FOLLOW_STRENGTH = "Follows motion: strength";
export const FOLLOW_LAG = "Follows motion: lag";
export const PREMASK = "Particle premask";
export const SHAPE = "Particle emitter";
export const AREA = "Particle area";
export const AI_GUIDE = "Guide for the AI (particles / drawn path / object shape / none)";
export const GUIDE_STRENGTH = "Guide strength (on black)";
export const ALSO_DRAW = "Particles: also draw (over the AI element)";
export const DISSOLVE_BG = "Dissolve: background behind the object (auto / smooth / structured)";
export const PANEL_ADV = [FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, SHAPE, AREA, GUIDE_STRENGTH, ALSO_DRAW, DISSOLVE_BG];
export const CRUMBLE = "Object crumbles under the effect (the dissolve is the plate)";
export const CRUMBLE_STYLE = "Dissolve style (plain / fire (LTX) / gold dust)";
export const CRUMBLE_DIR = "Dissolve direction (0 up, 90 right)";
export const CRUMBLE_VALUES = "Dissolve extra (JSON)";
const CRUMBLE_KEYS = [CRUMBLE, CRUMBLE_STYLE, CRUMBLE_DIR, CRUMBLE_VALUES];
const CRUMBLE_STYLES = [["plain", "Crumbles", "Pieces in the object's own colours"], ["gold dust", "Gold dust", "Glowing pieces"],
  ["fire (LTX)", "Burns away", "Embers painted by the AI"], ["explodes", "Explodes", "It bursts from the centre at the start: debris flies out and falls, the object is gone (with Explosion on top: debris and fireball)"]];

export function emitterKind(st) {
  if (!st) return null;
  if (st.variant === "dissolve") return "dissolve";
  if (st.settings?.Particles || st.variant === "climb") return "particles";
  return "ltx";
}
export const guideStyle = (st) => emitterKind(st) === "ltx" && st.variant !== "climb";
export const guideDefault = (st) => st?.settings?.[AI_GUIDE] || (emitterKind(st) === "particles" ? "particles" : "none");
export const guideNow = (st, e) => e?.adv?.[AI_GUIDE] || guideDefault(st);
export const effStyle = (st, e) => (e && st && st === styleDef(e.kind, e.style) ? styleOf(e) : st);
export function ownValues(f) {
  try {
    const o = JSON.parse(f?.emitter_values || "{}");
    return o && typeof o === "object" && !Array.isArray(o) ? o : {};
  } catch { return {}; }
}

export const SHAPES = [
  ["point A", "Point", "a click"],
  ["line A-B", "Between two points", "click A, Shift-click B"],
  ["drawing", "Drawn path", "the brush (Advanced)"],
  ["area", "Area", "the area dragged in the canvas"],
  ["whole frame", "Whole frame", "nothing"],
  ["object mask", "On the object", "the object's mask"],
  ["object contour", "Object outline", "the object's mask"],
  ["object edge + area", "Object outline + inside", "the object's mask"],
  ["object bottom edge", "Object bottom edge", "the object's mask"],
  ["groups", "Groups in depth", "a list of places"],
];
export const shapeOf = (e, st) => e?.adv?.[SHAPE] || st?.settings?.[SHAPE] || "point A";
export const shapeName = (v) => SHAPES.find(([k]) => k === v)?.[1] || v;
export const shapeFixed = (st) => !!st && (st.placement === "ab" || st.variant === "climb");

const r = (v, d = 2) => (v == null || Number.isNaN(+v) ? "" : String(+(+v).toFixed(d)));
const hex = (c) => "#" + c.map((x) => Math.round(Math.min(1, Math.max(0, x)) * 255).toString(16).padStart(2, "0")).join("");
const rgb = (s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16) / 255);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const DRAWN = new Set(["glow", "trail", "opacity", "shutter", "blob", "blob_choke", "blob_soft", "blob_fill", "blob_life", "color_var"]);

const key = (k, label, min, max, step, o = {}) => ({ k, label, min, max, step, ...o });
const EDGE_SHARE = key("edge_share", "On the outline", 0, 1, 0.05, { tip: "Share of the particles born on the object's outline, the rest inside it (1: only the outline, 0: only the inside)" });
const PARTICLES = {
  source: { main: [key("radius", "Emitter size", 0, 300, 1, { unit: "px", tip: "How far around the point or the line they are born (At 1080 px)" }),
      key("scale", "Scale", 0.05, 4, 0.05, { tip: "The whole effect smaller or larger: sizes, speeds and forces together. 0.3 = seen from far away" })],
    more: [key("max_particles", "Max. alive at once", 100, 40000, 100, { tip: "More would be dropped (rain over a long clip)" })] },
  emission: {
    main: [key("rate", "Rate", 0, 2000, 1, { unit: "/s", tip: "Particles per second (with a curve under Rate over time: at its top)" }),
      key("burst", "Burst", 0, 2000, 1, { unit: "", tip: "Particles at once" })],
    more: [key("burst_at", "Burst at", 0, 10, 0.05, { unit: "s", tip: "When the burst comes, after the start (on an object: after its first frame with a mask)" }),
      key("burst_every", "Burst every", 0, 10, 0.05, { unit: "s", tip: "0: once. Else the burst comes again every so many seconds (fireworks, shots, a storm's strikes)" })],
  },
  motion: {
    main: [key("spread", "Spread", 0, 180, 1, { unit: "°", tip: "How far the particles fan out around the direction" }),
      key("speed", "Speed", 0, 3000, 5, { unit: "px/s", tip: "How fast they leave the emitter (At 1080 px)" }),
      key("speed_var", "± Variation", 0, 1, 0.05, { tip: "0: all equally fast, 0.5: between half and one and a half times" })],
    more: [key("lift", "Lift", -90, 90, 1, { unit: "°", tip: "Against motion: the spray tilted upwards" }),
      key("spread_falloff", "Bunch to the centre", 0, 1, 0.05, { tip: "0: evenly over the spread, 1: most of them near the direction" }),
      key("speed_end", "Speed at the end", 0, 2, 0.05, { tip: "Times the speed at birth: 0.2 = they come to rest, 1 = as they are" }),
      key("speed_by_size", "Faster when bigger", 0, 1, 0.05, { tip: "Big particles faster, small ones slower (rain: big drops fall faster); 0 = off" }),
      key("max_speed", "Speed limit", 0, 3000, 5, { unit: "px/s", tip: "No particle gets faster (wind, vortex, attract); 0 = off" })],
  },
  particle: {
    main: [key("life", "Life", 0.05, 60, 0.05, { unit: "s" }), key("life_var", "± Life", 0, 1, 0.05),
      key("size", "Size", 0.2, 60, 0.1, { unit: "px" }), key("size_var", "± Size", 0, 1, 0.05),
      key("size_start", "Size at birth", 0, 5, 0.05, { tip: "Times the size, over the life to the end value" }),
      key("size_end", "Size at the end", 0, 8, 0.05)],
    more: [key("trail", "Trail", 0, 60, 1, { unit: "frames", int: true }), key("glow", "Glow", 0, 5, 0.05),
      key("flicker", "Flicker", 0, 1, 0.05), key("flicker_hz", "Flicker speed", 0.1, 20, 0.1, { unit: "Hz" }),
      key("flicker_size", "Flicker by size", 0, 2, 0.05, { tip: "Small particles flicker faster, large ones slower (fire)" }),
      key("flicker_duty", "Flicker as pulse", 0, 1, 0.01, { tip: "0: a soft wave. Above 0 a short flash of this share of each beat (fireflies: 0.1)" }),
      key("fine_share", "Small particles", 0, 1, 0.05, { tip: "Share of a second, smaller class: quick tongues beside the big body (fire)" }),
      key("fine_size", "Small: size", 0.05, 1, 0.05, { tip: "Times the size" }),
      key("fine_speed", "Small: speed", 0.2, 4, 0.05, { tip: "Times the speed" }),
      key("fine_life", "Small: life", 0.1, 2, 0.05, { tip: "Times the life" }),
      key("fade_in", "Fade in", 0, 1, 0.01, { tip: "Share of the life" }), key("fade_out", "Fade out", 0, 1, 0.01, { tip: "Share of the life" }),
      key("fade_in_max", "Fade in at most", 0, 2, 0.01, { unit: "s", tip: "The fade in never takes longer, however long the life (0: no limit)" }),
      key("shutter", "Motion blur", 0, 5, 0.1, { tip: "The streak over this many frames of motion" }),
      key("opacity", "Opacity", 0, 1, 0.01), key("color_var", "Colour variation", 0, 1, 0.05, { tip: "Each particle a bit brighter or darker" }),
      key("spin", "Spin", 0, 720, 5, { unit: "°/s", tip: "How fast a particle turns at most; 0 = not at all (calm smoke, flakes)" })],
  },
  merge: {
    main: [key("blob", "Blur", 0, 60, 0.5, { unit: "px", tip: "The particles blurred together into one body (At 1080 px)" }),
      key("blob_choke", "Choke", 0, 1, 0.01, { tip: "Where the blurred body ends: higher = thinner, lone particles vanish sooner" }),
      key("blob_soft", "Edge", 0, 0.5, 0.01, { tip: "Width of the edge: small = hard liquid edge" })],
    more: [key("blob_fill", "Fill", 0, 1, 0.05, { tip: "1: evenly dense (liquid), 0: as dense as the blur (smoke)" }),
      key("blob_life", "Only while young", 0, 1, 0.05, { tip: "0: all merge. Above 0 a particle merges while young and is apart from this share of its life on: tongues tear off at the top (fire)" })],
  },
  forces: {
    main: [key("gravity", "Gravity", -3000, 3000, 10, { unit: "px/s²", tip: "Negative rises (smoke, fire)" }),
      key("wind", "Wind", -1500, 1500, 5, { unit: "px/s²", tip: "Sideways, + = to the right", get: (P) => P.wind?.[0] ?? 0,
        put: (P, v) => [v, P.wind?.[1] ?? 0] }),
      key("drag", "Drag", 0, 10, 0.05, { tip: "Air resistance per second" }),
      key("turbulence", "Turbulence", 0, 1500, 5, { unit: "px/s", tip: "Swirling (curl noise)" }),
      key("turb_scale", "Turbulence size", 10, 800, 5, { unit: "px" })],
    more: [key("scene_height", "Frame height", 0, 200, 0.5, { unit: "m", tip: "How many metres the frame shows from top to bottom: what falls then falls at real speed (a person: 2 m); 0 = the Gravity above" }),
      key("gravity_end", "Gravity at the end", -3, 3, 0.05, { tip: "Times the gravity at birth: smoke loses its lift (0.3), an ember rises and then falls (-1.3); 1 = as it is" }),
      key("windy", "Wind up/down", -1500, 1500, 5, { unit: "px/s²", tip: "+ = down", k2: "wind", get: (P) => P.wind?.[1] ?? 0,
        put: (P, v) => [P.wind?.[0] ?? 0, v] }),
      key("turb_speed", "Turbulence change", 0, 3, 0.05),
      key("vortex", "Vortex", -3000, 3000, 10, { tip: "Swirl around the emitter" }),
      key("roll", "Mushroom roll", 0, 3000, 10, { unit: "px/s²", tip: "The cloud rolls like a mushroom: up in the middle, out at the top, down at the sides (explosions); 0 = off" }),
      key("sway", "Sway", 0, 200, 1, { unit: "px", tip: "Each particle swings sideways on its own (snowflakes); 0 = off" }),
      key("sway_hz", "Sway speed", 0.05, 5, 0.05, { unit: "Hz" }),
      key("attract", "Attract to B", 0, 6000, 20, { tip: "Pull towards point B" }),
      key("centres_follow", "Centres follow the emitter", 0, 1, 0.05, { tip: "1: the vortex's centre and the pull to B move with the emitter and B, the whole cloud goes along. 0: each particle keeps them where they were at its birth: only the emitter follows the track" }),
      key("flock", "Flocking", 0, 1, 0.05, { tip: "Neighbours pull together: streams wander, clump and break into drops" }),
      key("flock_radius", "Flocking: reach", 5, 200, 1, { unit: "px" }),
      key("flock_cohesion", "Flocking: pull", 0, 20, 0.1),
      key("turb_fade", "Turbulence fades in", 0, 1, 0.05, { tip: "Share of the life: calm at birth, the swirl comes later" }),
      key("turb_drag", "Drag calms turbulence", 0, 1, 0.05, { tip: "1: the swirl slows down with the drag, as the speed does" })],
  },
  contact: {
    main: [key("restitution", "Bounce", 0, 1, 0.05)],
    more: [key("land_fade", "Lying time", 0, 20, 0.1, { unit: "s", tip: "How long a particle that sticks stays before it fades" }),
      key("depth_spread", "Depth spread", 0, 0.5, 0.01, { tip: "Random spread of the particles' depth around the emitter" }),
      key("flow_around", "Flow around the scene", 0, 1, 0.05, { tip: "1: the particles flow around what is in front in the depth map (a hand, a face): along its outline, in front of it or behind it, never half cut by it. 0: they pass through and the depth only hides them" }),
      key("obstacle_depth", "Obstacle depth", 0.01, 0.5, 0.01, { tip: "How deep a surface counts for Flow around: a particle further behind it passes behind freely (a fist about 0.1)" }),
      key("friction", "Friction", 0, 1, 0.05)],
  },
};
const PATHS = [["particles", "None", "Only the particles"], ["bolt", "Bolt", "A bolt from A to B (without B it strikes down)"],
  ["strike", "Strike", "A lightning strike from the sky onto A, at every burst"],
  ["random", "Random bolts", "Bolts shoot from random places of the emitter, at random times, in random directions"],
  ["climb", "Climbs", "A charge climbs the thin parts of the object and jumps from its tips"],
  ["crack", "Cracks", "Cracks spread from A over the surface"]];
const AIMS = [["random", "Anywhere", "Each bolt in its own random direction"], ["emitter", "As the particles", "Direction and Spread of the particles (Motion)"],
  ["outward", "Outward", "Off the object, out of its outline"]];
const PATH_EXPL = {
  particles: "No path: only the particles. A path is drawn over them, in the same colours.",
  bolt: "From point A to point B; without B it strikes down. Shift-click sets B.",
  strike: "A strike from the sky onto point A at the burst (Emission: Burst at, Burst every): a faint leader steps down, the return stroke lights the channel, more strokes flicker in the same channel. B, if set, is the cloud's point.",
  random: "Bolts shoot from random places of the emitter (the object's mask or outline, the line, the area) at random times. Each flashes and is gone; New shape every, Fine jaggedness and Grows in (Bolt) count too.",
  climb: "It climbs the thin parts of the object you clicked: needs the object's track (Position).",
  crack: "Cracks spread from point A over the surface; the clip's depth makes nearer ones wider.",
};
const PATH = {
  main: [key("width", "Width", 0.3, 10, 0.1, { unit: "px" }), key("roughness", "Jaggedness", 0, 1, 0.01),
    key("branches", "Branches", 0, 20, 1, { int: true })],
  bolt: [key("reroll_frames", "New shape every", 1, 12, 1, { unit: "frames", int: true }),
    key("fine_rough", "Fine jaggedness", 0, 1, 0.01, { tip: "The finest level of the bolt: 0 = smooth in the small" }),
    key("grow_seconds", "Grows in", 0, 3, 0.05, { unit: "s", tip: "0: there at once. Else it grows from A to B in this time" })],
  strike: [key("strike_leader", "Leader", 0, 0.5, 0.005, { unit: "s", tip: "How long the faint leader steps down before the strike" }),
    key("strike_strokes", "Strokes", 1, 12, 1, { int: true, tip: "Return strokes in the same channel (the first with the branches)" }),
    key("strike_gap", "Between strokes", 0.01, 0.3, 0.005, { unit: "s" }),
    key("strike_decay", "Fades in", 0.005, 0.3, 0.005, { unit: "s", tip: "A stroke's light falls to a third in this time" }),
    key("strike_hold", "Glows on", 0, 1, 0.01, { unit: "s", tip: "After the last but one stroke the channel glows on this long, with a few flares; 0 = off" }),
    key("strike_hold_level", "Glow on: brightness", 0, 1, 0.05),
    key("strike_new_ground", "Second stroke beside", 0, 1, 0.05, { tip: "Chance that the second stroke forks off low and lands beside the first" }),
    key("strike_streamer", "Streamer from the ground", 0, 200, 1, { unit: "px", tip: "A short spark rising from A to meet the leader; 0 = none (At 1080 px)" }),
    key("strike_lean", "Lean", 0, 1, 0.01, { tip: "How far the cloud's point lies to the side, share of the height" }),
    key("strike_spread", "Lands within", 0, 800, 5, { unit: "px", tip: "Each strike lands this far left or right of A at random (At 1080 px)" })],
  random: [key("rand_rate", "Bolts per second", 0, 60, 0.5, { tip: "At random times; the rate curve (Emission) shapes it over time" }),
    key("rand_length", "Length", 5, 1500, 5, { unit: "px", tip: "A bolt's mean length (At 1080 px)" }),
    key("rand_length_var", "± Length", 0, 1, 0.05, { tip: "Share the length varies up and down" }),
    key("rand_life", "Flash", 0.02, 1, 0.01, { unit: "s", tip: "How long a bolt flashes before it is gone" })],
  climb: [key("climb_seconds", "Climb time", 0.05, 3, 0.05, { unit: "s", tip: "One climb from the base of a thin part to its tip" }),
    key("climb_rough", "Zigzag off the object", 0, 6, 0.05), key("climb_pitch", "Jag spacing", 0, 0.3, 0.005, { tip: "Share of the part's length; 0 = hugs it" }),
    key("climb_zigzag", "Fine zigzag", 0, 20, 0.5, { unit: "px", tip: "Crackles along the object (At 1080 px)" }),
    key("climb_head", "Bright head", 0, 1, 0.05, { tip: "0: glows evenly, 1: dark tail, bright head" }),
    key("climb_short", "Dim short stretches", 0, 600, 5, { unit: "px", tip: "Shorter climbs glow dimmer and fork less (At 1080 px)" }),
    key("fork_depth", "Forks fork again", 1, 4, 1, { int: true })],
  crack: [key("crack_speed", "Spread speed", 10, 60000, 5, { unit: "px/s", tip: "Glass cracks at once (50000), soil and stone slowly" }), key("crack_length", "Length", 20, 3000, 10, { unit: "px" }),
    key("crack_branch", "Branching", 0, 1, 0.01), key("crack_turn", "Curl", 0, 1.5, 0.01), key("crack_step", "Step", 1, 30, 0.5, { unit: "px" }),
    key("crack_seeds", "Start points", 1, 20, 1, { int: true }), key("crack_taper", "Wide at the start", 0, 2, 0.05),
    key("crack_angle", "Branch angle", 0, 1.6, 0.01, { unit: "rad", tip: "Glass 0.47 (27°), ice 1.05 (60°)" }),
    key("crack_angle_var", "± Branch angle", 0, 0.8, 0.01, { unit: "rad" }),
    key("crack_pairs", "Branches in pairs", 0, 1, 0.05, { tip: "Chance that a branch comes with one on the other side (frost)" }),
    key("relief", "Grooves", 0, 1, 0.05, { tip: "Lines read as grooves in the surface (dark rim, lit lower lip)" })],
};
const DISSOLVE = {
  emission: {
    main: [key("density", "Particles", 0, 1, 0.01, { tip: "Share of the crumbling pixels that fly off as particles" }),
      key("edge_noise", "Ragged edge", 0, 1, 0.05, { tip: "0: a straight front, 1: torn by noise" })],
    more: [key("noise_size", "Size of the tears", 0.02, 1, 0.01)],
  },
  motion: {
    main: [key("push", "Speed", 0, 1500, 5, { unit: "px/s", tip: "Along the direction" }), key("lift", "Lift", -500, 500, 5, { unit: "px/s" }),
      key("spread", "Spread", 0, 600, 5, { unit: "px/s", tip: "Random at birth" })],
    more: [],
  },
  particle: {
    main: [key("life", "Life", 0.1, 10, 0.05, { unit: "s" }), key("size", "Size", 0, 10, 0.1, { unit: "px" }),
      key("fade_out", "Fade out", 0, 1, 0.01), key("glow", "Glowing edge", 0, 5, 0.05)],
    more: [key("glow_width", "Width of the glow", 0, 0.5, 0.01), key("tint", "Glow colour over the life", 0, 1, 0.05)],
  },
  forces: {
    main: [key("gravity", "Gravity", -1500, 1500, 5, { unit: "px/s²", tip: "Negative rises (ash)" }), key("drag", "Drag", 0, 10, 0.05),
      key("turbulence", "Turbulence", 0, 1500, 5, { unit: "px/s" }), key("turb_scale", "Turbulence size", 10, 800, 5, { unit: "px" })],
    more: [],
  },
};

const BLENDS = [["add", "Glowing", "Adds light: sparks, fire, magic"], ["over", "Solid", "Covers what is behind: smoke, dust, debris"],
  ["contrast", "Contrast", "Lighter and darker than the clip: rain, snow"]];
const LOOK = [key("plate_color", "Clip colour", 0, 1, 0.05, { tip: "Each particle takes the clip's colour where it is born; the colours over life shade it (debris)" }),
  key("ambient", "Lit by the clip", 0, 1, 0.05, { tip: "Solid particles take the light around them in the clip (smoke in a dark wood)" })];
const GUIDE_DRAW = [["lines", "Lines", "Thin strokes along the paths (sparks, lightning)"], ["volume", "Volume", "Soft blobs, brighter when nearer"],
  ["temperature", "Heat", "Soft blobs, bright where the particle is hot (fire)"],
  ["depth", "Depth", "The clip's depth of the object, the particles where they are in front of it (needs the object's track)"]];
const DEPTH_SHOWS = [["object", "The object", "Only the clicked object's depth, the particles over it"],
  ["scene", "The whole scene", "The depth of the whole picture: the AI may redraw the background as well"]];
const DEPTH_OBJ = [["full", "Whole", "The object's whole surface"], ["edge", "Inner edge", "Only a thin edge inside the object: the AI follows its outline and builds less of a body"]];
function depthRows(ctx) {
  const { P } = ctx;
  if (P.guide_style !== "depth") return [];
  const edge = +P.depth_edge || 0, scene = P.depth_guide === "scene";
  return [choiceRow(ctx, "depth_guide", "Depth shows", DEPTH_SHOWS, "What the AI sees of the clip's depth"),
    scene ? null : dsChoice({ key: "depth_edge", label: "Object as", tip: "The object whole, or only a thin edge inside it", changed: edge > 0,
      control: ctx.ui.seg("Object as", DEPTH_OBJ, edge > 0 ? "edge" : "full", (v) => setOwn(ctx, "depth_edge", v === "edge" ? 2 : undefined)),
      onreset: () => setOwn(ctx, "depth_edge", undefined), resetTitle: "Back to the whole object" }),
    !scene && edge > 0 ? numRow(ctx, key("depth_edge", "Edge width", 1, 16, 1, { unit: "px", int: true })) : null,
    P.path && P.path !== "particles" ? ctx.ui.note("hint", "The path is drawn over the depth as lines.") : null].filter(Boolean);
}
const SPLASH0 = { count: 0, speed: 160, spread: 70, direction: 0, life: 0.25, size: 1.2, at_age: 0, chance: 1 };
const splash = (f, label, min, max, step, o = {}) => key(`splash_${f}`, label, min, max, step, { ...o, k2: "children",
  get: (P) => (P.children?.[f] ?? SPLASH0[f]), put: (P, v) => ({ ...SPLASH0, ...(P.children || {}), [f]: v }) });
const SPLASH = [splash("count", "Splash: particles", 0, 12, 1, { int: true, tip: "New particles where one hits the scene (Collision); 0 = none" }),
  splash("speed", "Splash: speed", 0, 1500, 5, { unit: "px/s" }), splash("spread", "Splash: spread", 0, 180, 1, { unit: "°" }),
  splash("life", "Splash: life", 0.05, 3, 0.05, { unit: "s" }), splash("size", "Splash: size", 0.2, 20, 0.1, { unit: "px" }),
  splash("at_age", "Splash: also in mid-air at", 0, 1, 0.05, { tip: "Share of the life: the particle bursts into the splash there, in mid-air (sparks); 0 = only where it hits" }),
  splash("chance", "Splash: chance in mid-air", 0, 1, 0.05, { tip: "How many of them burst in mid-air" })];

const MODES = [["angle", "Angle", "The direction of the arrow"], ["outward", "Outward", "Away from the object's outline"],
  ["against motion", "Against motion", "Sprayed backwards from the emitter's motion (grinding)"], ["random", "Random", "Every direction"]];
const COLLIDE = [["none", "None"], ["bounce", "Bounce"], ["stick", "Stick"], ["slide", "Slide"], ["die", "Die"]];
const SPRITES = ["soft", "dot", "flake", "puff", "wisp", "streak", "spark", "chunk"];
const EXPL = {
  inherit: "How much of the emitter's movement the particles take along. 0: they fly on their own. 1: they move with it.",
  carry: "Moving things in the clip push the particles along, e.g. a hand sweeping through smoke.",
  ltx: "The AI gets the path of the movement, so the effect leans and trails behind.",
  strength: "How strongly and how late the effect trails behind fast movement.",
};

const GUIDES = [["none", "Free"], ["object shape", "Object shape"], ["drawn path", "Drawn path"], ["particles", "Particles"]];
const GUIDE_PRESETS = ["fire", "embers", "sparks", "grinding sparks", "smoke", "dust burst", "magic dust", "aura", "liquid", "debris",
  "snow", "rain", "fireflies", "lightning", "cracks", "frost", "lightning climb", "lightning strike", "energy A-B", "explosion", "explosion side",
  "spirit threads", "spirit ribbons", "spirit veil"];
const GUIDE_EXPL = {
  none: "The AI paints the element freely from the prompt.",
  "object shape": "The AI shapes the element to the object it sits on (a flame wraps round the fist): the object's depth guides it, only near the object. Needs the object: click it in Position.",
  "drawn path": "The AI follows the strokes you paint on the canvas while this step is open.",
  particles: "The particles guide the AI: the emitter below shapes where and how it moves, the AI paints the look.",
};

function write(ctx, own) {
  if (ctx.write) return ctx.write(own);
  const keys = Object.keys(own);
  ctx.api.setFx("emitter_values", keys.length ? JSON.stringify(own) : "");
}
const setOwn = (ctx, k, v) => { const o = { ...ctx.own }; if (v === undefined) delete o[k]; else o[k] = v; write(ctx, o); };
function setEffect(fn, reason) {
  S.change((sh) => { const x = sh.effects.find((y) => y.id === sh.active); if (x) fn(x); }, reason);
}
const setAdvAll = (name, v) => setAdv(name, v);
export function setAdv(name, v) {
  setEffect((x) => { x.adv = { ...x.adv }; if (v === undefined) delete x.adv[name]; else x.adv[name] = v; }, "emitter");
}

function numRow(ctx, c) {
  const P = ctx.P, B = ctx.B;
  const get = c.get || ((p) => p[c.k]);
  let cur = get(P), base = get(B);
  let changed = (c.k2 || c.k) in ctx.own && !same(get(P), get(B));
  let set = (v) => setOwn(ctx, c.k2 || c.k, c.put ? c.put(P, v) : v);
  let reset = () => {
    if (!c.put) return setOwn(ctx, c.k, undefined);
    const back = c.put(P, get(B));
    setOwn(ctx, c.k2 || c.k, same(back, B[c.k2 || c.k]) ? undefined : back);
  };
  if (c.k === "rate" || c.k === "burst") {
    const a = ctx.amount || 1;
    cur = P[c.k] * a; base = B[c.k] * a;
    changed = c.k in ctx.own;
    set = (v) => setOwn(ctx, c.k, v / a);
  }
  const drawn = DRAWN.has(c.k2 || c.k) && !c.put && !ctx.write;
  return valRow({ key: c.k, label: c.label, tip: c.tip, unit: c.unit, value: cur, base, min: c.min, max: c.max, step: c.step, int: c.int, changed,
    onlive: drawn ? (v) => previewSimLook({ [c.k]: v }) : null, onset: (v) => set(c.int ? Math.round(v) : v), onreset: reset });
}
function choiceRow(ctx, k, label, options, tip) {
  const cur = ctx.P[k], changed = k in ctx.own && ctx.P[k] !== ctx.B[k];
  return dsChoice({ key: k, label, tip, changed, control: ctx.ui.seg(label, options, cur, (v) => setOwn(ctx, k, v === ctx.B[k] ? undefined : v)),
    onreset: () => setOwn(ctx, k, undefined), resetTitle: `Back to the style's value (${ctx.B[k]})` });
}
function spriteRow(ctx) {
  const cur = ctx.P.sprite, changed = "sprite" in ctx.own && cur !== ctx.B.sprite;
  const sel = h("select", { class: "text", "aria-label": "Sprite", onchange: (ev) => setOwn(ctx, "sprite", ev.target.value === ctx.B.sprite ? undefined : ev.target.value) },
    ...[...new Set([...SPRITES, cur])].map((s) => h("option", { value: s, selected: s === cur }, s)));
  return dsChoice({ key: "sprite", label: "Sprite", wide: false, changed, control: sel, onreset: () => setOwn(ctx, "sprite", undefined),
    resetTitle: `Back to the style's sprite (${ctx.B.sprite})` });
}
function colorsRow(ctx) {
  const stops = ctx.P.colors || [], changed = "colors" in ctx.own && !same(ctx.P.colors, ctx.B.colors);
  const put = (i, v) => setOwn(ctx, "colors", stops.map(([t, c], j) => [t, j === i ? rgb(v) : c]));
  return dsChoice({ key: "colors", label: "Colour over life", tip: "From birth (left) to the end of the life (right)", wide: false, changed,
    control: h("div", { class: "em-stops" }, ...stops.map(([t, c], i) => h("input", { type: "color", value: hex(c), title: `at ${Math.round(t * 100)} % of the life`,
      "aria-label": `Colour at ${Math.round(t * 100)} % of the life`, onchange: (ev) => put(i, ev.target.value) }))),
    onreset: () => setOwn(ctx, "colors", undefined), resetTitle: "Back to the style's colours" });
}
function hexRow(ctx, k, label) {
  const cur = ctx.P[k], changed = k in ctx.own && cur !== ctx.B[k];
  return dsChoice({ key: k, label, wide: false, changed,
    control: h("input", { type: "color", value: String(cur || "#ffffff"), "aria-label": label, onchange: (ev) => setOwn(ctx, k, ev.target.value) }),
    onreset: () => setOwn(ctx, k, undefined), resetTitle: "Back to the style's colour" });
}
function dialRow(ctx, label, value, dflt, onset, tip) {
  const deg = value ?? dflt ?? 0;
  const needle = h("span", { class: "em-needle", style: { transform: `rotate(${deg}deg)` } });
  const wrap = (v) => ((Math.round(v) % 360) + 360) % 360;
  const angle = (ev, el) => {
    const b = el.getBoundingClientRect();
    return wrap(Math.atan2(ev.clientX - (b.left + b.width / 2), -(ev.clientY - (b.top + b.height / 2))) * 180 / Math.PI);
  };
  let row = null;
  const dial = h("span", { class: "em-dial", role: "slider", tabindex: "0", "aria-label": `${label} dial`, "aria-valuenow": String(Math.round(deg)), title: "Drag around: 0 up, 90 right",
    onpointerdown: (ev) => {
      ev.preventDefault();
      const el = ev.currentTarget;
      el.setPointerCapture(ev.pointerId);
      let last = deg;
      const move = (m) => { last = angle(m, el); needle.style.transform = `rotate(${last}deg)`; const n = row?.querySelector(".val-num"); if (n) n.value = String(last); };
      const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); onset(last); };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      move(ev);
    },
    onkeydown: (ev) => { const d = { ArrowLeft: -5, ArrowDown: -5, ArrowRight: 5, ArrowUp: 5 }[ev.key]; if (d) { ev.preventDefault(); onset(wrap(deg + d)); } } }, needle);
  const changed = value != null && Math.round(value) !== Math.round(dflt ?? -1);
  row = valRow({ key: "direction", label, tip, unit: "°", value: Math.round(deg), base: Math.round(dflt ?? 0), min: 0, max: 359, step: 1, int: true, changed, extra: dial,
    onlive: (v) => { needle.style.transform = `rotate(${v}deg)`; }, onset: (v) => onset(wrap(v)), onreset: () => onset(null),
    resetTitle: `Back to the style's direction (${Math.round(dflt ?? 0)}°)` });
  return row;
}
const setDir = (v) => setEffect((x) => { x.dir = v; }, "emitter");
const EVEN = [[0, 1], [1, 1]];
const CURVES = [["even", "Even", EVEN], ["explosion", "Explosion", [[0, 1], [0.04, 1], [0.12, 0.2], [0.3, 0]]],
  ["pulses", "Pulses", [[0, 0], [0.08, 1], [0.2, 0], [0.4, 0], [0.48, 1], [0.6, 0], [0.8, 0], [0.88, 1], [1, 0]]],
  ["grows", "Grows", [[0, 0], [1, 1]]], ["dies down", "Dies down", [[0, 1], [1, 0]]]];
const SVGNS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => { const el = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v)); return el; };
const flat = (c) => !c?.length || c.every(([, v]) => Math.abs(v - 1) < 1e-6);
function curveRow(ctx) {
  const P = ctx.P, B = ctx.B;
  const cur = (P.rate_curve?.length ? P.rate_curve : EVEN).map(([t, v]) => [+t, +v]).sort((a, b) => a[0] - b[0]);
  const base = B.rate_curve?.length ? B.rate_curve : EVEN;
  const changed = "rate_curve" in ctx.own && !same(cur, base);
  const put = (pts) => {
    const c = pts.map(([t, v]) => [+t.toFixed(3), +v.toFixed(3)]).sort((a, b) => a[0] - b[0]);
    const plain = flat(c) && c.length <= 2;
    setOwn(ctx, "rate_curve", same(c, base) || (plain && flat(B.rate_curve)) ? undefined : (plain ? [] : c));
  };
  const W = 300, H = 76, PAD = 6;
  const X = (t) => PAD + t * (W - 2 * PAD), Y = (v) => PAD + (1 - v) * (H - 2 * PAD);
  const box = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "em-curve-svg", role: "img", "aria-label": "Rate over time: the share of the rate along the effect's time" });
  const grid = [0.25, 0.5, 0.75].map((g) => svg("line", { x1: X(g), x2: X(g), y1: PAD, y2: H - PAD, class: "em-curve-grid" }));
  const area = svg("path", { class: "em-curve-area" }), line = svg("polyline", { class: "em-curve-line" });
  const pts = cur.map((p) => [...p]);
  const dots = [];
  const draw = () => {
    const xy = [[0, pts[0][1]], ...pts, [1, pts[pts.length - 1][1]]].map(([t, v]) => `${X(t).toFixed(1)},${Y(v).toFixed(1)}`);
    line.setAttribute("points", xy.join(" "));
    area.setAttribute("d", `M${X(0)},${H - PAD} L${xy.join(" L")} L${X(1)},${H - PAD} Z`);
    dots.forEach((d, i) => { d.setAttribute("cx", X(pts[i][0]).toFixed(1)); d.setAttribute("cy", Y(pts[i][1]).toFixed(1)); });
  };
  const at = (ev) => {
    const b = box.getBoundingClientRect();
    return [Math.min(1, Math.max(0, ((ev.clientX - b.left) / b.width * W - PAD) / (W - 2 * PAD))),
      Math.min(1, Math.max(0, 1 - ((ev.clientY - b.top) / b.height * H - PAD) / (H - 2 * PAD)))];
  };
  pts.forEach((p, i) => {
    const d = svg("circle", { r: 5, class: "em-curve-dot", tabindex: "0", "aria-label": `Point ${i + 1}: ${Math.round(p[1] * 100)} % at ${Math.round(p[0] * 100)} % of the time` });
    d.addEventListener("pointerdown", (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      d.setPointerCapture(ev.pointerId);
      const lo = i === 0 ? 0 : pts[i - 1][0] + 0.001, hi = i === pts.length - 1 ? 1 : pts[i + 1][0] - 0.001;
      const ends = i === 0 || i === pts.length - 1;
      const move = (m) => { const [t, v] = at(m); pts[i] = [ends ? pts[i][0] : Math.min(hi, Math.max(lo, t)), v]; draw(); };
      const up = () => { d.removeEventListener("pointermove", move); d.removeEventListener("pointerup", up); put(pts); };
      d.addEventListener("pointermove", move);
      d.addEventListener("pointerup", up);
    });
    d.addEventListener("dblclick", (ev) => { ev.stopPropagation(); if (i > 0 && i < pts.length - 1) put(pts.filter((_, j) => j !== i)); });
    d.addEventListener("keydown", (ev) => {
      const dv = { ArrowUp: 0.05, ArrowDown: -0.05 }[ev.key];
      if (dv) { ev.preventDefault(); pts[i] = [pts[i][0], Math.min(1, Math.max(0, pts[i][1] + dv))]; put(pts); }
      if ((ev.key === "Delete" || ev.key === "Backspace") && i > 0 && i < pts.length - 1) { ev.preventDefault(); put(pts.filter((_, j) => j !== i)); }
    });
    dots.push(d);
  });
  box.addEventListener("dblclick", (ev) => { const [t] = at(ev); put([...pts, [t, rate_at(pts, t)]]); });
  box.append(...grid, area, line, ...dots);
  draw();
  const t = ctx.e.timing, c = S.getShot().clip, end = t.end ?? c?.seconds;
  const which = CURVES.find(([, , p]) => same(p, cur) || (flat(p) && flat(cur)))?.[0];
  return h("div", { class: "em-curve" + (changed ? " changed" : ""), "data-key": "rate_curve" },
    h("div", { class: "em-curve-head" },
      h("span", { class: "em-label" }, "Rate over time", info("Rate over time", "How many particles come when: the Rate is the top. Drag a point, double-click the line for a new one, a point to remove it.")),
      changed ? resetBtn("Back to the style's curve", () => setOwn(ctx, "rate_curve", undefined)) : h("span", { class: "reset-gap", "aria-hidden": "true" })),
    h("div", { class: "em-curve-plot" }, box),
    h("div", { class: "em-curve-axis muted small" }, h("span", {}, fmtSec(t.start || 0)), h("span", {}, end != null ? fmtSec(end) : "end")),
    ctx.ui.seg("Rate over time", CURVES.map(([k, l]) => [k, l]), which || "", (k) => put(CURVES.find(([x]) => x === k)[2])));
}
function rate_at(pts, t) {
  for (let i = 1; i < pts.length; i++) {
    const [a, va] = pts[i - 1], [b, vb] = pts[i];
    if (t <= b) return b - a <= 1e-9 ? vb : va + (vb - va) * (t - a) / (b - a);
  }
  return pts[pts.length - 1][1];
}
function depthWrap(ctx, cur, base, mine, set) {
  return valRow({ key: "depth_offset", label: "Depth offset", tip: "+ = nearer, less hidden by the scene", value: cur, base, min: -1, max: 1, step: 0.01, changed: !!mine,
    onset: set, onreset: () => set(base) });
}
function advNum(ctx, name, label, min, max, step, dflt, tip) {
  const cur = ctx.e.adv?.[name] ?? dflt, changed = ctx.e.adv?.[name] != null && ctx.e.adv[name] !== dflt;
  const set = (v) => setAdv(name, v === dflt ? undefined : v);
  return valRow({ key: name, label, tip, value: cur, base: dflt, min, max, step, changed, onset: set, onreset: () => setAdv(name, undefined) });
}

const rows = (ctx, list) => list.map((c) => numRow(ctx, c));
const rowName = (x) => x?.querySelector?.(".em-label")?.firstChild?.textContent || x?.querySelector?.(".toggle span:last-child")?.textContent || "";
const GROUP_DESC = { source: "where they start", emission: "rate, timing", motion: "direction and speed", particle: "size, life, look",
  merge: "drops flow together", forces: "gravity, turbulence", contact: "bounce or stick", path: "bolts and cracks", crumble: "object falls apart" };
function box(ctx, key_, title, main, more, explain, desc = GROUP_DESC[key_] || "", moreName = title.replace(/ \(.*\)$/, "").toLowerCase()) {
  const n = [...main, ...more].filter((x) => x?.classList?.contains("changed")).length;
  const m = more.filter((x) => x?.classList?.contains("changed")).length;
  const names = more.map(rowName).filter(Boolean).slice(0, 3).map((t) => t.trim().toLowerCase());
  return ctx.ui.group(`em-${key_}`, title, () => [
    explain ? ctx.ui.note("hint", explain) : null,
    ...main,
    more.length ? ctx.ui.group(`em-${key_}-more`,
      `More ${moreName} settings (${more.filter((x) => !x?.classList?.contains("sub")).length})`, () => more,
      { preview: names.join(", "), badge: m ? `${m} changed` : "", cls: "em-more" }) : null,
  ], { preview: desc, badge: n ? `${n} changed` : "", cls: "em-group", solo: (k) => /^em-[a-z_]+$/.test(k) });
}
const pname = (list, v) => list.find(([k]) => k === v)?.[1] || v;
function timing(ctx) {
  const t = ctx.e.timing, c = S.getShot().clip;
  const end = t.end ?? c?.seconds;
  return ctx.ui.note("hint", `From ${fmtSec(t.start || 0)} to ${end != null ? fmtSec(end) : "the end"}: drag the ends of its bar in the timeline.`);
}

function guideRows(ctx) {
  const { e, ui } = ctx, st = ctx.st0 || ctx.st;
  const cur = guideNow(st, e), dflt = guideDefault(st);
  const set = (v) => ctx.api.setFx("guide", v === dflt ? "style default" : v);
  const out = [dsChoice({ key: "guide", label: "Guide for the AI", tip: `What guides the AI where it paints the element. ${GUIDE_EXPL[cur] || ""}`, changed: cur !== dflt,
    control: ui.seg("Guide for the AI", GUIDES, cur, set), onreset: () => set(dflt),
    resetTitle: `Back to the style's guide (${GUIDES.find(([k]) => k === dflt)?.[1] || dflt})` })];
  if (aiOff(ctx)) out.push(ui.note("hint", "Counts when the AI makes the element (Made by: AI)."));
  if (cur === "drawn path") out.push(ui.note("hint", `${e.paint?.guide?.length || 0} strokes painted.`));
  if (cur !== "none") out.push(advNum(ctx, GUIDE_STRENGTH, "Guide strength", 0, 1, 0.05, (ctx.st0 || ctx.st)?.settings?.[GUIDE_STRENGTH] ?? 1.0,
    "How strictly the AI keeps to the guide on black: 1 = fully, lower leaves it more of its own look"));
  return out;
}

function startRow(ctx) {
  const { f } = ctx, st = ctx.st0 || ctx.st, own = startPreset(st);
  const pick = f.guide_particles && f.guide_particles !== "style default" ? f.guide_particles : own;
  const sel = h("select", { class: "text", "aria-label": "Particles it starts from",
    onchange: (ev) => ctx.api.setFx("guide_particles", ev.target.value === own ? "style default" : ev.target.value) },
    ...[...new Set([...GUIDE_PRESETS, own])].map((p) => h("option", { value: p, selected: p === pick }, p === own ? `${p} (style default)` : p)));
  return dsChoice({ key: "guide_particles", label: "Particles", tip: "The particle preset this effect starts from: the values below are its own", changed: pick !== own,
    control: sel, onreset: () => ctx.api.setFx("guide_particles", "style default"), resetTitle: `Back to the style's particles (${own})` });
}
const directLook = (ctx) => (ctx.e.adv?.[DIRECT_LOOK] ?? ctx.st.settings?.[DIRECT_LOOK]) === true;
const aiOff = (ctx) => directLook(ctx);
export const particlesUsed = (ctx) => directLook(ctx) || guideNow(ctx.st0 || ctx.st, ctx.e) === "particles" || ctx.e.adv?.[ALSO_DRAW] === true;
function alsoDrawRow(ctx) {
  const { e, ui } = ctx;
  if (directLook(ctx)) return null;
  return ui.toggle("Also draw the particles", e.adv?.[ALSO_DRAW] === true, (v) => setAlsoDraw(ctx, v),
    "The particles drawn over the AI's element as well, with their own pass \"particles\". Off: only the AI's element");
}
function setAlsoDraw(ctx, v) {
  const st = ctx.st0 || ctx.st;
  setEffect((x) => {
    x.adv = { ...x.adv };
    if (v) x.adv[ALSO_DRAW] = true; else delete x.adv[ALSO_DRAW];
    if (!st.settings?.Particles && guideNow(st, x) !== "particles" && !directLook({ ...ctx, e: x })) {
      if (v) { x.adv.Particles = true; x.adv["Particle preset"] = ctx.f.guide_particles && ctx.f.guide_particles !== "style default" ? ctx.f.guide_particles : startPreset(st); }
      else { delete x.adv.Particles; delete x.adv["Particle preset"]; }
    }
  }, "emitter");
}

const BG_CHOICES = [["auto", "Auto"], ["smooth", "Smooth"], ["structured", "Structured"]];
const BG_EXPL = {
  auto: "Measured around the object: a smooth background is filled from around it, a structured one gets the AI's clean plate.",
  smooth: "Sky, wall, studio: filled from around the object, no AI run (faster).",
  structured: "Leaves, crowd, pattern: the AI paints what was always behind the object.",
};
function backgroundRows(ctx) {
  const { e, ui } = ctx;
  const cur = e.adv?.[DISSOLVE_BG] || "auto";
  const set = (v) => setAdv(DISSOLVE_BG, v === "auto" ? undefined : v);
  return [dsChoice({ key: "background", label: "Background", tip: `What is behind the object where it never moves away. ${BG_EXPL[cur]}`, changed: cur !== "auto",
    control: ui.seg("Background", BG_CHOICES, cur, set), onreset: () => set("auto"), resetTitle: "Back to auto" })];
}

export function changedCount(ctx) {
  const e = ctx.e;
  let n = Object.keys(ctx.own).length;
  if (e.dir != null && !ctx.st.placement?.startsWith("ab")) n += Math.round(e.dir) !== Math.round(ctx.B?.direction ?? (ctx.kind === "dissolve" ? 90 : -1)) ? 1 : 0;
  if (e.depth) n += 1;
  for (const k of [FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, GUIDE_STRENGTH, ALSO_DRAW, DISSOLVE_BG, ...(ctx.kind === "dissolve" ? [] : CRUMBLE_KEYS)]) if (e.adv?.[k] != null) n += 1;
  for (const w of ["guide", "guide_particles"]) if (ctx.f?.[w] && ctx.f[w] !== "style default") n += 1;
  return n;
}
function resetAll(ctx) {
  setEffect((x) => {
    x.depth = 0;
    if (ctx.kind === "dissolve") x.dir = 90; else x.dir = null;
    x.adv = { ...x.adv };
    if (x.adv[ALSO_DRAW] && !(ctx.st0 || ctx.st).settings?.Particles) { delete x.adv.Particles; delete x.adv["Particle preset"]; }
    for (const k of [FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, GUIDE_STRENGTH, ALSO_DRAW, DISSOLVE_BG, ...(ctx.kind === "dissolve" ? [] : CRUMBLE_KEYS)]) delete x.adv[k];
  }, "emitter");
  ctx.api.setFx("emitter_values", "");
  for (const w of ["guide", "guide_particles"]) if (ctx.f?.[w] && ctx.f[w] !== "style default") ctx.api.setFx(w, "style default");
}

const ALL_PARTICLE_KEYS = [...Object.values(PARTICLES).flatMap((g) => [...g.main, ...g.more]),
  key("inherit", "Takes the emitter's motion", 0, 1, 0.05), key("motion_carry", "Carried by the clip", 0, 1, 0.05)];
function fillControls(ctx) {
  const a = ctx.amount || 1;
  const dirActs = ctx.P.direction_mode === "angle" || ctx.P.direction_mode === "against motion";
  const dir = dirActs && !ctx.st.placement?.startsWith("ab")
    ? [{ k: "direction", label: "Direction", min: 0, max: 359, step: 1, unit: "°", tip: "0 up, 90 right, 180 down, 270 left", int: true, angle: true,
      now: Math.round(ctx.e.dir ?? ctx.B.direction ?? 0) }] : [];
  return dir.concat(ALL_PARTICLE_KEYS.map((c) => {
    const get = c.get || ((p) => p[c.k]);
    const scale = c.k === "rate" || c.k === "burst" ? a : 1;
    const now = get(ctx.P);
    if (typeof now !== "number") return null;
    return { k: c.k, label: c.label, min: c.min, max: c.max, step: c.step, unit: c.unit || "", tip: c.tip || "", int: !!c.int, now: now * scale };
  }).filter(Boolean));
}
function applyFill(ctx, r) {
  const o = { ...ctx.own }, a = ctx.amount || 1;
  const before = { values: ctx.f?.emitter_values || "", dir: ctx.e.dir };
  const put = (k, v) => { if (same(v, ctx.B[k])) delete o[k]; else o[k] = v; };
  const wind = [...(ctx.P.wind || [0, 0])];
  for (const c of r.changes) {
    if (c.key === "direction") setDir(c.to);
    else if (c.key === "wind") wind[0] = c.to;
    else if (c.key === "windy") wind[1] = c.to;
    else put(c.key, c.key === "rate" || c.key === "burst" ? c.to / a : c.to);
  }
  if (r.changes.some((c) => c.key === "wind" || c.key === "windy")) put("wind", wind);
  if (r.mode) put("direction_mode", r.mode);
  if (r.collide) put("collide", r.collide);
  if (r.sprite) put("sprite", r.sprite);
  if (r.colors) put("colors", r.colors);
  write(ctx, o);
  return () => {
    ctx.api.setFx("emitter_values", before.values);
    if (r.changes.some((c) => c.key === "direction")) setDir(before.dir);
  };
}

export function basicFill(ctx) {
  if (ctx.kind !== "particles" || !ctx.P || !ctx.B || (ctx.P.path && ctx.P.path !== "particles")) return [];
  return [h("div", { class: "field fill-basic" }, ...fillRows(ctx, fillControls(ctx), (r) => applyFill(ctx, r), true))];
}

export function emitterHead(ctx) {
  const n = ctx.P && ctx.B ? changedCount(ctx) : 0;
  return n ? h("span", { class: "small" }, `${n} changed · `, ctx.ui.link("Reset all", () => resetAll(ctx))) : h("span", { class: "small" }, "as the style has it");
}
export function emitterFill(ctx) {
  if (!ctx.P || !ctx.B || ctx.kind === "dissolve") return [];
  return fillRows(ctx, fillControls(ctx), (r) => applyFill(ctx, r));
}
export function emitterPanel(ctx) {
  const { kind, st, P, B, ui } = ctx;
  const out = [];
  if (!P || !B) {
    if (kind !== "dissolve") out.push(...guideRows(ctx), startRow(ctx));
    out.push(ctx.ui.note("hint", S.getShot().clip ? "The values show once the live preview has answered." : "Pick a clip: the values show with the live preview."));
    return out;
  }
  if (kind === "dissolve") return out.concat(dissolveGroups(ctx));
  if (!particlesUsed(ctx)) {
    out.push(ctx.ui.note("hint", "The AI paints this element freely: the particles below come in when they guide it, are drawn over it (Source) or make it (Made by: Particles). ",
      ui.link("Let them guide the AI", () => ctx.api.setFx("guide", guideDefault(ctx.st0 || st) === "particles" ? "style default" : "particles"))));
  }
  return out.concat(particleGroups(ctx), pathGroup(ctx), crumbleGroup(ctx));
}

const crumbleCache = new Map();
function crumbleValues(style, extra) {
  const k = JSON.stringify([style, extra]);
  const got = crumbleCache.get(k);
  if (got) return got.P ? got : null;
  crumbleCache.set(k, { pending: true });
  fetch("/element-forge/api/dissolve-values", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ style, extra }) })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((d) => { crumbleCache.set(k, { P: d.params, B: d.base }); S.setUI({ crumbleValues: Date.now() }); })
    .catch(() => crumbleCache.delete(k));
  return null;
}
function crumbleGroup(ctx) {
  const { e, ui } = ctx;
  if (ctx.kind === "dissolve") return [];
  const on = !!e.adv?.[CRUMBLE];
  const setAdv = (k, v) => {
    if (ctx.f?.crumble) {
      setEffect((x) => { if (x.fromNode) { x.fromNode = { ...x.fromNode }; for (const c of CRUMBLE_KEYS) delete x.fromNode[c]; } }, "crumble");
      ctx.api.setFx("crumble", false);
    }
    setAdvAll(k, v);
  };
  const head = ui.toggle("The object crumbles", on, (v) => setAdv(CRUMBLE, v || undefined),
    "The clicked object falls apart into particles under the effect, and the scene behind it appears");
  if (!on) return [box(ctx, "crumble", "Crumble", [head, ctx.ui.note("hint", "The object stays whole.")], [], "")];
  const style = e.adv?.[CRUMBLE_STYLE] || "plain", extra = e.adv?.[CRUMBLE_VALUES] || "";
  let own = {};
  try { own = JSON.parse(extra || "{}") || {}; } catch { own = {}; }
  const v = crumbleValues(style, extra);
  const cx = { ...ctx, P: v?.P, B: v?.B, own, write: (o) => setAdv(CRUMBLE_VALUES, Object.keys(o).length ? JSON.stringify(o) : undefined) };
  const dir = e.adv?.[CRUMBLE_DIR] ?? 90;
  const notes = [];
  if (!e.where?.a) notes.push(ctx.ui.note("hint", "Needs the object: click it in Position. ", ui.link("Go to Position", () => ui.open("position"))));
  if (S.getShot().effects.findIndex((x) => x.id === e.id) > 0) {
    notes.push(ctx.ui.note("hint", "The crumbling is the clip under this effect, so it shows when this effect is the first in the list."));
  }
  const G = DISSOLVE;
  const main = [head, notes.length ? h("div", { class: "em-notes" }, ...notes) : null,
    dsChoice({ key: "crumble-style", label: "Look", changed: style !== "plain",
      control: ui.seg("Crumble look", CRUMBLE_STYLES, style, (s) => setAdv(CRUMBLE_STYLE, s === "plain" ? undefined : s)),
      onreset: () => setAdv(CRUMBLE_STYLE, undefined), resetTitle: "Back to Crumbles" }),
    dialRow(ctx, "Direction", +dir, 90, (d) => setAdv(CRUMBLE_DIR, d == null || Math.round(d) === 90 ? undefined : Math.round(d)), "Which way the object crumbles"),
    ctx.ui.note("hint", "Over the effect's time in the timeline. The live preview shows the effect's particles; the crumbling shows after the run."),
    ...backgroundRows(ctx)];
  const more = v ? [h("div", { class: "label sub" }, "Pieces"), ...rows(cx, G.emission.main), ...rows(cx, G.motion.main), ...rows(cx, G.particle.main),
    hexRow(cx, "glow_color", "Glow colour"), h("div", { class: "label sub" }, "Forces"), ...rows(cx, G.forces.main),
    ...rows(cx, [...G.emission.more, ...G.particle.more])] : [ctx.ui.note("hint", "Loading the values…")];
  const n = Object.keys(own).length;
  return [box(ctx, "crumble", "Crumble", main, more, "", GROUP_DESC.crumble, "crumble")];
}

function particleGroups(ctx) {
  const { e, st, P, B, ui } = ctx;
  const G = PARTICLES;
  const dirActs = P.direction_mode === "angle" || P.direction_mode === "against motion";
  const amt = ctx.amount || 1;
  const line = (k) => GROUP_DESC[k];
  return [
    box(ctx, "source", "Source", [
      ...guideRows(ctx),
      choiceRow(ctx, "guide_style", "Drawn for the AI as", GUIDE_DRAW, "How the particles are drawn in the guide the AI gets"),
      ...depthRows(ctx),
      startRow(ctx),
      alsoDrawRow(ctx),
      dsChoice({ key: "shape", label: "Shape", wide: false,
        control: h("span", { class: "small" }, shapeName(shapeOf(e, st)), " · ", ui.link("change in Position", () => ui.open("position"))) }),
      ...(shapeOf(e, st) === "object edge + area" ? [numRow(ctx, EDGE_SHARE)] : []),
      ...rows(ctx, G.source.main),
      ...ctx.extras.seed(),
    ], rows(ctx, G.source.more), "", line("source")),
    box(ctx, "emission", "Emission", [...rows(ctx, G.emission.main), curveRow(ctx), timing(ctx), ...ctx.extras.preroll()], rows(ctx, G.emission.more), "", line("emission")),
    box(ctx, "motion", "Motion", [
      choiceRow(ctx, "direction_mode", "Mode", MODES),
      dialRow(ctx, "Direction", e.dir, B.direction, setDir, dirActs ? "Which way they fly: the canvas arrow"
        : `Which way they fly: the canvas arrow (with the mode Angle or Against motion; ${pname(MODES, P.direction_mode)} sets its own)`),
      ...rows(ctx, G.motion.main),
      h("div", { class: "label sub" }, "Particles take the emitter's motion"),
      numRow(ctx, key("inherit", "How much", 0, 1, 0.05, { tip: EXPL.inherit })),
      numRow(ctx, key("motion_carry", "Carried by the clip", 0, 1, 0.05, { tip: EXPL.carry })),
      ...aiFollowRows(ctx),
    ].filter(Boolean), rows(ctx, G.motion.more), "", line("motion")),
    box(ctx, "particle", "Particle", [choiceRow(ctx, "blend", "Look", BLENDS, "Glowing adds light, solid covers what is behind"),
      ...rows(ctx, G.particle.main), colorsRow(ctx)], [spriteRow(ctx), ...rows(ctx, LOOK), ...rows(ctx, G.particle.more)], "", line("particle")),
    box(ctx, "merge", "Merge (liquid)", [
      ui.toggle("Merge into one body", P.blob > 0, (v) => setOwn(ctx, "blob", v ? (B.blob > 0 ? B.blob : 8) : 0),
        "The particles blurred together and choked: drops, thick smoke, flame tongues"),
      ...rows(ctx, G.merge.main),
    ], rows(ctx, G.merge.more), "", line("merge")),
    box(ctx, "forces", "Forces", rows(ctx, G.forces.main), rows(ctx, G.forces.more), "", line("forces")),
    box(ctx, "contact", "Contact & depth", [choiceRow(ctx, "collide", "Collision", COLLIDE, "What a particle does where it meets the scene (depth)"),
      ...rows(ctx, forCollide(P, G.contact.main)), depthWrapOf(ctx)],
    [...rows(ctx, forCollide(P, G.contact.more)), ui.toggle("Hidden by the scene", e.adv?.[PREMASK] ?? true, (v) => setAdv(PREMASK, v ? undefined : false),
      "Off: the particles stay in front of everything"), ...rows(ctx, SPLASH)], "", line("contact")),
  ];
}
const COLLIDE_USES = { restitution: ["bounce"], friction: ["bounce", "slide"], land_fade: ["stick", "bounce"] };
const forCollide = (P, list) => list.filter((c) => !COLLIDE_USES[c.k] || COLLIDE_USES[c.k].includes(P.collide || "none"));
const depthBase = new Map();
function depthWrapOf(ctx) {
  const mine = +(ctx.e.depth || 0);
  if (ctx.fresh || !depthBase.has(ctx.e.id)) depthBase.set(ctx.e.id, (ctx.P.depth_offset ?? 0) - mine);
  const base = depthBase.get(ctx.e.id), cur = base + mine;
  return depthWrap(ctx, cur, base, mine, (v) => setEffect((x) => { x.depth = +(v - base).toFixed(3); }, "emitter"));
}
function pathGroup(ctx) {
  const { P } = ctx, cur = P.path || "particles";
  const sub = (t, list) => [h("div", { class: "label sub" }, t), ...rows(ctx, list)];
  return [box(ctx, "path", "Paths", [choiceRow(ctx, "path", "Path", PATHS, `A path drawn over the particles: bolt, strike, random bolts, climbing charge or cracks. ${PATH_EXPL[cur] || ""}`),
    ...rows(ctx, PATH.main)],
  [...sub("Bolt", PATH.bolt), ...sub("Strike", PATH.strike), ...sub("Random bolts", PATH.random),
    choiceRow(ctx, "rand_aim", "Aim", AIMS, "Which way the random bolts shoot"), ...sub("Climbs", PATH.climb), ...sub("Cracks", PATH.crack)],
  "", GROUP_DESC.path, "path")];
}
function aiFollowRows(ctx) {
  const { e, f, ui } = ctx;
  const on = !!f.follows_motion, parts = guideNow(ctx.st0 || ctx.st, e) === "particles";
  return [h("div", { class: "label sub" }, "For the AI"),
    ui.toggle("The AI follows the motion", on, (v) => ctx.api.setFx("follows_motion", v), EXPL.ltx),
    aiOff(ctx) ? ui.note("hint", "Counts when the AI makes the element (Made by: AI).")
      : parts ? ui.note("hint", "With the particle guide the particles carry the motion (above); this counts with another guide or none.") : null,
    on ? advNum(ctx, FOLLOW_STRENGTH, "Strength", 0, 3, 0.05, 1.0, EXPL.strength) : null,
    on ? advNum(ctx, FOLLOW_LAG, "Lag", 0, 1, 0.05, 0.6, EXPL.strength) : null];
}
function dissolveGroups(ctx) {
  const G = DISSOLVE;
  return [
    box(ctx, "source", "Source", [ctx.ui.note("hint", "The object you clicked: its mask crumbles."), ...backgroundRows(ctx),
      ...ctx.extras.seed()], [], "", "what crumbles, what is behind"),
    box(ctx, "emission", "Emission", [...rows(ctx, G.emission.main), timing(ctx)], rows(ctx, G.emission.more), "", "pieces, timing"),
    box(ctx, "motion", "Motion", [
      dialRow(ctx, "Direction", ctx.e.dir, 90, (v) => setDir(v ?? 90), "Which way it crumbles: the canvas arrow"),
      ...rows(ctx, G.motion.main),
      h("div", { class: "label sub" }, "Particles take the object's motion"),
      numRow(ctx, key("inherit", "How much", 0, 1, 0.05, { tip: EXPL.inherit.replace("emitter's", "object's") })),
      numRow(ctx, key("motion_carry", "Carried by the clip", 0, 1, 0.05, { tip: EXPL.carry })),
    ], [], ""),
    box(ctx, "particle", "Particle", [...rows(ctx, G.particle.main), hexRow(ctx, "glow_color", "Glow colour")], rows(ctx, G.particle.more), ""),
    box(ctx, "forces", "Forces", rows(ctx, G.forces.main), [], ""),
  ];
}
