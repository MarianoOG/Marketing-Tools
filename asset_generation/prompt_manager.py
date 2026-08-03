"""Prompt composition for the four asset types this pipeline produces.

Pure data plus one function — no I/O, no API calls. A prompt is always assembled
in the same order:

    description -> style clause -> per-type framing rules -> reference clause

The framing rules are the part that must never drift: characters and objects are
*reference sheets* consumed by later animation steps, so their layout (white
background, fixed set of views) is fixed here rather than left to the caller.
"""

from __future__ import annotations

from typing import Literal

AssetType = Literal["character", "object", "location", "scene"]

#: Asset type -> the subdirectory of ``img/`` its renders belong in.
ASSET_DIRS: dict[str, str] = {
    "character": "characters",
    "object": "objects",
    "location": "locations",
    "scene": "scenes",
}

#: Style slug -> the clause injected into the prompt. Every style is an animation
#: style; they differ in medium, linework, palette and lighting. These are written
#: long on purpose — a one-word style label ("anime") leaves the model to average
#: over decades of wildly different work and the output turns to mush.
STYLES: dict[str, str] = {
    "flat_2d": (
        "Modern flat 2D vector animation style: clean uniform-weight outlines, "
        "large areas of flat unshaded colour, simple geometric shape language, a "
        "limited bright palette of six to eight hues, no gradients and no texture."
    ),
    "anime_cel": (
        "Japanese cel-animation style: crisp dark ink outlines of varying weight, "
        "two-tone cel shading with hard-edged shadow shapes, saturated but "
        "naturalistic colour, expressive large eyes, subtle rim light on the "
        "silhouette."
    ),
    "pixar_3d": (
        "Polished 3D CG animated-feature style: soft rounded appealing forms, "
        "subsurface-scattering skin, physically based materials, warm cinematic "
        "three-point lighting with soft shadows, shallow depth of field, high "
        "render fidelity."
    ),
    "stop_motion_clay": (
        "Handmade stop-motion claymation style: visible fingerprints and tool "
        "marks in the plasticine, slightly lumpy hand-sculpted forms, matte clay "
        "surface, practical soft studio lighting with real contact shadows, "
        "tangible miniature-set feel."
    ),
    "watercolor_storybook": (
        "Hand-painted watercolour storybook style: soft wet-on-wet colour washes "
        "with visible pigment blooms and paper grain, loose graphite underdrawing "
        "showing through, muted earthy palette, gentle diffuse light, edges that "
        "fade rather than stop."
    ),
    "comic_ink": (
        "Bold inked comic-book style: heavy brush-inked contours, dense "
        "cross-hatching and spotted blacks for shadow, halftone dot texture in the "
        "midtones, punchy high-contrast primary colours, dramatic directional "
        "lighting."
    ),
    "retro_cartoon_1930s": (
        "1930s rubber-hose cartoon style: bendy limbs without visible joints, "
        "pie-cut eyes and white gloves, thick tapering ink lines, sepia and "
        "cream limited palette with soft film grain and subtle vignetting, "
        "vintage animation-cel look."
    ),
    "pixel_art": (
        "Hand-crafted pixel art style: low resolution grid with large crisp square "
        "pixels and no anti-aliasing, deliberate dithering for gradients, a tight "
        "indexed palette of about sixteen colours, strong readable silhouettes, "
        "16-bit era game-sprite look."
    ),
    "low_poly_3d": (
        "Stylised low-poly 3D style: faceted geometry with visible flat triangular "
        "planes, hard flat-shaded facets and no smoothing, untextured solid colour "
        "materials, clean studio lighting, crisp geometric silhouette."
    ),
    "paper_cutout": (
        "Layered paper cutout animation style: shapes cut from textured coloured "
        "card with visible fibrous torn and scissor-cut edges, distinct stacked "
        "depth layers casting small soft drop shadows onto the layer beneath, matte "
        "paper surface."
    ),
}

#: The invariant part of a character prompt. These renders are turnaround sheets
#: used as identity references for later animation, so the pose and view order
#: must be identical every time.
CHARACTER_FRAMING = (
    "Render this as a character turnaround reference sheet. Pure solid white "
    "seamless background. Full body, head to feet, standing upright in a neutral "
    "relaxed A-pose with the arms held slightly away from the torso and the legs "
    "straight. Show exactly three views of the same character in a single image, "
    "arranged in one horizontal row, left to right: front view, side profile "
    "view, back view. All three views share the same character design, the same "
    "scale, the same height, and the same eye line. Even flat lighting with no "
    "cast shadow on the backdrop. No props, no accessories beyond the described "
    "costume, no scenery, no text, no labels, no borders or panel frames."
)

#: Object sheets mirror the character sheet: same white field, three fixed views,
#: but orthographic along the three axes so modelling and animation can read the
#: full form.
OBJECT_FRAMING = (
    "Render this as an object turnaround reference sheet. Pure solid white "
    "seamless background. Show exactly three orthographic views of the same "
    "object along the three axes in a single image, arranged in one horizontal "
    "row, left to right: front view along the Z axis, side view along the X axis, "
    "top-down view along the Y axis. All three views share the same object "
    "design, scale and lighting. The object is isolated and centred in each view. "
    "Even flat lighting, no cast shadow on the backdrop, no ground plane. No "
    "characters, no people, no hands holding the object, no text, no labels, no "
    "dimension lines, no borders."
)

#: Locations are background plates that characters get composited over later, so
#: the "no people" instruction is repeated several ways on purpose — it is the
#: single constraint these renders most often break.
LOCATION_FRAMING = (
    "Render this as an empty background plate for animation. The environment is "
    "completely unoccupied: no characters, no people, no figures, no crowds, no "
    "animals, and no foreground subject of any kind anywhere in the frame. Wide "
    "establishing view of the space itself with a consistent single-point "
    "perspective and a clear horizon. Light the environment as a usable backdrop, "
    "readable across the whole frame with nothing blown out and nothing crushed "
    "to black. No text, no signage lettering, no watermarks, no borders."
)

#: Scenes are finished frames rather than reference sheets, so the framing is
#: about composition and consistency instead of fixed views.
SCENE_FRAMING = (
    "Render this as a single finished composed frame depicting the situation "
    "described above. Compose it cinematically with a clear focal subject, a "
    "readable staging of every element mentioned, and depth between foreground, "
    "midground and background. Keep the characters, objects and environment "
    "exactly consistent with their reference designs. Unified lighting and colour "
    "grade across the whole frame. No text, no captions, no borders."
)

FRAMING: dict[str, str] = {
    "character": CHARACTER_FRAMING,
    "object": OBJECT_FRAMING,
    "location": LOCATION_FRAMING,
    "scene": SCENE_FRAMING,
}

#: How the reference images are meant to be *used* — and this differs sharply by
#: asset type, so there is one clause per type rather than one shared clause.
#:
#: Characters, objects and locations treat references as **inspiration**: they
#: pull world, palette and mood across so the new asset belongs beside what it
#: was shown, while the style always comes from this prompt's style clause, never
#: from the reference image. Scenes treat references as **authority**: the scene
#: is the composer, so the designs it was handed are facts to reproduce.
REFERENCE_CLAUSES: dict[str, str] = {
    "character": (
        "Reference images are provided as inspiration, not as something to copy. "
        "Do not adopt the art style, rendering, linework or medium of the "
        "reference images — the style is defined by the style description above "
        "and overrides anything seen in the references. If a reference shows "
        "another character, do not reproduce or clone that character: take only "
        "cues such as the world it belongs to, its palette, its costume language "
        "and its level of stylisation, so the new character plausibly lives "
        "alongside it. If a reference shows an object or a place instead, read the "
        "colours, materials, era and mood from it and design a character who "
        "would inhabit that world and use those objects. The described character "
        "above is always the subject; the references only inform it."
    ),
    "object": (
        "Reference images are provided as inspiration, not as something to copy. "
        "Do not adopt the art style, rendering, linework or medium of the "
        "reference images — the style is defined by the style description above "
        "and overrides anything seen in the references. If a reference shows "
        "another object, take only cues such as its materials, wear, construction "
        "language and palette so the new object reads as belonging to the same "
        "world and the same maker, without duplicating it. If a reference shows a "
        "character or a place instead, extract the palette, mood, era and material "
        "vocabulary and design an object that would belong in that world or be "
        "carried and used by that character, scaled and shaped to suit them. The "
        "described object above is always the subject; the references only inform it."
    ),
    "location": (
        "Use the reference images as the source of the world: carry across their "
        "palette, mood, era, architecture, materials and recurring design "
        "elements. Build the described location as a spin-off of that world — a "
        "neighbouring, adjacent or related place, not a reproduction of any place "
        "shown. If a reference shows characters or objects, do not include them in "
        "the frame; instead treat them as the inhabitants this plate must suit, and "
        "build a background they could plausibly stand in or that those objects "
        "would be found in, matched to their scale and their world. The style is "
        "defined by the style description above and overrides the rendering of the "
        "references."
    ),
    "scene": (
        "Use the attached reference images as the authority for this frame. They "
        "are fact, not inspiration: reproduce the identity, design, proportions, "
        "costume, materials and colour palette of every subject they depict "
        "faithfully and consistently. Do not redesign, restyle, simplify or "
        "substitute them — a viewer must recognise each one as the same character, "
        "object and place. Where a reference shows an environment, keep its layout, "
        "architecture and palette as the setting of this frame. Ignore only the "
        "sheet layout of the references themselves (the multiple views and the "
        "blank backdrop); their designs are what carry over."
    ),
}


def build_prompt(
    asset_type: AssetType,
    description: str,
    style: str,
    with_references: bool = False,
) -> str:
    """Compose the full prompt for one asset.

    ``description`` carries everything specific to this asset. For a character,
    object or location that is the subject description; for a scene it is the
    situation being depicted ("the fox hero holds the lantern up in the night
    market") — there is no separate situation argument.

    ``with_references`` appends this asset type's clause from
    :data:`REFERENCE_CLAUSES`; the caller sets it when it is actually attaching
    images. Character, object and location treat references as inspiration;
    scene treats them as authority.
    """
    if asset_type not in FRAMING:
        raise ValueError(
            f"asset_type must be one of {sorted(FRAMING)}, got {asset_type!r}"
        )
    if style not in STYLES:
        raise ValueError(f"style must be one of {sorted(STYLES)}, got {style!r}")
    if not description or not description.strip():
        raise ValueError("description must not be empty")

    parts = [description.strip(), STYLES[style], FRAMING[asset_type]]
    if with_references:
        parts.append(REFERENCE_CLAUSES[asset_type])
    return "\n\n".join(parts)
