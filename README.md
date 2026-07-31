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

This project is under active development. Current focus areas include dusk lighting refinement and additional gameplay polish. See [`GAME_GUIDE.md`](./GAME_GUIDE.md) for a full features and controls overview.

---

## Download

**Windows only.** This is a closed-source project — the source code is not published in this repository. A prebuilt executable is available under [Releases](../../releases).

1. Go to the [Releases](../../releases) page
2. Download the latest `BoundlessStrata.exe`
3. Run it — no installation required

> Windows Defender or your antivirus may flag the `.exe` on first run since it's an unsigned, self-contained PyInstaller build. This is a known false-positive pattern for this kind of packaging, not a sign of anything malicious. Click "More info" → "Run anyway" if prompted.

---

## License & Source Availability

This repository contains only the compiled game (Windows release) and project documentation. The source code is private and not licensed for reuse, modification, or redistribution. All rights reserved.
