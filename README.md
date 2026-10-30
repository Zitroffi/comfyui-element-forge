# Element Forge

**AI effects that sit in the shot.**

Put AI-generated fire, lightning, smoke and particles into your own footage – tracked, lit and in layers, inside ComfyUI.

Generated VFX usually looks pasted on: it does not light the scene, nothing passes in front of it, and you cannot fix
it in comp. Element Forge generates the element with **LTX-2.5** and then makes it belong to your shot.

- **It sits in the shot.** The element follows what you click, hides behind the fingers and objects in front of it
  (SAM 3), and lights the scene from its place in depth.
- **It stays editable.** Light, glow, colour and placement change live after the run. Every part comes out as a
  scene-linear EXR pass for your compositing app.
- **It runs on your machine.** Open weights only, LTX-2.5 at the core, tested on an 11 GB RTX 2080 Ti.

Two ways in:

- **The app**, in ComfyUI's App mode: pick a clip, click where the effect belongs, choose an effect, Run.
- **One workflow** from clip to EXR: Load Video and six stage nodes (EF Shot, EF Track, EF Element, EF Place,
  EF Light & Glow, EF Export), which you can also take apart for your own graphs.

Effects: fire · lightning · sparks · smoke · magic & energy · snow, rain & fireflies · dust & debris · liquid · dissolve ·
your own (describe any element).

The effects in these examples are AI-generated with LTX-2.5, except the fireflies (drawn particles); the footage is real.

| Example | Effect | How it sits in the shot |
|---|---|---|
| [![A shell of energy around a glowing ball](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/orb.gif)](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/orb.mp4) | A shell of energy around a glowing ball | follows the ball in her hands as she lifts it (object track) |
| [![Electricity crawls along a drawn katana](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/katana-charge.gif)](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/katana-charge.mp4) | Electricity crawls along a drawn katana | follows the blade (object track) through the draw |
| [![A cold pink flame on a rose](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/rose-flame.gif)](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/rose-flame.mp4) | A cold pink flame on a rose | follows the blossom through the swing of the arm |
| [![Sparks fly from the hem of a spinning dress](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/dress-sparks.gif)](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/dress-sparks.mp4) | Sparks fly from the hem of a spinning dress | follows the dress (object track); the particles start at its bottom edge |
| [![Fireflies over a lake at dusk](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/fireflies.gif)](https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/fireflies.mp4) | Fireflies over a lake at dusk | particles over the whole frame that stay in the scene; made without an AI run |

Click a picture for the full clip. Footage: Pexels and Mixkit, under their free licences; the effects are made with Element Forge.

## How it works

Element Forge turns a plate (your own video) plus a short prompt into a finished, editable VFX shot:

1. **Generate the element on black** – fire, lightning, fireflies, magic – with LTX-2.5 (local, INT8, runs on an
   11 GB GPU) and turn it into a clean layer with alpha (`Unmult`). Absorbing elements such as smoke are generated
   on white and unmultiplied the other way round, with an automatic correction for an uneven studio white.
2. **Pin and place it** – the element's base point is stabilized (`Anchor`) and follows a tracked point in the
   plate: optical-flow track or SAM3 object track.
3. **Make it sit in the shot** – SAM3 holdouts (fingers in front of the flame), the element as a 3D light on the
   plate (point cloud from Video Depth Anything, normals from MoGe-2 (**MoGe Normals**), inverse-square falloff, soft shadows), a glow with an
   inverse-square falloff like Deep Glow, depth of field, and night as a grade. Depth and light are deflickered with
   motion compensation, so the per-frame estimates stay calm; the plate itself is never changed.
4. **Go beyond 8 bit** – the light, glow and element stay scene-linear up to the EXR passes; on RTX cards NVIDIA RTX
   Video HDR turns the export into real HDR.
5. **Hand it over** – scene-linear EXR passes (plate, element, light, glow, depth, normals, the object's mask) for your
   compositing app, so color and intensity stay editable.

Optionally the element can also be generated *in* the shot instead of on black: the flame is shaped by the hand with
the LTX **Union Control** IC-LoRA (hand depth as control video).

## Requirements

**In short**

| | |
|---|---|
| GPU | **NVIDIA with 11 GB VRAM or more** for the AI styles (LTX-2.5). Tested: RTX 2080 Ti (11 GB) and RTX PRO 4500 (32 GB). Not tested on Apple, AMD or Intel GPUs |
| System RAM | tested with 80 GB (local) and 94 GB (cloud); less is not tested. Windows: a page file of 32 GB or more |
| Disk | about 45 GB for the default models (list below), about 6 GB more for the optional Bonsai |
| ComfyUI | 0.41.2 or newer, plus ComfyUI-Video-Depth-Anything and ComfyUI-LTXVideo |

The app checks the GPU and RAM before a run and says so when they are below what was tested.

- ComfyUI 0.41.2 or newer (uses core nodes for SAM3, MoGe-2, video I/O)
- Custom nodes: [ComfyUI-Video-Depth-Anything](https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything)
  (Apache-2.0; depth for light, holdouts and depth of field), [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)
  (IC-LoRA loader, IC-LoRA guide and track drawing) and this pack (`comfyui-element-forge`). These are all the custom node
  packs the workflow `Element Forge.json` and the app use; everything else is ComfyUI core.
  [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) is only needed for the optional GGUF Q4 file (see below)
- Optional, for **NVIDIA SR + HDR** in **EF LTX Options** (in the app: Upscale NVIDIA × 2 and the HDR export): the [NVIDIA VFX nodes](https://github.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes)
  (RTX Video Super Resolution and RTX Video HDR; RTX 20 series or newer, installs the `nvidia-vfx` package). Without them
  leave it off; the workflow and the app leave the switched-off branch out.
  Known hurdle: in the Windows portable build of ComfyUI (tested with 0.42.1) installing the pack's requirements failed
  with `Cannot import 'wheel_stub.buildapi'`, and the nodes then failed to load with `No module named 'nvvfx'`
- Python packages: `opencv-python-headless`, `OpenImageIO` (EXR export)
- GPU: tested on an RTX 2080 Ti (11 GB) with 80 GB system RAM
- System RAM, measured for an 81-frame 1080×1920 shot (fireflies in depth): 28 GB peak with ComfyUI's `--cache-none`;
  with the default cache ComfyUI keeps results while RAM is free (46 GB on the 80 GB test machine). The LTX workflows
  also hold the text encoder and model in RAM. With less RAM, `--cache-none` keeps the use near that peak (not tested on
  a smaller machine). Depth, light and normals are computed at the clip's resolution, so RAM grows with it: a 4K
  clip has four times the pixels of 1080p (not tested). For a clip or picture larger than 1080p the app offers a 1080p
  copy (`<name>_1080p.mp4` next to it in `input`, upright, about a minute for 11 s of 4K) or the full size
- Windows: every allocation counts against the commit limit (RAM + page file), not only against free RAM. With a small
  page file the limit can run out while RAM still looks free, and ComfyUI then dies with an access violation. Before each
  Element Forge node runs, the pack checks the limit and, when it gets close, frees ComfyUI's model pins and cached
  results (logged as `memory guard`). A page file of 32 GB or more gives extra room

### Models

| File | Folder | Source |
|---|---|---|
| `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` (21.5 GB) | `diffusion_models` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5), folder `diffusion_models` (log in and accept the terms). Without a login: `LTX25-distilled-DiT-comfy-int8.safetensors` from [joeygambino/LTX-2.5-Quantized](https://huggingface.co/joeygambino/LTX-2.5-Quantized) gave practically the same video. When the official file is missing, the app uses another installed LTX file (pick it at **LTX model** under the gear at the top of the app) |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` (15.4 GB) | `text_encoders` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5), folder `text_encoders` (log in and accept the terms) |
| `ltx-2.5-video-vae-conv-bf16.safetensors` (1.45 GB) | `vae` | [unsloth/LTX-2.5-GGUF](https://huggingface.co/unsloth/LTX-2.5-GGUF) |
| `ltx-2.5-audio-vae-bf16.safetensors` (0.36 GB) | `vae` | [unsloth/LTX-2.5-GGUF](https://huggingface.co/unsloth/LTX-2.5-GGUF) |
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` (1.0 GB) | `latent_upscale_models` | [unsloth/LTX-2.5-GGUF](https://huggingface.co/unsloth/LTX-2.5-GGUF) |
| `sam3.1_multiplex_fp16.safetensors` | `checkpoints` | [Comfy-Org/sam3.1](https://huggingface.co/Comfy-Org/sam3.1) (the checkpoint of the ComfyUI SAM3 template) |
| `video_depth_anything_vits.pth` (0.12 GB, Apache-2.0) | `videodepthanything` | [depth-anything/Video-Depth-Anything-Small](https://huggingface.co/depth-anything/Video-Depth-Anything-Small); the node downloads it on first use. Until then ComfyUI's setup panel lists it as a missing model (the Run button stays enabled); its **Download** button fetches it as well. Depth that stays consistent over time |
| `moge_2_vitl_normal_fp16.safetensors` (0.66 GB, MIT) | `geometry_estimation` | [Comfy-Org/MoGe](https://huggingface.co/Comfy-Org/MoGe) (ComfyUI core node `LoadMoGeModel` + **MoGe Normals**); normals for the light |
| `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors` (0.33 GB: the element follows the emitter's motion) | `loras` | [Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control) |
| `ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors` (0.33 GB: the background behind **Dissolve**) | `loras` | [Lightricks/LTX-2.5-22b-IC-LoRA-Clean-Plate](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Clean-Plate) (log in and accept the terms) |
| `ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors` (1.31 GB) | `loras` | [Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen) (log in and accept the terms) |
| `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors` (0.65 GB) | `loras` | [Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control), see the [official guide](https://docs.ltx.io/open-source-model/feature-guides/structural-control/union-control) (the 2.5 graph uses this 2.3 IC-LoRA) |

### Optional models and speed (measured)

Same shot (skater, sparks), same seed, measured on an RTX 2080 Ti 11 GB and an RTX PRO 4500 Blackwell 32 GB. In the app,
open the gear at the top of the app panel and pick the file at **LTX model** (with **INT8 attention**; kept in ComfyUI's
settings of this computer). In the workflow, pick it in **EF Models** (*LTX model*, *attention*, *text encoder*):

| Option | File | Folder | What it changes |
|---|---|---|---|
| INT8 attention (with an INT8 file) | – | – | 2080 Ti: sampler 30 s instead of 41 s. With the GGUF file it is much slower (213 s): do not combine them |
| LTX as GGUF Q4 instead of INT8 | `ltx-2.5-22b-distilled-transformer-bf16-Q4_K_M.gguf` (12.2 GB, [agosh/LTX-2.5-Comfy-GGUF](https://huggingface.co/agosh/LTX-2.5-Comfy-GGUF)), needs [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | `unet` | 8 GB less disk and system RAM; 2080 Ti: the LTX sampler takes 82 s instead of 41 s, the picture is the same to the eye. RTX PRO 4500 (32 GB): a full run takes about as long as with INT8 (81 frames 137 s against 147 s, 153 frames 209 s against 245 s), the picture again the same to the eye. **Dissolve**: the Clean Plate LoRA runs at strength 1.5 with INT8 (at 1.0 blurred grey patches stayed where the object was) and at 1.0 with GGUF, which was clean there. The app and the workflow switch it by themselves |
| LTX as W4A4 | `LTX25-distilled-DiT-comfy-w4a4.safetensors` (10.5 GB, [joeygambino/LTX-2.5-Quantized](https://huggingface.co/joeygambino/LTX-2.5-Quantized)) | `diffusion_models` | half the memory of INT8, same picture to the eye; not faster on the Blackwell card |
| LTX as NVFP4 | `ltx-2.5-22b-distilled-transformer-nvfp4.safetensors` (17.4 GB, [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5), log in and accept the terms) | `diffusion_models` | FP4 needs an RTX 50 / Blackwell card. On the RTX PRO 4500 the whole shot took 172–236 s against 187 s (INT8) and 198 s (GGUF): no clear gain; same picture to the eye |
| Text encoder as bf16 | `gemma4-12b-with-proj-ltx-2.5-bf16.safetensors` (26.3 GB, [unsloth/LTX-2.5-GGUF](https://huggingface.co/unsloth/LTX-2.5-GGUF), no login) | `text_encoders` | 11 GB more memory; the same flame as with INT8 in our test (RTX PRO 4500, same seed). In the app: **Text encoder** under the gear (a choice once a second Gemma 12B file is installed); in the workflow: *text encoder* in **EF Models** |
| Language model for **✦ Enhance** | `gemma4_e2b_it_int8_convrot.safetensors` (4.8 GB, [Comfy-Org/gemma-4](https://huggingface.co/Comfy-Org/gemma-4)) | `text_encoders` | 2–6 s per description. Needed for **✦ Enhance** when Bonsai is not set up. The LTX text encoder (Gemma 12B) is not offered for it: it answered only "SSSS…" on both test cards |

Which file for which card (from these measurements):

- **RTX 20 (11 GB):** the INT8 default, best with **INT8 attention**: half the LTX sampler time of GGUF Q4.
- **RTX 30 / 40:** not tested. These cards have INT8 tensor cores like the RTX 20, so INT8 should help as well.
- **RTX 50 / Blackwell (32 GB tested):** GGUF, INT8 and NVFP4 were within the run-to-run spread (170–240 s for the
  same shot).
- **Less system RAM or disk:** the GGUF Q4 file needs about 8 GB less.

The whole app shot (tracking, depth, normals, LTX, light, all passes) took 5–10 minutes on the 2080 Ti; most of the time
outside LTX goes to depth, normals and deflicker. On the Blackwell card the generation took 7.6 minutes
including the first model loading.

## Install

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything
git clone https://github.com/Lightricks/ComfyUI-LTXVideo
git clone <this repo> comfyui-element-forge
pip install -r ComfyUI-Video-Depth-Anything/requirements.txt
pip install -r ComfyUI-LTXVideo/requirements.txt
pip install -r comfyui-element-forge/requirements.txt
```

Optionally, for **NVIDIA SR + HDR**, also
`git clone https://github.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes` and its requirements; the workflow and the app run
without them. See
the known hurdle with the portable build under **Requirements**.

Use the Python environment ComfyUI runs in for `pip`. With the Windows portable build, `pip` alone installs into the
wrong Python; run it through the embedded one from the `ComfyUI_windows_portable` folder instead:

```bat
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-Video-Depth-Anything\requirements.txt
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-LTXVideo\requirements.txt
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\comfyui-element-forge\requirements.txt
```

Video Depth Anything pulls in `opencv-python`, this pack asks for
`opencv-python-headless`; both provide `cv2`, so keep one of them if pip reports a conflict. Restart ComfyUI. The nodes appear under **Element Forge**
(display names `EF …`); the workflow is in `example_workflows/` and shows up in ComfyUI's templates
(left sidebar **Templates** → **Extensions** → `comfyui-element-forge`).

## Quick start

### With the app

1. Install the pack, the custom nodes and the models (above); restart ComfyUI.
2. Left sidebar **Templates** → **Extensions** → `comfyui-element-forge` → **Element Forge (app)**. It opens in
   ComfyUI's App mode: the steps on the right, your clip as a canvas in the middle, a timeline below. ComfyUI may show
   its own App-mode tour first; **Skip** closes it.
3. Pick your clip, click where the effect belongs, pick an effect and a style, **Run**.
4. Change light, glow and colour live in **Scene & finish** (nothing is made again), then **Export** in **Output**: MP4,
   ProRes or H.265 10 bit, PNG or EXR, with the layers as EXR if you like.

More in *The app* below.

### With the workflow

1. Install the pack and the models (above), restart ComfyUI.
2. Put your clip into ComfyUI's `input` folder and pick it in **Load Video** (the template names `my_clip.mp4`).
3. Open the workflow: left sidebar **Templates** → **Extensions** → `comfyui-element-forge` → **Element Forge**, or
   drag `example_workflows/Element Forge.json` onto the canvas. Its note lists the steps.
4. Seven nodes in a row, each one step of the app: **Load Video** → **EF Shot** (the clip, depth model, night) →
   **EF Track** (click into the first frame for point A, Shift-click for B; object word, what it follows) →
   **EF Element** (effect and style, overlay or inpaint, words, timing, quality; the template starts on preview) →
   **EF Place** (size, side, depth, blend) → **EF Light & Glow** → **EF Export** (run name, EXR passes, track check).
   **EF Models** says which LTX files this computer uses. **Run**.
5. The comp shows on **EF Export**, the track check on **EF Track**, the element on **EF Element**; everything goes to
   `output/element-forge/<run>/`: the comp MP4, the passes as scene-linear EXR (half float) for compositing, the
   settings.

Change only the light strength or the glow exposure and run again: LTX does not generate the element again, it comes
from ComfyUI's cache (while RAM allows; Element Forge frees the cache when the computer's memory runs short).

The **options** are in the workflow but bypassed (select one and press Ctrl+B to use it): **EF Particles**, **EF Guide**
(with a Load Image for a drawn path), **EF Dissolve**, **EF LTX Options**, a Load Image for your own object mask and
**EF Library Element**. Without them the style's tested values hold. Every value of an option starts at **style default**
(numbers: −2), the style's tested value; set only what you want to change. Rarely used fields are advanced inputs: in the Vue node view they are hidden
until you choose *Show advanced inputs* in the node's menu, the classic view shows them all.

When the run is queued, the chain of EF nodes is replaced by the same graph the app runs, so only the parts whose
settings changed run again. The template, the app and a chain you build yourself
give the same graph for the same settings.

Measured with the stage nodes on an RTX 2080 Ti 11 GB (INT8 file with INT8 attention, as recommended above) and on an
RTX PRO 4500 32 GB, effect *Fire · Flame on the object*, from queueing to the finished comp with all passes. The rows ran
in this order: from the second row of a clip on, its analysis (depth, normals, track) was reused, as the app does for every
further run on a clip; on the 32 GB card earlier runs had analysed both clips already. *cold*: the first run after
starting ComfyUI, with loading the models.

| Clip | Element | Quality | RTX 2080 Ti 11 GB | RTX PRO 4500 32 GB |
|---|---|---|---|---|
| Katana, 1920×1012, 89 frames | AI element on black, overlay | preview | 3.8 min (cold) | 1.1 min |
| Katana, 1920×1012, 89 frames | AI element on black, overlay | full | 4.2 min | 1.9 min |
| Katana, 1920×1012, 89 frames | AI element generated in the plate (inpaint) | full | 5.3 min | 1.9 min |
| Katana, 1920×1012, 89 frames | AI element guided by particles | preview | 2.6 min | 1.7 min |
| Katana, 1920×1012, 89 frames | AI element guided by particles | full | 4.9 min | 4.0 min |
| Glowing ball, 720×1280, 160 frames | AI element on black, overlay | preview | 2.2 min | 1.6 min |
| Glowing ball, 720×1280, 160 frames | AI element on black, overlay | full | 5.5 min | 2.5 min |
| Glowing ball, 720×1280, 160 frames | AI element generated in the plate (inpaint) | full | 6.6 min | 2.6 min |
| Glowing ball, 720×1280, 160 frames | AI element guided by particles | preview | 2.2 min | 1.8 min |
| Glowing ball, 720×1280, 160 frames | AI element guided by particles | full | 5.3 min | 4.9 min |

Earlier measurements on the 2080 Ti, each including the analysis: a 161-frame portrait clip with a climbing bolt took
12.5 minutes, a dissolve 14.5 minutes. A place-only shot from the element library took about 5 minutes; it skips LTX, the
rest of the pipeline stays. Changing only the light took 1.5–3 minutes.

<details><summary><b>Effect keys</b>: the value of <i>effect</i> on EF Element and its name in the app</summary>

| `effect` on EF Element | In the app | |
|---|---|---|
| `fire/flame` | Fire · Flame on the object | AI |
| `fire/burst` | Fire · Short burst | AI |
| `fire/smolder` | Fire · Smoldering ground | AI |
| `lightning/between` | Lightning · Between two points | AI |
| `lightning/climb` | Lightning · Climbs an object: fine filaments | AI |
| `lightning/climb_arcs` | Lightning · Climbs an object: blue arcs | AI |
| `lightning/climb_drawn` | Lightning · Climbs an object: particles only | no AI |
| `sparks/grind` | Sparks · From a moving object | AI |
| `sparks/burst` | Sparks · Burst from a point | AI |
| `smoke/rise` | Smoke · Rises from a point | AI |
| `smoke/rise_drawn` | Smoke · Rises from a point: particles only | no AI |
| `magic/aura` | Magic & energy · Aura around a figure | AI |
| `magic/aura_drawn` | Magic & energy · Aura: particles only | no AI |
| `magic/flow` | Magic & energy · Energy between two points | AI |
| `magic/orb` | Magic & energy · Energy ball | AI |
| `weather/snow` | Snow, rain & fireflies · Snow | AI |
| `weather/rain` | Snow, rain & fireflies · Rain | AI |
| `weather/fireflies` | Snow, rain & fireflies · Fireflies | no AI |
| `debris/debris` | Dust & debris · Debris burst | AI |
| `debris/debris_drawn` | Dust & debris · Debris burst: particles only | no AI |
| `debris/dust` | Dust & debris · Dust burst | AI |
| `liquid/drip` | Liquid · Drips from a point | AI |
| `dissolve/plain` | Dissolve · Crumbles into particles | AI |
| `dissolve/gold` | Dissolve · Gold dust | AI |
| `dissolve/fire` | Dissolve · Burns away | AI |
| `own/point` | Your own effect · At a point | AI |

</details>

## The app (inside ComfyUI)

The template **Element Forge (app)** turns Element Forge into an app in ComfyUI's own **App mode**, the way ComfyUI's
template apps open: no graph to touch, every job goes into ComfyUI's queue, no extra server. In short:

1. **Clip** – a video or a picture from ComfyUI's `input` folder, from your computer, dropped onto the canvas or dragged
   from ComfyUI's Assets library. **Analysis** works out depth, normals and the camera's motion once per clip.
2. **Position & Track** – click where the effect belongs (Shift-click: point B), choose what it follows (point, object,
   scene or screen) and check the track. On a silhouette without texture (all black against a bright wall) a hand that
   crosses the body can be lost by every kind of track; the track check shows it before anything is generated.
3. **Effect** – effect and style, strength, the description (with **Enhance**), Advanced for the emitter. Several
   effects per clip in the strip at the top (**＋ Effect**); each is its own run with its own versions.
4. **Scene & finish** – live on the finished run: light, glow, colour, placement, brightness and depth blur of the clip.
5. **Output** – Quality (Preview or Full), Upscale, the passes (depth, normals and the object's mask, `mask_*.exr`),
   **Save the element** (an AI element on black also goes into the element library, see *Element library*), **Run**, the
   versions (compare, restore the settings, make final, add passes) and **Export** of the comp as you see it.

With several effects on a clip, **Lit by the other effects** (Scene & finish) lets the light of the other effects fall on
this one: smoke next to a flame turns warm where the flame's light reaches it, in the live view and in the export.

The gear at the top of the panel shows this computer's choices (LTX file, INT8 attention, text encoder, text model,
NVIDIA functions, depth model) and every model with its status, size, folder and source. **Depth model** is Video Depth
Anything (Small, Apache-2.0) or, when [ComfyUI-DepthCrafter-Nodes](https://github.com/akatz-ai/ComfyUI-DepthCrafter-Nodes)
is installed, DepthCrafter (clean edges without a fringe, about as calm after Deflicker, much slower: an 81-frame run took 20
instead of 4 minutes on an RTX 2080 Ti; non-commercial licence; it loads about 7.5 GB into `models/depthcrafter` on first use). The clip's analysis keeps the model it was made with; a run takes the kept
depth only when the same model is chosen, otherwise it works the depth out again.

Effects and styles (*AI* = made with LTX, minutes; *no AI* = drawn, fast):

| Effect | Styles |
|---|---|
| Fire | Flame on the object · Short burst · Smoldering ground* |
| Lightning | Between two points · Climbs an object: fine filaments* · Climbs an object: blue arcs* · Climbs an object: drawn (no AI) |
| Sparks | From a moving object* · Burst from a point |
| Smoke | Rises from a point · Rises from a point: drawn (no AI) |
| Magic & energy | Aura around a figure · Aura: drawn (no AI) · Energy between two points* · Energy ball |
| Snow, rain & fireflies | Snow · Rain · Fireflies (no AI) |
| Dust & debris | Debris burst · Debris burst: drawn (no AI) · Dust burst |
| Liquid | Drips from a point |
| Dissolve | Crumbles into particles · Gold dust · Burns away |
| Your own effect | At a point* (describe any element yourself) |

\* experimental: no tested description yet; the app says so before you generate.

The canvas moves like ComfyUI's graph and follows its settings: by default the mouse wheel zooms, dragging empty space
pans, Space-drag and the middle button pan too, `.` fits the clip. The effect's area and the finished result share one
transform box: drag inside to move it, a corner or an edge to size it freely (Shift keeps its shape, Alt sizes from the
centre), just outside a corner of the result to turn it (Shift: 15° steps). Arrow keys and `+`/`−` do the same without
dragging, Delete resets what you clicked; `?` lists every key.

The timeline shows the clip as a filmstrip and the bar of the chosen effect (start, end, fade in and out, *Start here* /
*End here* at the playhead). Advanced adds keyframes for position and brightness. `?` lists the shortcuts.

**How it goes in** (Effect, for effects made with AI at a place in the clip; not for Snow and Rain, the *Climbs an object*
styles or Dissolve) chooses between two ways:

- **Overlay**: the effect is made alone on black and laid over your clip. Light, glow, colour and placement stay
  adjustable afterwards. Best for glowing effects.
- **Inpaint**: the AI repaints that part of your clip with the effect (inpainting). The effect touches
  surfaces and takes on the light of the scene; its light and place are part of the picture. The sentence about the shot
  is written by the text model from the area around the effect when you run (or typed by you); the matching keys per
  effect kind:
  glowing effects are keyed by their colour and added, solid ones (smoke, debris, liquid) are laid over. With the
  light switched off, no light and normals EXR are written, in both modes (the run is shorter; the light pass can be
  added to the run later).
  Effects over the whole frame (snow, rain) are always laid on black: painting needs a place in the clip to follow.
  Effects between two points (lightning or magic between the hands) send the object word *hand* when painted in and the
  word field is empty, because the track of two clicks alone lost the hands in our tests; type another word for other
  objects. In our test runs **Inpaint** worked for sparks from a moving object, smoke, a flame (it starts from the flame made on
  black), lightning and energy between the hands; for most other styles **Overlay** gave the clearer result.

**Quality** (in Output, for effects made with LTX and laid over the clip, except the *Climbs an object* styles and
Dissolve) chooses **Preview (fast)** (the default) or
**Full** (full size with all passes). Preview is half the size, without the light, glow and normals passes, about 2.5 instead of
12 minutes on an RTX 2080 Ti. A finished preview offers **Make version N final (x2)**: LTX's second pass goes on from the
preview's kept latent (latent upscaler x2), so the final keeps the preview's shape and motion and comes as a new version.
Every version keeps its latent, so missing passes can be added afterwards one by one (**Add Light
pass / Glow pass / Normals / All**): they are decoded again from that latent and written into the same run, without
generating anything again. **Dissolve** has its own workflow: *Gold dust* and *Burns away* light the scene from their glowing edge and particles
(light and normals passes, on by default), *Crumbles into particles* does not glow and writes no light. The light controls
appear once a version has a light pass.

The app runs the same graphs as the workflow (`api_workflows/element_forge_app.json`; `element_forge_climb.json` for
lightning that climbs an object, `element_forge_dissolve.json` for **Dissolve**). It needs the custom nodes and models
listed above for the app; when one is missing it says which before you generate.

### Optional: Bonsai 2 as the language model

**Describe what you want** (only with Bonsai: the app sets up an effect from a sentence and the first frame of the clip,
you apply it as one undo step) and the prompt enhancer use PrismML's **Ternary Bonsai 2** with image input. It is loaded
inside ComfyUI's process like any other model: ComfyUI's own models are unloaded first, and the
language model is freed after the answer. Its ternary weights need PrismML's CUDA kernels, so the pack calls PrismML's
llama.cpp libraries in-process (no server, no second program). On an RTX 2080 Ti it writes 33 tokens/s: 3–10 s for
**✦ Enhance**, about 25 s for **Describe what you want** with the picture. Without Bonsai the enhancer uses Gemma 4
E2B (see *Optional models*); the LTX text encoder is not used for this. When both are installed, the gear at the top of
the app panel switches between them; the choice is kept in ComfyUI's settings of this computer. Should ComfyUI's console say `[Bonsai] no
CUDA backend`, the CUDA libraries are missing and the model runs on the CPU (about 20× slower).
Tested on Windows (RTX 2080 Ti) and Linux (cloud GPU, PyTorch with CUDA 13: 66 tokens/s, 2 s for a sentence, 16 s with the
picture). macOS is not tested yet; there the pack uses PrismML's `macos-arm64` or `macos-x64` package (`.dylib`).

The quickest way: in the app, open **Advanced → Effect → Description**. Without Bonsai, a line under **✦ Enhance**
offers **Install Bonsai 2** with the download size (about 7.2 GB on Windows with an NVIDIA card). It names the files
first, then downloads PrismML's package for your system and the model, checks each file against its published sha256,
unpacks the package into the pack's `runtime/` folder and puts the model into `models/LLM`. No restart is needed. The same
from a terminal: `python custom_nodes/comfyui-element-forge/setup_bonsai.py --model` (with the Python of your ComfyUI);
`--dry-run` shows what it would do. Neither installs Python packages. By hand:

1. Put the model and its vision projector into `models/LLM` (e.g. `Ternary-Bonsai-2-27B-PTQ1_0.gguf`,
   `Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf`).
2. Unpack PrismML's llama.cpp release (tag `prism-b10743-adfffbe`) for your system into
   `custom_nodes/comfyui-element-forge/runtime/`, or name its folder in the settings below. The pack checks the library
   version on load.
   - Windows: the `win-cuda-12.4-x64` package (`llama.dll`, `mtmd.dll`, the `ggml*.dll`) plus
     `cudart-llama-bin-win-cuda-12.4-x64` (the CUDA runtime), both into the same folder.
   - Linux: the `linux-cuda` package that matches the CUDA version of your PyTorch (`python -c "import torch;
     print(torch.version.cuda)"`): 13.x → `cuda-13.3`, 12.x → `cuda-12.8`. It brings `libllama.so`, `libmtmd.so` and the
     `libggml*.so`, but no CUDA runtime: the pack loads `libcudart`/`libcublas` of that version from the system or from
     PyTorch's `nvidia` pip packages. With a mismatched package the console says `[Bonsai] no CUDA backend`.
3. Only for other file names or a runtime folder elsewhere: name them in `<ComfyUI user dir>/element-forge/bonsai.json`
   (a workflow can never set these paths). Without it the app uses the two file names above from `models/LLM` and the
   pack's `runtime/` folder:

```json
{"model": "Ternary-Bonsai-2-27B-PTQ1_0.gguf", "mmproj": "Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf",
 "runtime": "", "context": 4096, "keep_seconds": 120}
```

The app keeps the model loaded for `keep_seconds` between requests; it is freed at once when the next ComfyUI job is queued.

## Workflow

`Element Forge.json` is one workflow for every route of the app (see *With the workflow*): element on black or in the
clip (inpaint), point A or the window between A and B, a point, the whole object, the scene or the screen to follow,
particles as guide or start video (or as a finished look without LTX), lightning that climbs an object, dissolve of the
clicked object or of your own painted mask, an element from the library or your own, preview or full quality, NVIDIA
SR + HDR, night, light and glow. Which route runs follows from the effect and style in **EF Element** and the options
you switch on; there are no switches to set by hand.

It writes to `output/element-forge/<run>/`: the comp MP4 (8 bit, dithered, crf 10, a preview) and, with *EXR passes*
on, the scene-linear EXR passes for grading and compositing.

### Your own nodes around it

- **EF Unpack** (Element Forge/Tools) gives the parts of a run as ordinary outputs: plate (sRGB), depth, normals and
  object mask from **EF Shot** and **EF Track**, the element (linear, on black) with its alpha, light, glow and the comp
  from **EF Element** on. Only what is connected is computed.
- **EF Shot** takes a video, frames from other nodes (*images* with *fps*) or a single picture (*picture*, held for
  *still length*).
- **EF Element from Images** turns frames from another generator (with an optional alpha) into an element for
  **EF Place**; it is saved once into the element library and then placed like a generated one. **EF Library
  Element** takes a saved one.
- The compositing tools (**EF Glow**, **EF Depth Light**, **EF Deflicker**, **EF Dither**, **EF Unmult**, **EF MoGe
  Normals**, **EF Save Element**, **EF Load Element**) are under Element Forge/Tools for graphs of your own.

### Particles: which control for which effect

The emitter steers LTX in two ways: as **Guide** (the particle paths as lines or volume for Union Control) or as **start
video** (the rendered particles as the start of the generation at sigma 0.909). Tested with the same graphs; in the
workflow these are the settings of **EF Guide** (*guide*: particles, *guide particles*: the preset) and **EF Particles**:

| Effect (preset) | Works best with | Notes |
|---|---|---|
| sparks | Guide (lines) | long sparks flying off a skate wheel or a hand; as start video only a short burst |
| lightning, energy A-B | Guide, window between A and B | give the window room around both points (e.g. 800×1200), else the bolt is cut at its edge |
| lightning climb (emitter object mask) | Guide or the direct look without LTX; click the thin object and give a word (*thin stick*, *staff*, *snake*; for all sticks of a crown turn on **Object word: all alike objects**) | the charge crawls along the object and jumps from its tips; without LTX thin, jagged bolts; with LTX describe **hair-thin filaments** ("hair-thin, crisp blue-white electric filaments … a few pixels wide, sharp and jagged like fine cracks of light … No glow tube, no plasma beam") - with "lightning arcs" LTX painted a wide, clipped plasma tube along a staff or snake (4.6x the clipped area); a thinner guide line did not change that. On a bright plate (a staff in front of a white wall) the hair-thin filaments almost vanished (bolt in 26 of 81 frames, with "lightning arcs" 62) - there use the direct look or the arcs prompt. In the app: Lightning → *Climbs an object: fine filaments*, *Climbs an object: blue arcs* or *Climbs an object: drawn* (no AI) (workflow `element_forge_climb`) |
| magic dust, line A-B | Guide | a dense glowing band between two hands; lower the amount for a finer band |
| rain | Guide | prompt "many fast bright streaks … no fog"; rain adds light, so it shows on dark plates, hardly on bright ones |
| liquid | Guide, collide = none | a guided stream; with collision the stream bursts at once on the surface below |
| smoke | Guide (volume) | a thin, curling, translucent plume; as start video (sprite "wisp") a denser but blob-like column |
| snow | start video (soft flakes) or Guide with a "heavy snowfall" prompt | start video: clean but sparse, more than ×1 turns into bokeh discs; Guide: dense, with a few dark specks |
| dust burst | start video or Guide (volume) | both work, stays small |
| aura (preset *aura*, emitter object contour) | Guide, on black over the whole figure; the preset sets the depth offset −0.15 | a glowing halo with rising strands behind head and shoulders, the face stays clear; in the inpaint route only glassy streaks, even at start 0.9875; as a look without LTX a glowing lavender envelope with rising wisps just outside the outline (`shell`) |
| fireflies | Guide | soft glowing points across the whole frame, near ones bigger; as start video nothing showed |
| embers | Guide | glowing embers with curved trails from a hand |
| fire (on a hand) | – | the guide gives glowing embers, not flames; use the flame element |
| frost (preset *frost*, emitter object mask) | Guide, Inpaint (the preset starts at 0.9875) | sharp pale blue crystal clusters over the object; prompt *crystals grow along thin branching lines, the stone between them stays clearly visible* – "the whole statue frozen, thick frost" lays a grey glassy veil over it |
| cracks | direct look without LTX, on a hard surface (concrete, a wall) | dark grooves with a lit lower edge that stay on the surface and hide behind what moves in front; with LTX they come out as painted glowing lines or the surface is repainted; on soft ground (a forest path) they read as twigs |
| debris | Guide | chips and a dust cloud burst up where a skate hits the ground; they come out light (white-grey) even with "grey concrete" in the prompt; without LTX the chunks take the colour of the ground where they break off, a little darker (`plate_color`). The chunks are solid, angular fragments that tumble (sprite *chunk*, also in the volume guide); soft flakes with trails had turned into glowing embers with LTX and read as thin streaks without it. **Prompt:** describe a dull, dusty, matte material in daylight ("dull, dusty, sun-lit chunks of broken terracotta brick … matte … in flat daylight"); hot colour words such as "orange-red" on the black background made LTX paint glowing embers |
| own sprite | start video | an own sprite only acts in the start video |

Each style brings the guide it was tested with; **EF Guide** changes it. The generate size is rounded to what LTX takes (32, with a guide or inpaint 64) and a window between A and B is sized from both points. With point B and an **object word** in **EF Track** (e.g. *hand* for both hands) the word is detected again in every frame and up to two objects are followed, so two crossing hands are not lost. With particles on, A and B then hang on the two objects (the nearest points of their outlines), e.g. lightning between both hands; `"ab_on_objects": 0` in *extra* of **EF Particles** turns it off. With one object and an object word, the word also finds the object again after SAM lost it (a fast staff, a thin stick); only objects that look like the clicked one are let in, and only while it is lost; where the word track drops the clicked object and finds nothing, the click-only track fills in (a large surface such as *concrete ground*). *all alike* in **EF Track** takes every such object instead (all sticks of a crown); off, a second hand or person of the same word stays out.

### Element library

Generating an element with LTX is the slow part; placing a saved one skips it. **EF Save Element** keeps a generated
element as a 16-bit RGBA sequence with a manifest in `output/element-forge/elements/<name>/`; **EF Load Element** brings
it back (every frame is checked against the manifest) for any shot. In the app, **Save the element** (Output) does the
same for an AI element made on black, under the run's name; in the workflow *save element* in **EF Export** does it, and
**EF Library Element** into *own element* of **EF Place** places a saved one.

`api_workflows/` holds the graphs the app and the workflow run, in API format for scripting: `element_forge_app.json`,
`element_forge_climb.json`, `element_forge_dissolve.json` and `element_forge.json` (the track check). They take their
values from `element_forge.settings.json`; `element_forge.stages.json` says which of their nodes belong to which EF node.

## Nodes

### In the node list

| Node | Purpose |
|---|---|
| EF Models | which LTX file, attention and text encoder this computer uses (default: the tested INT8 files); without it **EF Element** takes those |
| EF Shot | the clip: a video, frames from other nodes (*images*, *fps*) or one picture (*picture*, *still length*); the depth model and day for night |
| EF Track | where the effect goes and what it follows: point A and B (click into the first frame, Shift-click for B, right-click clears B, or type clip pixels), object word, *follows* (point, object, scene, screen), *all alike*, *follows motion* (with strength and lag), an optional own object mask; the track check shows on the node |
| EF Element | the effect and its style as in the app, how it goes in (overlay or inpaint), strength, the description, when it starts, quality (preview or full), seed; advanced: look, motion and contact words, the whole prompt, the scene sentence, direction, end, the area, soft edge, solid, keep original. Takes the options below. Makes the element (AI, particles or dissolve), which shows on the node |
| EF Place | size, side, depth offset and blend of the element in the clip; *own element* takes one from **EF Library Element** or **EF Element from Images** instead of the generated one; advanced: groups, the inpaint key and blend, *object in front* (the clicked object's mask hides the element wherever the object is, e.g. a person in front of a portal; sharper than the depth edge; in the app: Object → *In front of the effect*), *lock base* (the element's base stays on point A in every frame: a flame on a wick or a blossom without jitter) |
| EF Light & Glow | the light the effect casts on the clip (as the style, on, off; strength) and its glow (as the style, on, off; exposure) |
| EF Export | makes the run: run name, EXR passes, track check; advanced: save element, only check the track, passes, then (make final, add passes) and from run. The comp shows on the node; everything goes to `output/element-forge/<run>/` |

Options (Element Forge/Options) go into **EF Element**. Every value starts at **style default** (numbers −2 or empty), the
style's tested value, and only what you change is passed on:

| Node | Purpose |
|---|---|
| EF Particles | particles on or off, preset, emitter, amount, speed, size, life, direction, spread, follow, seed, pre-roll; advanced: every engine setting (area, gravity, turbulence, drag, collide, sprite, guide style, trail, colour, start video, direct look, latent mask, *extra* as JSON …) |
| EF Guide | what guides the AI: none, the object's shape, a drawn path (a mask, e.g. from Load Image) or particles (with their preset), strength, reach; advanced: prompt addition, source, animation, grow, trail, repeat |
| EF Dissolve | amount, glowing edge, style; advanced: clean plate where the object never leaves, sharper clean plate, the ember and empty-scene prompts, ember strength, carried by motion, *extra* |
| EF LTX Options | sharper ×2, NVIDIA SR + HDR, more room around the element; advanced: black margin, inpaint sigmas, inpaint starts from the element |

Tools (Element Forge/Tools):

| Node | Purpose |
|---|---|
| EF Unpack | the parts of a run as ordinary outputs: plate (sRGB), depth, normals, object mask, element (linear, on black), element alpha, light, glow, comp, fps; only what is connected is computed |
| EF Element from Images | frames of your own (optional alpha) as an element for **EF Place**, saved once into the element library |
| EF Library Element | a saved element for **EF Place** |
| EF Unmult | element on black/white → straight color + alpha, split in linear light (added back it gives exactly the rendered light); on white optionally with background correction and luminance alpha (smoke); optional external matte (e.g. Alpha Gen) as alpha |
| EF Save Element / EF Load Element | keep a generated element as a 16-bit RGBA sequence with manifest; place it again in other shots without generating it again; optional HDR version as half-float EXRs (values above 1), loaded as `hdr_premult_linear` |
| EF Glow | post-process glow in linear light in the spirit of Deep Glow: gaussians half an octave apart from `core` up to half the radius, weighted to 1/r^falloff (2 = inverse square: equal energy in every octave of distance, so the halo really reaches the radius), threshold with knee, tint, aspect, chromatic spread; `core` keeps a strong glow from burning the element white; separate glow pass |
| EF Depth Light | the element lights the plate as a 3D light: point cloud from the depth map at the clip resolution; normals from `normals_image` (MoGe-2 `normal_opengl` in the templates) or, without it, from the depth map smoothed within surfaces (no relief from depth noise, no rim around people; `normals`, `normal_resolution`), inverse-square falloff, Lambert with wrap, screen-space shadows with limited object thickness, relief from the plate (`surface_detail`), light colour; lights spread over the emission (several swarms, long arcs), optional per-pixel element depth; outputs comp, linear light pass and normals (OpenGL camera space: +X right, +Y up, +Z towards the camera, 0.5 + 0.5 n); computed frame by frame (`device`: `auto` computes on ComfyUI's GPU and falls back to the CPU when the GPU is full; `cpu` always on the CPU) |
| EF Deflicker | removes flicker from passes estimated frame by frame: every frame is averaged with its neighbours after aligning them with optical flow measured on the plate (motion stays, a photometric check drops neighbours where the alignment fails); optional level smoothing (light that pumps with a flickering flame) and an edge-aware filter guided by the plate (removes the 14 px patch grid of Depth Anything 3 that shows in the normals, keeps every edge of the image); can swap the cleaned light pass into its comp. Used on the depth before Depth Light and on the light pass; the plate is never changed; frames run in parallel threads (same result) |
| EF Dither | against banding in 8-bit video: a fine triangular noise of about one 8-bit step before Create Video, so smooth dark gradients (light falloff, glow) do not break into steps; the workflows also re-encode the comp video at crf 10 in Save Video, otherwise H.264 removes the noise again. EXR passes are float and need no dither |
| EF MoGe Normals | MoGe-2 normals for Depth Light in one step (the core nodes *Run MoGe Inference* + *Render MoGe Geometry* with the same settings), one batch of frames at a time; keeps only the normal image, so the GPU holds the geometry of one batch instead of the whole clip and nothing stays in ComfyUI's cache for the next job |

### Building blocks

The graphs the EF nodes run are made of these nodes. They are hidden from the node search and the node library, but
workflows that use them still load and run.

| Node | Purpose |
|---|---|
| HDR Merge | real HDR for an element: where the SDR element clips to white, the core is brightened with the result of the LTX SDR-to-HDR IC-LoRA (ACEScg → linear Rec.709, luminance ratio, hue back in the core); edges and alpha stay at full resolution |
| Anchor | base point of the element, removes slow drift, fades out glow below the base; passes an HDR version through with the same shift |
| Track ROI | point track (optical flow, frame to frame with forward-backward check), stabilized crop, mask; when the texture around the point is lost (it left the frame, motion blur) it seeds again in a wider area and goes on with the motion around it instead of failing, and returns to the point's own features as soon as they are back (frames listed as `reseeded_frames` in the track) |
| Mask Track | point track from a per-frame object mask (e.g. SAM3), for fast motion |
| Track: Keep Objects Alike | object mask from a SAM3 video track that re-detects the object word (finds a fast, thin object again after SAM lost it): the clicked object always, later objects only in the frames where they are about as big and as elongated as the clicked one - a word with two meanings ("staff") no longer takes other things along; an object found again where the kept one was counts as the same, and an optional fallback mask (the click-only track) fills frames where nothing is found |
| Free VRAM | unloads all models before a node that moves its own model to the GPU (Video Depth Anything after SAM3 on 11 GB) |
| Clip Frames | keeps only the first frames of the plate before it is decoded (in every template with a plate): a long phone clip no longer fills the RAM – a 69 s 1080p clip needed about 40 GB, trimmed to 121 frames 2.8 GB. It cuts at the time stamps of the frames, so clips that start later than 0 or have a variable frame rate (phone clips) keep all their frames; shorter clips pass unchanged. Keep its `frames` at least as high as those of Frame Step / Track ROI |
| Still Clip | a picture from the input folder as a clip: held for the length you set at 24 fps (16-bit pictures keep their precision); without a picture it passes the video on |
| Save Analysis / Load Analysis | keep the scene analysis of a clip (depth, normals as 16 bit, the camera's motion, MP4 previews) in `output/element-forge/clips/<clip>/`; a later run of the clip with the same frames loads depth and normals instead of computing them |
| Save Track / Load Track | keep the object masks of a track (SAM3) per click, word and mask; a later run or check of the same place loads them instead of tracking again |
| Place Element | element follows a track (position and scale), holdout mask, add/screen/over in linear light; optional edge feather, recolour and density (for smoke); depth placement: with a depth map the element sits at the tracked point's depth plus `depth_offset`, so only nearer parts hide it (in front of / in / behind a hand); a point on a far surface that would hide the element almost completely (a back wall, the sky) puts it in front of that surface; `element_hdr` keeps values above 1 in the linear layer and EXR |
| Motion Tracks (LTX) | the same motion as point tracks for `LTXVDrawTracks` and the LTX motion-track IC-LoRA: one point on the emitter, one short tip point that lags like a spring, optional body points; in the crop of Track ROI / Follow Crop or on its own canvas (`stabilise`). Tested: in a crop where the emitter stands still, the generated flame leans, trails and swings past along the tip point |
| Place Between | element stretched between two tracks (lightning between hands); edges of the element frame fade out; `element_hdr` keeps HDR values (a lightning core above 1) in the layer and EXR |
| Follow Crop | a crop that follows an object mask (SAM3: a hand, a person) through the shot, smoothed, optionally growing with the object, kept inside the plate; scaled for generation or inpainting, and **Place Layer** puts the result back along its track (crop size per frame). For moving hands and people, where the point track of **Track ROI** loses the object |
| Particles | a particle emitter that steers LTX instead of a hand-drawn guide: presets (sparks, grinding sparks, embers, fire, smoke, dust burst, snow, rain, fireflies, magic dust, aura, liquid, lightning, lightning climb, cracks, frost, energy A-B, debris, groups), emitters at point A, along the line A-B (magic between two hands), on a drawing (hung on the track, the image or the object: snapped onto the object's edge and carried with it), an object mask, its contour or its bottom edge (sparks under the wheels; *grinding sparks* spray backwards against the object's motion and arc over the ground), in an area or the whole frame, or as fixed groups in depth (the generated element as a playing sprite per group, hidden behind nearer parts of the scene); gravity, wind, drag, curl-noise swirl, vortex and attraction, life with fade in/out; particles live in the scene (the plate's camera motion is measured) and in depth (Video Depth Anything): nearer ones are bigger and faster, ones behind the scene are left out already, falling ones land, bounce, slide or burst on surfaces. Path forms for lightning (A to B, branching, re-struck; or *lightning climb*: charge climbing the thin parts of the object mask, e.g. the sticks of a crown, from their base to their tips and jumping from tip to tip; short stretches glow dimmer, and a tip where the part goes on behind something nearer, e.g. a hand round a staff, does not jump), growing cracks and rings. Outputs: guide lines or volume for Union Control, point tracks for the motion-track IC-LoRA (`LTXVDrawTracks` format), a soft start video (seed) that LTX turns into the real effect, alpha, region and holdout masks for placing the result, a preview over the plate and a report; the preset's way of placing (rain and snow: *contrast*, visible on dark and bright parts) and its Inpaint start (cracks, frost: from 0.9875); for pros the particles as a **finished look without LTX** (light presets glow, smoke, dust and frost lie over the clip, cracks are shaded as grooves in the surface, own sprites included); optionally carried by the motion in the clip (`motion_carry`: the plate's optical flow takes the flying particles along where something moves, a camera move alone does not); pure NumPy/OpenCV, no extra model |
| Dissolve | an object crumbles along a front into particles in its own colours while the background appears: the front moves with the object (direction relative to it, fractal edge, per-pixel crumble), the particles keep the object's motion (optical flow) and, with `motion_carry`, are carried on by whatever moves under them, rise, swirl and fade, a style (plain; fire = glowing edge and ember tint, with an output that switches LTX embers on; gold dust = the same glow without LTX), a duration that would end after the clip is shortened to fit (the report says so); the background comes from the other frames of the clip (camera motion measured, near frames first, matched to the frame's light), a clean plate (input) only where the object never moves away (colour matched, spots where it still shows the object inpainted, grain added where it is softer than the plate); outputs comp (also without the glow), particles, alpha, emission, object matte, dissolve mask, background, a guide of the glowing parts (for LTX embers; the particles leave it shortly after the dissolve ends) and a report |
| Clean Plate Reference | the input for the LTX Clean Plate IC-LoRA: the object blurred into its surroundings, so a figure that fills the frame is removed instead of kept |
| Clean Plate Crop / Uncrop | the clean plate sharper in the hole: the box around the object in every frame is cut out and generated at about its own resolution (at most the LoRA's 1024 x 576) instead of the whole frame, then put back into the plate |
| Comp To Layer | a finished comp (e.g. the dissolve) as an element pass over its plate: linear, premultiplied, alpha where the comp differs from the plate or the mask is set; over the plate it gives the comp back. The app's dissolve workflow (`api_workflows/element_forge_dissolve.json`) saves it with plate and depth |
| Screen | screen blend of a layer over a base with a gain; optional `band` (e.g. the burning front of a dissolve) outside which the layer is scaled by `outside` (LTX embers only at the edge, no haze over the ash) |
| Particle Settings | fine settings for **Particles** (pro): gravity, swirl and drag as multipliers, fades, depth spread, collision, sprite (dot, flake, puff, streak, spark, soft, chunk = a solid angular fragment that tumbles, or *custom*: your own image or clip, e.g. a library element, as a flipbook over each particle's life), guide style, trails, colour and any other value as JSON; only the changed values are passed on |
| Guide | general guide lines for the LTX Union Control IC-LoRA: strokes drawn on the first frame or the lines of an object mask, still, growing or flickering; lines from an object follow it |
| Guide Choice | one switch for the guide of the AI (particles, drawn path, object shape, none): whether Union Control runs with a guide image and whether the Motion-Track LoRA runs (Follows motion, not with the particle guide) |
| Points | the clicked points A and B of a shot in one place, as point prompts for SAM3 |
| Start At | lets an element begin at a given second of the clip (empty frames before it) |
| Track Preview | checks the track before the long generation: the plate with the tracked points, their path, the window and the object mask |
| Margin Mask | a mask that is 1 inside and 0 in a margin along the border, for a latent noise mask that keeps the border as it is |
| Video Latent Mask | a per-frame mask as LTX's spatial noise mask on a video latent (latent frames x latent cells, union over the 8 pixel frames of each latent frame, optional grow and floor): LTX may change only the masked area, e.g. the particle region when inpainting; works with the LTX guide nodes, where the 4D mask of Set Latent Noise Mask fails |
| Pass Preview (App) | packs the EXR passes of a run (plate, element, light, smoke, alpha, depth, glow) into a small atlas video for playback and two full-size atlas videos for paused frames (`full_size`), with a manifest, for the live post of the Element Forge app; BT.709 full-range YUV computed by the node with a triangular dither at its 8-bit rounding, so dark gradients in light, glow and depth do not band; every EXR is read once (about 76 s for 121 frames at 1080p) |
| Keep Run Latent (App) / Load Run Latent (App) | keep a run's LTX latent in its run folder and load it again, for the app's *Make final* (the second LTX pass goes on from a preview) and *Add passes* (missing passes decoded again without generating) |
| Finish Stack (App, several runs) | the same for several runs of one clip as layers of one comp (the app's Studio): plate graded once, each layer with its own look, start, end and fades, then haze and finish once; EXR + MP4 + `stack.json` |
| In-Plate Guides | guide videos for rendering an element into the plate itself with Union Control: the crop's own edges (Canny) for the control run, the same edges plus the element's lines (e.g. lightning arcs) for the element run, and the lines as a mask for **Effect Layer** |
| Night Grade | day-for-night grade in linear light |
| Save EXR | scene-linear EXR sequences (half/float, alpha) |
| Effect Layer / Place Layer | difference layer of an in-plate generation against a control run (key warm for fire, cold for lightning; optionally only inside the mask or the convex hull of all its parts, e.g. between two hands, and near guide lines, with an HDR core), back into the plate; Place Layer optionally fades the layer out towards the crop border (`edge_feather`), so a tall flame shows no hard cut |
| Comp Preview | quick comp over a plate or checkerboard, blended in linear light; *largest side* shrinks it for long, large clips |

## License

The code of this pack (nodes, app, workflows) is released under the [MIT License](LICENSE).

The models keep their own licenses, which also apply to what you make with them. Read them before you publish or sell
results. Checked at the sources on 22 and 23 October 2026 (not legal advice):

| Model | Used for | License | Notes |
|---|---|---|---|
| LTX-2.5 (INT8 transformer, Gemma text encoder with projection, video and audio VAE, latent upscaler, GGUF Q4) and the LTX IC-LoRAs (Alpha Gen, Clean Plate, Motion Track, Union Control, SDR to HDR, Day to Night) | generating the effects | [LTX-2.x Community License Agreement](https://huggingface.co/Lightricks/LTX-2.5) | free for individuals and companies below 10 million USD annual revenue; keep a copy of the license with the model files; its use restrictions (Attachment A) apply. Outputs you publish must be marked as machine-generated (Attachment A, point 5). Some repositories ask you to log in and accept the terms |
| Gemma 4 E2B ([Comfy-Org/gemma-4](https://huggingface.co/Comfy-Org/gemma-4)) | **✦ Enhance** | Apache-2.0 | – |
| SAM 3.1 ([Comfy-Org/sam3.1](https://huggingface.co/Comfy-Org/sam3.1)) | object masks and tracks | SAM License (Meta) | commercial use allowed; export control and use restrictions apply |
| Video Depth Anything Small ([depth-anything/Video-Depth-Anything-Small](https://huggingface.co/depth-anything/Video-Depth-Anything-Small)) | depth | Apache-2.0 | the Base and Large models offered in the same node are CC-BY-NC-4.0 (non-commercial) |
| MoGe-2 ViT-L normal ([Comfy-Org/MoGe](https://huggingface.co/Comfy-Org/MoGe)) | normals for the light | MIT | – |
| Ternary Bonsai 2 27B ([prism-ml/Ternary-Bonsai-2-27B-gguf](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf)), optional | prompt help | Apache-2.0 | runs with PrismML's llama.cpp (MIT) |

Node packs this pack works with: ComfyUI (GPL-3.0), ComfyUI-Video-Depth-Anything (Apache-2.0), ComfyUI-GGUF (Apache-2.0,
optional) and ComfyUI-LTXVideo, whose code is under the LTX-2 Community License as well.
