# Using Element Forge

[README](../README.md) · [Setup](setup.md) · [Nodes](nodes.md) · [Licenses](licenses.md)

## Work in the app

Open **Templates → Extensions → comfyui-element-forge → Element Forge (app)**.

1. **Clip:** load a video or picture. Analysis estimates depth, surface normals and camera motion once per clip.
2. **Position & Track:** click the effect's position and choose what it follows. Check the track before generating.
3. **Effect:** choose an effect and style, then describe the result you want. **Enhance** can help when a language model is installed.
4. **Output:** choose Preview or Full quality and run. Each effect can keep several versions.
5. **Scene & finish:** adjust the finished result, compare versions, then export from Output.

Use **+ Effect** to add another effect to the same clip. Each has its own settings and versions. **Lit by the other effects** lets one effect receive light from the others.

## Position, tracking and masking

| Goal | Control |
|---|---|
| Follow a point or object | Click point A, choose the tracking mode, and inspect the track check. An object word helps identify what to follow. |
| Connect two positions | Shift-click point B. Give the effect area enough room around both points. |
| Keep an effect behind the selected object | Under Object, enable **In front of the effect**. Its mask hides the effect. |
| Keep the base of an effect on its tracked point | In Advanced, enable **Base stays on the point**. |
| Include matching objects | Enable **all alike** in the workflow's EF Track node. Otherwise the selected object stays the target. |

Fast motion, crossings and silhouettes without texture can lose a track. Review the track before a full generation and change the point, object word or mode when needed.

## Choose how the effect is made

- **Overlay** generates a separate element and composites it over the footage. Light, glow, colour and placement remain adjustable. Start here for glowing effects.
- **Inpaint** generates the effect within an area of the footage. Use it for contact with surfaces; the generated appearance and lighting are less separable.
- **Drawn styles** use particles without an AI generation. These include fireflies and selected lightning, smoke, aura and debris styles.

Availability depends on the effect. The app marks experimental styles before a run. Whole-frame effects and Dissolve use their own routes.

## Preview, finish and export

**Preview** uses a smaller generation and fewer passes for supported AI overlay effects. **Make version N final (x2)** continues that preview into a full-size version. **Add passes** can produce missing passes from a saved result without generating the effect again.

The app's live controls use the passes available in the selected version. If light controls are missing, add a light pass or choose a version that has one.

Export the visible composite as MP4, ProRes, H.265 10-bit, PNG or EXR, or export separate scene-linear EXR passes. Runs are stored in `output/element-forge/<run>/`.

### Canvas and timing

Drag the transform box to move or resize the effect. Shift preserves its shape; Alt resizes from the centre. Drag outside a corner to rotate. The timeline sets start, end and fades; Advanced adds keyframes. Press **?** in the app for shortcuts.

## Use the workflow

Open **Element Forge** from the same template list, or drag [Element Forge.json](../example_workflows/Element%20Forge.json) onto ComfyUI's canvas.

Follow the chain:

**Load Video → EF Shot → EF Track → EF Element → EF Place → EF Light & Glow → EF Export**

Choose your installed models in **EF Models**, set the clip and effect, then run. The result appears on EF Export. Optional nodes are bypassed by default; select one and press **Ctrl+B** to enable it. Unchanged options use the style defaults.

The app and workflow use the same underlying graphs. ComfyUI can reuse unchanged results while they remain cached; changing an earlier input or clearing the cache may require recomputation.

## Reuse an element

Enable **Save the element** in Output to keep an AI element generated on black. The library is stored under `output/element-forge/elements/<name>/`.

In a workflow, connect **EF Library Element** to EF Place's *own element* input. **EF Element from Images** accepts frames from another generator, with optional alpha. Placing a saved element skips its AI generation; tracking, lighting and compositing still run as needed.

## Build a custom graph

**EF Unpack** exposes the footage, element, alpha and available passes as ordinary node outputs. **EF Shot** can accept video, frames with an FPS value, or a still image. Compositing tools are listed in the [node reference](nodes.md).

For scripting, the graphs are in `api_workflows/`. Settings are described by `element_forge.settings.json`; `element_forge.stages.json` maps the graph sections to stage nodes.
