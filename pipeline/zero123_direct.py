"""
Direct Zero123 inference — bypasses ComfyUI entirely.
Loads the stable_zero123 checkpoint and runs view synthesis directly.

Usage:
    python -m pipeline.zero123_direct --input bakeoff/zero123_seeds/front_seed.png --azimuth 90
    python -m pipeline.zero123_direct --input front.png --all-views
"""

import argparse
import torch
import numpy as np
from pathlib import Path
from PIL import Image

CHECKPOINT = "F:/AI-Models/ComfyUI/models/checkpoints/stable_zero123.ckpt"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

DIRECTIONS = [
    ("front", 0),
    ("front_right", 45),
    ("right", 90),
    ("back_right", 135),
    ("back", 180),
    ("back_left", -135),
    ("left", -90),
    ("front_left", -45),
]


def load_zero123_pipeline():
    """Load Stable Zero123 using the diffusers pipeline."""
    from diffusers import StableDiffusionImageVariationPipeline
    import torch

    # Load the raw state dict
    print("Loading checkpoint...")
    sd = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    if "state_dict" in sd:
        sd = sd["state_dict"]

    # Stable Zero123 is based on SD 2.1 with custom conditioning
    # Use the ComfyUI-compatible approach: load via diffusers
    from diffusers import DiffusionPipeline

    pipe = DiffusionPipeline.from_pretrained(
        "stabilityai/stable-zero123",
        custom_pipeline="zero123",
        torch_dtype=torch.float16,
    )
    pipe = pipe.to(DEVICE)
    return pipe


def load_zero123_manual():
    """Load Zero123 manually from the checkpoint — no diffusers dependency."""
    import sys
    sys.path.insert(0, "F:/AI-Models/ComfyUI-runtime")

    from comfy.utils import load_torch_file
    from comfy.model_detection import unet_prefix_from_state_dict, detect_unet_config, model_config_from_unet_config
    from comfy import model_management, model_base, model_patcher
    import comfy.ops
    import comfy.sd
    import comfy.clip_vision

    print("Loading checkpoint via ComfyUI internals...")
    sd = load_torch_file(CHECKPOINT)

    # Stash cc_projection BEFORE anything else
    cc_weight = sd["cc_projection.weight"].clone()
    cc_bias = sd["cc_projection.bias"].clone()
    print(f"  cc_projection stashed: weight {cc_weight.shape}, bias {cc_bias.shape}")

    # Detect model config
    prefix = unet_prefix_from_state_dict(sd)
    print(f"  UNet prefix: {prefix}")

    unet_config = detect_unet_config(sd, prefix)
    model_config = model_config_from_unet_config(unet_config, sd)
    print(f"  Model config: {type(model_config).__name__}")

    # Load clip vision
    clip_vision_prefix = model_config.clip_vision_prefix
    clipvision = comfy.clip_vision.load_clipvision_from_sd(sd, clip_vision_prefix, True)
    print(f"  CLIP Vision loaded, prefix: {clip_vision_prefix}")

    # Check if cc_projection survived
    cc_in_sd = "cc_projection.weight" in sd
    print(f"  cc_projection still in sd after clip load: {cc_in_sd}")

    # Create the model with stashed weights
    load_device = model_management.get_torch_device()
    unet_dtype = torch.float16
    model_config.set_inference_dtype(unet_dtype, None)

    model = model_base.Stable_Zero123(
        model_config,
        device=load_device,
        cc_projection_weight=cc_weight,
        cc_projection_bias=cc_bias,
    )
    print(f"  Stable_Zero123 model created")

    # Load weights
    model.load_model_weights(sd, prefix)
    print(f"  Weights loaded")

    # Load VAE
    vae_sd = {k.replace("first_stage_model.", ""): v for k, v in sd.items() if k.startswith("first_stage_model.")}
    vae = comfy.sd.VAE(sd=vae_sd)
    print(f"  VAE loaded")

    patcher = model_patcher.ModelPatcher(model, load_device=load_device, offload_device=torch.device("cpu"))

    return patcher, clipvision, vae


def generate_view(patcher, clipvision, vae, input_image, azimuth, elevation=5.0):
    """Generate a single rotated view."""
    import sys
    sys.path.insert(0, "F:/AI-Models/ComfyUI-runtime")
    import comfy.sample
    import comfy.samplers
    import comfy.utils

    # Prepare image
    img = input_image.convert("RGB").resize((256, 256))
    img_np = np.array(img).astype(np.float32) / 255.0
    img_tensor = torch.from_numpy(img_np).unsqueeze(0)  # [1, H, W, 3]

    # CLIP Vision encode
    clip_output = clipvision.encode_image(img_tensor)

    # Zero123 conditioning
    # The conditioning includes the CLIP embedding + camera params
    tokens = clip_output.last_hidden_state

    # Build conditioning with camera embedding
    import math
    azimuth_rad = math.radians(azimuth)
    elevation_rad = math.radians(elevation)

    camera_params = torch.tensor([[elevation_rad, azimuth_rad, 0.0]], dtype=torch.float32)

    # Concatenate CLIP tokens with camera params for cross attention
    positive = [[tokens, {"concat_latent_image": vae.encode(img_tensor[:, :, :, :3]), "camera": camera_params}]]
    negative = [[torch.zeros_like(tokens), {}]]

    # Generate
    latent = torch.zeros([1, 4, 32, 32])
    samples = comfy.sample.sample(
        patcher, noise=torch.randn_like(latent),
        positive=positive, negative=negative,
        cfg=5.0, sampler_name="euler", scheduler="sgm_uniform",
        steps=20, latent_image=latent,
        denoise=1.0,
    )

    # Decode
    decoded = vae.decode(samples)
    img_out = decoded[0].cpu().numpy()
    img_out = (img_out * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img_out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input image path")
    parser.add_argument("--azimuth", type=float, help="Single azimuth angle")
    parser.add_argument("--all-views", action="store_true", help="Generate all 8 views")
    parser.add_argument("--output", default="bakeoff/zero123_direct", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_image = Image.open(args.input)
    print(f"Input: {args.input} ({input_image.size})")

    # Load model
    patcher, clipvision, vae = load_zero123_manual()

    if args.all_views:
        for name, az in DIRECTIONS:
            print(f"\n  Generating {name} (azimuth {az})...")
            result = generate_view(patcher, clipvision, vae, input_image, az)
            result.save(str(out_dir / f"{name}.png"))
            print(f"  Saved {name}.png")
    elif args.azimuth is not None:
        print(f"\n  Generating view at azimuth {args.azimuth}...")
        result = generate_view(patcher, clipvision, vae, input_image, args.azimuth)
        result.save(str(out_dir / "output.png"))
        print(f"  Saved output.png")
    else:
        print("Specify --azimuth or --all-views")


if __name__ == "__main__":
    main()
