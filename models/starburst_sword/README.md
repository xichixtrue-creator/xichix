# Starburst Blade

The fiery sword from your effects sheet (item 3), built in Blender and set up as a
Roblox tool. It keeps the reference's silhouette and layout, but it is drawn entirely
from glowing energy, so it reads as a legendary energy weapon and not as a solid model.
The sheet's other items (the darts, ground flames, the starburst impact and the portal
swirl) became its effects.

![reference vs model](previews/compare_reference.png)

| Made of energy | The blended circles | Special attack |
| --- | --- | --- |
| ![hero](previews/hero.png) | ![star](previews/star_detail.png) | ![special](previews/vfx_special.png) |

## How it matches the reference

The reference sword was rotated upright around its star and measured. Every outline
in `blender/build_starburst.py` comes from that, at 0.004 studs per reference pixel, so
the sword is 4.5 studs long.

- **Blade:** a 748 px needle that swells into a flame-shaped leaf near the star. It has a
  yellow-white core, an orange band, an orange-brown rim on one edge, and a red band plus
  a dark crimson band with white sparkles on the other edge.
- **Star guard:** a dark eye inside **two energy circles that blend into each other** (one round
  the eye, one round the top of the handle). It has seven spikes at the measured angles and
  lengths, flame petals between them, and four curling **red swirl** ribbons.
- **Handle:** a 382 px tapering spike with dark red edges, an orange band and a thin yellow centre line.

## Made of energy, not a model

The meshes are only a faint glow underneath (`Config.VFX.MeshTransparency = 0.8`). Everything you
see is camera-facing beams and particles that add light, so the sword looks like one flowing effect
from every angle.

**The blended circles** are one energy structure, not two rings placed next to each other:

- **One stream:** a single closed stream of energy runs anticlockwise round the top circle, crosses
  the junction, runs clockwise round the bottom circle and crosses back. The two crossings form an X
  where the circles meet. The stream's glowing body is a ring of smoothly curved beams. A wave of
  light keeps running round it.
- **Moving light:** three bright light trails chase each other along the stream, braiding as they go
  and shedding sparkle dust.
- **Soft rings:** each circle also has soft energy rings that slowly spin and breathe. Their glows
  overlap, so there is no seam or gap between the circles.
- **The junction:** where the circles meet is a white-hot core, the brightest point on the sword.
  Energy fragments fly off it, and an energy ring pulses outward from it now and then.
- **The eye:** a dark eye sits in the top circle, melting into the glow with no hard edge.

**The rest of the sword:**

- **Blade and handle:** camera-facing beams painted from the measured reference
  (`fx_bladepaint.png`, `fx_handlepaint.png`), with energy streaks scrolling up through them and a
  white-hot core line.
- **Spikes:** beams of light (white core, gold and orange body, glowing red edge) that flicker like
  live energy.
- **Particles:**
  - soft energy wisps curl off the blade and dissolve;
  - embers rise and sparkles twinkle;
  - a ForceField heat shimmer wraps the blade;
  - fiery darts shoot off the spikes now and then.
- **Ribbons:** red swirl trails keep tracing the reference's ribbons outward from the star.

## Effects

- **Swing:** a fire trail with dark rims and a soft glow trail, plus a painted crescent slash. The slash is
  built from beam segments, with a yellow core, orange and red bands and a dark rim. Sparks and darts fly off the tip.
- **Hit:** a dark-eyed starburst with a hot flash, sparks, embers and darts (sheet item 3).
- **Special (E):**
  - **Charge:** a spinning swirl gathers at the star.
  - **Strike:** a giant streak hits from the sky into a huge starburst. A dark starry portal with
    a fiery rim and swirl opens behind it (sheet item 4).
  - **Fire:** flames burst up from the ground (sheet item 2), with darts flying out.
  - **Screen:** a warm screen flash, and camera shake for the attacker.

## Install in Roblox Studio

1. **Import 3D**: `export/StarburstSword.fbx` (it becomes a model called `StarburstSword`).
2. **Import 3D**: `export/StarburstVFX.fbx`. This brings in all the effect textures.
3. **Model** tab > **Run Script** > `roblox/Installer.lua` (or paste it into View > Command Bar).
4. Press Play. *Starburst Blade* is in your backpack: click to slash, press **E** (gamepad Y / the
   on-screen button on mobile) for the special.

The installer reads marker cubes in the import, so the size and orientation come out right
whatever units the importer used. It puts:

- the Tool in **StarterPack**, with a copy in **ServerStorage**;
- the scripts in `ReplicatedStorage.StarburstSword`, `ServerScriptService.StarburstServer` and
  `StarterPlayerScripts.StarburstClient`.

Running it again updates the scripts and keeps your `Config`.

**Tip:** add a `BloomEffect` to Lighting for the strongest glow.

## Settings

Everything is in `ReplicatedStorage.StarburstSword.Config`:

- **Colours:** the colour of every glowing part.
- **Combat:** damage, ranges and cooldowns.
- **Controls and feel:** the special attack key, slash angles, sounds and animations.
- **Textures:** overrides for any effect texture.
- **Look:** `MeshTransparency` (1 = effects only, 0 = solid meshes).
- **The figure-8 stream:** `Figure8`, `FlowSpeed`, `FlowStrands`, `FlowLifetime`, `FlowWidth`.
- **Idle extras:** the swirl speed, width and length, the darts, and the screen flash and shake.

A `Config` kept from an older install still works: any new setting it lacks uses its default.

To resize the sword, change `SWORD_SCALE` at the top of `Installer.lua` and run it again.

## Hooking it into Pop or Drop

- `ReplicatedStorage.StarburstSword.SwordHit` (a BindableEvent) fires on the server for every hit,
  with `(player, hitInstance, damage, isSpecial)`.
- Tag balloons or anything else **`SwordHittable`** with CollectionService and the sword hits them too.
- Set `Config.Combat.DamageHumanoids = false` to handle damage yourself.

The Mo Feng Blade (`models/sword`) is a separate package, so both swords work in the same game.

## Files

| File | What it is |
| --- | --- |
| `export/StarburstSword.fbx` / `.glb` | The sword's faint base: 7 meshes, 13,256 triangles |
| `export/StarburstVFX.fbx` / `.glb` | Carrier quads that bring the 24 effect textures into Roblox |
| `export/StarburstSword.blend` | The Blender scene |
| `roblox/Installer.lua` | Run once in Studio |
| `roblox/*.lua` | The scripts (edit these, then run `build_installer.py`) |
| `roblox/Layout.lua` | Generated: spike tips, ribbon paths and the figure-8 path, measured in Blender |
| `blender/build_starburst.py` | Rebuilds the model, textures, exports and previews (`--render`) |
| `blender/fire_textures.py` | All the effect textures: the energy layers and the sheet-style fire |
| `textures/` | Every texture as a PNG |

## Good to know

- I built and checked this in real Blender: renders, and the glTF validator (0 errors). The Luau scripts
  pass a syntax check and a linter. **They have not been run inside Roblox Studio yet**, so if
  anything prints an error, send it to me.
- The camera-facing blade paint shows the dark sparkle band on one edge from the front. From the
  other side it mirrors, the same as a real double-sided effect.
- The figure-8 stream follows the flat of the sword, while the soft rings always face the camera. Seen
  from far round the side, the stream narrows into a line and the rings stay round.
- Re-run the installer after updating: it adds the new beams and emitters to the Tool.
- If the importer doesn't bring a texture in, the installer tells you which one is missing. Upload the PNG
  from `textures/` and put its ID in `Config.Textures`.
