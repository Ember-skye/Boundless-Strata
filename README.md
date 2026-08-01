# Boundless Strata

A 2D sandbox survival game built from scratch in Python with Pygame — inspired by Terraria. Explore a 100,000-tile-wide procedurally generated world spanning 7 biomes, mine and craft your way through tiered gear and armor, fight off nighttime enemies, and dig deep underground where torches are the only thing between you and the dark.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Pygame](https://img.shields.io/badge/pygame-2.x-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

### Procedural World Generation
- **100,000 × 5,000 tile world** (1,000 tiles of sky, 4,000 underground), generated **lazily** — only columns near the player are built and kept in memory
- Fully **deterministic per seed**, using time-budgeted generation (8ms/frame, up to 8 columns at once) prioritized by distance to the player, so exploration stays smooth even at high speed
- Layered terrain generation using Simplex noise (via `opensimplex`, with an automatic layered-sine-wave fallback if it isn't installed) for natural-looking surface height, caves, and ore veins

### Biomes
- **7 distinct biomes** spanning the width of the world — Sea, Tundra, Grassland, Forest, Jungle, Savanna, and Desert — each with its own surface/subsurface blocks, wall types, tree species, sky tints, and animal spawns
- **Seamless blending** at biome borders via a 12-tile dither zone that probabilistically mixes blocks from adjacent biomes, avoiding hard, obviously-generated seams
- Biome-specific set pieces: ice patches in the tundra, hanging vines in the jungle, cacti and sandstone strata in the desert, and sandy sea floors at the world's edges

### Survival Mechanics
- Health, hunger, and water/thirst systems that drain over time and must be managed through food and water bottles
- Full **day/night cycle** (30 real-time minutes per day) with five lighting phases — night, dawn, day, dusk, night — and a **Bed** block that lets you skip straight to dawn or dusk
- **Biome- and time-aware spawning**: enemies (slimes, zombies) only appear at night and are cleared at dawn; animals only spawn by day and grow restless after dark

### Combat & Equipment
- Melee weapons, bows with arrows, and throwable items, each with their own damage, reach, and handling
- A tiered **armor system** with distinct defense values, crafted at the anvil
- Tools and weapons carry **durability**, tracked and shown in tooltips and the debug overlay

### Crafting & Progression
- Five separate crafting contexts, each unlocking deeper tiers of gear: basic crafting (`E` menu), the **Workbench**, **Furnace** smelting, **Campfire** cooking, and the **Anvil** for armor
- Dozens of blocks, tools, weapons, food items, and misc materials, each with their own recipes and material tiers

### Liquid Simulation
- **Cellular-automaton** water and lava that actually flows, pools, and spreads tile-by-tile rather than being static
- Water and lava interact — contact between the two can form obsidian
- Liquid state is tracked and saved sparsely, so only tiles that actually contain liquid take up space in the save file

### Dynamic Lighting
- Two-tier darkness model: gentle dimming near the surface, ramping up to near-total darkness deep underground (max darkness reached ~200 tiles below the surface)
- Multiple light sources — torches, lamps, campfires, lava, and even a small radius around the player — each with their own falloff radius and intensity
- Light is box-blurred at tile resolution and upscaled for smooth, non-blocky gradients, written directly via `pygame.surfarray` for performance

### World Map & Navigation
- **Zoomable, pannable world map** (`TAB`) with a lazily-built, memory-freed-on-close minimap
- **Fog-of-war style exploration** — only areas you've actually visited are revealed; the rest stays black
- Live player marker, seed display, and zoom level shown directly on the map

### UI & Interface
- Full inventory and hotbar system with stacking, tooltips (damage, mining power, durability, defense, and more), and drag/swap interactions
- **Creative mode** item browser with category tabs and instant item spawning for testing or free-building
- Chest storage with a dedicated transfer UI
- Debug overlay (`F1`) showing FPS, coordinates, biome, entity counts, and world seed
- Pause menu with save, help, and quit options

### Save/Load System
- Efficient **column-based JSON saves** — only generated columns (not the full 100k-wide world) and non-empty liquid data are persisted, keeping file sizes manageable
- Automatic **backward compatibility** with older save formats, including upgrading legacy chest sizes and converting old static water/lava tiles into the new flowing-liquid system
- Quick save (`F5`) and save-and-exit from the pause menu

For the complete breakdown of every block, item, recipe, biome, and system, see [`Boundless_Strata_Documentation.md`](./Boundless_Strata_Documentation.md).

---

## Screenshots
<img width="1920" height="1080" alt="Screenshot (749)" src="https://github.com/user-attachments/assets/9a5c065f-981b-450f-b49e-974c7e99d69a" />
<img width="1920" height="1080" alt="Screenshot (750)" src="https://github.com/user-attachments/assets/d24ee9ea-5525-46d0-91d6-01dc5928ed32" />
<img width="1920" height="1080" alt="Screenshot (752)" src="https://github.com/user-attachments/assets/46c2cc97-f46b-4c82-a2dc-17859dc1ec8f" />
<img width="1920" height="1080" alt="Screenshot (754)" src="https://github.com/user-attachments/assets/544ac658-f50c-439b-97dd-ff8a151e17a1" />
<img width="1920" height="1080" alt="Screenshot (756)" src="https://github.com/user-attachments/assets/7ab9aac5-e7e1-4d77-aeb0-eb3cb896ce39" />

---

## Getting Started

### Requirements

- Python 3.9+
- [pygame](https://www.pygame.org/)
- [numpy](https://numpy.org/)
- [opensimplex](https://pypi.org/project/opensimplex/) *(optional — enables smoother terrain noise; the game falls back to layered sine-wave noise if not installed)*

### Installation

```bash
git clone https://github.com/Ember-skye/Boundless-Strata.git
cd Boundless-Strata
pip install pygame numpy opensimplex
```

### Run

```bash
python Boundless_Strata.py
```

---

## Controls

| Key / Input | Action |
|---|---|
| `A` / `D` / `←` / `→` | Move left / right |
| `W` / `Space` / `↑` | Jump |
| `Left Click` (hold) | Mine / attack / place block (context-based) / collect items |
| `Left Click` (double-click) | Eat/drink selected item / arm item throw |
| `Right Click` | Pick up & swap inventory items / fill water bottle  |
| `1`–`9`, `0` | Select hotbar slot |
| `E` | Open/close inventory & basic crafting |
| `TAB` | Open/close world map |
| `F` | Eat selected food |
| `R` | Respawn *(Creative mode only)* |
| `T` | Skip to next time phase *(Creative mode only)* |
| `F1` | Toggle debug overlay |
| `F2` | Toggle slow motion *(Creative mode only)*|
| `F5` | Quick save |
| `F11` | Toggle fullscreen |
| `F12` | Toggle Creative mode |
| `ESC` | Pause menu / close panels |

Full input details (block placement rules, inventory interactions, throwing) are in the [documentation](./Boundless_Strata_Documentation.md#player-controls).

---

## World Overview

| Property | Value |
|---|---|
| World Size | 100,000 × 5,000 tiles |
| Tile Size | 24 × 24 px |
| Day Length | 30 minutes real-time |
| Biomes | 7 (Sea, Tundra, Grassland, Forest, Jungle, Savanna, Desert) |
| World Generation | Lazy, column-based, deterministic per seed |

---

## Saves

Saves are stored as JSON in `~/.boundless_strata_saves/`. Only generated columns and non-empty liquid data are saved, keeping file sizes manageable even on a 100k-tile-wide world. Use `F5` for a quick save, or **Pause Menu → Save & Exit** to save and return to the main menu.

---

## Project Status

Boundless Strata is a solo hobby project under active development. Current version: **v6**. 

### Known limitations
- Single-file architecture (~9,500 lines) — a modular refactor is a future goal
- Minimap can use significant memory (~1.9 GB) on fully explored large worlds

---

## Contributing

This is currently a personal project, but bug reports, suggestions, and pull requests are welcome — feel free to open an issue.

---

## 👤 Author

**Ember_skye**

BCA Student | Python Developer | Indie Game Developer

---

*"Every block broken is another step into the unknown."*
