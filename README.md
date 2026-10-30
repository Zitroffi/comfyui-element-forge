<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/branding/logo-on-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/branding/logo-on-light.svg">
    <img src="docs/assets/branding/logo-on-light.svg" alt="Element Forge" width="560">
  </picture>
</h1>

<p align="center"><strong>AI effects that sit in the shot.</strong></p>

<p align="center">
  <a href="#get-started">Get started</a> ·
  <a href="#your-first-effect">Your first effect</a> ·
  <a href="#more-examples">Examples</a> ·
  <a href="#documentation">Documentation</a>
</p>

Add fire, lightning, smoke and particles to your own footage in ComfyUI. Track effects through your shot, adjust their light and colour, and export the result or separate EXR passes.

Use the app for a guided workflow, or connect the nodes in your own graph. AI effects are generated locally with **LTX-2.5**; selected particle styles run without AI generation.

<p align="center">
  <a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/katana-charge.mp4">
    <img src="docs/assets/examples/katana-charge.gif" alt="Electricity following a moving katana" width="640">
  </a>
</p>

<p align="center"><em>Electricity follows the blade through the shot. Click the image for the full clip.</em><br><sub>AI-generated effects; stock footage.</sub></p>

## What you can do

- **Place effects in the scene.** Follow a point, object or camera motion, and use masks to hide an effect behind foreground objects.
- **Shape the finished look.** Adjust light, glow, colour and placement in the app. Keep versions and combine several effects on one clip.
- **Continue in your compositor.** Export a finished video or separate scene-linear EXR passes for further work.

Choose from fire, lightning, sparks, smoke, magic, weather, debris, liquid and dissolve styles, or describe your own effect. The app identifies experimental styles before you generate.

## Get started

You need **ComfyUI 0.41.2 or newer**, the two node packs below and the [required models](docs/setup.md#default-models).

The AI routes have been tested with NVIDIA GPUs from **11 GB VRAM** on Windows and Linux. This is a tested configuration, not a confirmed minimum. Allow about **45 GB** for the default models; RAM use varies with the models and clip size. Other GPU platforms have not been tested.

### 1. Install

With ComfyUI's Python environment active, run this from the ComfyUI folder. For **Windows portable**, use the [embedded-Python instructions](docs/setup.md#install-the-node-packs).

```bash
cd custom_nodes
git clone https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything
git clone https://github.com/Lightricks/ComfyUI-LTXVideo
git clone https://github.com/Zitroffi/comfyui-element-forge
python -m pip install -r ComfyUI-Video-Depth-Anything/requirements.txt
python -m pip install -r ComfyUI-LTXVideo/requirements.txt
python -m pip install -r comfyui-element-forge/requirements.txt
```

### 2. Add the models

Follow the [model list](docs/setup.md#default-models) for filenames, download links and folders, then restart ComfyUI. The app's gear menu shows each model's status and source.

Prompt enhancement, Bonsai, NVIDIA upscaling and HDR are optional. You can add them later through the [setup guide](docs/setup.md#optional-additions).

## Your first effect

Start with a short clip and an overlay effect.

1. Open **Templates → Extensions → comfyui-element-forge → Element Forge (app)**.
2. Load your clip in **Clip**.
3. In **Position & Track**, click where the effect belongs and choose what it follows. Check the track before generating.
4. In **Effect**, choose a style and describe what you want. Use **Preview** quality when available, then **Run**.
5. Adjust the result in **Scene & finish**. Light and glow controls depend on the passes available in the selected version.
6. Export from **Output**. Choose a finished video or image sequence, with separate EXR passes when needed.

The app keeps versions so you can compare results and restore their settings. For supported previews, **Make final** creates a full-size version; **Add passes** provides missing layers without another effect generation.

Prefer a node graph? Open the **Element Forge** template instead. It uses the same underlying graphs as the app. See [the workflow guide](docs/usage.md#use-the-workflow).

## More examples

The effects below are AI-generated with LTX-2.5, except the fireflies, which are drawn particles. Footage comes from Pexels and Mixkit.

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/assets/examples/orb.gif" alt="Energy around a moving ball" width="160"><br>
      <strong>Energy around a moving ball</strong><br>
      <a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/orb.mp4">Download MP4</a>
    </td>
    <td align="center" width="50%">
      <img src="docs/assets/examples/rose-flame.gif" alt="Flame following a rose" width="160"><br>
      <strong>Flame following a rose</strong><br>
      <a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/rose-flame.mp4">Download MP4</a>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="docs/assets/examples/dress-sparks.gif" alt="Sparks from a spinning dress" width="160"><br>
      <strong>Sparks from a spinning dress</strong><br>
      <a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/dress-sparks.mp4">Download MP4</a>
    </td>
    <td align="center" width="50%">
      <img src="docs/assets/examples/fireflies.gif" alt="Fireflies over a lake" width="160"><br>
      <strong>Fireflies over a lake</strong><br>
      <a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/fireflies.mp4">Download MP4</a>
    </td>
  </tr>
</table>

All clips, stills and GIFs are available in the [examples release](https://github.com/Zitroffi/comfyui-element-forge/releases/tag/examples).

## Documentation

- [Setup and troubleshooting](docs/setup.md): dependencies, models and optional additions.
- [Usage guide](docs/usage.md): tracking, masks, generation modes, versions, export and reusable elements.
- [Node reference](docs/nodes.md): extend the supplied workflow or build your own.
- [Report an issue](https://github.com/Zitroffi/comfyui-element-forge/issues): include the error and steps to reproduce it.

## License

The code, app and workflows use the [MIT License](LICENSE). Models retain their own licenses and conditions. See the [model license summary](docs/licenses.md) before using or publishing their outputs.
