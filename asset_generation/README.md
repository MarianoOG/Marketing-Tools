# Asset Generation

Generate the four asset types an animation pipeline needs — **characters**,
**objects**, **locations** and **scenes** — from two providers behind one
interface: OpenAI (`gpt-image-2`) and Gemini (`gemini-3.1-flash-image`, "Nano
Banana 2").

- `prompt_manager.py` — pure prompt composition: styles, per-type framing rules,
  reference clauses. No I/O.
- `generation.py` — API calls and file writing.
- `Home.py` + `pages/` — a Streamlit UI over both: browse the library, generate
  new assets, download and delete. `shared/` holds its state, file-scanning
  helpers and the background job runner; neither core module imports Streamlit.

## Setup

```bash
source .venv/bin/activate
pip install -r asset_generation/requirements.txt
```

Fill in `asset_generation/.env` (gitignored):

```env
GEMINI_API_KEY=...
OPENAI_API_KEY=...
```

## The app

```bash
cd asset_generation && streamlit run Home.py
```

**Asset Library** (`Home.py`) lists everything under `img/`, filtered by type,
style and provider, with a download and a delete behind each thumbnail. There is
no database — the file tree is the store, read on demand into `st.cache_data`
and re-scanned whenever a file is written or removed.

**Create** (`pages/1_Create.py`) is the same arguments as `generate_asset`, as a
form. References work differently per type, mirroring the module:

- **character / object / location** — upload reference images. They are written
  to a temporary directory for the length of the call and **never saved** into
  `img/`.
- **scene** — multi-select any number of existing characters, objects and
  locations from the library; their files are passed straight through.

There is no results panel: finishing a generation sends you back to the library,
which already lists the newest asset first.

### Generations run in the background

A render costs real money, so `shared/jobs.py` runs it on a thread pool that
outlives the script run that started it (see the module docstring for why the
process-wide registry, rather than session state, is the source of truth):

- Clicking **Generate** locks the whole form through the button's `on_click`
  callback, which fires *before* the rerun paints. One click is one generation —
  a second click cannot start a second paid call.
- Leaving the page, or closing the tab, does not cancel anything. The image is
  still written into `img/`, and the library refreshes itself when it lands —
  including in a session that never submitted the job.
- The library shows an "N generations in progress" banner while any job is
  running, and drops the new tile in as soon as it finishes.
- A failure keeps you on **Create** with the error under the form and your
  inputs intact. With `provider="both"`, one provider failing still counts as a
  success — the other image is saved and you are redirected — but the dead
  provider is named in a warning on the library.

## Usage

```python
from generation import AssetImageGenerator, save_image

gen = AssetImageGenerator()

# One asset per type. Returns {"openai": Path, "gemini": Path} by default.
gen.generate_character("fox_hero", "a lanky fox in a patched coat", "flat_2d")
gen.generate_object("lantern", "a dented brass lantern", "low_poly_3d")
gen.generate_location("night_market", "a cramped canal-side night market", "watercolor_storybook")

# A single provider returns the Path directly.
path = gen.generate_character("fox_hero", "...", "flat_2d", provider="openai")

# Scenes compose the sheets: description is the situation, references are facts.
gen.generate_scene(
    "market_night",
    "the fox hero holds the lantern up in the night market",
    "anime_cel",
    reference_images=[
        "img/characters/fox_hero_flat_2d_3f9c1a02_openai.png",
        "img/objects/lantern_low_poly_3d_b71e4d58_openai.png",
    ],
    quality="high",
)
```

All four wrappers delegate to `generate_asset(asset_type, name, description,
style, ...)` and share its keyword arguments: `reference_images`,
`aspect_ratio`, `quality`, `provider`.

Files land in `img/<asset-type-dir>/` (`characters/`, `objects/`, `locations/`,
`scenes/`) named `{name}_{style}_{uuid8}_{provider}`, so an OpenAI run never
overwrites its Gemini counterpart. The extension comes from the actual returned
bytes.

The uuid is minted once per `generate_asset` call, so **re-rendering the same
name and style keeps every attempt** instead of replacing the previous one —
that is what makes iterating on a description possible. A `provider="both"` run
shares one uuid across its two images, so the pair stays recognisable as a
single generation.

`provider="both"` never raises for a provider failure: the failing provider's
slot holds the exception instead, so one outage doesn't discard the other image.

To write bytes yourself — or to re-tag a file for print — call `save_image(data,
filename, asset_type, dpi=300)`.

## Asset types

| Type | What it renders | References are treated as |
| --- | --- | --- |
| `character` | Turnaround sheet: front, side, back on white | inspiration |
| `object` | Turnaround sheet: three orthographic views on white | inspiration |
| `location` | Empty background plate, no figures anywhere | inspiration |
| `scene` | Finished composed frame | **authority** — reproduce faithfully |

Characters, objects and locations pull world, palette and mood from their
references while the style always comes from the `style` argument. Scenes treat
references as designs to reproduce exactly. See `REFERENCE_CLAUSES` in
`prompt_manager.py`.

## Parameters

### `style`

Ten animation styles, keys of `STYLES` in `prompt_manager.py`: `flat_2d`,
`anime_cel`, `pixar_3d`, `stop_motion_clay`, `watercolor_storybook`,
`comic_ink`, `retro_cartoon_1930s`, `pixel_art`, `low_poly_3d`, `paper_cutout`.

Each expands to a long clause rather than a one-word label — "anime" alone
leaves the model averaging over decades of unrelated work.

### `aspect_ratio` — default `landscape`

| Friendly name | Ratio  | OpenAI pixels | Gemini pixels |
|---------------|--------|---------------|---------------|
| `landscape`   | `16:9` | 2048x1152     | 2752x1536     |
| `square`      | `1:1`  | 2048x2048     | 2048x2048     |
| `portrait`    | `9:16` | 1152x2048     | 1536x2752     |

Either spelling works. The two providers disagree on what "2K" means: OpenAI
takes explicit pixels (both dimensions divisible by 16, see `OPENAI_SIZES`),
Gemini takes the ratio and picks its own — the numbers above were measured off
live responses, not documented.

Output is fixed at 2K: enough for TikTok/Shorts (1080x1920), and marginal-to-fine
for A5 print at 300 DPI. A4 at 300 DPI (2480x3508) would need 4K, which is
slower, experimental on OpenAI above 2560x1440, and unused downstream.

### `quality` — default `low`

| `quality`       | OpenAI `quality` | Gemini `thinking_level`  |
|-----------------|------------------|--------------------------|
| `low` (default) | `low`            | not sent (model default) |
| `medium`        | `medium`         | not sent (model default) |
| `high`          | `high`           | `high`                   |

Gemini has no `quality` field — its cost/quality dial is `thinking_level`, which
controls how much the model reasons before the final render.

In practice `gemini-3.1-flash-image` rejects every `thinking_level` except
`high`: passing `minimal` returns *"allowed values are: high, low"*, and passing
`low` then returns *"Thinking level LOW is not supported for this model"*. So
below `quality="high"` the module sends no `thinking_level` at all and takes the
model default — the only cheap path available. If Google opens up the lower
rungs later, add them to `QUALITY` in `generation.py`.

## File format

**OpenAI returns PNG, Gemini returns JPEG.** That asymmetry is an API
constraint, not a choice: the Gemini Interactions API accepts exactly one image
mime type, `image/jpeg`. Bytes are written provider-native — transcoding the
JPEG to PNG would inflate the file 3-5x while baking in artifacts it cannot
remove.

Why PNG where it's available: it's lossless, so flat colour, line art and any
text the model renders survive intact, and there's no generational loss when the
image is later cropped, composited, or used as the first frame of a video model.

For printing, pass `dpi=300` to `save_image`. PNG carries no DPI tag by default,
and without one the printer guesses the physical size. Tagging a JPEG this way
uses Pillow's `quality="keep"`, so it is not re-compressed.

For social delivery, upload the master directly — TikTok and Shorts re-encode
everything anyway, and a lossless source gives their encoder the best input.
