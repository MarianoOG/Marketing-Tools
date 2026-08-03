"""Asset image generation via OpenAI (gpt-image-2) and Gemini (Nano Banana 2).

Both providers sit behind one interface. Every render is written under
``img/<asset-type-dir>/`` and the methods return the :class:`Path` written.
Prompts come from :mod:`prompt_manager`; attaching reference images routes
OpenAI through ``images.edit`` and Gemini through multimodal content blocks.

OpenAI emits PNG, Gemini JPEG (the only mime type its API accepts). Bytes are
stored provider-native — transcoding would inflate the file while baking in
artifacts it cannot remove. Output is always 2K.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

from dotenv import load_dotenv
from PIL import Image

from prompt_manager import ASSET_DIRS, REFERENCE_STYLE_SLUG, AssetType, build_prompt

IMG_DIR = Path(__file__).parent / "img"
ENV_PATH = Path(__file__).parent / ".env"

OPENAI_MODEL = "gpt-image-2"
GEMINI_MODEL = "gemini-3.1-flash-image"

AspectRatio = Literal["landscape", "square", "portrait", "16:9", "1:1", "9:16"]
Quality = Literal["low", "medium", "high"]
Provider = Literal["openai", "gemini"]

#: Gemini takes this string directly in `response_format`.
IMAGE_SIZE = "2K"

#: Friendly names -> the ratio strings the Gemini API accepts.
ASPECT_RATIOS: dict[str, str] = {
    "landscape": "16:9",
    "square": "1:1",
    "portrait": "9:16",
    "16:9": "16:9",
    "1:1": "1:1",
    "9:16": "9:16",
}

#: gpt-image-2 takes explicit pixels, not a ratio; both dimensions must be
#: divisible by 16. These are the 2K rows, verified against the live API.
OPENAI_SIZES: dict[str, str] = {
    "1:1": "2048x2048",
    "16:9": "2048x1152",
    "9:16": "1152x2048",
}

#: friendly quality -> (openai `quality`, gemini `thinking_level`). Gemini has no
#: quality field; its dial is `thinking_level`, and gemini-3.1-flash-image 400s on
#: every value except "high". `None` means "send nothing and take the model
#: default" — the only cheap path available today.
QUALITY: dict[str, tuple[Quality, str | None]] = {
    "low": ("low", None),
    "medium": ("medium", None),
    "high": ("high", "high"),
}

#: Extension per format sniffed off the returned bytes.
_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


def save_image(
    data: bytes,
    filename: str,
    asset_type: AssetType,
    dpi: int | None = None,
) -> Path:
    """Write image bytes into ``img/<asset-type-dir>/`` and return the path.

    ``filename`` is a stem: the extension comes from the actual format of
    ``data``, so a JPEG never ends up named ``.png``. ``dpi`` tags the file with
    a physical resolution (300 for print) — without one a printer guesses.
    """
    stem = Path(filename).stem
    if not stem or any(sep in filename for sep in ("/", "\\")):
        raise ValueError(f"filename must be a bare name, got {filename!r}")
    if asset_type not in ASSET_DIRS:
        raise ValueError(
            f"asset_type must be one of {sorted(ASSET_DIRS)}, got {asset_type!r}"
        )

    image = Image.open(BytesIO(data))
    image_format = image.format or "PNG"
    directory = IMG_DIR / ASSET_DIRS[asset_type]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}{_EXTENSIONS.get(image_format, '.png')}"

    if dpi is None:
        path.write_bytes(data)
    else:
        # quality="keep" reuses the source quantization tables, so tagging a JPEG
        # with DPI does not re-compress it. Ignored for PNG (lossless).
        image.save(path, format=image_format, dpi=(dpi, dpi), quality="keep")
    return path


def _resolve(aspect_ratio: str, quality: str) -> tuple[str, Quality, str | None]:
    """Validate the friendly arguments -> (ratio, openai quality, thinking_level)."""
    ratio = ASPECT_RATIOS.get(aspect_ratio)
    if ratio is None:
        raise ValueError(
            f"aspect_ratio must be one of {sorted(ASPECT_RATIOS)}, got {aspect_ratio!r}"
        )
    if quality not in QUALITY:
        raise ValueError(f"quality must be one of {sorted(QUALITY)}, got {quality!r}")
    return (ratio, *QUALITY[quality])


def _as_paths(reference_images: Sequence[Path | str] | None) -> list[Path]:
    """Normalise the reference argument and fail early on a missing file."""
    paths = [Path(p) for p in reference_images or ()]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"reference image not found: {path}")
    return paths


class AssetImageGenerator:
    """Generate character, object, location and scene images from both providers."""

    def __init__(
        self,
        gemini_api_key: str | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        load_dotenv(ENV_PATH)
        self._gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self._openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self._gemini_client = None
        self._openai_client = None

    # Clients are built lazily so a missing key only breaks its own provider.
    @property
    def gemini(self):
        if self._gemini_client is None:
            if not self._gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is not set (see asset_generation/.env)")
            from google import genai

            self._gemini_client = genai.Client(api_key=self._gemini_api_key)
        return self._gemini_client

    @property
    def openai(self):
        if self._openai_client is None:
            if not self._openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not set (see asset_generation/.env)")
            from openai import OpenAI

            self._openai_client = OpenAI(api_key=self._openai_api_key)
        return self._openai_client

    def _openai_bytes(
        self, prompt: str, ratio: str, quality: Quality, references: list[Path]
    ) -> bytes:
        if references:
            # References go through `images.edit`. No `input_fidelity`: gpt-image-2
            # rejects it outright, so reference adherence rests on the prompt's
            # REFERENCE_CLAUSE alone on this provider.
            handles = [path.open("rb") for path in references]
            try:
                result = self.openai.images.edit(
                    model=OPENAI_MODEL,
                    image=handles,
                    prompt=prompt,
                    size=OPENAI_SIZES[ratio],
                    quality=quality,
                    output_format="png",
                )
            finally:
                for handle in handles:
                    handle.close()
        else:
            result = self.openai.images.generate(
                model=OPENAI_MODEL,
                prompt=prompt,
                size=OPENAI_SIZES[ratio],
                quality=quality,
                output_format="png",
            )

        if not result.data or not result.data[0].b64_json:
            raise RuntimeError("OpenAI returned no image data")
        return base64.b64decode(result.data[0].b64_json)

    def _gemini_bytes(
        self, prompt: str, ratio: str, thinking_level: str | None, references: list[Path]
    ) -> bytes:
        # Without references the input is a plain string; with them it becomes one
        # text block followed by one image block per reference.
        model_input: str | list[dict] = prompt
        if references:
            model_input = [{"type": "text", "text": prompt}]
            for path in references:
                model_input.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(path.read_bytes()).decode(),
                        "mime_type": mimetypes.guess_type(path.name)[0] or "image/png",
                    }
                )

        # `thinking_level` is only sent for quality="high" — omitted entirely
        # otherwise, so it has to be unpacked rather than passed as None. Typed
        # loosely because `create` is heavily overloaded and a narrower dict makes
        # the checker match the unpacked values against every other parameter.
        #
        # The SDK also types a `delivery` field, but the API rejects both of its
        # values; the response comes back as inline base64 either way.
        config: dict[str, Any] = {}
        if thinking_level:
            config["generation_config"] = {"thinking_level": thinking_level}

        interaction = self.gemini.interactions.create(
            model=GEMINI_MODEL,
            input=model_input,
            # `response_format` supersedes the deprecated generation_config.image_config.
            response_format={
                "type": "image",
                "aspect_ratio": ratio,
                "image_size": IMAGE_SIZE,
                "mime_type": "image/jpeg",  # The only image mime type the API accepts.
            },
            **config,
        )

        # Terminal success is reported as "completed" (and has been "succeeded"),
        # so image data — not the status — is the real success test.
        output = getattr(interaction, "output_image", None)
        if output is None or not output.data:
            status = getattr(interaction, "status", None)
            raise RuntimeError(f"Gemini returned no image data (status={status})")
        return base64.b64decode(output.data)

    def _render(
        self,
        provider: Provider,
        prompt: str,
        filename: str,
        asset_type: AssetType,
        aspect_ratio: AspectRatio,
        quality: Quality,
        reference_images: Sequence[Path | str] | None,
    ) -> Path:
        """Call one provider with a finished prompt, save the bytes, return the path."""
        ratio, openai_quality, thinking_level = _resolve(aspect_ratio, quality)
        references = _as_paths(reference_images)
        if provider == "openai":
            data = self._openai_bytes(prompt, ratio, openai_quality, references)
        else:
            data = self._gemini_bytes(prompt, ratio, thinking_level, references)
        return save_image(data, filename, asset_type)

    def generate_openai(
        self,
        prompt: str,
        filename: str,
        asset_type: AssetType,
        aspect_ratio: AspectRatio = "landscape",
        quality: Quality = "low",
        reference_images: Sequence[Path | str] | None = None,
    ) -> Path:
        """Generate one image with gpt-image-2 and save it."""
        return self._render(
            "openai", prompt, filename, asset_type, aspect_ratio, quality, reference_images
        )

    def generate_gemini(
        self,
        prompt: str,
        filename: str,
        asset_type: AssetType,
        aspect_ratio: AspectRatio = "landscape",
        quality: Quality = "low",
        reference_images: Sequence[Path | str] | None = None,
    ) -> Path:
        """Generate one image with Gemini 3.1 Flash Image and save it."""
        return self._render(
            "gemini", prompt, filename, asset_type, aspect_ratio, quality, reference_images
        )

    def generate_both(
        self,
        prompt: str,
        filename: str,
        asset_type: AssetType,
        aspect_ratio: AspectRatio = "landscape",
        quality: Quality = "low",
        reference_images: Sequence[Path | str] | None = None,
    ) -> dict[str, Path | Exception]:
        """Generate the same prompt with both providers, concurrently.

        Returns ``{"openai": Path, "gemini": Path}``. A provider that fails puts
        its exception in its slot rather than raising, so one failure never
        discards the other provider's image.
        """
        stem = Path(filename).stem
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                provider: pool.submit(
                    self._render,
                    provider,
                    prompt,
                    f"{stem}_{provider}",
                    asset_type,
                    aspect_ratio,
                    quality,
                    reference_images,
                )
                for provider in ("openai", "gemini")
            }

        results: dict[str, Path | Exception] = {}
        for provider, future in futures.items():
            try:
                results[provider] = future.result()
            except Exception as exc:  # surfaced per-provider, not raised
                results[provider] = exc
        return results

    def generate_asset(
        self,
        asset_type: AssetType,
        name: str,
        description: str,
        style: Optional[str],
        reference_images: Sequence[Path | str] | None = None,
        aspect_ratio: AspectRatio = "landscape",
        quality: Quality = "low",
        provider: Literal["openai", "gemini", "both"] = "both",
    ) -> Path | dict[str, Path | Exception]:
        """Build the prompt for ``asset_type`` and render it.

        Files are named ``{name}_{style}_{uuid8}_{provider}`` inside the asset
        type's folder, so an openai run never overwrites a gemini one and a
        listing stays readable. ``style=None`` — the styleless mode that reads its
        look off the references — is written as
        :data:`~prompt_manager.REFERENCE_STYLE_SLUG`, since the slot has to hold
        something for the gallery to group on. The uuid is minted once per call —
        re-rendering the same name and style keeps every attempt instead of
        replacing the previous one, and a ``provider="both"`` run shares one uuid
        across its two images so the pair stays recognisable as a single
        generation.

        ``provider="both"`` returns the per-provider dict (it appends the provider
        suffix itself); a single provider returns its :class:`Path`.
        """
        references = _as_paths(reference_images)
        prompt = build_prompt(
            asset_type, description, style, with_references=bool(references)
        )
        style_slug = style or REFERENCE_STYLE_SLUG
        uid = uuid.uuid4().hex[:8]
        if provider == "both":
            return self.generate_both(
                prompt,
                f"{name}_{style_slug}_{uid}",
                asset_type,
                aspect_ratio,
                quality,
                references,
            )
        if provider in ("openai", "gemini"):
            return self._render(
                provider,
                prompt,
                f"{name}_{style_slug}_{uid}_{provider}",
                asset_type,
                aspect_ratio,
                quality,
                references,
            )
        raise ValueError(
            f"provider must be 'openai', 'gemini' or 'both', got {provider!r}"
        )

    # Per-type entry points. They differ only in the asset type they pass through
    # and share every keyword argument of :meth:`generate_asset`.

    def generate_character(self, name: str, description: str, style: Optional[str], **kwargs) -> Path | dict[str, Path | Exception]:
        """Turnaround sheet: front, side and back on white."""
        return self.generate_asset("character", name, description, style, **kwargs)

    def generate_object(self, name: str, description: str, style: Optional[str], **kwargs) -> Path | dict[str, Path | Exception]:
        """Turnaround sheet: front and side orthographic views on white."""
        return self.generate_asset("object", name, description, style, **kwargs)

    def generate_location(self, name: str, description: str, style: Optional[str], **kwargs) -> Path | dict[str, Path | Exception]:
        """Empty background plate — no characters anywhere in the frame."""
        return self.generate_asset("location", name, description, style, **kwargs)

    def generate_scene(self, name: str, description: str, style: Optional[str], **kwargs) -> Path | dict[str, Path | Exception]:
        """Finished frame. ``description`` is the situation being depicted; pass
        the character/object/location sheets as ``reference_images``."""
        return self.generate_asset("scene", name, description, style, **kwargs)
