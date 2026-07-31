# Boundless Strata v6

Complete game documentation covering all items, blocks, recipes, biomes, terrain generation, animals, enemies, survival mechanics, and controls.

---

## Table of Contents

- [World Configuration](#world-configuration)
- [Player Controls](#player-controls)
- [Day & Night Cycle](#day--night-cycle)
- [Biomes](#biomes)
- [Terrain Generation](#terrain-generation)
- [Liquid Simulation](#liquid-simulation)
- [Player Survival Mechanics](#player-survival-mechanics)
- [Combat System](#combat-system)
- [Armor System](#armor-system)
- [Blocks](#blocks)
- [Walls](#walls)
- [Items](#items)
  - [Tools](#tools)
  - [Weapons & Ammo](#weapons--ammo)
  - [Food](#food)
  - [Misc Materials](#misc-materials)
- [Crafting Recipes](#crafting-recipes)
  - [Basic Crafting (E key)](#basic-crafting-e-key)
  - [Workbench Crafting](#workbench-crafting)
  - [Furnace Smelting](#furnace-smelting)
  - [Campfire Cooking](#campfire-cooking)
  - [Anvil Crafting (Armor)](#anvil-crafting-armor)
- [Animals](#animals)
- [Enemies](#enemies)
- [Dropped Items & Throwing](#dropped-items--throwing)
- [UI & Interfaces](#ui--interfaces)
  - [HUD & Status Bars](#hud--status-bars)
  - [Inventory & Crafting](#inventory--crafting)
  - [Creative Inventory](#creative-inventory)
  - [Chest Storage](#chest-storage)
  - [World Map](#world-map)
  - [Pause Menu & Help](#pause-menu--help)
  - [Debug Overlay](#debug-overlay)
  - [Tooltip System](#tooltip-system)
- [Rendering Systems](#rendering-systems)
  - [Sky Rendering](#sky-rendering)
  - [Parallax Background](#parallax-background)
  - [Tile Rendering & Textures](#tile-rendering--textures)
  - [Lighting System](#lighting-system)
  - [Minimap](#minimap)
- [Save System](#save-system)

---

## World Configuration

| Property | Value |
|---|---|
| World Width | 100,000 tiles |
| World Height | 5,000 tiles (1000 sky + 4000 underground) |
| Tile Size | 24 x 24 pixels |
| Window Resolution | 1280 x 720 (virtual, scales to fullscreen) |
| Target FPS | 60 |
| Day Length | 30 minutes (1800 seconds) |
| Player Interaction Reach | ~5.5 tiles (132 px) |
| Gravity | 1400 px/s² |
| Jump Velocity | -410 px/s |
| Move Speed | 220 px/s |
| Air Acceleration | 1400 px/s² (ground: 2100 px/s²) |
| Ground Friction | 1600 px/s² |
| Air Friction | 200 px/s² |
| Max Fall Speed | 1200 px/s |

The world uses **lazy column generation** — only columns near the player are generated and stored in memory. Columns are generated on-demand as you explore, using deterministic RNG seeded per column so the world is always consistent. Generation is time-budgeted at 8ms per frame with a maximum of 8 columns, prioritized by distance to the player (closest first).

---

## Player Controls

| Key / Input | Action |
|---|---|
| `A` / `D` / `Left` / `Right` | Move left / right |
| `W` / `Space` / `Up` | Jump |
| `Left Click` (hold) | Mine blocks / attack enemies / **place blocks** (context-based: holding block→place, holding tool→mine) / collect surface items |
| `Left Click` (double-click) | Eat/drink selected food item; fill water bottle at water |
| `Right Click` | Pick up & swap inventory items / arm item throw |
| `1` – `9`, `0` | Select hotbar slot (0 = slot 10) |
| `Mouse Wheel` | Cycle through hotbar slots |
| `E` | Open/close Inventory & Basic Crafting |
| `TAB` | Open/close World Map |
| `R` | Respawn (Creative mode only) |
| `T` | Toggle time forward (skip to next phase) |
| `F` | Eat selected food item |
| `F1` | Toggle debug overlay (FPS, coords, biome, day info) |
| `F2` | Toggle slow motion (0.2x speed) |
| `F5` | Quick save |
| `F11` | Toggle fullscreen |
| `F12` | Toggle Creative Mode |
| `ESC` | Open pause menu / close panels |

### Block Placement (Left Click)

- **Left Click** in the world while holding a placeable block to place it
- Context-based: if you're holding a block (not a tool, weapon, food, or ammo), left-click places the block
- If holding a tool/weapon, left-click mines or attacks instead
- Placement requires the target tile to be air and adjacent to an existing solid block

### Inventory Interaction

- **Left Click** a slot: Pick up item (or place held item into slot, with stack merging)
- **Right Click** a slot: Swap held item with slot contents
- **Click a recipe**: Craft it (if you have materials)
- Tools, bows, and armor do not stack (max 1 per slot); all other items stack up to 99

### Item Throwing

- **Right Click** a stackable hotbar slot to arm a throw
- **Left Click** in the world to launch one item toward the cursor
- Throw is cancelled by: clicking a hotbar slot, timeout (1.5s), or opening any panel

---

## Day & Night Cycle

A full day lasts 30 minutes real-time. The day progress (`time` value from 0.0 to 1.0):

| Phase | Time Range | Sky Color |
|---|---|---|
| Night | 0.00 – 0.20 | Dark blue |
| Dawn | 0.20 – 0.40 | Orange → blue (gradual transition) |
| Day | 0.40 – 0.60 | Bright blue |
| Dusk | 0.60 – 0.80 | Blue → orange (gradual transition) |
| Night | 0.80 – 1.00 | Dark blue |

- **Daylight factor**: 1.0 during day (t=0.30–0.70), 0.55 at night — transitions smoothly during dawn/dusk
- **Night** is defined as `time < 0.22` or `time > 0.78`
- Enemies (slimes, zombies) only spawn at night and are cleared at dawn
- Animals only spawn during the day and become restless at night
- The **Bed** block can skip time: sleeping at night advances to dawn; resting during day advances to dusk

---

## Biomes

The world is divided into 7 biome zones spanning the full width. Each biome has unique surface blocks, subsurface blocks, wall types, tree types, sky tints, and animal spawns.

| Biome | World Position | Surface Block | Subsurface | Wall Type | Trees |
|---|---|---|---|---|---|
| **Sea** | 0% – 4%, 96% – 100% | Sand | Sand | Sandstone Wall | None |
| **Tundra** | 4% – 18% | Snow | Dirt | Dirt Wall | Pine (18% chance) — always dark green leaves |
| **Grassland** | 18% – 40% | Grass | Dirt | Dirt Wall | Tree (8%), Bent Tree (2%), Flower (12%) |
| **Forest** | 40% – 55% | Grass | Dirt | Dirt Wall | Tree (14%), Giant Tree (3%), Bent Tree (3%), Flower (6%) |
| **Jungle** | 55% – 72% | Jungle Grass | Mud | Mud Wall | Tall Tree (21%), Giant Tree (4%), Vines |
| **Savanna** | 72% – 86% | Savanna Grass | Dirt | Dirt Wall | Dead Tree (35% in dead zones), Tree (6% outside zones) |
| **Desert** | 86% – 96% | Sand | Sand | Sandstone Wall | Cactus (10%) |

### Biome Blending

Biome transitions are not hard edges. A **12-tile dither zone** at each border blends blocks between adjacent biomes using `_blend_biome_for_column(x)`. Near a border, each tile has a probability of using either biome's blocks based on the blend factor, creating a natural-looking transition rather than an abrupt seam.

### Biome-Specific Features

- **Sea**: Water-filled columns at world edges (15 tiles deep, sandy bottom)
- **Tundra**: Ice patches randomly replace snow near surface (15% chance)
- **Jungle**: Vines hang from leaves and jungle grass blocks (1–4 tiles long)
- **Desert**: Cacti instead of trees (no canopy, just tall green blocks); underground stone replaced with sandstone

### Biome Sky Tints

Each biome applies a color tint to the sky during rendering, blended between day and night values:

| Biome | Day Tint | Night Tint |
|---|---|---|
| Sea | (+20, +30, +50) | (+5, +10, +20) |
| Tundra | (+30, +30, +40) | (+15, +15, +20) |
| Grassland | (0, 0, 0) — neutral | (0, 0, 0) |
| Forest | (-10, +5, -15) | (-3, +2, -5) |
| Jungle | (-15, +10, -20) | (-5, +5, -8) |
| Savanna | (+25, +15, -20) | (+8, +5, -7) |
| Desert | (+35, +20, -30) | (+12, +7, -10) |

These tints give each biome a distinct atmospheric feel — jungles look greener, deserts warmer, oceans cooler, and tundras brighter.

---

## Terrain Generation

### Surface Height

Surface height is computed using layered sine waves (deterministic, no RNG), vectorized with numpy for performance:

```
height(x) = 1000 + sin(x * 0.025 + 0.3) * 5
                  + sin(x * 0.07 + 1.7) * 2.5
                  + sin(x * 0.15 + 4.1) * 1.2
```

The result is smoothed with a 5-tile moving average, giving gentle rolling hills. On top of this, **plateau/mesa bands** are layered — every 48-tile band has a 22% chance of receiving a height offset (±9, ±14, or +20 tiles), with 4-tile ramp transitions between bands, creating occasional steep cliff faces and flat-topped mesas.

### Geology Layers (Depth Below Surface)

Progressively harder stone layers replace the default subsurface as you dig deeper. The subsurface zone (depth 0–24) uses biome-specific blocks (dirt, mud, or sand):

| Layer | Depth Range | Block | Hardness | Color |
|---|---|---|---|---|
| Shallow Stone | 25 – 299 | Stone | 1.2 | Gray |
| Limestone | 300 – 999 | Limestone | 1.5 | Light gray |
| Granite | 1000 – 1999 | Granite | 2.2 | Dark gray |
| Basalt | 2000 – 2999 | Basalt | 3.0 | Very dark |
| Obsidian | 3000 – 3499 | Obsidian | 4.5 | Near black |
| Bedrock | 3500+ | Bedrock | 999 (unbreakable) | Black |

Note: In the Desert biome, the Stone layer (25–299) is overridden with Sandstone instead.

### Ore Distribution

Ores are placed probabilistically per column within specific depth ranges. Veins spread up to 1 tile in each direction (x and y) from a center point, replacing stone or geology blocks.

| Ore | Spawn Chance | Cluster Size | Min Depth | Max Depth | Hardness |
|---|---|---|---|---|---|
| Coal | 30% | 4 tiles | 10 | 2500 | 1.4 |
| Copper Ore | 10% | 3 tiles | 30 | 800 | 1.6 |
| Tin Ore | 9% | 3 tiles | 30 | 800 | 1.7 |
| Iron Ore | 12% | 3 tiles | 50 | 1500 | 2.0 |
| Silver Ore | 5% | 2 tiles | 300 | 2200 | 2.2 |
| Gold Ore | 4.5% | 2 tiles | 500 | 2800 | 2.4 |
| Marble | 3% | 3 tiles | 200 | 1200 | 2.0 |
| Mithril Ore | 2.5% | 2 tiles | 1200 | 3200 | 3.2 |
| Diamond Ore | 2% | 2 tiles | 1800 | 3500 | 3.5 |
| Ruby Ore | 1.2% | 1 tile | 1200 | 3500 | 3.0 |
| Sapphire Ore | 1.2% | 1 tile | 1200 | 3500 | 3.0 |
| Emerald Ore | 1.2% | 1 tile | 1200 | 3500 | 3.0 |

### Cave Generation

Caves are carved using a **3-octave smooth value noise** system (deterministic, integer hash-based — no RNG objects):

- **Octave 1**: Scale 16, weight 0.65 — primary tunnel network
- **Octave 2**: Scale 8, weight 0.35 — finer detail and noise
- **Octave 3**: Scale 40 — large-scale cavern formation

A tile is carved into air if the combined noise exceeds a threshold. The base threshold is 0.66, but when the large-scale octave (n3) exceeds 0.7, the threshold drops by 0.18 (to 0.48), creating big open caverns amidst the usual narrow tunnels. Additionally, tiles with noise just below the threshold (within 0.06) have a 30% random chance of being carved, creating organic-feeling cave edges.

Caves only replace mineable blocks (stone, geology layers, ores). They start at depth 8+ below surface and stop 4 tiles above bedrock. The noise is deterministic (integer hash-based), so caves are always consistent across sessions.

### Ravines

Ravines are long diagonal gashes carved through the terrain, independent of the noise-based cave system:

- **Spacing**: One region every 260 tiles, with 35% chance of a ravine per region
- **Length**: 220–420 tiles long
- **Start Depth**: 15–40 tiles below surface
- **Width**: 2.5–5.0 tiles (half-width), with a 30-tile taper at both ends
- **Drift**: 0.4–1.3 tiles/tile diagonal descent, direction randomly ±1

Ravines carve through all mineable blocks and can intersect caves, creating dramatic interconnected underground networks.

### Floating Islands

Rare detached landmasses floating high above the surface:

- **Spacing**: One region every 340 tiles, with 30% chance per region
- **Height**: 55–110 tiles above the local surface
- **Width**: 9–16 tiles (half-width)
- **Thickness**: 4–7 tiles, with a parabolic profile (thinner at edges: `thickness × max(0.15, 1 - (dx/half_w)²)`)
- **Cap block**: Grass (most biomes), Snow (tundra), Sand (desert); interior filled with Dirt

Floating islands provide elevated platforms for exploration and can contain surface decorations.

### Lava

Starting at depth 3600 below surface, lava pools replace obsidian and basalt:
- 40% chance to replace obsidian with lava
- Below depth +50, all obsidian and basalt become lava

Lava deals **30 damage per second** on contact, emits light (radius 10), and reduces buoyancy (gravity × 0.2, max fall 200 px/s). Lava also interacts with the liquid simulation — when flowing lava contacts flowing water, both are consumed and an obsidian block is created at the lava's position.

### Water

Water uses the **flowing liquid simulation** (see [Liquid Simulation](#liquid-simulation) below) rather than being baked as static tiles:

- **Sea water**: Fills the first 15 tiles below surface at world edges (0–4% and 96–100% width), with a sand floor at the bottom
- **Surface lakes**: Form naturally in surface depressions where neighboring columns are 2+ tiles higher, up to 6 tiles deep
- **Surface ponds**: Shallow basins (3–5 tiles deep, 5–9 tile radius) scattered across grassland, forest, savanna, and jungle biomes (~30% chance per 180-tile region). Bottom lined with sand. Excluded from sea, desert, and tundra biomes.
- **Waterfalls**: When generated water sits above a cave or ravine, the liquid simulation activates and water flows downward, creating natural waterfalls into underground caves.

### Tree Generation

Trees are placed deterministically per column using per-column seeded RNG (`_column_rng`). When a column generates, it checks if a tree should start there, verifies spacing rules (minimum 3 empty columns between trees), places the trunk, then neighboring columns (±3) place canopy leaves that extend sideways. Trees do not generate on water, in sea biomes, or near coastlines.

| Tree Type | Biome | Spawn Chance | Height | Canopy | Leaves Color |
|---|---|---|---|---|---|
| Tree (oak) | Forest | 14% | 5–9 tiles | Round, ~5 tile radius | Green (varies, see below) |
| Tree (oak) | Grassland | 8% | 4–7 tiles | Round, ~5 tile radius | Green (varies) |
| Giant Tree | Forest | 3% | 12–18 tiles | Round, ~5 tile radius | Green (varies) |
| Giant Tree | Jungle | 4% | 14–20 tiles | Round, ~5 tile radius | Green (varies) |
| Tree (tall) | Jungle | 21% | 7–12 tiles | Round, ~5 tile radius | Green (varies) |
| Bent Tree | Forest | 3% | 5–8 tiles | Round, ~5 tile radius | Green (varies) |
| Bent Tree | Grassland | 2% | 4–7 tiles | Round, ~5 tile radius | Green (varies) |
| Pine | Tundra | 18% | 8–14 tiles | Tiered triangle, 3 tiers | **Always Dark Green** |
| Dead Tree | Savanna | 35% (in dead zones) | 3–5 tiles | Round, ~5 tile radius | **Always Autumn (orange)** |
| Cactus | Desert | 10% | 3–6 tiles | None (just trunk) | N/A |
| Flower | Grassland/Forest | ~12% (grass), ~6% (forest) | N/A | Single tile decoration | N/A |

#### Leaf Color Variety

Most tree types (oak, giant, bent) have varied leaf colors determined by `_leaf_type_for_tree()`. Pine trees always use Dark Green leaves, and dead trees always use Autumn (orange) leaves. For other trees, the leaf color is determined in this priority order:

1. **Colored Leaf Zones** (~15% of zones): The world is divided into 30-tile zones. About 15% of these zones become "colored leaf zones" with a 4–12 tile inner radius. All trees inside a zone share the same leaf color, creating clusters of cherry blossom, autumn, red, yellow, or dark forest trees. This mimics real-world patches of same-species forests.
2. **Per-column random**: Outside of colored leaf zones, each tree gets a random leaf color weighted as: 45% standard green, 15% dark green, 8% cherry blossom, 8% autumn orange, 6% red, 6% yellow, 12% default green.

| Leaf Type | Color | Hex | Assignment |
|---|---|---|---|
| Leaves (standard) | Green | (60, 140, 60) | Default, most common |
| Dark Leaves | Dark green | (30, 100, 30) | Pine trees, dark forest zones, random chance |
| Autumn Leaves | Orange-brown | (200, 130, 40) | Dead trees, autumn zones, random chance |
| Red Leaves | Red | (180, 50, 30) | Red zones, random chance |
| Yellow Leaves | Yellow | (200, 190, 50) | Yellow zones, random chance |
| Cherry Blossom | Pink | (240, 150, 180) | Cherry zones, random chance |

#### Dead Tree Zones

Dead trees spawn in grouped clusters using the `_in_dead_tree_zone()` system. The world is divided into 25-tile zones; ~8% of zones are designated as "dead tree zones" with an inner radius of 3–10 tiles. Inside these zones, only dead trees spawn (35% chance per column), and no other tree types appear. Outside dead tree zones in the Savanna biome, normal trees have a 6% spawn chance and dead trees have 0% chance.

#### Colored Leaf Zones

Similar to dead tree zones, colored leaf zones use a zone-based system (`_get_leaf_zone_type()`). The world is divided into 30-tile zones; ~15% of zones become colored leaf zones with an inner radius of 4–12 tiles. Each colored leaf zone is assigned a single dominant leaf color (cherry blossom 22%, autumn orange 20%, red 18%, yellow 18%, dark green 22%). All trees within the zone's radius use that specific leaf color, creating natural-looking groves of trees with matching foliage.

#### Tree Spacing Rules

Trees have a minimum spacing constraint to prevent overlapping: a tree cannot spawn if another tree already exists within 3 columns in either direction (checked via `_nearest_tree_distance()`). This prevents the bug where multiple trees could spawn directly adjacent with no gaps.

### Surface Decorations

Decorations are placed on the surface during column generation. They skip sea biomes, water surfaces, and pond locations.

| Decoration | Biomes | Chance | Collection Method |
|---|---|---|---|
| Small Stone | All land | 8% | Left-click to collect (drops as world item) |
| Grass Tuft | Grassland, Forest, Savanna | 15% | Left-click to collect (drops as world item) |
| Rock (boulder) | All land | 3% | Mine with pickaxe (drops Stone as world item) |
| Bush | Forest, Jungle, Grassland | 8% | Left-click to collect (drops Bush as world item) |
| Berry Bush | Forest, Jungle, Grassland | ~3% (40% of bushes) | Left-click (drops Bush + Berry as world items); right-click picks berries (drops 2 Berry, converts to Bush) |
| Tall Grass | Grassland, Forest, Savanna | ~6% | Left-click to collect (drops as world item) |
| Flowers (Red/Yellow/Blue/White) | Grassland, Forest | ~12% (grass), ~6% (forest) | Left-click to collect (drops Flower as world item) |

### Lazy Two-Phase Generation

World generation happens in two phases to avoid generating thousands of tiles the player hasn't explored:

1. **Surface Phase** (on-demand): Generates columns from the top down to `max(surface + 200, 300)`. This is fast and covers all above-ground content plus shallow underground.
2. **Deep Phase** (triggered when player goes deeper): Extends an already-generated column further downward, adding geology, caves, ores, lava, and ravines to the new depth range.

Each column goes through these generation steps in order: floating islands → terrain fill → bedrock → walls → caves → ravines → ores → sea/lake/pond water → surface decorations → trees → neighbor canopies → biome decorations (vines, ice) → liquid conversion → liquid wake-up.

---

## Liquid Simulation

Water and lava use a **falling-sand-style cellular automaton** system, independent from the tile grid. Each tile stores a separate liquid amount (0–255) and liquid type (none/water/lava).

### Simulation Parameters

| Constant | Value | Description |
|---|---|---|
| MAX_LIQUID | 255 | Full liquid cell |
| MIN_LIQUID | 6 | Below this, no sideways spread |
| LIQUID_FLOW_MAX | 48 | Max sideways transfer per tick |
| LIQUID_TICK | 0.05s | ~20 Hz simulation rate |
| MAX_ACTIVE_PER_TICK | 4000 | Safety cap per tick |

### Flow Rules

1. **Lava + Water reaction**: When flowing lava is adjacent to flowing water, both are consumed and an obsidian block is placed at the lava's cell position.
2. **Downward flow**: Liquid transfers downward first, filling the cell below up to MAX_LIQUID.
3. **Sideways flow**: Any remaining liquid above MIN_LIQUID spreads toward lower neighbors, transferring `min(diff/2, LIQUID_FLOW_MAX)` per tick.
4. **Active set tracking**: Only cells that recently changed are simulated — calm, settled water costs zero CPU.
5. **Block changes wake neighbors**: Mining, placing, or breaking blocks adjacent to liquid activates those cells for re-evaluation. This enables digging channels to redirect water and building dams to stop flow.

### Visual Rendering

- **Water**: Blue fill height based on amount (half-full cells look half full), with a wavy white foam highlight on the surface using `sin(time * 2.2 + tileX * 0.6)`.
- **Lava**: Orange-red fill with a pulsing glow line `sin(time * 3.0 + tileX * 0.4)`, color intensity oscillating ±60 around 150.
- Pre-built texture surfaces for each fill level for fast blitting.

### Water Bottles

- **Empty Water Bottle**: Crafted at workbench (2 Plank + 1 Glass)
- **Filling**: Double-click an empty water bottle while targeting a water tile to fill it
- **Filled Water Bottle**: Restores 35 water (thirst) when consumed

---

## Player Survival Mechanics

The player has three survival stats that must be managed:

### Health

- **Max**: 100 HP
- Regenerated by eating food (see Food section for heal values)
- Reduced by: enemy contact, starvation, dehydration, lava contact, falling below the world
- **Starvation**: 2 HP/sec damage when hunger reaches 0
- **Dehydration**: 3 HP/sec damage when water reaches 0
- **Death in Survival Mode**: At 0 HP, the player dies with a "Game Over" message. No respawn — the player must reload a save.
- **Death in Creative Mode**: At 0 HP, the player respawns at the world spawn point with full stats and 1 second of invulnerability

### Hunger

- **Max**: 100
- **Drain rate**: 0.3/sec base, plus an additional 0.3/sec when running (`|velocity| > 176 px/s`)
- **Restored by eating**: food restores hunger equal to `heal_value × 0.8`
- At 0 hunger, starvation damage begins (2 HP/sec)
- Starting value: 100

### Thirst (Water)

- **Max**: 100
- **Drain rate**: 0.5/sec when not standing in water
- **Refill rate**: 8/sec when standing in water (any tile with liquid amount ≥ 32)
- **Restored by drinking**: Water Bottle (Filled) restores 35 water
- At 0 water, dehydration damage begins (3 HP/sec)
- Starting value: 100

### Swimming

When the player is in water (liquid at mid-body tile with amount ≥ 32):
- Gravity is reduced to 35% of normal (490 px/s²)
- Maximum fall speed drops to 220 px/s
- Jump velocity changes to -260 px/s (slower but more buoyant)
- Horizontal velocity is multiplied by 0.85 (water drag)
- Water stat refills at 8/sec

### Lava Contact

- 30 damage per second
- Gravity reduced to 20% (280 px/s²), max fall 200 px/s
- Orange damage particles spawn every other frame

### Starting Items

New players start with: Wooden Pickaxe ×1, Wooden Sword ×1, Torch ×20, Dirt ×50, Stone ×50, Wood ×20, Plank ×20, Apple ×5.

---

## Combat System

### Damage Values

| Weapon/Tool | Damage | Durability | Notes |
|---|---|---|---|
| Bare Hands | 2 | — | Always available |
| Wooden Sword | 10 | 100 | |
| Stone Sword | 16 | 200 | |
| Iron Sword | 24 | 400 | |
| Gold Sword | 32 | 350 | |
| Diamond Sword | 42 | 800 | Kills slime in 1 hit, zombie in 2 |
| Bow (arrow hit) | 18 | 200 (bow) | Arrows are consumable, travel at 600 px/s |

### Attack Mechanics

- **Melee cooldown**: 0.35 seconds
- **Bow cooldown**: 0.5 seconds
- **Arrows**: Affected by gravity (×0.3), live for 3 seconds, destroyed on hitting solid tiles or enemies
- **Knockback on enemies**: Horizontal `copysign(150-180 + damage×5, direction)`, vertical -200 px/s
- **Player invulnerability**: 0.8 seconds after being hit by an enemy

### Enemy Damage to Player

Damage is reduced by the player's total armor defense: `actual_damage = max(1, base_damage - total_defense)`

| Enemy | Base Damage | Knockback |
|---|---|---|
| Slime | 10 | 280 px/s horizontal, 300 px/s vertical up |
| Zombie | 14 | 320 px/s horizontal, 300 px/s vertical up |

---

## Armor System

Armor is crafted at the **Anvil** and provides defense that reduces incoming enemy damage. There are 5 tiers (wood, stone, iron, gold, diamond) with 4 pieces each (helmet, chestplate, leggings, boots).

### Armor Defense Values

| Piece | Wood | Stone | Iron | Gold | Diamond |
|---|---|---|---|---|---|
| Helmet | 2 | 3 | 5 | 6 | 8 |
| Chestplate | 4 | 6 | 8 | 10 | 14 |
| Leggings | 3 | 4 | 6 | 8 | 10 |
| Boots | 1 | 2 | 3 | 4 | 5 |
| **Total** | **10** | **15** | **22** | **28** | **37** |

### Armor Behavior

- All armor pieces are non-stackable (one per slot)
- Equipped in the 4 armor slots visible in the inventory panel
- **Left Click** an armor piece to pick it up; click an armor slot to equip
- **Right Click** an armor piece on a valid slot for quick-equip
- Armor has no durability — it does not break
- Defense is calculated as the sum of all 4 equipped pieces
- Wood and Stone armor exist in the game data but have **no crafting recipes** — they are only available via Creative Mode (F12)

---

## Blocks

All **67** block types (IDs 0–66) with their properties:

### Natural Blocks

| Block | Color | Solid | Opaque | Hardness | Mined Into | Special |
|---|---|---|---|---|---|---|
| Air | Black | No | No | 0 | — | — |
| Grass | Green | Yes | Yes | 0.4 | Dirt | Surface block (grassland/forest) |
| Dirt | Brown | Yes | Yes | 0.4 | Dirt | Subsurface block |
| Stone | Gray | Yes | Yes | 1.2 | Stone | Common underground |
| Wood | Brown | Yes | Yes | 0.8 | Wood | Dropped from trees |
| Leaves | Green | No | Yes | 0.2 | Nothing | Tree canopy (standard green) |

### Leaf Variants

Six leaf block types exist with different colors. Leaves are non-solid (player can walk through) but opaque (blocks light). None of them drop items when mined (leaf blocks are destroyed). However, destroying an entire tree will cause leaves to drop sticks, and apple items have a 15% chance per leaf block.

| Block | Color | Solid | Opaque | Hardness | Notes |
|---|---|---|---|---|---|
| Leaves | Green (60, 140, 60) | No | Yes | 0.2 | Standard green, most common |
| Dark Leaves | Dark green (30, 100, 30) | No | Yes | 0.2 | Pine trees, dark forest zones |
| Autumn Leaves | Orange-brown (200, 130, 40) | No | Yes | 0.2 | Dead trees, autumn zones |
| Red Leaves | Red (180, 50, 30) | No | Yes | 0.2 | Red leaf zones |
| Yellow Leaves | Yellow (200, 190, 50) | No | Yes | 0.2 | Yellow leaf zones |
| Cherry Blossom | Pink (240, 150, 180) | No | Yes | 0.2 | Cherry blossom zones |
| Sand | Tan | Yes | Yes | 0.3 | Sand | Desert/sea surface |
| Water | Blue | No | No | 0 | Nothing | Legacy placeholder (now uses liquid sim) |
| Torch | Yellow | No | No | 0.1 | Torch | Light radius 8, needs wall/adjacent block |
| Coal Ore | Dark gray | Yes | Yes | 1.4 | Coal | Fuel, torch crafting |
| Iron Ore | Tan | Yes | Yes | 2.0 | Iron | Tool/armor material |
| Gold Ore | Gold | Yes | Yes | 2.4 | Gold | Tool material |
| Diamond Ore | Cyan | Yes | Yes | 3.5 | Diamond | Top-tier tool material |

### Geology Blocks

| Block | Color | Hardness | Mined Into | Depth Range |
|---|---|---|---|---|
| Sandstone | Tan | 1.0 | Sandstone | 25 – 299 (also Desert shallow) |
| Limestone | Light gray | 1.5 | Limestone | 300 – 999 |
| Granite | Dark gray | 2.2 | Granite | 1000 – 1999 |
| Basalt | Very dark | 3.0 | Basalt | 2000 – 2999 |
| Obsidian | Near black | 4.5 | Obsidian | 3000 – 3499 (also created by lava+water) |
| Bedrock | Black | 999 (unbreakable) | Nothing | 3500+ |
| Lava | Orange | 0 | Nothing | Deep underground (liquid sim) |

### Biome Blocks

| Block | Color | Solid | Hardness | Mined Into | Notes |
|---|---|---|---|---|---|
| Snow | White | Yes | 0.3 | Snow | Tundra surface |
| Ice | Light blue | Yes | 0.6 | Ice | Tundra (replaces some snow near surface) |
| Jungle Grass | Bright green | Yes | 0.4 | Mud | Jungle surface |
| Savanna Grass | Yellow-green | Yes | 0.4 | Dirt | Savanna surface |
| Mud | Dark brown | Yes | 0.5 | Mud | Jungle subsurface |
| Cactus | Green | No | 0.4 | Cactus | Desert trees (damage on contact) |
| Vine | Dark green | No | 0.1 | Vine | Jungle decoration (hangs from leaves) |
| Pine Trunk | Dark brown | No | 0.8 | Wood | Tundra tree trunks |
| Flower | Pink | No | 0.1 | Flower | Grassland decoration |
| Marble | White | Yes | 2.0 | Marble | Rare stone pockets (200–1200 depth) |

### Ore Blocks

| Block | Color | Hardness | Mined Into | Depth Range |
|---|---|---|---|---|
| Copper Ore | Copper | 1.6 | Copper Ore | 30 – 800 |
| Tin Ore | Silver | 1.7 | Tin Ore | 30 – 800 |
| Silver Ore | White | 2.2 | Silver Ore | 300 – 2200 |
| Mithril Ore | Blue | 3.2 | Mithril Ore | 1200 – 3200 |
| Ruby Ore | Red | 3.0 | Ruby Ore | 1200 – 3500 |
| Sapphire Ore | Blue | 3.0 | Sapphire Ore | 1200 – 3500 |
| Emerald Ore | Green | 3.0 | Emerald Ore | 1200 – 3500 |

### Crafted & Placeable Blocks

| Block | Color | Solid | Opaque | Hardness | Special |
|---|---|---|---|---|---|
| Plank | Light brown | Yes | Yes | 0.7 | Crafted from Wood |
| Brick | Red | Yes | Yes | 1.8 | Crafted from stone/sand |
| Glass | Light blue | Yes | No | 0.5 | Transparent, light passes through |
| Tree Trunk | Brown | No | Yes | 0.8 | Drops Wood (standard oak tree trunk) |
| Tree Trunk (Giant) | Brown | No | Yes | 0.8 | Drops Wood (tall giant tree trunk) |
| Tree Trunk (Dead) | Gray-brown | No | Yes | 0.8 | Drops Wood (dead/skeletal tree) |
| Tree Trunk (Bent) | Brown | No | Yes | 0.8 | Drops Wood (bent/curved tree) |
| Workbench | Brown | Yes | Yes | 0.7 | **Interactable** — opens workbench crafting |
| Bookshelf | Dark brown | Yes | Yes | 0.8 | Decorative |
| Lamp | Yellow | No | No | 0.2 | **Light radius 12** |
| Chest | Gold-brown | Yes | Yes | 0.8 | **Interactable** — 50-slot storage |
| Furnace | Dark gray | Yes | Yes | 1.5 | **Interactable** — smelting/cooking station |
| Anvil | Gray | Yes | Yes | 2.0 | **Interactable** — armor crafting |
| Campfire | Orange | No | No | 0.3 | **Interactable**, **light radius 10** |
| Bed | Red | No | No | 0.5 | **Interactable** — skip time (sleep/rest) |

### Surface Decoration Blocks

| Block | Solid | Collection | Notes |
|---|---|---|---|
| Rock | Yes | Mine with pickaxe → drops Stone | Large boulder, hardness 1.5 |
| Small Stone | No | Left-click → drops Small Stone | Ground pickup |
| Grass Tuft | No | Left-click → drops Grass Tuft | Ground pickup |
| Bush | No | Left-click → drops Bush | Ground pickup |
| Berry Bush | No | Left-click → drops Bush + Berry; Right-click → picks berries (2 Berry, converts to Bush) | 40% of bushes are fruit bushes |
| Tall Grass | No | Left-click → drops Tall Grass | Ground pickup, taller grass decoration |
| Flower (Red) | No | Left-click → drops Flower | Red flower decoration |
| Flower (Yellow) | No | Left-click → drops Flower | Yellow flower decoration |
| Flower (Blue) | No | Left-click → drops Flower | Blue flower decoration |
| Flower (White) | No | Left-click → drops Flower | White flower decoration |

---

## Walls

Background walls placed behind tiles. They provide visual backdrop underground and have their own hardness values for mining with a hammer.

| Wall | Color | Hardness | Found In |
|---|---|---|---|
| Dirt Wall | Brown | 0.3 | Shallow underground (most biomes) |
| Stone Wall | Dark gray | 0.8 | Mid-depth underground (all biomes) |
| Wood Wall | Brown | 0.5 | — (available as block type) |
| Sandstone Wall | Tan | 0.6 | Sea and Desert underground |
| Granite Wall | Dark gray | 1.2 | Deep underground (all biomes) |
| Mud Wall | Dark brown | 0.4 | Jungle underground |

Wall placement rules by depth below surface:
- Depth 0–24: Biome-specific wall type
- Depth 25–199: Stone Wall
- Depth 200+: Granite Wall

---

## Items

Items are divided into categories by ID range:
- **0–66**: Blocks (same IDs as block types)
- **100–119**: Tools (pickaxe, axe, sword, hammer × 5 tiers)
- **130–131**: Weapons (bow) and ammo (arrow)
- **140–144**: Food items
- **150–154**: Misc materials (stick, paper, wool, leather, feather)
- **155–174**: Armor (4 pieces × 5 tiers)
- **175–178**: Water bottles (empty, filled, wooden empty, wooden filled)

### Tools

All tools have durability and lose 1 point per use. When durability reaches 0, the tool breaks and is destroyed. Axes receive a ×1.5 mining bonus when used on wood-based blocks (Tree Trunk, Wood, Plank, Workbench, Bookshelf, Chest).

#### Pickaxes

| Tool | Tier | Mine Multiplier | Damage | Durability | Recipe |
|---|---|---|---|---|---|
| Wooden Pickaxe | Wood | 2.0x | 4 | 60 | 3 Plank + 2 Stick |
| Stone Pickaxe | Stone | 3.0x | 6 | 150 | 2 Plank + 5 Stone + 2 Stick |
| Iron Pickaxe | Iron | 4.5x | 9 | 300 | 2 Plank + 8 Iron + 2 Stick |
| Gold Pickaxe | Gold | 6.0x | 10 | 250 | 2 Plank + 8 Gold + 2 Stick |
| Diamond Pickaxe | Diamond | 8.0x | 14 | 600 | 2 Plank + 5 Diamond + 2 Stick |

#### Axes

| Tool | Tier | Mine Multiplier | Damage | Durability | Recipe |
|---|---|---|---|---|---|
| Wooden Axe | Wood | 2.5x | 3 | 60 | 3 Plank + 2 Stick |
| Stone Axe | Stone | 3.5x | 5 | 150 | 2 Plank + 5 Stone + 2 Stick |
| Iron Axe | Iron | 5.0x | 8 | 300 | 2 Plank + 8 Iron + 2 Stick |
| Gold Axe | Gold | 6.5x | 9 | 250 | 2 Plank + 8 Gold + 2 Stick |
| Diamond Axe | Diamond | 8.5x | 12 | 600 | 2 Plank + 5 Diamond + 2 Stick |

#### Swords

| Tool | Tier | Damage | Durability | Recipe |
|---|---|---|---|---|
| Wooden Sword | Wood | 10 | 100 | 2 Plank + 1 Stick |
| Stone Sword | Stone | 16 | 200 | 2 Plank + 5 Stone + 1 Stick |
| Iron Sword | Iron | 24 | 400 | 2 Plank + 8 Iron + 1 Stick |
| Gold Sword | Gold | 32 | 350 | 2 Plank + 8 Gold + 1 Stick |
| Diamond Sword | Diamond | 42 | 800 | 2 Plank + 5 Diamond + 1 Stick |

#### Hammers

Hammers are used to mine walls. They have lower mine multipliers than pickaxes but are the only tools that can break background walls.

| Tool | Tier | Mine Multiplier | Damage | Durability | Recipe |
|---|---|---|---|---|---|
| Wooden Hammer | Wood | 1.5x | 2 | 60 | 3 Plank + 2 Stick |
| Stone Hammer | Stone | 2.5x | 4 | 150 | 2 Plank + 5 Stone + 2 Stick |
| Iron Hammer | Iron | 3.5x | 6 | 300 | 2 Plank + 8 Iron + 2 Stick |
| Gold Hammer | Gold | 4.5x | 8 | 250 | 2 Plank + 8 Gold + 2 Stick |
| Diamond Hammer | Diamond | 6.0x | 10 | 600 | 2 Plank + 5 Diamond + 2 Stick |

### Weapons & Ammo

| Item | Damage | Durability | Special | Recipe |
|---|---|---|---|---|
| Bow | 18 per arrow | 200 | Ranged, uses Arrows | 3 Plank + 3 Stick |
| Arrow | 18 (per hit) | — | Consumable ammo, 600 px/s, gravity ×0.3 | 1 Stick + 1 Stone → 4 Arrows |

### Food

Food restores both health and hunger when eaten. Hunger restored = `heal_value × 0.8`.

| Food | Heal (HP) | Hunger Restored | Notes | Source |
|---|---|---|---|---|
| Berry | 8 | 6.4 | Common, low heal | Berry Bushes (left-click or right-click) |
| Apple | 15 | 12 | Decent early-game food | Craft: 2 Plank |
| Raw Meat | 5 | 4 | Risky to eat raw | Animals (Rabbit, Sheep, Cow, Goat, Chicken) |
| Cooked Meat | 40 | 32 | Best healing item | Furnace/Campfire/Workbench: 1 Raw Meat + 1 Coal |
| Bread | 30 | 24 | Good mid-game food | Furnace: 2 Plank; Workbench: 3 Plank |

Press `F` or **double-click** the hotbar slot to eat the selected food item.

### Misc Materials

| Item | Color | Source |
|---|---|---|
| Stick | Brown | Craft: 1 Plank → 4 Sticks |
| Paper | Off-white | Craft: 3 Wood → 3 Paper (workbench) |
| Wool | White | Sheep (100% drop) |
| Leather | Brown | Cow (80% drop), Goat (40% drop) |
| Feather | Off-white | Chicken (100% drop) |
| Water Bottle (empty) | Light blue | Craft: 2 Plank + 1 Glass (workbench) |
| Water Bottle (filled) | Blue | Fill at water tile by double-clicking; restores 35 thirst |

---

## Crafting Recipes

### Basic Crafting (E key)

Available anytime from the inventory screen. No crafting station required.

| Result | Quantity | Materials |
|---|---|---|
| Planks | 4 | 1 Wood |
| Torches | 4 | 1 Plank + 1 Coal |
| Sticks | 4 | 1 Plank |
| Workbench | 1 | 4 Plank |
| Wooden Pickaxe | 1 | 3 Plank + 2 Stick |
| Wooden Axe | 1 | 3 Plank + 2 Stick |
| Wooden Sword | 1 | 2 Plank + 1 Stick |
| Wooden Hammer | 1 | 3 Plank + 2 Stick |

### Workbench Crafting

Requires placing and left-clicking a **Workbench** block nearby (while holding a tool, not a block). Unlocks stone-tier and above tools, building blocks, crafting stations, and more.

#### Building Blocks

| Result | Quantity | Materials |
|---|---|---|
| Bricks | 2 | 2 Stone |
| Glass | 2 | 2 Sand + 1 Coal |
| Bookshelf | 1 | 4 Plank + 3 Paper |
| Lamp | 1 | 1 Plank + 1 Coal + 1 Glass |
| Chest | 1 | 8 Plank |
| Paper | 3 | 3 Wood |
| Water Bottle (empty) | 1 | 2 Plank + 1 Glass |
| Sandstone Bricks | 4 | 4 Sandstone |
| Marble Bricks | 2 | 2 Limestone |
| Granite Bricks | 4 | 4 Granite |
| Basalt Bricks | 4 | 4 Basalt |

#### Stone Tools

| Result | Quantity | Materials |
|---|---|---|
| Stone Pickaxe | 1 | 2 Plank + 5 Stone + 2 Stick |
| Stone Axe | 1 | 2 Plank + 5 Stone + 2 Stick |
| Stone Sword | 1 | 2 Plank + 5 Stone + 1 Stick |
| Stone Hammer | 1 | 2 Plank + 5 Stone + 2 Stick |

#### Iron Tools

| Result | Quantity | Materials |
|---|---|---|
| Iron Pickaxe | 1 | 2 Plank + 8 Iron + 2 Stick |
| Iron Axe | 1 | 2 Plank + 8 Iron + 2 Stick |
| Iron Sword | 1 | 2 Plank + 8 Iron + 1 Stick |
| Iron Hammer | 1 | 2 Plank + 8 Iron + 2 Stick |

#### Gold Tools

| Result | Quantity | Materials |
|---|---|---|
| Gold Pickaxe | 1 | 2 Plank + 8 Gold + 2 Stick |
| Gold Axe | 1 | 2 Plank + 8 Gold + 2 Stick |
| Gold Sword | 1 | 2 Plank + 8 Gold + 1 Stick |
| Gold Hammer | 1 | 2 Plank + 8 Gold + 2 Stick |

#### Diamond Tools

| Result | Quantity | Materials |
|---|---|---|
| Diamond Pickaxe | 1 | 2 Plank + 5 Diamond + 2 Stick |
| Diamond Axe | 1 | 2 Plank + 5 Diamond + 2 Stick |
| Diamond Sword | 1 | 2 Plank + 5 Diamond + 1 Stick |
| Diamond Hammer | 1 | 2 Plank + 5 Diamond + 2 Stick |

#### Ranged & Combat

| Result | Quantity | Materials |
|---|---|---|
| Bow | 1 | 3 Plank + 3 Stick |
| Arrows | 4 | 1 Stick + 1 Stone |

#### Food & Cooking

| Result | Quantity | Materials |
|---|---|---|
| Apple | 1 | 2 Plank |
| Cooked Meat | 1 | 1 Raw Meat + 1 Coal |
| Bread | 1 | 3 Plank |

#### Crafting Stations

| Result | Quantity | Materials | Purpose |
|---|---|---|---|
| Furnace | 1 | 8 Stone + 1 Coal | Smelting & cooking |
| Anvil | 1 | 5 Iron | Armor crafting |
| Campfire | 1 | 3 Wood + 2 Stick | Basic cooking & light |
| Bed | 1 | 6 Plank + 3 Wool | Skip time (sleep/rest) |

> **Note**: All interactable blocks (Workbench, Chest, Furnace, Anvil, Campfire, Bed) are opened by **left-clicking** them while holding a **tool**. If you're holding a block instead of a tool, left-click will place the block.

### Furnace Smelting

Requires placing and left-clicking a **Furnace** block (while holding a tool).

| Result | Quantity | Materials |
|---|---|---|
| Cooked Meat | 1 | 1 Raw Meat |
| Smelt Bricks | 4 | 4 Sand |
| Smelt Glass | 4 | 4 Sand |
| Bake Bread | 1 | 2 Plank |

### Campfire Cooking

Requires placing and left-clicking a **Campfire** block (while holding a tool). Also emits light (radius 10).

| Result | Quantity | Materials |
|---|---|---|
| Cooked Meat | 1 | 1 Raw Meat |
| Torches | 2 | 1 Stick + 1 Coal |

### Anvil Crafting (Armor)

Requires placing and left-clicking an **Anvil** block (while holding a tool). All armor recipes require the tier material plus 2 Plank.

#### Iron Armor

| Piece | Defense | Materials |
|---|---|---|
| Iron Helmet | 5 | 5 Iron + 2 Plank |
| Iron Chestplate | 8 | 8 Iron + 2 Plank |
| Iron Leggings | 6 | 7 Iron + 2 Plank |
| Iron Boots | 3 | 4 Iron + 2 Plank |

#### Gold Armor

| Piece | Defense | Materials |
|---|---|---|
| Gold Helmet | 6 | 5 Gold + 2 Plank |
| Gold Chestplate | 10 | 8 Gold + 2 Plank |
| Gold Leggings | 8 | 7 Gold + 2 Plank |
| Gold Boots | 4 | 4 Gold + 2 Plank |

#### Diamond Armor

| Piece | Defense | Materials |
|---|---|---|
| Diamond Helmet | 8 | 5 Diamond + 2 Plank |
| Diamond Chestplate | 14 | 8 Diamond + 2 Plank |
| Diamond Leggings | 10 | 7 Diamond + 2 Plank |
| Diamond Boots | 5 | 4 Diamond + 2 Plank |

Note: Wood and Stone armor exist as items (IDs 155–162) but have no crafting recipes — they are only obtainable through Creative Mode (F12).

---

## Animals

Passive creatures that spawn during the day in biome-appropriate areas. Max 15 animals at once, spawning every 4.0 seconds off-screen at surface level. They wander randomly, flee from the player (if marked as "flees"), and drop loot when killed.

| Animal | Health | Speed | Flees? | Flies? | Size (tiles) | Spawn Biomes | Drops |
|---|---|---|---|---|---|---|---|
| Rabbit | 8 | 90 | Yes | No | 0.5 × 0.5 | Grassland, Forest, Savanna, Tundra | Raw Meat ×1 (50%) |
| Sheep | 16 | 50 | Yes | No | 0.9 × 0.8 | Grassland, Savanna | Wool ×1 (100%), Raw Meat ×1 (70%) |
| Cow | 24 | 35 | No | No | 1.2 × 1.0 | Grassland, Savanna | Raw Meat ×2 (100%), Leather ×1 (80%) |
| Goat | 18 | 60 | Yes | No | 0.8 × 0.9 | Tundra, Savanna, Grassland | Raw Meat ×1 (80%), Leather ×1 (40%) |
| Chicken | 6 | 70 | Yes | No | 0.5 × 0.6 | Grassland, Forest, Savanna | Feather ×1 (100%), Raw Meat ×1 (60%) |
| Frog | 4 | 80 | Yes | No | 0.4 × 0.4 | Jungle, Grassland, Forest | None |
| Butterfly | 1 | 40 | No | Yes | 0.3 × 0.3 | Jungle, Forest, Grassland | None |

### Animal Behavior

- **Ground animals**: Wander randomly every 1.5–4 seconds, affected by gravity, collide with terrain. Ground friction 0.95, air friction 0.99.
- **Jumping**: Animals jump over 1-block obstacles with `vy = -350` (frogs: -300). They detect solid blocks ahead and jump automatically.
- **Flying animals** (butterfly): Hover with sine-wave motion, drift randomly, ignore gravity entirely.
- **Flee behavior**: When player is within 8 tiles, fleeing animals run away at full speed.
- **Night**: All animals keep moving (wander cooldown set to 0). Animals are not killed at night but stop spawning.
- **Frogs**: Special hop-jump behavior when on ground (vy = -300).

---

## Enemies

Hostile mobs that spawn **only at night** (time < 0.22 or > 0.78). Max 10 enemies at once, spawning every 3.5 seconds off-screen (40–200 px beyond camera edge). 40% chance zombie, 60% chance slime per spawn. All enemies are cleared when dawn arrives.

### Slime

| Property | Value |
|---|---|
| Health | 30 |
| Size | 1.0 × 0.8 tiles |
| Contact Damage | 10 (reduced by armor) |
| Knockback | 280 px/s horizontal, 300 px/s vertical up |
| Colors | Green (90,200,120), Blue (120,180,220), Pink (200,120,180) — random per spawn |

**Behavior**: Hops toward the player when on ground (jump every 0.8–1.8s, `vy = -360`). Random wandering when player is far. Low damage but can be numerous. Ground friction: 0.995.

### Zombie

| Property | Value |
|---|---|
| Health | 50 |
| Size | 0.8 × 1.6 tiles (tall) |
| Contact Damage | 14 (reduced by armor) |
| Knockback | 320 px/s horizontal, 300 px/s vertical up |
| Color | Green (110, 160, 100) |

**Behavior**: Walks toward the player persistently at 80 px/s. Ground acceleration is 4× air acceleration. Detects solid blocks ahead and jumps over 1-tile obstacles (`vy = -420`). More dangerous than slimes due to higher damage, persistence, and wall-climbing ability.

### Combat Tips

- Both enemies have a **0.8 second invulnerability window** after hitting the player
- Slimes and zombies drop loot when killed
- The bow is effective for ranged combat — arrows deal 18 damage each
- Diamond Sword deals 42 damage (kills slime in 1 hit, zombie in 2 hits)
- Armor significantly reduces damage — full diamond armor (37 defense) reduces slime damage to 1 and zombie damage to 1

---

## Dropped Items & Throwing

Items can exist in the world as physics-enabled objects that bounce, settle, and can be picked up. **Mined blocks, collected decorations, and tree destruction products all drop as world items** (not directly into inventory) — the player must walk over them to collect.

### How Items Enter the World

- **Mining**: When you finish mining a block, its drop (stone, wood, ore items, etc.) spawns as a DroppedItem at the block's position
- **Tree Destruction**: Cutting down a tree drops Wood at the trunk position and has a chance to drop Sticks from leaves and Apples from leaf blocks
- **Surface Collection**: Collecting grass tufts, bushes, berry bushes, small stones, flowers, and tall grass spawns the item at the collection point
- **Manual Throwing**: Right-click a hotbar slot to arm a throw, then left-click to launch

### How to Throw

1. **Right Click** a stackable hotbar slot to arm the throw gesture
2. **Left Click** in the world to launch one item from the stack toward the cursor
3. The throw gesture auto-cancels after 1.5 seconds, or if you open any panel, or click a hotbar slot

### Physics

- **Launch speed**: 520 px/s toward cursor, with 80 px/s upward bias
- **Gravity**: 900 px/s² (less than world gravity for a flatter arc)
- **Air drag**: `vx *= (1 - min(1, 0.5 × dt))` per frame
- **Bounce**: Horizontal 0.35×, Vertical 0.30×, with 0.6× ground friction on horizontal velocity
- **Sub-stepping**: Prevents tunneling through thin walls at high speeds
- **Lifetime**: 120 seconds before despawning
- **Pickup delay**: 0.6 seconds (so the thrower doesn't instantly re-grab it)
- **Pickup radius**: 1.6 tiles — walk near a dropped item to auto-collect it

### Visuals

Dropped items render as a small icon with a count badge (if stacked > 1), a shadow ellipse below, and a gentle bobbing animation (`sin(life × 4) × 1.5`).

---

## UI & Interfaces

### HUD & Status Bars

Four status bar groups are displayed above the hotbar, each containing 10 icons:

| Bar | Icon | Color | Max Value | Flash Warning |
|---|---|---|---|---|
| Health | Hearts (red) | Red | 100 HP | Flashes when < 20 HP |
| Armor | Shields | Blue | 40 (display max) | — |
| Hunger | Drumsticks | Orange/brown | 100 | Flashes when < 20 |
| Thirst | Water drops | Blue | 100 | Flashes when < 20 |

Icons are 9×9 pixels with 10px spacing, 10px gap between groups. Half-filled states are rendered for all icons. Total HUD width is 426 pixels, centered above the hotbar.

### Hotbar

- 10 slots, 44×44 pixels each, 4px gap
- **Selected slot**: Blue highlight (90, 110, 200)
- **Hovered slot**: Dark blue (60, 80, 120)
- **Normal slot**: Dark (40, 40, 60)
- Positioned at bottom of screen (`WINDOW_H - 44 - 14`)
- No number labels displayed (clean minimalist look)

### Inventory & Crafting

Opened with `E`. Contains:

- **Player grid**: 10×5 grid (50 slots), 44×44 px, 2px gap
- **Armor slots**: 4 slots on the left side (Helmet, Chestplate, Leggings, Boots)
- **Crafting panel**: 2-column recipe list on the right side
  - Craftable recipes shown in green text, uncraftable in red
  - Each recipe shows: icon, name, material list
- **Interactions**: LMB to pick up/place/stack-merge; RMB to swap entire stack
- **Armor equip**: LMB to pick up and place in armor slot; RMB for quick-equip (validates slot type)
- **Interactable blocks**: Left-click on workbench, chest, furnace, anvil, campfire, or bed while holding a tool to open their interface (not while holding a block — that would place the block instead)

### Creative Inventory

Opened with `E` while Creative Mode is active (F12). Provides access to all items in the game:

- **Title**: "Creative Inventory" centered at top
- **7 category tabs**: All, Blocks, Tools, Armor, Weapons, Food, Misc
- **Grid**: 20-column layout, 36×36 px slots, 5 visible rows (100 items at a time)
- **Scrolling**: Mouse wheel (2 rows per notch), smooth interpolation
- **Scroll bar**: Visible on the right side
- **Item count label**: Shows total items in category
- **"Your Inventory" section**: Player's 10×5 grid at the bottom
- **Interactions**: LMB gives 99× item (1× for non-stackable) with full durability; RMB gives 1×
- Green color scheme (vs blue for normal inventory)

### Chest Storage

Opened by left-clicking a placed Chest block (while holding a tool, not a block):

- **Chest grid**: 10×5 grid (50 slots) at top, brown themed
- **Player grid**: 10×5 grid at bottom, blue themed
- Click items to move between chest and inventory (cursor holds item)
- **Hint text**: "Click items to move between chest and inventory | ESC: close"

### World Map

Opened with `TAB`. Shows a zoomable, pannable overview of the explored world:

- **Lazy-built minimap**: Generated on first TAB press, freed on close (saves memory)
- **Zoom**: Mouse wheel, range 0.5×–30×, default 5×
- **Pan**: Left-click or right-click drag to pan the map
- **Reset**: Middle mouse button resets zoom to 5× and offset to 0
- **Player marker**: Red circle with white border, size scales with zoom (max 6px radius at zoom ≥ 3)
- **Title bar**: Shows seed and current zoom level
- **Exploration**: Only areas within 20 tiles of the player are revealed; unexplored areas are black
- **Hint**: "Scroll: zoom | LMB/RMB drag: pan | MMB: reset zoom | ESC: close"

### Pause Menu & Help

Opened with `ESC`. Semi-transparent overlay with 4 buttons:

| Button | Action |
|---|---|
| Resume | Close pause menu |
| Save & Exit to Menu | Save and return to main menu |
| Help | Show full controls list |
| Quit to Desktop | Close the game entirely |

The Help panel shows all keyboard/mouse controls in a scrollable list.

### Debug Overlay

Toggled with `F1`. Displays at the top-left of the screen:

- FPS, day count, time value, time phase
- Player position (world pixels and tile coordinates)
- Player velocity, on_ground, in_water status
- Entity counts (particles, slimes, zombies, arrows)
- Night/slow-motion status indicators
- World seed and generated column count
- Selected item name (with durability for tools)
- Background panel (0, 0, 0, 140 alpha) for readability

### Tooltip System

Hovering over any item in the inventory/hotbar shows a detailed tooltip:

- **Position**: Upper-right of cursor (18px offset), wraps to left/below if off-screen
- **Content**: Item name, tier, type, damage, mining power, durability, defense, slot info, hardness, tags
- **Style**: Dark panel (18, 6, 36, 225 alpha) with blue border (70, 170, 255)

---

## Rendering Systems

### Sky Rendering

The sky is rendered with smooth color interpolation through the day/night cycle, with biome-specific tints applied per-phase:

- **Day sky**: (135, 206, 235) blended with biome day tint
- **Night sky**: (12, 18, 40) blended with biome night tint
- **Dusk sky**: (235, 130, 70) transitional color
- **Sun**: Visible from time 0.25–0.75, arc across the sky, radius 28px (day) / 22px (dusk), colors (255, 230, 130) / (255, 200, 80)
- **Moon**: Visible during night, opposite arc from sun, rendered as a crescent using overlapping circles
- **Stars**: 80 random white positions, visible only at night (time < 0.20 or > 0.80), with twinkling brightness variation

### Parallax Background

A scenic silhouette of the terrain rendered behind the actual game world, scrolling at 40% of camera speed for a depth effect:

- **Parallax factor**: 0.4 (camera position × 0.4)
- **Numpy-vectorized**: Per-pixel rendering for performance
- **Three depth layers** per column: surface (4 tiles), subsurface (10 tiles), deep — each with darker, more muted colors
- **Biome-specific colors**: 7 biomes × 3 layers = 21 color definitions, creating distinct silhouettes per biome
- **Surface height**: Smoothed with 5-neighbor average (2-tile left/right) for gentle rolling appearance
- **Vegetation silhouettes**: Deterministic tree outlines (12% chance), pine trees (6% in tundra), cacti (8% in desert) — no flicker due to per-position seeding. Giant tree and bent tree silhouettes are also included in appropriate biomes.
- **Depth fade**: 80px gradient at the bottom, alpha up to 100, blending into darkness

### Tile Rendering & Textures

Blocks are rendered with procedurally generated textures (not sprite sheets). Each block type has unique visual features:

- **Grass/Leaves**: Random noise dots, lighter top edge (all 6 leaf color variants use the same texture pattern with their respective colors)
- **Stone/Granite/Basalt**: Beveled edges, crack lines, dark veins
- **Dirt/Mud**: Pebble dot patterns
- **Sand**: Subtle dot pattern
- **Snow**: Sparkle highlights
- **Ice**: Crack lines
- **Sandstone**: Horizontal sedimentary lines at specific y-offsets
- **Torch**: Transparent background, wood stick, 3-layer animated flame with glow halo
- **Furnace/Anvil/Campfire/Bed/Chest**: Custom-drawn multi-shape illustrations
- **Rock/Bush/Grass Tuft/Small Stone**: Detailed multi-shape drawings

Walls are drawn first (only visible where foreground is AIR), then foreground blocks on top.

### Lighting System

A two-tier darkness system creates atmospheric underground lighting:

- **Sky light**: Tiles above the sky height (first opaque block) are fully lit at the current daylight factor
- **Torch/Lamp/Campfire light**: Radius 8 (Lamp: 12, Lava: 10), intensity falls off as `1 - distance/radius`
- **Player light**: Radius 6, intensity 0.7 — the player emits a small amount of light around them
- **Depth-based darkness**: Computed as `min(1.0, depth_below_surface / 200.0)`, reaching maximum at 200 tiles below surface
- **Two-tier alpha blending**:
  - Near surface: shadowed to max alpha 80 (subtle dimming)
  - Deep underground: shadowed to max alpha 245 (nearly black)
  - Formula: `max_alpha = 80 + (245 - 80) × clip(depth, 0, 1)`
- **Box blur**: 3×3 blur at tile resolution, then upscaled to screen pixels for smooth gradients
- **Performance**: Written via `pygame.surfarray.pixels_alpha` for fast pixel-level manipulation

### Minimap

The minimap used for the world map is built lazily and freed when closed:

- **1 pixel per tile**: Full world represented at world_w × world_h pixels
- **Exploration system**: Sparse chunk set (16×16 tiles per chunk), revealed within 20 tiles of player
- **Color coding**: Unexplored = black, liquid = blue, opaque blocks = block color, walls = darker shade
- **Memory**: ~1.9GB when loaded (for a 100k × 5k world), hence freed on map close
- **Not saved**: Exploration data resets on world reload

---

## Save System

- Saves are stored as JSON files in `~/.boundless_strata_saves/`
- Only **generated columns** are saved (not the entire 100,000 × 5,000 world), keeping file sizes manageable
- **Liquid data** saved sparsely — only columns that actually contain liquid are included
- Save data includes: world name, seed, time of day, day count, player position/health/hunger/water, inventory (50 slots), armor (4 slots), chest contents, generated tile/wall columns, liquid columns, surface heights, and biome assignments
- Saving uses **column-based serialization** — bytearrays converted to JSON lists
- Old saves with the same name and seed are automatically deleted before writing a new one
- **Filename format**: `{safe_name}_{seed}_{timestamp}.json`
- **Quick Save**: `F5` at any time
- **Save & Exit**: Pause menu (ESC) → Save & Exit to Menu
- The game supports returning to the main menu without quitting (for loading other worlds)

### Save Compatibility

- Handles both old format (full tiles array) and new format (generated columns with liquid)
- Converts old baked WATER/LAVA tile placeholders into the flowing-liquid layer on load
- Upgrades old 30-slot chests to 50 slots automatically
- Exploration data (minimap reveal) is not saved — re-explored on load

---

## Changelog

### v6 — Boundless Strata

- **Rebranded** from "Terraria Clone" to **Boundless Strata**
- **Font changed** to Carlito (with DejaVu Sans fallback) for a cleaner, more modern in-game appearance
- **Hotbar numbers removed** — slot labels (1–9, 0) no longer clutter the hotbar for a minimalist UI
- **Respawn restricted to Creative mode** — in Survival mode, death shows "Game Over" (no auto-respawn); the `R` key only functions in Creative mode
- **Save directory** moved to `~/.boundless_strata_saves/`
- **Window caption** and **main menu title** updated to Boundless Strata