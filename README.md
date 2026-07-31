# Boundless Strata

A 2D sandbox survival game built from scratch in Python/Pygame — procedurally generated terrain, biome-blended worlds, dynamic liquid simulation, and layered underground lighting.

![Status](https://img.shields.io/badge/status-in%20development-yellow)
![Python](https://img.shields.io/badge/python-3.x-blue)
![Pygame](https://img.shields.io/badge/engine-Pygame-green)

---

## About

**Boundless Strata** is a survival sandbox game inspired by genre classics like Terraria, built as a from-scratch engine rather than a wrapper around an existing framework. The focus has been on getting the systems-level foundations right: lazy infinite-feeling world generation, believable biome transitions, cellular-automaton liquid physics, and a lighting model that actually makes underground exploration feel atmospheric.

The world spans **100,000 × 5,000 tiles**, generated on the fly as the player explores, with deterministic per-column seeding so the same world is always reproducible.

---

## Features

### 🌍 Procedural World Generation
- Lazy column generation — only terrain near the player is generated and held in memory, time-budgeted per frame
- 7 distinct biomes (Sea, Tundra, Grassland, Forest, Jungle, Savanna, Desert), each with unique surface/subsurface blocks, wall types, and tree generation
- 12-tile dithered blend zones at biome borders for natural, non-jarring transitions
- Layered geology, ravines, and floating islands

### 💧 Liquid Simulation
- Cellular-automaton-based water and lava simulation
- Water/lava interactions (obsidian generation on contact)
- Sparse liquid storage — only columns containing liquid are tracked and saved

### 💡 Lighting System
- Two-tier darkness model: gentle dimming near the surface, near-total darkness deep underground
- Dynamic light sources: torches, lamps, campfires, lava glow, and player-emitted light
- Box-blurred lighting for smooth gradients, written via fast pixel-level surface manipulation

### 🎮 Core Gameplay
- Full day/night cycle (30-minute real-time days) with enemy/animal spawn rules tied to time of day
- Mining, building, and combat with a context-aware input system
- Crafting chains: basic crafting, workbench, furnace smelting, campfire cooking, and anvil armor crafting
- Inventory, hotbar, chest storage, creative mode, and a zoomable/pannable world map
- Procedurally drawn tile textures (no sprite sheets) for grass, stone, sand, snow, ice, and more

### 💾 Save System
- Column-based JSON serialization — only generated/explored terrain is saved, keeping file sizes manageable
- Backward-compatible save loading, with automatic upgrades from older save formats

---

## Controls

| Key / Input | Action |
|---|---|
| `A` / `D` / `Arrow Keys` | Move |
| `W` / `Space` | Jump |
| `Left Click` | Mine / attack / place (context-based) |
| `Right Click` | Swap inventory items / arm item throw |
| `E` | Inventory & crafting |
| `TAB` | World map |
| `F1` | Debug overlay |
| `F5` | Quick save |
| `F12` | Toggle creative mode |
| `ESC` | Pause menu |

*(Full control list in-game via the Help menu.)*

---

## Tech Stack

- **Language:** Python
- **Engine:** Pygame
- **Rendering:** Numpy-vectorized parallax and pixel manipulation for performance
- **World Storage:** JSON, column-based sparse serialization

---

## Status

This project is under active development. Current focus areas include dusk lighting refinement and a mouse-only HUD input system. See [`Terraria_Clone_Documentation.md`](./Terraria_Clone_Documentation.md) *(consider renaming to `docs/DESIGN.md`)* for full system documentation covering world config, biomes, combat, crafting recipes, UI, and rendering internals.

---

## Getting Started

```bash
git clone https://github.com/<your-username>/boundless-strata.git
cd boundless-strata
pip install -r requirements.txt
python main.py
```

*(Update the clone URL, entry-point filename, and requirements once finalized.)*

---

## License

*(Add a license of your choice — MIT is a common pick for personal/portfolio projects.)*
