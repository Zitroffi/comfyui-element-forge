# Licenses

[README](../README.md) · [Setup](setup.md) · [Usage](usage.md) · [Nodes](nodes.md)

The code of this pack (nodes, app, workflows) is released under the [MIT License](../LICENSE).

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

## Brand artwork

The wordmark uses Montserrat. Its [SIL Open Font License](assets/branding/Montserrat-OFL.txt) is included for attribution; no font installation is needed to display the logos.
