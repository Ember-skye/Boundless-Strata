"""
Boundless Strata - v6 

Controls:
  A / D or Left/Right Arrows : Move
  W / Space / Up             : Jump
  Left Click                 : Mine / attack / place block / select hotbar 
  Right Click                : Interact / fill water bottle / swap hotbar items
  1-9, 0                     : Select hotbar slot
  E                          : Inventory & basic crafting
  TAB                        : World map
  R                          : Respawn (Creative mode only)
  T                          : Toggle time (Creative mode only)
  F                          : Eat selected food
  F1                         : Debug overlay
  F2                         : Slow motion (Creative mode only)
  F5                         : Quick save
  F11                        : Toggle fullscreen
  ESC                        : Pause menu

Requires: pygame, numpy
Run:       python Boundless_Strata_v6.py
"""

import json
import math
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pygame

try:
    import opensimplex
    HAS_OPENSIMPLEX = True
except ImportError:
    HAS_OPENSIMPLEX = False

# ============================================================
# FONT HELPER
# ============================================================

def _make_font(size, bold=False, candidates=("comicsansms", "inkfree", "segoeprint", "trebuchetms")):
    """Load the first available font from candidates using match_font for reliability.
    Uses Font(path) instead of SysFont to guarantee the correct font is loaded."""
    for name in candidates:
        path = pygame.font.match_font(name, bold=bold)
        if path:
            try:
                f = pygame.font.Font(path, size)
                return f
            except Exception:
                continue
    return pygame.font.Font(None, size)  # pygame built-in fallback

# ============================================================
# PROCEDURAL SOUND SYSTEM
# ============================================================

def _make_sound(samples_array):
    """Convert a numpy float array [-1, 1] to a pygame Sound object (mono 16-bit)."""
    clipped = np.clip(samples_array, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    stereo = np.column_stack((pcm, pcm))  # mono → stereo for pygame
    return pygame.sndarray.make_sound(stereo)

def _gen_mine_hit():
    """Short crunchy hit sound for mining — filtered noise burst."""
    sr = 22050; dur = 0.06; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    env = np.linspace(1.0, 0.0, n) ** 2
    freq_env = np.linspace(800, 200, n)
    carrier = np.sin(2 * np.pi * np.cumsum(freq_env / sr))
    return _make_sound((noise * 0.5 + carrier * 0.5) * env)

def _gen_mine_break():
    """Block break sound — crunchier, slightly longer."""
    sr = 22050; dur = 0.12; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    env = np.linspace(1.0, 0.0, n) ** 1.5
    carrier = np.sin(2 * np.pi * np.cumsum(np.linspace(600, 150, n) / sr))
    return _make_sound((noise * 0.6 + carrier * 0.4) * env * 0.8)

def _gen_sword_swing():
    """Whoosh sound for melee attack."""
    sr = 22050; dur = 0.15; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    ramp_up = n // 3
    env = np.concatenate([np.linspace(0, 1, ramp_up), np.linspace(1, 0, n - ramp_up)])
    freq = np.linspace(200, 1500, n)
    sweep = np.sin(2 * np.pi * np.cumsum(freq / sr)) * 0.3
    return _make_sound((noise * 0.4 + sweep) * env * 0.6)

def _gen_hit():
    """Impact sound when hitting an enemy."""
    sr = 22050; dur = 0.1; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    env = np.linspace(1.0, 0.0, n) ** 2
    thud = np.sin(2 * np.pi * np.cumsum(np.linspace(150, 60, n) / sr))
    return _make_sound((noise * 0.3 + thud * 0.7) * env * 0.7)

def _gen_hurt():
    """Player hurt sound."""
    sr = 22050; dur = 0.2; n = int(sr * dur)
    env = np.linspace(1.0, 0.0, n) ** 1.5
    tone = np.sin(2 * np.pi * np.cumsum(np.linspace(300, 100, n) / sr))
    noise = np.random.uniform(-1, 1, n) * 0.2
    return _make_sound((tone + noise) * env * 0.5)

def _gen_click():
    """UI click sound."""
    sr = 22050; dur = 0.05; n = int(sr * dur)
    env = np.linspace(1.0, 0.0, n) ** 3
    tone = np.sin(2 * np.pi * 1200 * np.arange(n) / sr)
    return _make_sound(tone * env * 0.3)

def _gen_place():
    """Block placement sound."""
    sr = 22050; dur = 0.08; n = int(sr * dur)
    env = np.linspace(1.0, 0.0, n) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(np.linspace(500, 300, n) / sr))
    return _make_sound(tone * env * 0.4)

def _gen_pickup():
    """Item pickup sound — short ascending blip."""
    sr = 22050; dur = 0.1; n = int(sr * dur)
    ramp_up = n // 4
    env = np.concatenate([np.linspace(0, 1, ramp_up), np.linspace(1, 0, n - ramp_up)])
    tone = np.sin(2 * np.pi * np.cumsum(np.linspace(800, 1200, n) / sr))
    return _make_sound(tone * env * 0.3)

def _gen_jump():
    """Jump sound."""
    sr = 22050; dur = 0.08; n = int(sr * dur)
    env = np.linspace(1.0, 0.0, n) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(np.linspace(250, 500, n) / sr))
    return _make_sound(tone * env * 0.25)

def _gen_rain_ambient():
    """Looping rain ambient sound (1 second)."""
    sr = 22050; dur = 1.0; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    # Low-pass via moving average
    kernel_size = 8
    kernel = np.ones(kernel_size) / kernel_size
    filtered = np.convolve(noise, kernel, mode='same')
    # Gentle pulsing
    pulse = 0.7 + 0.3 * np.sin(2 * np.pi * 2.0 * np.arange(n) / sr)
    return _make_sound(filtered * pulse * 0.15)

def _gen_footstep():
    """Soft footstep on dirt/grass — short filtered noise burst with a low thud."""
    sr = 22050; dur = 0.08; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    # Low-pass: moving average smoothing
    kernel = np.ones(6) / 6
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 2
    thud = np.sin(2 * np.pi * np.cumsum(np.linspace(120, 60, n) / sr))
    return _make_sound((filtered * 0.5 + thud * 0.5) * env * 0.25)

def _gen_footstep_stone():
    """Harder, clickier footstep on stone/rock — brighter noise burst."""
    sr = 22050; dur = 0.06; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(3) / 3  # less smoothing = brighter
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 3
    click = np.sin(2 * np.pi * np.cumsum(np.linspace(400, 200, n) / sr))
    return _make_sound((filtered * 0.6 + click * 0.4) * env * 0.22)

def _gen_footstep_water():
    """Wet splashy footstep in water — bubbly noise splash."""
    sr = 22050; dur = 0.12; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(5) / 5
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 1.5
    # Add some "bloop" oscillator
    bloop = np.sin(2 * np.pi * np.cumsum(np.linspace(300, 800, n) / sr)) * 0.3
    return _make_sound((filtered * 0.6 + bloop) * env * 0.3)

def _gen_footstep_snow():
    """Crunchy soft footstep on snow — muffled crunch."""
    sr = 22050; dur = 0.1; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(10) / 10  # heavy smoothing = muffled
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 2
    return _make_sound(filtered * env * 0.22)

def _gen_footstep_sand():
    """Gritty footstep on sand — short hiss."""
    sr = 22050; dur = 0.07; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(4) / 4
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 2
    return _make_sound(filtered * env * 0.2)

def _gen_bow_shoot():
    """Bow shoot sound — quick string twang + arrow whoosh."""
    sr = 22050; dur = 0.18; n = int(sr * dur)
    # Twang: descending pitch oscillator
    twang_freq = np.linspace(800, 200, n)
    twang = np.sin(2 * np.pi * np.cumsum(twang_freq / sr)) * 0.5
    # Whoosh: short noise burst
    noise = np.random.uniform(-1, 1, n)
    env_noise = np.linspace(0, 1, n // 4)
    env_noise = np.concatenate([env_noise, np.linspace(1, 0, n - n // 4)])
    whoosh = noise * env_noise * 0.3
    # Combined envelope
    env = np.linspace(1.0, 0.0, n) ** 1.2
    return _make_sound((twang + whoosh) * env * 0.4)

def _gen_arrow_hit():
    """Arrow hitting enemy/dirt — fleshy thwack + crunch."""
    sr = 22050; dur = 0.1; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(4) / 4
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 2
    thwack = np.sin(2 * np.pi * np.cumsum(np.linspace(220, 80, n) / sr))
    return _make_sound((filtered * 0.4 + thwack * 0.6) * env * 0.4)

def _gen_arrow_thud():
    """Arrow missing and hitting a solid block — wooden/stone thud."""
    sr = 22050; dur = 0.08; n = int(sr * dur)
    env = np.linspace(1.0, 0.0, n) ** 2
    thud = np.sin(2 * np.pi * np.cumsum(np.linspace(180, 70, n) / sr))
    noise = np.random.uniform(-1, 1, n) * 0.2
    return _make_sound((thud + noise) * env * 0.35)

def _gen_tree_fall():
    """Tree falling — long creaky crash with leaves rustling."""
    sr = 22050; dur = 0.6; n = int(sr * dur)
    t = np.arange(n) / sr
    # Creak: low rumble + slight pitch wobble
    creak = np.sin(2 * np.pi * np.cumsum(np.linspace(80, 40, n) / sr)) * 0.4
    creak += np.sin(2 * np.pi * 3.0 * t) * 0.1 * np.exp(-t * 2)
    # Crash: noise burst at the start
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(8) / 8
    filtered = np.convolve(noise, kernel, mode='same')
    # Rustle: brighter noise tail
    rustle_noise = np.random.uniform(-1, 1, n) * 0.3
    rustle_env = np.where(t > 0.1, np.exp(-(t - 0.1) * 2.0), 0)
    rustle = rustle_noise * rustle_env
    # Combined envelope
    env = np.exp(-t * 2.5)
    return _make_sound((creak + filtered * 0.3 + rustle) * env * 0.4)

def _gen_eat():
    """Eating food — chompy bite sounds."""
    sr = 22050; dur = 0.25; n = int(sr * dur)
    t = np.arange(n) / sr
    out = np.zeros(n)
    # Three bite bursts
    for bite_t in (0.0, 0.09, 0.18):
        bite_n = int(0.05 * sr)
        start = int(bite_t * sr)
        if start + bite_n > n: bite_n = n - start
        if bite_n <= 0: continue
        bt = np.arange(bite_n) / sr
        noise = np.random.uniform(-1, 1, bite_n)
        kernel = np.ones(3) / 3
        filtered = np.convolve(noise, kernel, mode='same')[:bite_n]
        chomp = np.sin(2 * np.pi * np.cumsum(np.linspace(200, 80, bite_n) / sr))
        env = np.linspace(1.0, 0.0, bite_n) ** 2
        out[start:start+bite_n] = (filtered * 0.5 + chomp * 0.5) * env * 0.5
    return _make_sound(out)

def _gen_drink():
    """Drinking — gulping water sound."""
    sr = 22050; dur = 0.4; n = int(sr * dur)
    t = np.arange(n) / sr
    out = np.zeros(n)
    # Two gulps
    for gulp_t in (0.0, 0.18):
        gulp_n = int(0.15 * sr)
        start = int(gulp_t * sr)
        if start + gulp_n > n: gulp_n = n - start
        if gulp_n <= 0: continue
        noise = np.random.uniform(-1, 1, gulp_n)
        kernel = np.ones(5) / 5
        filtered = np.convolve(noise, kernel, mode='same')[:gulp_n]
        # Pitch sweep up (swallow)
        sweep = np.sin(2 * np.pi * np.cumsum(np.linspace(150, 400, gulp_n) / sr)) * 0.3
        # Envelope: ramp up over first third, ramp down over remaining two thirds
        ramp_up = gulp_n // 3
        env = np.concatenate([np.linspace(0, 1, ramp_up), np.linspace(1, 0, gulp_n - ramp_up)])
        out[start:start+gulp_n] = (filtered * 0.5 + sweep) * env * 0.35
    return _make_sound(out)

def _gen_craft():
    """Crafting sound — short assembly chime."""
    sr = 22050; dur = 0.2; n = int(sr * dur)
    t = np.arange(n) / sr
    # Two ascending tones
    tone1 = np.sin(2 * np.pi * 600 * t) * np.exp(-t * 8) * 0.4
    tone2 = np.sin(2 * np.pi * 900 * (t - 0.08)) * np.exp(-(t - 0.08) * 10) * 0.4
    tone2 = np.where(t > 0.08, tone2, 0)
    return _make_sound(tone1 + tone2)

def _gen_splash():
    """Water splash — entering water."""
    sr = 22050; dur = 0.25; n = int(sr * dur)
    t = np.arange(n) / sr
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(6) / 6
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 1.5
    # Pitchy bubble
    bubble = np.sin(2 * np.pi * np.cumsum(np.linspace(800, 200, n) / sr)) * 0.3
    return _make_sound((filtered * 0.6 + bubble) * env * 0.4)

def _gen_land():
    """Landing on ground after a fall — soft thud."""
    sr = 22050; dur = 0.1; n = int(sr * dur)
    env = np.linspace(1.0, 0.0, n) ** 2
    thud = np.sin(2 * np.pi * np.cumsum(np.linspace(140, 50, n) / sr)) * 0.7
    noise = np.random.uniform(-1, 1, n) * 0.2
    return _make_sound((thud + noise) * env * 0.35)

def _gen_break_tool():
    """Tool breaking — sharp snap."""
    sr = 22050; dur = 0.15; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    env = np.linspace(1.0, 0.0, n) ** 1.5
    snap = np.sin(2 * np.pi * np.cumsum(np.linspace(1200, 100, n) / sr)) * 0.5
    return _make_sound((noise * 0.5 + snap * 0.5) * env * 0.45)

def _gen_lightning():
    """Lightning strike — sharp crack + rumble."""
    sr = 22050; dur = 0.8; n = int(sr * dur)
    t = np.arange(n) / sr
    # Crack: sharp noise burst at start
    crack_n = int(0.05 * sr)
    crack = np.random.uniform(-1, 1, n) * np.exp(-t * 30) * 0.7
    # Rumble: low-frequency rumble following
    rumble = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 2) * 0.3
    rumble += np.sin(2 * np.pi * 40 * t) * np.exp(-t * 1.5) * 0.2
    return _make_sound(crack + rumble)

def _gen_door():
    """Door / chest open sound — wooden creak."""
    sr = 22050; dur = 0.25; n = int(sr * dur)
    t = np.arange(n) / sr
    # Creak: pitch wobble around 200 Hz
    freq = 200 + 50 * np.sin(2 * np.pi * 4 * t)
    creak = np.sin(2 * np.pi * np.cumsum(freq / sr)) * 0.4
    # Three-stage envelope: ramp up / hold / fade out (each exactly a third of n)
    third = n // 3
    env = np.concatenate([
        np.linspace(0, 1, third),
        np.linspace(1, 0.3, third),
        np.linspace(0.3, 0, n - 2 * third),  # last segment picks up the remainder
    ])
    return _make_sound(creak * env * 0.35)

def _gen_furnace():
    """Furnace smelting — short whoosh of flame."""
    sr = 22050; dur = 0.3; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(4) / 4
    filtered = np.convolve(noise, kernel, mode='same')
    ramp_up = n // 4
    env = np.concatenate([np.linspace(0, 1, ramp_up), np.linspace(1, 0, n - ramp_up)])
    # Crackling tone
    crackle = np.sin(2 * np.pi * np.cumsum(np.linspace(150, 80, n) / sr)) * 0.2
    return _make_sound((filtered * 0.6 + crackle) * env * 0.3)

def _gen_step_animal():
    """Soft passive-animal step — barely audible."""
    sr = 22050; dur = 0.05; n = int(sr * dur)
    noise = np.random.uniform(-1, 1, n)
    kernel = np.ones(8) / 8
    filtered = np.convolve(noise, kernel, mode='same')
    env = np.linspace(1.0, 0.0, n) ** 2
    return _make_sound(filtered * env * 0.12)

# Sound cache — lazily initialized after pygame.init()
_SOUNDS = {}
_SOUNDS_ENABLED = True

def _init_sounds():
    """Generate all procedural sounds. Call after pygame.init() and mixer.init()."""
    global _SOUNDS, _SOUNDS_ENABLED
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        _SOUNDS = {
            # Original sounds
            # Mine hit/break sounds removed (were unpleasant — particle feedback is used instead)
            "sword_swing": _gen_sword_swing(),
            "hit": _gen_hit(),
            "hurt": _gen_hurt(),
            "click": _gen_click(),
            "place": _gen_place(),
            "pickup": _gen_pickup(),
            "jump": _gen_jump(),
            "rain": _gen_rain_ambient(),
            # New footstep variants (chosen at runtime based on surface tile)
            "footstep": _gen_footstep(),          # default dirt/grass
            "footstep_stone": _gen_footstep_stone(),
            "footstep_water": _gen_footstep_water(),
            "footstep_snow": _gen_footstep_snow(),
            "footstep_sand": _gen_footstep_sand(),
            # Combat
            "bow_shoot": _gen_bow_shoot(),
            "arrow_hit": _gen_arrow_hit(),
            "arrow_thud": _gen_arrow_thud(),
            # World
            "tree_fall": _gen_tree_fall(),
            "splash": _gen_splash(),
            "land": _gen_land(),
            "lightning": _gen_lightning(),
            # Inventory / stations
            "eat": _gen_eat(),
            "drink": _gen_drink(),
            "craft": _gen_craft(),
            "door": _gen_door(),
            "furnace": _gen_furnace(),
            "break_tool": _gen_break_tool(),
            # Animal
            "step_animal": _gen_step_animal(),
        }
    except Exception:
        _SOUNDS_ENABLED = False

def play_sound(name, volume=0.5):
    """Play a named procedural sound."""
    if not _SOUNDS_ENABLED or not _SOUNDS:
        return
    snd = _SOUNDS.get(name)
    if snd:
        try:
            ch = snd.play()
            if ch:
                ch.set_volume(volume)
        except Exception:
            pass

# ============================================================
# PATHS & DIRECTORIES
# ============================================================

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
SAVES_DIR = os.path.join(os.path.expanduser("~"), ".boundless_strata_saves")
os.makedirs(SAVES_DIR, exist_ok=True)

# ============================================================
# CONFIGURATION
# ============================================================

TILE = 24
WORLD_W = 100000  # 100k wide - massive world with lazy generation
WORLD_H = 5000    # 1000 sky + 4000 underground
SURFACE = 1000    # average surface tile-y
GRAVITY = 1400.0
JUMP_VEL = -410.0
MOVE_SPEED = 220.0
AIR_ACCEL = 1400.0
GROUND_FRICTION = 1600.0
AIR_FRICTION = 200.0
MAX_FALL = 1200.0
REACH = 5.5 * TILE
DOUBLE_CLICK_TIME = 0.35  # seconds within which two LMB presses count as a double-click
THROW_SPEED = 520.0       # initial speed of a thrown item (pixels/sec)
THROW_GRAVITY = 900.0     # gravity applied to thrown items (less than world gravity for a flatter arc)
THROW_ARM_TTL = 5.0       # how long the throw gesture stays armed before auto-cancelling

WINDOW_W, WINDOW_H = 1280, 720  # Updated to native resolution at runtime
# Runtime globals: set to actual screen resolution in _init_display
VIEW_W, VIEW_H = WINDOW_W, WINDOW_H  # Actual screen pixel dimensions
ui_scale = 1.0  # VIEW_W / WINDOW_W
FPS = 60
DAY_LENGTH = 1800.0  # 30 minutes

COL_SKY_DAY = (135, 206, 235)
COL_SKY_NIGHT = (12, 18, 40)
COL_SKY_DUSK = (235, 130, 70)

# ============================================================
# BLOCKS - expanded with geology, biome, and new ore blocks
# ============================================================

(AIR, GRASS, DIRT, STONE, WOOD, LEAVES, SAND, WATER, TORCH, COAL, IRON, GOLD,
 DIAMOND, PLANK, BRICK, GLASS, TREE_TRUNK, WORKBENCH, BOOKSHELF, LAMP, CHEST,
 # Geology layers (depth-ordered)
 SANDSTONE, LIMESTONE, GRANITE, BASALT, OBSIDIAN, BEDROCK, LAVA,
 # Biome blocks
 SNOW, ICE, JUNGLE_GRASS, SAVANNA_GRASS, MUD, CACTUS, VINE, PINE_TRUNK, FLOWER, MARBLE,
 # New ores
 COPPER_ORE, TIN_ORE, SILVER_ORE, MITHRIL_ORE, RUBY_ORE, SAPPHIRE_ORE, EMERALD_ORE,
 # New natural blocks
 ROCK, SMALL_STONE, GRASS_TUFT, BUSH, BUSH_FRUIT,
 # New crafting stations
 FURNACE, ANVIL, CAMPFIRE,
 BED,
 # Extended vegetation
 TALL_GRASS, FLOWER_RED, FLOWER_YELLOW, FLOWER_BLUE, FLOWER_WHITE,
 TREE_GIANT, TREE_DEAD, TREE_BENT,
 LEAVES_DARK, LEAVES_AUTUMN, LEAVES_RED, LEAVES_YELLOW, LEAVES_CHERRY,
 # Dried grass
 DRIED_GRASS,
 # Seedling blocks (placed by tree seeds, grow into full trees)
 SEEDLING_TREE, SEEDLING_PINE, SEEDLING_GIANT, SEEDLING_DEAD, SEEDLING_BENT,
 # Dried tall grass (2-tile vertical, savanna/grassland)
 DRIED_TALL_GRASS,
) = range(74)

NUM_BLOCKS = 74

# ============================================================
# ITEM IDs — must be defined BEFORE BLOCK_DEFS so that
# ore "drops" can reference COAL_ITEM etc.
# ============================================================

# Tool/Item ID ranges:
#   0-61   : blocks (matches NUM_BLOCKS)
#   100-119: basic tools (pickaxe/axe/sword/hammer x wood/stone/iron)
#   120-129: gold/diamond tools
#   130-139: weapons (bow, arrow as material)
#   140-149: food items
#   150-154: misc materials (stick, paper, wool, leather, feather)
#   155-174: armor (4 pieces x 5 tiers)
#   175-178: water bottles
#   180-190: ore items

# Basic tools
WOOD_PICKAXE, WOOD_AXE, WOOD_SWORD, WOOD_HAMMER = 100, 101, 102, 103
STONE_PICKAXE, STONE_AXE, STONE_SWORD, STONE_HAMMER = 104, 105, 106, 107
IRON_PICKAXE, IRON_AXE, IRON_SWORD, IRON_HAMMER = 108, 109, 110, 111
GOLD_PICKAXE, GOLD_AXE, GOLD_SWORD, GOLD_HAMMER = 112, 113, 114, 115
DIAMOND_PICKAXE, DIAMOND_AXE, DIAMOND_SWORD, DIAMOND_HAMMER = 116, 117, 118, 119

# Weapons / ammo
BOW, ARROW = 130, 131

# Food items
APPLE, BREAD, COOKED_MEAT, RAW_MEAT, BERRY = 140, 141, 142, 143, 144

# Misc materials
STICK, PAPER, WOOL, LEATHER, FEATHER = 150, 151, 152, 153, 154

# Water bottles
WATER_BOTTLE, WOODEN_BOTTLE, WATER_BOTTLE_FILLED, WOODEN_BOTTLE_FILLED = 175, 177, 176, 178

# Ore items (separate from ore blocks for crafting)
COAL_ITEM, IRON_ITEM, GOLD_ITEM, DIAMOND_ITEM = 180, 181, 182, 183
COPPER_ITEM, TIN_ITEM, SILVER_ITEM, MITHRIL_ITEM = 184, 185, 186, 187
RUBY_ITEM, SAPPHIRE_ITEM, EMERALD_ITEM = 188, 189, 190
ROPE = 191
TREE_SEED, PINE_SEED, GIANT_SEED, DEAD_SEED, BENT_SEED = 192, 193, 194, 195, 196

# ------------------------------------------------------------
# LIQUID SIMULATION
# Liquids are no longer baked into the tile grid as WATER/LAVA blocks.
# Instead each tile has a separate "liquid amount" (0-255) and "liquid type"
# so water/lava can flow, spread, and drain like a real cellular-automaton fluid,
# independent from the solid block underneath it.
# ------------------------------------------------------------
LIQUID_NONE = 0
LIQUID_WATER = 1
LIQUID_LAVA = 2
MAX_LIQUID = 255
MIN_LIQUID = 6          # amounts at/below this don't bother spreading sideways
LIQUID_FLOW_MAX = 48    # cap on how much moves sideways in a single tick (keeps flow gradual/visible)
LIQUID_TICK = 0.05      # seconds between simulation steps (~20 Hz, plenty smooth, cheap)
LIQUID_MAX_ACTIVE_PER_TICK = 4000  # safety cap so a big flood can't stall a frame

BLOCK_DEFS = {
    AIR:       {"name": "Air",       "color": (0, 0, 0),        "solid": False, "opaque": False, "mineable": False, "hardness": 0.0, "drops": None},
    GRASS:     {"name": "Grass",     "color": (90, 170, 70),    "solid": True,  "opaque": True,  "mineable": True,  "hardness": 0.4, "drops": DIRT},
    DIRT:      {"name": "Dirt",      "color": (134, 87, 56),    "solid": True,  "opaque": True,  "mineable": True,  "hardness": 0.4, "drops": DIRT},
    STONE:     {"name": "Stone",     "color": (110, 110, 120),  "solid": True,  "opaque": True,  "mineable": True,  "hardness": 1.2, "drops": STONE},
    WOOD:      {"name": "Wood",      "color": (95, 65, 40),     "solid": True,  "opaque": True,  "mineable": True,  "hardness": 0.8, "drops": WOOD},
    LEAVES:    {"name": "Leaves",    "color": (60, 140, 60),    "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.2, "drops": None},
    SAND:      {"name": "Sand",      "color": (220, 200, 130),  "solid": True,  "opaque": True,  "mineable": True,  "hardness": 0.3, "drops": SAND},
    WATER:     {"name": "Water",     "color": (50, 100, 200),   "solid": False, "opaque": False, "mineable": False, "hardness": 0.0, "drops": None},
    TORCH:     {"name": "Torch",     "color": (255, 200, 80),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.1, "drops": TORCH},
    COAL:      {"name": "Coal Ore",  "color": (45, 45, 45),     "solid": True,  "opaque": True,  "mineable": True,  "hardness": 1.4, "drops": COAL_ITEM},
    IRON:      {"name": "Iron Ore",  "color": (180, 150, 110),  "solid": True,  "opaque": True,  "mineable": True,  "hardness": 2.0, "drops": IRON_ITEM},
    GOLD:      {"name": "Gold Ore",  "color": (230, 200, 70),   "solid": True,  "opaque": True,  "mineable": True,  "hardness": 2.4, "drops": GOLD_ITEM},
    DIAMOND:   {"name": "Diamond Ore","color": (120, 230, 230), "solid": True,  "opaque": True,  "mineable": True,  "hardness": 3.5, "drops": DIAMOND_ITEM},
    PLANK:     {"name": "Plank",     "color": (170, 120, 70),   "solid": True,  "opaque": True,  "mineable": True,  "hardness": 0.7, "drops": PLANK},
    BRICK:     {"name": "Brick",     "color": (160, 70, 60),    "solid": True,  "opaque": True,  "mineable": True,  "hardness": 1.8, "drops": BRICK},
    GLASS:     {"name": "Glass",     "color": (200, 230, 240),  "solid": True,  "opaque": False, "mineable": True,  "hardness": 0.5, "drops": GLASS},
    TREE_TRUNK:{"name": "Tree",      "color": (95, 65, 40),     "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.8, "drops": WOOD},
    WORKBENCH: {"name": "Workbench", "color": (130, 80, 40),    "solid": False, "opaque": False, "mineable": True,  "hardness": 0.7, "drops": WORKBENCH, "interactable": True},
    BOOKSHELF: {"name": "Bookshelf", "color": (110, 70, 35),    "solid": False, "opaque": False, "mineable": True,  "hardness": 0.8, "drops": BOOKSHELF},
    LAMP:      {"name": "Lamp",      "color": (255, 240, 150),  "solid": False, "opaque": False, "mineable": True,  "hardness": 0.2, "drops": LAMP, "light": 12},
    CHEST:     {"name": "Chest",     "color": (180, 130, 60),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.8, "drops": CHEST, "interactable": True},
    # Geology layers - get progressively harder deeper down
    SANDSTONE:   {"name": "Sandstone",  "color": (210, 180, 120), "solid": True, "opaque": True, "mineable": True, "hardness": 1.0, "drops": SANDSTONE},
    LIMESTONE:   {"name": "Limestone",  "color": (200, 200, 190), "solid": True, "opaque": True, "mineable": True, "hardness": 1.5, "drops": LIMESTONE},
    GRANITE:     {"name": "Granite",    "color": (150, 130, 130), "solid": True, "opaque": True, "mineable": True, "hardness": 2.2, "drops": GRANITE},
    BASALT:      {"name": "Basalt",     "color": (60, 60, 70),    "solid": True, "opaque": True, "mineable": True, "hardness": 3.0, "drops": BASALT},
    OBSIDIAN:    {"name": "Obsidian",   "color": (30, 25, 40),    "solid": True, "opaque": True, "mineable": True, "hardness": 4.5, "drops": OBSIDIAN},
    BEDROCK:     {"name": "Bedrock",    "color": (25, 25, 30),    "solid": True, "opaque": True, "mineable": False, "hardness": 999, "drops": None},
    LAVA:        {"name": "Lava",       "color": (230, 90, 30),   "solid": False, "opaque": False, "mineable": False, "hardness": 0, "drops": None, "light": 10, "damage": 30},
    # Biome blocks
    SNOW:        {"name": "Snow",       "color": (240, 245, 255), "solid": True, "opaque": True, "mineable": True, "hardness": 0.3, "drops": SNOW},
    ICE:         {"name": "Ice",        "color": (170, 210, 240), "solid": True, "opaque": True, "mineable": True, "hardness": 0.6, "drops": ICE},
    JUNGLE_GRASS:{"name": "Jungle Grass","color": (50, 170, 60),  "solid": True, "opaque": True, "mineable": True, "hardness": 0.4, "drops": MUD},
    SAVANNA_GRASS:{"name":"Savanna Grass","color": (180, 170, 80),"solid": True, "opaque": True, "mineable": True, "hardness": 0.4, "drops": DIRT},
    MUD:         {"name": "Mud",        "color": (70, 55, 40),    "solid": True, "opaque": True, "mineable": True, "hardness": 0.5, "drops": MUD},
    CACTUS:      {"name": "Cactus",     "color": (80, 150, 70),   "solid": False, "opaque": True, "mineable": True, "hardness": 0.4, "drops": CACTUS},
    VINE:        {"name": "Vine",       "color": (40, 110, 50),   "solid": False, "opaque": False, "mineable": True, "hardness": 0.1, "drops": VINE},
    PINE_TRUNK:  {"name": "Pine Tree",  "color": (75, 55, 35),    "solid": False, "opaque": True, "mineable": True, "hardness": 0.8, "drops": WOOD},
    FLOWER:      {"name": "Flower",     "color": (220, 80, 120),  "solid": False, "opaque": False, "mineable": True, "hardness": 0.1, "drops": FLOWER},
    MARBLE:      {"name": "Marble",     "color": (230, 230, 235), "solid": True, "opaque": True, "mineable": True, "hardness": 2.0, "drops": MARBLE},
    # New ores
    COPPER_ORE:  {"name": "Copper Ore", "color": (180, 110, 70),  "solid": True, "opaque": True, "mineable": True, "hardness": 1.6, "drops": COPPER_ITEM},
    TIN_ORE:     {"name": "Tin Ore",    "color": (180, 180, 175), "solid": True, "opaque": True, "mineable": True, "hardness": 1.7, "drops": TIN_ITEM},
    SILVER_ORE:  {"name": "Silver Ore", "color": (220, 220, 230), "solid": True, "opaque": True, "mineable": True, "hardness": 2.2, "drops": SILVER_ITEM},
    MITHRIL_ORE: {"name": "Mithril Ore","color": (130, 180, 230), "solid": True, "opaque": True, "mineable": True, "hardness": 3.2, "drops": MITHRIL_ITEM},
    RUBY_ORE:    {"name": "Ruby Ore",   "color": (220, 40, 60),   "solid": True, "opaque": True, "mineable": True, "hardness": 3.0, "drops": RUBY_ITEM},
    SAPPHIRE_ORE:{"name": "Sapphire Ore","color": (40, 80, 220),  "solid": True, "opaque": True, "mineable": True, "hardness": 3.0, "drops": SAPPHIRE_ITEM},
    EMERALD_ORE: {"name": "Emerald Ore","color": (40, 200, 100),  "solid": True, "opaque": True, "mineable": True, "hardness": 3.0, "drops": EMERALD_ITEM},
    # New natural blocks
    ROCK:       {"name": "Rock",       "color": (120, 120, 130),  "solid": False, "opaque": False, "mineable": True,  "hardness": 1.5, "drops": STONE},
    SMALL_STONE:{"name": "Small Stone","color": (140, 140, 150),  "solid": False, "opaque": False, "mineable": True,  "hardness": 0.1, "drops": SMALL_STONE, "collect_rclick": True},
    GRASS_TUFT: {"name": "Grass Tuft", "color": (80, 160, 60),    "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": GRASS_TUFT, "collect_lclick": True},
    BUSH:       {"name": "Bush",       "color": (50, 130, 50),    "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.1, "drops": BUSH, "collect_lclick": True},
    BUSH_FRUIT: {"name": "Berry Bush", "color": (50, 130, 50),    "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.1, "drops": BUSH, "collect_lclick": True, "fruit_drops": 144},  # 144 = BERRY (defined later)
    # New crafting stations
    FURNACE:    {"name": "Furnace",    "color": (80, 70, 65),     "solid": False, "opaque": False, "mineable": True,  "hardness": 1.5, "drops": FURNACE, "interactable": True, "station": "furnace"},
    ANVIL:      {"name": "Anvil",      "color": (90, 90, 100),    "solid": False, "opaque": False, "mineable": True,  "hardness": 2.0, "drops": ANVIL, "interactable": True, "station": "anvil"},
    CAMPFIRE:   {"name": "Campfire",   "color": (200, 100, 40),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.3, "drops": CAMPFIRE, "interactable": True, "station": "campfire", "light": 10},
    BED:       {"name": "Bed",        "color": (180, 60, 80),    "solid": False, "opaque": False, "mineable": True,  "hardness": 0.5, "drops": BED, "interactable": True, "station": "bed"},
    # Extended vegetation
    TALL_GRASS:   {"name": "Tall Grass",  "color": (60, 150, 40),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": GRASS_TUFT, "collect_lclick": True},
    FLOWER_RED:   {"name": "Red Flower",  "color": (220, 50, 50),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.1, "drops": FLOWER_RED},
    FLOWER_YELLOW:{"name": "Yellow Flower","color": (240, 220, 50), "solid": False, "opaque": False, "mineable": True,  "hardness": 0.1, "drops": FLOWER_YELLOW},
    FLOWER_BLUE:  {"name": "Blue Flower", "color": (80, 100, 230),  "solid": False, "opaque": False, "mineable": True,  "hardness": 0.1, "drops": FLOWER_BLUE},
    FLOWER_WHITE: {"name": "White Flower","color": (240, 240, 245), "solid": False, "opaque": False, "mineable": True,  "hardness": 0.1, "drops": FLOWER_WHITE},
    TREE_GIANT:   {"name": "Giant Tree",  "color": (75, 55, 35),    "solid": False, "opaque": True,  "mineable": True,  "hardness": 1.5, "drops": WOOD},
    TREE_DEAD:    {"name": "Dead Tree",   "color": (100, 85, 70),   "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.6, "drops": WOOD},
    TREE_BENT:    {"name": "Bent Tree",   "color": (85, 60, 40),    "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.8, "drops": WOOD},
    # Leaf color variants
    LEAVES_DARK:    {"name": "Dark Leaves",    "color": (30, 100, 30),    "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.2, "drops": None},
    LEAVES_AUTUMN:  {"name": "Autumn Leaves",  "color": (200, 130, 40),   "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.2, "drops": None},
    LEAVES_RED:     {"name": "Red Leaves",     "color": (180, 50, 30),    "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.2, "drops": None},
    LEAVES_YELLOW:  {"name": "Yellow Leaves",  "color": (200, 190, 50),   "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.2, "drops": None},
    LEAVES_CHERRY:  {"name": "Cherry Blossom",  "color": (240, 150, 180),  "solid": False, "opaque": True,  "mineable": True,  "hardness": 0.2, "drops": None},
    DRIED_GRASS:  {"name": "Dried Grass",  "color": (180, 160, 80),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": DRIED_GRASS, "collect_lclick": True},
    DRIED_TALL_GRASS: {"name": "Dried Tall Grass", "color": (170, 150, 60), "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": DRIED_GRASS, "collect_lclick": True},
    # Seedling blocks (placed by tree seeds, grow into trees over 7 game days)
    SEEDLING_TREE:  {"name": "Tree Seedling",  "color": (60, 100, 40),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": TREE_SEED},
    SEEDLING_PINE:  {"name": "Pine Seedling",  "color": (40, 80, 35),    "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": PINE_SEED},
    SEEDLING_GIANT: {"name": "Giant Seedling", "color": (70, 110, 45),   "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": GIANT_SEED},
    SEEDLING_DEAD:  {"name": "Dead Seedling",  "color": (120, 100, 70),  "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": DEAD_SEED},
    SEEDLING_BENT:  {"name": "Bent Seedling",  "color": (90, 80, 45),    "solid": False, "opaque": False, "mineable": True,  "hardness": 0.0, "drops": BENT_SEED},
}

SEEDLING_TO_TRUNK = {
    SEEDLING_TREE: TREE_TRUNK, SEEDLING_PINE: PINE_TRUNK,
    SEEDLING_GIANT: TREE_GIANT, SEEDLING_DEAD: TREE_DEAD, SEEDLING_BENT: TREE_BENT,
}
SEED_TO_SEEDLING = {
    TREE_SEED: SEEDLING_TREE, PINE_SEED: SEEDLING_PINE,
    GIANT_SEED: SEEDLING_GIANT, DEAD_SEED: SEEDLING_DEAD, BENT_SEED: SEEDLING_BENT,
}
ALL_SEEDLING_TYPES = set(SEEDLING_TO_TRUNK.keys())

# All leaf block types (used for tree destruction, rendering, etc.)
ALL_LEAF_TYPES = {LEAVES, LEAVES_DARK, LEAVES_AUTUMN, LEAVES_RED, LEAVES_YELLOW, LEAVES_CHERRY}

# Remove the duplicate NUM_BLOCKS line below
BLOCK_COLOR_ARRAY = None  # built later for minimap

# Pre-compute block color lookup for fast minimap rendering
_BLOCK_COLOR_LOOKUP = None
_WALL_COLOR_LOOKUP = None

# ============================================================
# WALLS (background blocks)
# ============================================================

WALL_NONE, WALL_DIRT, WALL_STONE, WALL_WOOD, WALL_SANDSTONE, WALL_GRANITE, WALL_MUD = 0, 1, 2, 3, 4, 5, 6
WALL_DEFS = {
    WALL_DIRT:     {"name": "Dirt Wall",     "color": (70, 48, 30)},
    WALL_STONE:    {"name": "Stone Wall",    "color": (55, 55, 65)},
    WALL_WOOD:     {"name": "Wood Wall",     "color": (60, 42, 25)},
    WALL_SANDSTONE:{"name": "Sandstone Wall","color": (140, 110, 70)},
    WALL_GRANITE:  {"name": "Granite Wall",  "color": (90, 80, 80)},
    WALL_MUD:      {"name": "Mud Wall",      "color": (50, 40, 30)},
}
WALL_HARDNESS = {WALL_DIRT: 0.3, WALL_STONE: 0.8, WALL_WOOD: 0.5,
                 WALL_SANDSTONE: 0.6, WALL_GRANITE: 1.2, WALL_MUD: 0.4}

# ============================================================
# ITEMS: TOOL/WEAPON/FOOD/MATERIAL DEFINITIONS
# ============================================================

# (Item ID constants are already defined above, before BLOCK_DEFS)

TOOL_DEFS = {
    WOOD_PICKAXE:    {"name": "Wooden Pickaxe",  "type": "pickaxe", "tier": "wood",    "mine_mult": 2.0, "damage": 4,  "durability": 60},
    WOOD_AXE:        {"name": "Wooden Axe",      "type": "axe",     "tier": "wood",    "mine_mult": 2.5, "damage": 3,  "durability": 60},
    WOOD_SWORD:      {"name": "Wooden Sword",    "type": "sword",   "tier": "wood",    "mine_mult": 1.0, "damage": 10, "durability": 100},
    WOOD_HAMMER:     {"name": "Wooden Hammer",   "type": "hammer",  "tier": "wood",    "mine_mult": 1.5, "damage": 2,  "durability": 60},
    STONE_PICKAXE:   {"name": "Stone Pickaxe",   "type": "pickaxe", "tier": "stone",   "mine_mult": 3.0, "damage": 6,  "durability": 150},
    STONE_AXE:       {"name": "Stone Axe",       "type": "axe",     "tier": "stone",   "mine_mult": 3.5, "damage": 5,  "durability": 150},
    STONE_SWORD:     {"name": "Stone Sword",     "type": "sword",   "tier": "stone",   "mine_mult": 1.0, "damage": 16, "durability": 200},
    STONE_HAMMER:    {"name": "Stone Hammer",    "type": "hammer",  "tier": "stone",   "mine_mult": 2.5, "damage": 4,  "durability": 150},
    IRON_PICKAXE:    {"name": "Iron Pickaxe",    "type": "pickaxe", "tier": "iron",    "mine_mult": 4.5, "damage": 9,  "durability": 300},
    IRON_AXE:        {"name": "Iron Axe",        "type": "axe",     "tier": "iron",    "mine_mult": 5.0, "damage": 8,  "durability": 300},
    IRON_SWORD:      {"name": "Iron Sword",      "type": "sword",   "tier": "iron",    "mine_mult": 1.0, "damage": 24, "durability": 400},
    IRON_HAMMER:     {"name": "Iron Hammer",     "type": "hammer",  "tier": "iron",    "mine_mult": 3.5, "damage": 6,  "durability": 300},
    GOLD_PICKAXE:    {"name": "Gold Pickaxe",    "type": "pickaxe", "tier": "gold",    "mine_mult": 6.0, "damage": 10, "durability": 250},
    GOLD_AXE:        {"name": "Gold Axe",        "type": "axe",     "tier": "gold",    "mine_mult": 6.5, "damage": 9,  "durability": 250},
    GOLD_SWORD:      {"name": "Gold Sword",      "type": "sword",   "tier": "gold",    "mine_mult": 1.0, "damage": 32, "durability": 350},
    GOLD_HAMMER:     {"name": "Gold Hammer",     "type": "hammer",  "tier": "gold",    "mine_mult": 4.5, "damage": 8,  "durability": 250},
    DIAMOND_PICKAXE: {"name": "Diamond Pickaxe", "type": "pickaxe", "tier": "diamond", "mine_mult": 8.0, "damage": 14, "durability": 600},
    DIAMOND_AXE:     {"name": "Diamond Axe",     "type": "axe",     "tier": "diamond", "mine_mult": 8.5, "damage": 12, "durability": 600},
    DIAMOND_SWORD:   {"name": "Diamond Sword",   "type": "sword",   "tier": "diamond", "mine_mult": 1.0, "damage": 42, "durability": 800},
    DIAMOND_HAMMER:  {"name": "Diamond Hammer",  "type": "hammer",  "tier": "diamond", "mine_mult": 6.0, "damage": 10, "durability": 600},
}

WEAPON_DEFS = {
    BOW: {"name": "Bow", "type": "bow", "damage": 18, "durability": 200, "ammo": ARROW},
}

# Items that don't stack (each occupies its own slot)
NON_STACKABLE = set([BOW])  # tools added dynamically below
for _tid in TOOL_DEFS: NON_STACKABLE.add(_tid)
# armor and bed added below after their definitions

FOOD_DEFS = {
    APPLE:       {"name": "Apple",        "heal": 15, "color": (220, 60, 60)},
    BREAD:       {"name": "Bread",        "heal": 30, "color": (230, 190, 100)},
    COOKED_MEAT: {"name": "Cooked Meat",  "heal": 40, "color": (180, 90, 60)},
    RAW_MEAT:    {"name": "Raw Meat",     "heal": 5,  "color": (200, 80, 80)},  # low heal, risky
    BERRY:       {"name": "Berry",       "heal": 8,  "color": (180, 40, 80)},
}

MISC_DEFS = {
    STICK:                {"name": "Stick",          "color": (160, 110, 60)},
    PAPER:                {"name": "Paper",          "color": (240, 240, 220)},
    WOOL:                 {"name": "Wool",           "color": (230, 230, 230)},
    LEATHER:              {"name": "Leather",        "color": (120, 80, 50)},
    FEATHER:              {"name": "Feather",        "color": (220, 220, 200)},
    ROPE:                 {"name": "Rope",           "color": (160, 140, 100)},
    TREE_SEED:            {"name": "Tree Seed",      "color": (60, 120, 40)},
    PINE_SEED:            {"name": "Pine Seed",      "color": (40, 100, 50)},
    GIANT_SEED:           {"name": "Giant Seed",     "color": (80, 130, 50)},
    DEAD_SEED:            {"name": "Dead Seed",      "color": (140, 120, 80)},
    BENT_SEED:            {"name": "Bent Seed",      "color": (100, 90, 50)},
    WATER_BOTTLE:         {"name": "Water Bottle",   "color": (180, 200, 220), "drink": 0},
    WATER_BOTTLE_FILLED:  {"name": "Water Bottle (Filled)", "color": (80, 130, 200), "drink": 35},
    WOODEN_BOTTLE:        {"name": "Wooden Bottle",  "color": (150, 110, 60),  "drink": 0},
    WOODEN_BOTTLE_FILLED: {"name": "Wooden Bottle (Filled)", "color": (70, 110, 170), "drink": 30},
    # Ore items
    COAL_ITEM:            {"name": "Coal",           "color": (45, 45, 45)},
    IRON_ITEM:            {"name": "Iron Ore",       "color": (180, 150, 110)},
    GOLD_ITEM:            {"name": "Gold Ore",       "color": (230, 200, 70)},
    DIAMOND_ITEM:         {"name": "Diamond",        "color": (120, 230, 230)},
    COPPER_ITEM:          {"name": "Copper Ore",     "color": (180, 110, 70)},
    TIN_ITEM:             {"name": "Tin Ore",        "color": (180, 180, 175)},
    SILVER_ITEM:          {"name": "Silver Ore",     "color": (220, 220, 230)},
    MITHRIL_ITEM:         {"name": "Mithril Ore",    "color": (130, 180, 230)},
    RUBY_ITEM:            {"name": "Ruby",           "color": (220, 40, 60)},
    SAPPHIRE_ITEM:        {"name": "Sapphire",       "color": (40, 80, 220)},
    EMERALD_ITEM:         {"name": "Emerald",        "color": (40, 200, 100)},
}

# Armor item IDs: 155-174 (4 pieces x 5 tiers)
(WOOD_HELMET, WOOD_CHESTPLATE, WOOD_LEGGINGS, WOOD_BOOTS,
 STONE_HELMET, STONE_CHESTPLATE, STONE_LEGGINGS, STONE_BOOTS,
 IRON_HELMET, IRON_CHESTPLATE, IRON_LEGGINGS, IRON_BOOTS,
 GOLD_HELMET, GOLD_CHESTPLATE, GOLD_LEGGINGS, GOLD_BOOTS,
 DIAMOND_HELMET, DIAMOND_CHESTPLATE, DIAMOND_LEGGINGS, DIAMOND_BOOTS) = range(155, 175)

ARMOR_DEFS = {
    # format: defense, tier, name
    WOOD_HELMET:     {"name": "Wood Helmet",      "defense": 2, "tier": "wood"},
    WOOD_CHESTPLATE: {"name": "Wood Chestplate",   "defense": 4, "tier": "wood"},
    WOOD_LEGGINGS:   {"name": "Wood Leggings",     "defense": 3, "tier": "wood"},
    WOOD_BOOTS:      {"name": "Wood Boots",        "defense": 1, "tier": "wood"},
    STONE_HELMET:     {"name": "Stone Helmet",      "defense": 3, "tier": "stone"},
    STONE_CHESTPLATE: {"name": "Stone Chestplate",   "defense": 6, "tier": "stone"},
    STONE_LEGGINGS:   {"name": "Stone Leggings",     "defense": 4, "tier": "stone"},
    STONE_BOOTS:      {"name": "Stone Boots",        "defense": 2, "tier": "stone"},
    IRON_HELMET:     {"name": "Iron Helmet",      "defense": 5, "tier": "iron"},
    IRON_CHESTPLATE: {"name": "Iron Chestplate",   "defense": 8, "tier": "iron"},
    IRON_LEGGINGS:   {"name": "Iron Leggings",     "defense": 6, "tier": "iron"},
    IRON_BOOTS:      {"name": "Iron Boots",        "defense": 3, "tier": "iron"},
    GOLD_HELMET:     {"name": "Gold Helmet",      "defense": 6, "tier": "gold"},
    GOLD_CHESTPLATE: {"name": "Gold Chestplate",   "defense": 10, "tier": "gold"},
    GOLD_LEGGINGS:   {"name": "Gold Leggings",     "defense": 8, "tier": "gold"},
    GOLD_BOOTS:      {"name": "Gold Boots",        "defense": 4, "tier": "gold"},
    DIAMOND_HELMET:     {"name": "Diamond Helmet",      "defense": 8, "tier": "diamond"},
    DIAMOND_CHESTPLATE: {"name": "Diamond Chestplate",   "defense": 14, "tier": "diamond"},
    DIAMOND_LEGGINGS:   {"name": "Diamond Leggings",     "defense": 10, "tier": "diamond"},
    DIAMOND_BOOTS:      {"name": "Diamond Boots",        "defense": 5, "tier": "diamond"},
}
for _aid in ARMOR_DEFS: NON_STACKABLE.add(_aid)
NON_STACKABLE.add(BED)

TIER_COLORS = {
    "wood": (140, 95, 50), "stone": (140, 140, 150), "iron": (200, 200, 210),
    "gold": (240, 200, 80), "diamond": (130, 230, 240),
}

# Maximum item ID + 1 (for color array)
NUM_ITEMS = 200

def is_ore_item(item_id): return 180 <= item_id <= 190

def is_tool(item_id): return 100 <= item_id < 120
def is_weapon(item_id): return item_id == BOW  # only the bow itself; arrows are ammo
def is_ammo(item_id): return item_id == ARROW
def is_food(item_id): return 140 <= item_id < 150
def is_misc(item_id): return 150 <= item_id < 155 or item_id in (WATER_BOTTLE, WOODEN_BOTTLE, WATER_BOTTLE_FILLED, WOODEN_BOTTLE_FILLED) or 180 <= item_id <= 196
def is_block(item_id): return 0 <= item_id < NUM_BLOCKS
def is_armor(item_id): return 155 <= item_id < 175
def is_bed(item_id): return item_id == BED

def get_item_name(item_id):
    if is_tool(item_id): return TOOL_DEFS[item_id]["name"]
    if is_weapon(item_id): return WEAPON_DEFS[item_id]["name"]
    if is_ammo(item_id): return "Arrow"
    if is_armor(item_id): return ARMOR_DEFS[item_id]["name"]
    if is_food(item_id): return FOOD_DEFS[item_id]["name"]
    if is_misc(item_id): return MISC_DEFS.get(item_id, {"name": "???"})["name"]
    return BLOCK_DEFS[item_id]["name"]

def get_item_color(item_id):
    if is_tool(item_id): return TIER_COLORS[TOOL_DEFS[item_id]["tier"]]
    if is_weapon(item_id): return (150, 100, 60)
    if is_ammo(item_id): return (200, 200, 200)
    if is_armor(item_id): return TIER_COLORS[ARMOR_DEFS[item_id]["tier"]]
    if is_food(item_id): return FOOD_DEFS[item_id]["color"]
    if is_misc(item_id): return MISC_DEFS[item_id]["color"]
    return BLOCK_DEFS[item_id]["color"][:3]

# ============================================================
# BIOMES - regions across the world width
# ============================================================

BIOME_SEA, BIOME_TUNDRA, BIOME_GRASSLAND, BIOME_FOREST, BIOME_JUNGLE, BIOME_SAVANNA, BIOME_DESERT = range(7)

BIOME_NAMES = {
    BIOME_SEA: "Sea", BIOME_TUNDRA: "Tundra", BIOME_GRASSLAND: "Grassland",
    BIOME_FOREST: "Forest", BIOME_JUNGLE: "Jungle", BIOME_SAVANNA: "Savanna", BIOME_DESERT: "Desert",
}

# Biome layout as (type, start_frac, end_frac). Spans the world width.
BIOME_LAYOUT = [
    (BIOME_SEA,       0.00, 0.04),
    (BIOME_TUNDRA,    0.04, 0.18),
    (BIOME_GRASSLAND, 0.18, 0.40),
    (BIOME_FOREST,    0.40, 0.55),
    (BIOME_JUNGLE,    0.55, 0.72),
    (BIOME_SAVANNA,   0.72, 0.86),
    (BIOME_DESERT,    0.86, 0.96),
    (BIOME_SEA,       0.96, 1.00),
]

def biome_at(x: int, w: int) -> int:
    """Return biome type for column x in world of width w."""
    frac = x / max(1, w)
    for biome, start, end in BIOME_LAYOUT:
        if start <= frac < end:
            return biome
    return BIOME_GRASSLAND

# Biome surface block (top tile of ground)
BIOME_SURFACE_BLOCK = {
    BIOME_SEA: SAND,
    BIOME_TUNDRA: SNOW,
    BIOME_GRASSLAND: GRASS,
    BIOME_FOREST: GRASS,
    BIOME_JUNGLE: JUNGLE_GRASS,
    BIOME_SAVANNA: SAVANNA_GRASS,
    BIOME_DESERT: SAND,
}

# Biome subsurface block (just below surface)
BIOME_SUBSURFACE = {
    BIOME_SEA: SAND,
    BIOME_TUNDRA: DIRT,
    BIOME_GRASSLAND: DIRT,
    BIOME_FOREST: DIRT,
    BIOME_JUNGLE: MUD,
    BIOME_SAVANNA: DIRT,
    BIOME_DESERT: SAND,
}

# Biome wall type
BIOME_WALL = {
    BIOME_SEA: WALL_SANDSTONE,
    BIOME_TUNDRA: WALL_DIRT,
    BIOME_GRASSLAND: WALL_DIRT,
    BIOME_FOREST: WALL_DIRT,
    BIOME_JUNGLE: WALL_MUD,
    BIOME_SAVANNA: WALL_DIRT,
    BIOME_DESERT: WALL_SANDSTONE,
}

# Geology layer depths (relative to surface). Layer = (block, start_depth, end_depth)
GEOLOGY_LAYERS = [
    (STONE,    25, 300),      # shallow stone
    (LIMESTONE, 300, 1000),   # sedimentary
    (GRANITE,   1000, 2000),  # igneous
    (BASALT,    2000, 3000),  # volcanic
    (OBSIDIAN,  3000, 3500),  # near lava
    (BEDROCK,   3500, 99999), # unbreakable bottom
]

# Ore distribution: (ore, probability_per_column, cluster, min_depth, max_depth)
ORE_DISTRIBUTION = [
    (COAL,       0.30, 4, 10, 2500),
    (COPPER_ORE, 0.10, 3, 30, 800),
    (TIN_ORE,    0.09, 3, 30, 800),
    (IRON,       0.12, 3, 50, 1500),
    (SILVER_ORE, 0.05, 2, 300, 2200),
    (GOLD,       0.045, 2, 500, 2800),
    (MARBLE,     0.03, 3, 200, 1200),  # decorative stone pockets
    (MITHRIL_ORE,0.025, 2, 1200, 3200),
    (DIAMOND,    0.02, 2, 1800, 3500),
    (RUBY_ORE,   0.012, 1, 1200, 3500),
    (SAPPHIRE_ORE,0.012, 1, 1200, 3500),
    (EMERALD_ORE, 0.012, 1, 1200, 3500),
]

# ============================================================
# RECIPES
# ============================================================

# Basic recipes (always available in inventory crafting)
RECIPES_BASIC = [
    {"result": (PLANK, 4),          "materials": [(WOOD, 1)],              "name": "Planks"},
    {"result": (TORCH, 4),          "materials": [(PLANK, 1), (COAL, 1)],  "name": "Torches"},
    {"result": (ROPE, 3),           "materials": [(DRIED_GRASS, 3)],       "name": "Rope"},
    {"result": (WORKBENCH, 1),      "materials": [(PLANK, 4)],             "name": "Workbench"},
    {"result": (WOOD_PICKAXE, 1),   "materials": [(WOOD, 1), (DRIED_GRASS, 1)], "name": "Wooden Pickaxe"},
    {"result": (WOOD_AXE, 1),       "materials": [(WOOD, 1), (DRIED_GRASS, 1)], "name": "Wooden Axe"},
    {"result": (WOOD_SWORD, 1),     "materials": [(WOOD, 1), (DRIED_GRASS, 1)], "name": "Wooden Sword"},
    {"result": (WOOD_HAMMER, 1),    "materials": [(WOOD, 1), (DRIED_GRASS, 1)], "name": "Wooden Hammer"},
]

# Workbench recipes (require nearby workbench)
RECIPES_WORKBENCH = [
    {"result": (BRICK, 2),          "materials": [(STONE, 2)],                       "name": "Bricks"},
    {"result": (GLASS, 2),          "materials": [(SAND, 2), (COAL, 1)],             "name": "Glass"},
    {"result": (BOOKSHELF, 1),      "materials": [(PLANK, 4), (PAPER, 3)],           "name": "Bookshelf"},
    {"result": (LAMP, 1),           "materials": [(PLANK, 1), (COAL, 1), (GLASS, 1)], "name": "Lamp"},
    {"result": (CHEST, 1),          "materials": [(PLANK, 8)],                       "name": "Chest"},
    {"result": (PAPER, 3),          "materials": [(WOOD, 3)],                        "name": "Paper"},
    {"result": (WATER_BOTTLE, 1),   "materials": [(PLANK, 2), (GLASS, 1)],          "name": "Water Bottle (empty)"},
    {"result": (WOODEN_BOTTLE, 1),  "materials": [(PLANK, 4)],                       "name": "Wooden Bottle (early water)"},  # early game, no glass needed
    {"result": (STONE_PICKAXE, 1),  "materials": [(WOOD, 1), (STONE, 5), (DRIED_GRASS, 1)], "name": "Stone Pickaxe"},
    {"result": (STONE_AXE, 1),      "materials": [(WOOD, 1), (STONE, 5), (DRIED_GRASS, 1)], "name": "Stone Axe"},
    {"result": (STONE_SWORD, 1),    "materials": [(WOOD, 1), (STONE, 5), (DRIED_GRASS, 1)], "name": "Stone Sword"},
    {"result": (STONE_HAMMER, 1),   "materials": [(WOOD, 1), (STONE, 5), (DRIED_GRASS, 1)], "name": "Stone Hammer"},
    {"result": (IRON_PICKAXE, 1),   "materials": [(WOOD, 1), (IRON_ITEM, 5), (ROPE, 1)], "name": "Iron Pickaxe"},
    {"result": (IRON_AXE, 1),       "materials": [(WOOD, 1), (IRON_ITEM, 5), (ROPE, 1)], "name": "Iron Axe"},
    {"result": (IRON_SWORD, 1),     "materials": [(WOOD, 1), (IRON_ITEM, 5), (ROPE, 1)], "name": "Iron Sword"},
    {"result": (IRON_HAMMER, 1),    "materials": [(WOOD, 1), (IRON_ITEM, 5), (ROPE, 1)], "name": "Iron Hammer"},
    {"result": (GOLD_PICKAXE, 1),   "materials": [(WOOD, 1), (GOLD_ITEM, 5), (ROPE, 1)], "name": "Gold Pickaxe"},
    {"result": (GOLD_AXE, 1),       "materials": [(WOOD, 1), (GOLD_ITEM, 5), (ROPE, 1)], "name": "Gold Axe"},
    {"result": (GOLD_SWORD, 1),     "materials": [(WOOD, 1), (GOLD_ITEM, 5), (ROPE, 1)], "name": "Gold Sword"},
    {"result": (GOLD_HAMMER, 1),    "materials": [(WOOD, 1), (GOLD_ITEM, 5), (ROPE, 1)], "name": "Gold Hammer"},
    {"result": (DIAMOND_PICKAXE, 1),"materials": [(WOOD, 1), (DIAMOND_ITEM, 5), (ROPE, 1)], "name": "Diamond Pickaxe"},
    {"result": (DIAMOND_AXE, 1),    "materials": [(WOOD, 1), (DIAMOND_ITEM, 5), (ROPE, 1)], "name": "Diamond Axe"},
    {"result": (DIAMOND_SWORD, 1),  "materials": [(WOOD, 1), (DIAMOND_ITEM, 5), (ROPE, 1)], "name": "Diamond Sword"},
    {"result": (DIAMOND_HAMMER, 1), "materials": [(WOOD, 1), (DIAMOND_ITEM, 5), (ROPE, 1)], "name": "Diamond Hammer"},
    {"result": (BOW, 1),            "materials": [(PLANK, 3), (STICK, 3)],           "name": "Bow"},
    {"result": (ARROW, 4),          "materials": [(STICK, 1), (STONE, 1)],           "name": "Arrows"},
    {"result": (APPLE, 1),          "materials": [(PLANK, 2)],                       "name": "Apple"},  # crafted from planks (placeholder)
    # Cooking & animal products
    {"result": (COOKED_MEAT, 1),    "materials": [(RAW_MEAT, 1), (COAL, 1)],         "name": "Cook Meat"},
    {"result": (BREAD, 1),          "materials": [(PLANK, 3)],                        "name": "Bread"},
    # Building blocks from new geology
    {"result": (BRICK, 4),          "materials": [(SANDSTONE, 4)],                   "name": "Sandstone Bricks"},
    {"result": (BRICK, 2),          "materials": [(LIMESTONE, 2)],                   "name": "Marble Bricks"},
    {"result": (BRICK, 4),          "materials": [(GRANITE, 4)],                     "name": "Granite Bricks"},
    {"result": (BRICK, 4),          "materials": [(BASALT, 4)],                      "name": "Basalt Bricks"},
    # New crafting stations - crafted at workbench
    {"result": (FURNACE, 1),        "materials": [(STONE, 8), (COAL, 1)],            "name": "Furnace"},
    {"result": (ANVIL, 1),          "materials": [(IRON_ITEM, 5)],                        "name": "Anvil"},
    {"result": (CAMPFIRE, 1),       "materials": [(WOOD, 3), (STICK, 2)],            "name": "Campfire"},
    {"result": (BED, 1),            "materials": [(PLANK, 6), (WOOL, 3)],             "name": "Bed"},
]

# Furnace recipes (require furnace - smelting & advanced cooking)
RECIPES_FURNACE = [
    {"result": (BRICK, 4),          "materials": [(SAND, 4)],                        "name": "Smelt Bricks"},
    {"result": (GLASS, 4),          "materials": [(SAND, 4)],                        "name": "Smelt Glass"},
    {"result": (IRON, 1),           "materials": [(IRON, 0)],                        "name": "(smelts automatically)"},  # placeholder, removed below
]

# Clean up placeholder - furnace actually just cooks meat and smelts sand
RECIPES_FURNACE = [
    {"result": (COOKED_MEAT, 1),    "materials": [(RAW_MEAT, 1)],                    "name": "Cook Meat"},
    {"result": (BRICK, 4),          "materials": [(SAND, 4)],                        "name": "Smelt Bricks"},
    {"result": (GLASS, 4),          "materials": [(SAND, 4)],                        "name": "Smelt Glass"},
    {"result": (BREAD, 1),          "materials": [(PLANK, 2)],                       "name": "Bake Bread"},
    {"result": (IRON_ITEM, 1),      "materials": [(IRON, 1)],                        "name": "Smelt Iron"},
    {"result": (GOLD_ITEM, 1),      "materials": [(GOLD, 1)],                        "name": "Smelt Gold"},
    {"result": (DIAMOND_ITEM, 1),   "materials": [(DIAMOND, 1)],                     "name": "Refine Diamond"},
    {"result": (COPPER_ITEM, 1),    "materials": [(COPPER_ORE, 1)],                  "name": "Smelt Copper"},
    {"result": (TIN_ITEM, 1),       "materials": [(TIN_ORE, 1)],                     "name": "Smelt Tin"},
    {"result": (SILVER_ITEM, 1),    "materials": [(SILVER_ORE, 1)],                  "name": "Smelt Silver"},
    {"result": (MITHRIL_ITEM, 1),   "materials": [(MITHRIL_ORE, 1)],                 "name": "Smelt Mithril"},
    {"result": (RUBY_ITEM, 1),      "materials": [(RUBY_ORE, 1)],                    "name": "Refine Ruby"},
    {"result": (SAPPHIRE_ITEM, 1),  "materials": [(SAPPHIRE_ORE, 1)],                "name": "Refine Sapphire"},
    {"result": (EMERALD_ITEM, 1),   "materials": [(EMERALD_ORE, 1)],                 "name": "Refine Emerald"},
    {"result": (COAL_ITEM, 1),      "materials": [(COAL, 1)],                        "name": "Refine Coal"},
]

# Furnace fuel burn times (seconds per item)
FUEL_BURN_TIME = {
    STICK: 5.0, WOOD: 15.0, PLANK: 12.0, COAL: 30.0, COAL_ITEM: 30.0,
    CACTUS: 8.0, LEAVES: 2.0, BUSH: 3.0, GRASS_TUFT: 1.5, SAPPHIRE_ORE: 0,
}
FURNACE_COOK_TIME = 5.0  # seconds to complete one cook/smelting operation

# Anvil recipes (require anvil - tool repair & advanced gear)
RECIPES_ANVIL = [
    # Iron armor
    {"result": (IRON_HELMET, 1),     "materials": [(IRON_ITEM, 5), (PLANK, 2)],                   "name": "Iron Helmet"},
    {"result": (IRON_CHESTPLATE, 1), "materials": [(IRON_ITEM, 8), (PLANK, 2)],                   "name": "Iron Chestplate"},
    {"result": (IRON_LEGGINGS, 1),   "materials": [(IRON_ITEM, 7), (PLANK, 2)],                   "name": "Iron Leggings"},
    {"result": (IRON_BOOTS, 1),      "materials": [(IRON_ITEM, 4), (PLANK, 2)],                   "name": "Iron Boots"},
    # Gold armor
    {"result": (GOLD_HELMET, 1),     "materials": [(GOLD_ITEM, 5), (PLANK, 2)],                   "name": "Gold Helmet"},
    {"result": (GOLD_CHESTPLATE, 1), "materials": [(GOLD_ITEM, 8), (PLANK, 2)],                   "name": "Gold Chestplate"},
    {"result": (GOLD_LEGGINGS, 1),   "materials": [(GOLD_ITEM, 7), (PLANK, 2)],                   "name": "Gold Leggings"},
    {"result": (GOLD_BOOTS, 1),      "materials": [(GOLD_ITEM, 4), (PLANK, 2)],                   "name": "Gold Boots"},
    # Diamond armor
    {"result": (DIAMOND_HELMET, 1),     "materials": [(DIAMOND_ITEM, 5), (PLANK, 2)],               "name": "Diamond Helmet"},
    {"result": (DIAMOND_CHESTPLATE, 1), "materials": [(DIAMOND_ITEM, 8), (PLANK, 2)],               "name": "Diamond Chestplate"},
    {"result": (DIAMOND_LEGGINGS, 1),   "materials": [(DIAMOND_ITEM, 7), (PLANK, 2)],               "name": "Diamond Leggings"},
    {"result": (DIAMOND_BOOTS, 1),      "materials": [(DIAMOND_ITEM, 4), (PLANK, 2)],               "name": "Diamond Boots"},
]

# Campfire recipes (require campfire - basic cooking + light)
RECIPES_CAMPFIRE = [
    {"result": (COOKED_MEAT, 1),    "materials": [(RAW_MEAT, 1)],                    "name": "Cook Meat"},
    {"result": (TORCH, 2),          "materials": [(STICK, 1), (COAL, 1)],            "name": "Char Torches"},
]

# ============================================================
# ITEM STACK & INVENTORY
# ============================================================

@dataclass
class ItemStack:
    item_id: int
    count: int = 1
    durability: Optional[int] = None
    def max_stack(self):
        if self.item_id in NON_STACKABLE: return 1
        return 99

class Inventory:
    def __init__(self, size=50):
        self.slots: List[Optional[ItemStack]] = [None] * size
        self.held: Optional[ItemStack] = None

    def add(self, item_id, count=1, durability=None):
        # Non-stackable items (tools, bow) each go in their own slot
        if item_id in NON_STACKABLE:
            for _ in range(count):
                placed = False
                for i, s in enumerate(self.slots):
                    if s is None:
                        if is_tool(item_id):
                            max_d = TOOL_DEFS[item_id]["durability"]
                        elif is_weapon(item_id):
                            max_d = WEAPON_DEFS[item_id]["durability"]
                        else:
                            max_d = None  # armor, bed, etc. have no durability
                        self.slots[i] = ItemStack(item_id, 1, durability or max_d)
                        placed = True; break
                if not placed: return count
            return 0
        for s in self.slots:
            if s and s.item_id == item_id and s.count < 99:
                add = min(count, 99 - s.count); s.count += add; count -= add
                if count <= 0: return 0
        for i, s in enumerate(self.slots):
            if s is None:
                add = min(count, 99); self.slots[i] = ItemStack(item_id, add); count -= add
                if count <= 0: return 0
        return count

    def remove(self, item_id, count=1):
        total = sum(s.count for s in self.slots if s and s.item_id == item_id)
        if total < count: return False
        for i, s in enumerate(self.slots):
            if s and s.item_id == item_id:
                take = min(count, s.count); s.count -= take; count -= take
                if s.count <= 0: self.slots[i] = None
                if count <= 0: return True
        return True

    def count(self, item_id): return sum(s.count for s in self.slots if s and s.item_id == item_id)
    def has_materials(self, mats): return all(self.count(i) >= q for i, q in mats)
    def consume_materials(self, mats):
        for i, q in mats: self.remove(i, q)

    def to_dict(self):
        return [{"id": s.item_id, "count": s.count, "dur": s.durability} if s else None for s in self.slots]

    @staticmethod
    def from_dict(data):
        inv = Inventory(len(data))
        for i, entry in enumerate(data):
            if entry:
                inv.slots[i] = ItemStack(entry["id"], entry["count"], entry.get("dur"))
        return inv

# ============================================================
# WORLD
# ============================================================

class World:
    """Dict-based world with lazy partial-column generation.
    Columns are generated in two phases:
    1. Surface phase: generates 0..max(surface+200, 300) — fast, for surface play
    2. Deep phase: extends downward when player goes deeper — triggered lazily
    Only generated Y-ranges are stored; ungenerated tiles return AIR."""

    def __init__(self, w, h, seed):
        self.w, self.h, self.seed = w, h, seed
        # Dict-based column storage: {x: bytearray(h)}
        # Columns are created with full height but only filled up to generated_y[x]
        self.tile_columns: Dict[int, list] = {}
        self.wall_columns: Dict[int, list] = {}
        # OPTIMIZED: use numpy arrays instead of Python lists (saves ~8MB, better cache)
        self.surface_y = np.full(w, SURFACE, dtype=np.int32)
        self.sky_heights = np.full(w, h, dtype=np.int32)
        self.biomes = np.full(w, BIOME_GRASSLAND, dtype=np.uint8)
        self.generated_set = set()  # set of generated column x values
        self.generated_depth: Dict[int, int] = {}  # x -> max Y generated (exclusive)
        self.rng = random.Random(seed)
        # Liquid simulation storage: sparse, only columns that ever contain liquid get an entry.
        self.liquid_amount: Dict[int, bytearray] = {}   # 0-255 fill amount per tile
        self.liquid_type: Dict[int, bytearray] = {}     # LIQUID_NONE / LIQUID_WATER / LIQUID_LAVA
        self.active_liquids = set()  # (x, y) cells that still need simulating; empty = everything at rest
        # Pre-compute cheap per-column metadata (surface height + biome) for ALL columns
        self._precompute_surface()
        self._assign_biomes()
        # Do NOT generate tiles here - done lazily per column

    # ---- precomputation (cheap, runs for all columns) ----
    def _precompute_surface(self):
        """Compute surface heights using OpenSimplex coherent noise (falls back to
        layered sine waves if opensimplex is not installed).
        Produces natural-looking coastlines, valleys, rolling hills, and mountain ranges
        while remaining fully deterministic from the world seed."""
        # Keep the active terrain profile aligned with the documented, stable
        # layered-sine specification. OpenSimplex remains optional for future
        # experiments, but must not alter the persisted world-layer contract.
        self.surface_y = self._precompute_surface_sine()
        # Smooth with moving average (vectorized)
        padded = np.pad(self.surface_y, 2, mode='edge')
        self.surface_y = (padded[:-4] + padded[1:-3] + padded[2:-2] + padded[3:-1] + padded[4:]) // 5
        # Layer occasional mesa-style elevation steps ("cliffs") on top of the smooth rolling
        # hills above, so the surface isn't just gentle bumps everywhere.
        self.surface_y = (self.surface_y + self._compute_plateaus()).astype(np.int32)

    def _precompute_surface_opensimplex(self):
        """Use OpenSimplex noise for natural, coherent terrain.
        Multiple octaves create realistic coastlines, valleys, and mountain ranges.

        BUG FIX: Previously `opensimplex.seed(self.seed)` was called ONCE before the
        chunk loop, but subsequent `opensimplex.seed(self.seed + N)` calls inside the
        loop overwrote the global state. As a result, the octave-1 noise (n1) was
        evaluated with the WRONG seed for every chunk after the first — producing a
        hard terrain discontinuity at every 5000-tile chunk boundary (x=5000, 10000,
        15000, …). This is what caused the world to look "corrupted" past a certain
        point. Fix: re-seed before each n1 evaluation so the global state is always
        correct for that octave."""
        # Generate chunk by chunk to avoid memory issues with 100k-wide worlds
        CHUNK = 5000
        ys = np.empty(self.w, dtype=np.float64)
        for start in range(0, self.w, CHUNK):
            end = min(start + CHUNK, self.w)
            chunk_xs = np.arange(start, end, dtype=np.float64)
            # Octave 1: continental scale (very large features)
            opensimplex.seed(self.seed)      # <-- FIX: re-seed every iteration
            n1 = opensimplex.noise2array(chunk_xs * 0.0008, np.array([0.0]))[0] * 30
            # Octave 2: regional hills
            opensimplex.seed(self.seed + 1)
            n2 = opensimplex.noise2array(chunk_xs * 0.003, np.array([0.0]))[0] * 15
            # Octave 3: local rolling terrain
            opensimplex.seed(self.seed + 2)
            n3 = opensimplex.noise2array(chunk_xs * 0.01, np.array([0.0]))[0] * 7
            # Octave 4: small detail bumps
            opensimplex.seed(self.seed + 3)
            n4 = opensimplex.noise2array(chunk_xs * 0.04, np.array([0.0]))[0] * 2.5
            # Combine octaves
            chunk_ys = SURFACE + n1 + n2 + n3 + n4
            ys[start:end] = chunk_ys
        return ys.astype(np.int32)

    def _precompute_surface_sine(self):
        """Fallback: layered sine waves (original method)."""
        xs = np.arange(self.w, dtype=np.float64)
        ys = (SURFACE + np.sin(xs * 0.025 + 0.3) * 5
              + np.sin(xs * 0.07 + 1.7) * 2.5
              + np.sin(xs * 0.15 + 4.1) * 1.2)
        return ys.astype(np.int32)

    def _compute_plateaus(self):
        """Occasional stepped elevation bands layered onto the rolling-hill terrain.
        Each ~48-tile band either sits flat or gets a hash-picked height offset; only the last
        few tiles of a band ramp between two different offsets, so the transition reads as a
        short, steep cliff face rather than another smooth hill."""
        band = 48
        ramp_w = 4
        band_count = self.w // band + 2
        band_offsets = np.zeros(band_count, dtype=np.float64)
        choices = (-14.0, -9.0, 9.0, 14.0, 20.0)
        for b in range(band_count):
            rng = random.Random(self.seed * 7333 + b * 104729)
            if rng.random() < 0.22:
                band_offsets[b] = rng.choice(choices)
        xs = np.arange(self.w)
        band_id = xs // band
        local = xs % band
        h0 = band_offsets[band_id]
        h1 = band_offsets[np.minimum(band_id + 1, band_count - 1)]
        in_ramp = local >= (band - ramp_w)
        ramp_t = np.where(in_ramp, (local - (band - ramp_w)) / ramp_w, 0.0)
        return h0 + (h1 - h0) * ramp_t

    def _assign_biomes(self):
        # OPTIMIZED: vectorized biome assignment
        for biome, start, end in BIOME_LAYOUT:
            x0 = int(start * self.w)
            x1 = int(end * self.w)
            self.biomes[x0:x1] = biome

    # ---- smoother biome transitions ----
    BIOME_BLEND_WIDTH = 12  # tiles dithered across each biome border

    def _blend_biome_for_column(self, x):
        """Returns (primary_biome, other_biome, blend_t). Near a biome border, blend_t rises
        toward 0.5 so callers can dither block choice between the two biomes instead of an
        instant hard-edge switch."""
        biome = self.biomes[x]
        w = self.BIOME_BLEND_WIDTH
        for d in range(1, w + 1):
            lo, hi = x - d, x + d
            if lo >= 0 and self.biomes[lo] != biome:
                t = (w - d) / w * 0.5
                return biome, self.biomes[lo], t
            if hi < self.w and self.biomes[hi] != biome:
                t = (w - d) / w * 0.5
                return biome, self.biomes[hi], t
        return biome, biome, 0.0

    # ---- ravines: long diagonal carved gashes, independent of the tunnel-cave noise ----
    RAVINE_SPACING = 260

    def _ravine_for_region(self, region_id):
        rng = random.Random(self.seed * 51241 + region_id * 9161 + 777)
        if rng.random() > 0.35 or region_id < 0:
            return None
        start_x = region_id * self.RAVINE_SPACING + rng.randint(0, self.RAVINE_SPACING - 1)
        if start_x < 10 or start_x >= self.w - 10:
            return None
        return {
            "start_x": start_x,
            "start_depth": rng.randint(15, 40),
            "length": rng.randint(220, 420),
            "direction": rng.choice((-1, 1)),
            "drift": rng.uniform(0.4, 1.3),
            "width": rng.uniform(2.5, 5.0),
        }

    def _ravine_carve_at(self, x):
        """Return (y0, y1) depth range to carve for a ravine passing through column x, or None."""
        region_id = x // self.RAVINE_SPACING
        for rid in (region_id - 1, region_id):
            rav = self._ravine_for_region(rid)
            if not rav:
                continue
            dx = (x - rav["start_x"]) * rav["direction"]
            if 0 <= dx < rav["length"]:
                sy = self.surface_y[x]
                center_depth = rav["start_depth"] + dx * rav["drift"] * 0.15
                taper = min(1.0, dx / 30.0, (rav["length"] - dx) / 30.0)
                half_w = max(1.0, rav["width"] * max(0.15, taper))
                y_center = sy + center_depth
                return int(y_center - half_w), int(y_center + half_w)
        return None

    # ---- floating islands: rare detached landmasses above the surface ----
    FLOATING_ISLAND_SPACING = 340

    def _floating_island_for_region(self, region_id):
        rng = random.Random(self.seed * 62851 + region_id * 15485867 + 55)
        if rng.random() > 0.30 or region_id < 0:
            return None
        cx = region_id * self.FLOATING_ISLAND_SPACING + rng.randint(40, self.FLOATING_ISLAND_SPACING - 40)
        if cx < 20 or cx >= self.w - 20:
            return None
        return {
            "cx": cx,
            "height_above": rng.randint(55, 110),
            "half_w": rng.randint(9, 16),
            "thickness": rng.randint(4, 7),
        }

    # ---- surface ponds: small bodies of water scattered across the land ----
    POND_SPACING = 180

    def _pond_for_region(self, region_id):
        """Deterministically decide on a pond in this ~180-tile region, or None.
        Ponds are shallow water-filled basins placed on the surface so the player
        can refill water bottles without having to travel to the sea at the world edge."""
        rng = random.Random(self.seed * 41137 + region_id * 2221 + 91)
        # ~30% chance per region -> roughly one pond every 600 tiles
        if rng.random() > 0.30 or region_id < 0:
            return None
        cx = region_id * self.POND_SPACING + rng.randint(20, self.POND_SPACING - 20)
        if cx < 30 or cx >= self.w - 30:
            return None
        # Skip ponds in desert/snow biomes (would look odd as water) — keep them in
        # grassland/forest/savanna/jungle where small ponds read naturally.
        biome = self.biomes[cx]
        if biome in (BIOME_SEA, BIOME_DESERT, BIOME_TUNDRA):
            return None
        return {
            "cx": cx,
            "half_w": rng.randint(5, 9),    # pond radius in tiles
            "depth": rng.randint(3, 5),     # pond depth in tiles
            "region_id": region_id,
        }

    def _pond_at_column(self, x):
        """Return the pond dict if column x falls within a pond's radius, else None."""
        region_id = x // self.POND_SPACING
        for rid in (region_id - 1, region_id, region_id + 1):
            pond = self._pond_for_region(rid)
            if not pond: continue
            if abs(x - pond["cx"]) <= pond["half_w"]:
                return pond
        return None

    def _floating_island_profile(self, x):
        """Return (top_y, bottom_y) for the floating island band at column x, or None."""
        region_id = x // self.FLOATING_ISLAND_SPACING
        for rid in (region_id - 1, region_id):
            isl = self._floating_island_for_region(rid)
            if not isl:
                continue
            dx = x - isl["cx"]
            if abs(dx) > isl["half_w"]:
                continue
            sy = self.surface_y[x]
            top_y = sy - isl["height_above"]
            frac = 1.0 - (dx / isl["half_w"]) ** 2
            local_thick = max(1, int(isl["thickness"] * max(0.15, frac)))
            return top_y, top_y + local_thick
        return None

    # ---- deterministic per-column helpers ----
    def _column_rng(self, x, salt=0):
        """Get a deterministic RNG for column x (with optional salt for different uses)."""
        return random.Random(self.seed * 100003 + x * 7919 + salt)

    @staticmethod
    def _geology_block(depth):
        """Return the geology block for a given depth below surface."""
        for block, start, end in GEOLOGY_LAYERS:
            if start <= depth < end:
                return block
        return BEDROCK

    @staticmethod
    def _hash01(x, y, seed):
        """Fast deterministic hash -> float in [0, 1). Uses only integer math."""
        h = (x * 374761393 + y * 668265263 + seed * 982451653) & 0xFFFFFFFF
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
        h = (h ^ (h >> 16)) & 0xFFFFFFFF
        return h / 4294967296.0

    def _noise_at(self, x, y, scale, seed_offset):
        """Fast smooth noise using integer hash (no Random object creation)."""
        gx, gy = x / scale, y / scale
        x0, y0 = int(gx), int(gy)
        fx, fy = gx - x0, gy - y0
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)
        s = self.seed + seed_offset
        v00 = self._hash01(x0, y0, s)
        v10 = self._hash01(x0 + 1, y0, s)
        v01 = self._hash01(x0, y0 + 1, s)
        v11 = self._hash01(x0 + 1, y0 + 1, s)
        top = v00 * (1 - fx) + v10 * fx
        bot = v01 * (1 - fx) + v11 * fx
        return top * (1 - fy) + bot * fy

    def _leaf_type_for_tree(self, x, tree_type):
        """Determine the leaf block type for a tree at column x."""
        rng = self._column_rng(x, salt=55555)
        if tree_type == "dead_tree":
            return LEAVES_AUTUMN  # dead trees have dry/withered leaves
        elif tree_type == "pine":
            return LEAVES_DARK  # pine = dark green
        else:
            # Use the tree zone's leaf type if applicable
            zone_leaf = self._get_leaf_zone_type(x)
            if zone_leaf is not None:
                return zone_leaf
            # Default random leaf color for regular trees, giant trees, bent trees
            r = rng.random()
            if r < 0.45:
                return LEAVES  # standard green (most common)
            elif r < 0.60:
                return LEAVES_DARK  # dark green
            elif r < 0.68:
                return LEAVES_CHERRY  # cherry blossom
            elif r < 0.76:
                return LEAVES_AUTUMN  # autumn orange
            elif r < 0.82:
                return LEAVES_RED  # autumn red
            elif r < 0.88:
                return LEAVES_YELLOW  # autumn yellow
            else:
                return LEAVES  # default green

    def _get_leaf_zone_type(self, x):
        """Check if column x is inside a colored-leaf tree zone.
        Leaf zones are rare clusters where all trees share a specific leaf color,
        similar to dead tree zones."""
        zone_size = 30
        zone_center = (x // zone_size) * zone_size + zone_size // 2
        rng = self._column_rng(zone_center, salt=88888)
        r = rng.random()
        # Only ~15% of zones are colored leaf zones
        if r < 0.15:
            inner_radius = rng.randint(4, 12)
            if abs(x - zone_center) <= inner_radius:
                # Pick which leaf color this zone uses
                zone_type_rng = self._column_rng(zone_center, salt=99999)
                leaf_choice = zone_type_rng.random()
                if leaf_choice < 0.22:
                    return LEAVES_CHERRY  # cherry blossom zone
                elif leaf_choice < 0.42:
                    return LEAVES_AUTUMN  # autumn orange zone
                elif leaf_choice < 0.60:
                    return LEAVES_RED  # autumn red zone
                elif leaf_choice < 0.78:
                    return LEAVES_YELLOW  # autumn yellow zone
                else:
                    return LEAVES_DARK  # dark forest zone
        return None

    def _in_dead_tree_zone(self, x):
        """Check if column x is inside a dead tree zone.
        Dead tree zones are rare clusters where only dead trees spawn,
        and no other tree types appear nearby."""
        zone_size = 25
        zone_center = (x // zone_size) * zone_size + zone_size // 2
        rng = self._column_rng(zone_center, salt=77777)
        # Only ~8% of zones are dead tree zones
        if rng.random() < 0.08:
            inner_radius = rng.randint(3, 10)
            return abs(x - zone_center) <= inner_radius
        return False

    def _nearest_tree_distance(self, x):
        """Check the distance to the nearest tree in either direction.
        Returns the minimum number of empty columns between x and the
        nearest tree (or a large number if no tree nearby)."""
        min_gap = 999
        for dx in range(1, 6):
            for direction in (-1, 1):
                nx = x + direction * dx
                if 0 <= nx < self.w:
                    tree_info = self._tree_at_column_raw(nx)
                    if tree_info is not None and tree_info[0] != "flower":
                        min_gap = min(min_gap, dx)
        return min_gap

    def _tree_at_column_raw(self, x):
        """Internal: check if a tree type is assigned at column x (probability only),
        without checking spacing rules. Used by _nearest_tree_distance to avoid recursion."""
        if x < 4 or x >= self.w - 4: return None
        biome = self.biomes[x]
        sy = self.surface_y[x]
        if sy < 0 or sy >= self.h - 8: return None
        if biome == BIOME_SEA: return None
        if self._pond_at_column(x) is not None: return None
        if (x >= 1 and x < self.w - 1
            and self.surface_y[x-1] > sy and self.surface_y[x+1] > sy
            and self.surface_y[x-1] - sy >= 2 and self.surface_y[x+1] - sy >= 2):
            return None
        rng = self._column_rng(x, salt=4242)
        r = rng.random()
        if biome == BIOME_FOREST:
            if r < 0.03: return ("giant_tree", rng.randint(12, 18))
            elif r < 0.06: return ("bent_tree", rng.randint(5, 8))
            elif r < 0.20: return ("tree", rng.randint(5, 9))
            elif r < 0.30: return ("flower", 0)
        elif biome == BIOME_GRASSLAND:
            if r < 0.02: return ("bent_tree", rng.randint(4, 7))
            elif r < 0.08: return ("tree", rng.randint(4, 7))
            elif r < 0.20: return ("flower", 0)
        elif biome == BIOME_JUNGLE:
            if r < 0.04: return ("giant_tree", rng.randint(14, 20))
            elif r < 0.25: return ("tree", rng.randint(7, 12))
        elif biome == BIOME_TUNDRA and r < 0.18:
            return ("pine", rng.randint(8, 14))
        elif biome == BIOME_DESERT and r < 0.10:
            return ("cactus", rng.randint(3, 6))
        elif biome == BIOME_SAVANNA:
            if self._in_dead_tree_zone(x):
                if r < 0.35: return ("dead_tree", rng.randint(3, 5))
            else:
                if r < 0.06: return ("tree", rng.randint(4, 6))
        return None

    def _tree_at_column(self, x):
        """Deterministically decide if a tree/feature starts at column x.
        Returns (tree_type, height) or None. Does NOT require column to be generated."""
        if x < 4 or x >= self.w - 4: return None
        biome = self.biomes[x]
        sy = self.surface_y[x]
        if sy < 0 or sy >= self.h - 8: return None
        # Don't generate trees in water/sea biomes or where there's water
        if biome == BIOME_SEA: return None
        # Check if there's a pond at this column
        if self._pond_at_column(x) is not None: return None
        # Check if this is a water pool dip (neighbors are higher and this is a low point)
        if (x >= 1 and x < self.w - 1
            and self.surface_y[x-1] > sy and self.surface_y[x+1] > sy
            and self.surface_y[x-1] - sy >= 2 and self.surface_y[x+1] - sy >= 2):
            return None  # this is a water pool location, skip tree
        # Check if neighbors are sea biome (trees at coastline would be on water)
        sea_near = False
        for dx_check in range(-3, 4):
            nx = x + dx_check
            if 0 <= nx < self.w and self.biomes[nx] == BIOME_SEA:
                sea_near = True
                break
        if sea_near: return None
        # Check if this column has liquid (water) at or near the surface
        if x in self.generated_set:
            col = self.tile_columns.get(x)
            if col:
                for check_y in range(max(0, sy - 1), min(self.h, sy + 3)):
                    amt_col = self.liquid_amount.get(x)
                    if amt_col and amt_col[check_y] > 0:
                        ltype = self.liquid_type[x][check_y]
                        if ltype == LIQUID_WATER:
                            return None  # water at surface, no tree
        # For ungenerated columns, check if surface is below sea level (likely water)
        sea_surface = int(SURFACE)  # normal surface level
        if sy > sea_surface + 3:
            return None  # surface is well below normal, likely underwater
        # Minimum tree spacing: ensure no tree within 3 columns
        # This prevents trees from spawning with no gaps
        nearest = self._nearest_tree_distance(x)
        if nearest <= 2:
            return None  # too close to another tree
        rng = self._column_rng(x, salt=4242)
        r = rng.random()
        if biome == BIOME_FOREST:
            if r < 0.03: return ("giant_tree", rng.randint(12, 18))
            elif r < 0.06: return ("bent_tree", rng.randint(5, 8))
            elif r < 0.20: return ("tree", rng.randint(5, 9))
            elif r < 0.30: return ("flower", 0)
        elif biome == BIOME_GRASSLAND:
            if r < 0.02: return ("bent_tree", rng.randint(4, 7))
            elif r < 0.08: return ("tree", rng.randint(4, 7))
            elif r < 0.20: return ("flower", 0)
        elif biome == BIOME_JUNGLE:
            if r < 0.04: return ("giant_tree", rng.randint(14, 20))
            elif r < 0.25: return ("tree", rng.randint(7, 12))
        elif biome == BIOME_TUNDRA and r < 0.18:
            return ("pine", rng.randint(8, 14))
        elif biome == BIOME_DESERT and r < 0.10:
            return ("cactus", rng.randint(3, 6))
        elif biome == BIOME_SAVANNA:
            if self._in_dead_tree_zone(x):
                # Inside a dead tree zone: high chance of dead trees, no other trees
                if r < 0.35: return ("dead_tree", rng.randint(3, 5))
            else:
                # Outside dead tree zone: normal trees, no dead trees
                if r < 0.06: return ("tree", rng.randint(4, 6))
        return None

    # ---- lazy column generation ----
    def generate_column(self, x, y_end=None):
        """Generate tiles for column x.
        If y_end is None, generates the initial surface phase (up to surface+200).
        If y_end is specified, extends an already-generated column down to that Y.
        Uses dict-based storage: creates a column list, fills it, stores in dict."""
        if x < 0 or x >= self.w: return
        sy = self.surface_y[x]
        biome = self.biomes[x]
        # Dither surface/subsurface/wall material near biome borders instead of a hard switch,
        # so transitions look like a natural blend rather than a seam.
        biome_a, biome_b, blend_t = self._blend_biome_for_column(x)
        blend_rng = self._column_rng(x, salt=24680)
        use_b = blend_t > 0 and blend_rng.random() < blend_t
        blended_biome = biome_b if use_b else biome_a
        surface_block = BIOME_SURFACE_BLOCK[blended_biome]
        sub_block = BIOME_SUBSURFACE[blended_biome]
        blended_wall = BIOME_WALL[blended_biome]

        if x not in self.generated_set:
            # === INITIAL GENERATION (surface phase) ===
            # Only generate down to a reasonable depth for surface play
            initial_depth = min(max(sy + 200, 300), self.h)

            # Create column bytearrays (1 byte per tile)
            col = bytearray(self.h)       # all AIR (0)
            wall_col = bytearray(self.h)  # all WALL_NONE (0)

            # 0. Floating islands (placed above the normal surface; never overlaps the terrain
            # fill below since it only touches rows above sy).
            island = self._floating_island_profile(x)
            if island:
                top_y, bottom_y = island
                cap_block = SAND if biome in (BIOME_DESERT,) else (SNOW if biome == BIOME_TUNDRA else GRASS)
                for yy in range(max(0, top_y), min(self.h, bottom_y)):
                    col[yy] = cap_block if yy == top_y else DIRT

            # 1. Fill terrain (surface + subsurface + geology layers) up to initial_depth
            for yy in range(sy, initial_depth):
                depth = yy - sy
                if depth == 0:
                    col[yy] = surface_block
                elif depth < 25:
                    col[yy] = sub_block
                else:
                    geo = self._geology_block(depth)
                    if blended_biome == BIOME_DESERT and geo == STONE:
                        col[yy] = SANDSTONE
                    else:
                        col[yy] = geo

            # Bedrock at bottom (only if initial_depth reaches near bottom)
            for y in range(max(initial_depth, self.h - 2), self.h):
                col[y] = BEDROCK

            # 2. Place walls up to initial_depth
            for y in range(sy + 1, initial_depth):
                depth = y - sy
                if depth < 25:
                    wall_col[y] = blended_wall
                elif depth < 200:
                    wall_col[y] = WALL_STONE
                else:
                    wall_col[y] = WALL_GRANITE

            # Store column
            self.tile_columns[x] = col
            self.wall_columns[x] = wall_col
            self.generated_set.add(x)
            self.generated_depth[x] = initial_depth

            # 3. Carve caves (only in generated range) — uses bigger-cavern noise octave
            self._carve_caves(x, sy, initial_depth)

            # 3b. Ravines: long diagonal gashes independent of the tunnel-cave noise above
            rav = self._ravine_carve_at(x)
            if rav:
                y0r, y1r = rav
                mineable_blocks = {SANDSTONE, LIMESTONE, GRANITE, BASALT, OBSIDIAN, DIRT, MUD, SAND,
                                  COAL, IRON, GOLD, DIAMOND, COPPER_ORE, TIN_ORE, SILVER_ORE,
                                  MITHRIL_ORE, RUBY_ORE, SAPPHIRE_ORE, EMERALD_ORE, MARBLE, STONE}
                for y in range(max(sy + 2, y0r), min(initial_depth, self.h - 4, y1r + 1)):
                    if col[y] in mineable_blocks:
                        col[y] = AIR

            # 4. Place ores (only in generated range)
            self._place_ores_column(x, max_y=initial_depth)

            # 5. Seas at edges
            sea_width = int(self.w * 0.04)
            if x < sea_width or x >= self.w - sea_width:
                self._fill_sea_column(x)

            # 6. Water pools/lakes in surface dips
            if 2 <= x < self.w - 2:
                if (self.surface_y[x - 1] > sy and self.surface_y[x + 1] > sy
                        and self.surface_y[x - 1] - sy >= 2 and self.surface_y[x + 1] - sy >= 2):
                    depth = min(self.surface_y[x - 1] - sy, self.surface_y[x + 1] - sy, 6)
                    for d in range(depth):
                        yy = sy + d
                        if 0 <= yy < self.h and col[yy] == AIR:
                            col[yy] = WATER

            # 6b. Surface ponds: dig a small basin and fill it with water so the player
            # has nearby water sources for filling bottles (and for visual variety).
            pond = self._pond_at_column(x)
            if pond:
                dx = x - pond["cx"]
                # Elliptical basin: deeper in the center, shallower at the edges.
                # Carve out dirt/stone to form the basin, then fill with WATER.
                # The carve depth tapers as we move away from the pond center.
                taper = 1.0 - (dx / max(1, pond["half_w"])) ** 2  # 1 at center, 0 at edge
                carve_depth = max(1, int(pond["depth"] * taper))
                # Lower the surface by carve_depth tiles for this column (digging basin)
                basin_top = sy  # original surface
                basin_bottom = sy + carve_depth
                # Carve: remove any solid blocks in the basin region (replace with AIR first)
                for yy in range(basin_top, min(self.h, basin_bottom + 1)):
                    if col[yy] != AIR and BLOCK_DEFS.get(col[yy], {}).get("mineable", False):
                        col[yy] = AIR
                # Fill the basin with WATER (will be converted to flowing liquid in step 11)
                for yy in range(basin_top, min(self.h, basin_bottom)):
                    if col[yy] == AIR:
                        col[yy] = WATER
                # Line the bottom of the basin with SAND (so it looks like a pond bottom)
                if basin_bottom < self.h:
                    if col[basin_bottom] in (DIRT, GRASS, STONE, SANDSTONE, LIMESTONE):
                        col[basin_bottom] = SAND

            # 7. Surface decorations
            self._place_surface_decorations(x, col)

            # 8. Trees
            tree_info = self._tree_at_column(x)
            if tree_info:
                tree_type, height = tree_info
                if tree_type == "tree":
                    self._plant_tree_trunk(x, sy - 1, TREE_TRUNK, height)
                elif tree_type == "pine":
                    self._plant_pine_trunk(x, sy - 1, height)
                elif tree_type == "cactus":
                    self._plant_cactus(x, sy - 1, height)
                elif tree_type == "giant_tree":
                    self._plant_tree_trunk(x, sy - 1, TREE_GIANT, height)
                elif tree_type == "dead_tree":
                    self._plant_tree_trunk(x, sy - 1, TREE_DEAD, height)
                elif tree_type == "bent_tree":
                    self._plant_tree_trunk(x, sy - 1, TREE_BENT, height)
                elif tree_type == "flower":
                    if sy - 1 >= 0 and col[sy - 1] == AIR:
                        # Random flower type
                        rng_fl = self._column_rng(x, salt=99999)
                        flower_type = rng_fl.choice([FLOWER, FLOWER_RED, FLOWER_YELLOW, FLOWER_BLUE, FLOWER_WHITE])
                        col[sy - 1] = flower_type

            # 9. Neighbor tree canopies
            for dx in range(-3, 4):
                if dx == 0: continue
                nx = x + dx
                if 0 <= nx < self.w:
                    neighbor_tree = self._tree_at_column(nx)
                    if neighbor_tree:
                        tree_type, nheight = neighbor_tree
                        nsy = self.surface_y[nx]
                        leaf_block = self._leaf_type_for_tree(nx, tree_type)
                        if tree_type == "tree":
                            top = nsy - 1 - nheight
                            rng = self._column_rng(nx, salt=7777)
                            for dy in range(-2, 2):
                                for ddx in range(-2, 3):
                                    if abs(ddx) + abs(dy) <= 3 and ddx == -dx:
                                        ly = top + dy
                                        if 0 <= ly < self.h and col[ly] == AIR:
                                            if rng.random() < 0.85:
                                                col[ly] = leaf_block
                        elif tree_type == "pine":
                            top = nsy - 1 - nheight
                            for tier in range(3):
                                tier_w = 3 - tier
                                tier_y = top + tier * 2
                                for ddx in range(-tier_w, tier_w + 1):
                                    for dy in range(0, 2):
                                        if abs(ddx) + dy <= tier_w + 1 and ddx == -dx:
                                            ly = tier_y + dy
                                            if 0 <= ly < self.h and col[ly] == AIR:
                                                col[ly] = leaf_block
                        elif tree_type == "giant_tree":
                            top = nsy - 1 - nheight
                            rng = self._column_rng(nx, salt=7777)
                            for dy in range(-3, 4):
                                for ddx in range(-3, 4):
                                    if abs(ddx) + abs(dy) <= 4 and ddx == -dx:
                                        ly = top + dy
                                        if 0 <= ly < self.h and col[ly] == AIR:
                                            if rng.random() < 0.9:
                                                col[ly] = leaf_block
                        elif tree_type == "dead_tree":
                            # Dead trees have sparse canopy with autumn-colored leaves
                            top = nsy - 1 - nheight
                            rng = self._column_rng(nx, salt=7777)
                            for dy in range(-2, 2):
                                for ddx in range(-2, 3):
                                    if abs(ddx) + abs(dy) <= 3 and ddx == -dx:
                                        ly = top + dy
                                        if 0 <= ly < self.h and col[ly] == AIR:
                                            if rng.random() < 0.3:  # sparse
                                                col[ly] = leaf_block
                        elif tree_type == "bent_tree":
                            top = nsy - 1 - nheight
                            rng = self._column_rng(nx, salt=7777)
                            for dy in range(-2, 2):
                                for ddx in range(-2, 3):
                                    if abs(ddx) + abs(dy) <= 3 and ddx == -dx:
                                        ly = top + dy
                                        if 0 <= ly < self.h and col[ly] == AIR:
                                            if rng.random() < 0.7:
                                                col[ly] = leaf_block

            # 10. Biome decorations
            self._place_biome_decorations_column(x, max_y=initial_depth)

            self.update_sky_height(x)

            # 11. Convert baked WATER/LAVA placeholders (from the sea/lake/lava fills above)
            # into the flowing-liquid layer. They start "at rest" -- the simulation only
            # wakes up cells that get disturbed, so a calm lake costs nothing until something
            # changes it.
            self._convert_legacy_liquid_column(x)

            # 12. Wake up any liquid that isn't actually resting on solid ground or full liquid
            # below it (e.g. a lake generated directly above a cave/ravine gap). This is what
            # makes water immediately start pouring into caves as waterfalls once the area
            # loads in.
            amt_col = self.liquid_amount.get(x)
            if amt_col:
                for y in range(self.h - 1):
                    amt = amt_col[y]
                    if amt <= 0:
                        continue
                    if not BLOCK_DEFS[col[y + 1]]["solid"]:
                        below_amt = amt_col[y + 1]
                        if below_amt < amt:
                            self.mark_liquid_active(x, y)
            # Also wake up already-generated neighboring liquid near the surface (lakes/coastline)
            # now that this column exists, so it can flow into fresh terrain.
            for nx in (x - 1, x + 1):
                if self.is_generated(nx):
                    n_amt_col = self.liquid_amount.get(nx)
                    if n_amt_col:
                        nsy = int(self.surface_y[nx])
                        band_lo = max(0, nsy - 20)
                        band_hi = min(self.h, nsy + 60)
                        for yy in range(band_lo, band_hi):
                            if n_amt_col[yy] > 0:
                                self.mark_liquid_active(nx, yy)

            # A caller may need deep terrain immediately (for collision around a
            # player already below the surface). Complete the surface pass first,
            # then enter the normal deep pass in the same request. Previously the
            # requested depth truncated the surface pass at surface + 200 and left
            # a visible horizontal seam until a later frame happened to extend it.
            if y_end is not None and y_end > initial_depth:
                self.generate_column(x, y_end)

        elif y_end is not None and y_end > self.generated_depth.get(x, 0):
            # === EXTEND GENERATION (deep phase) ===
            col = self.tile_columns.get(x)
            wall_col = self.wall_columns.get(x)
            if not col or not wall_col: return

            old_end = self.generated_depth[x]
            new_end = min(y_end, self.h)

            # Fill terrain in the new range
            for yy in range(old_end, new_end):
                depth = yy - sy
                if depth < 25:
                    col[yy] = sub_block
                else:
                    geo = self._geology_block(depth)
                    if blended_biome == BIOME_DESERT and geo == STONE:
                        col[yy] = SANDSTONE
                    else:
                        col[yy] = geo

            # Bedrock
            for y in range(max(new_end, self.h - 2), self.h):
                col[y] = BEDROCK

            # Walls
            for y in range(old_end, new_end):
                depth = y - sy
                if depth < 25:
                    wall_col[y] = blended_wall
                elif depth < 200:
                    wall_col[y] = WALL_STONE
                else:
                    wall_col[y] = WALL_GRANITE

            # Lava at bottom
            lava_start = sy + 3600
            if lava_start < self.h:
                lrng = self._column_rng(x, salt=99999)
                for y in range(max(old_end, lava_start), min(new_end, self.h - 2)):
                    if col[y] == OBSIDIAN and lrng.random() < 0.4:
                        col[y] = LAVA
                    elif y >= lava_start + 50:
                        if col[y] in (OBSIDIAN, BASALT):
                            col[y] = LAVA

            # Caves and ores in new range (uses bigger-cavern noise octave)
            self._carve_caves(x, sy, new_end, skip_above=old_end)
            self._place_ores_column(x, max_y=new_end, skip_above=old_end)

            # Ravines that pass through the newly-generated deep range
            rav = self._ravine_carve_at(x)
            if rav:
                y0r, y1r = rav
                mineable_blocks = {SANDSTONE, LIMESTONE, GRANITE, BASALT, OBSIDIAN, DIRT, MUD, SAND,
                                  COAL, IRON, GOLD, DIAMOND, COPPER_ORE, TIN_ORE, SILVER_ORE,
                                  MITHRIL_ORE, RUBY_ORE, SAPPHIRE_ORE, EMERALD_ORE, MARBLE, STONE}
                for y in range(max(sy + 2, y0r, old_end), min(new_end, self.h - 4, y1r + 1)):
                    if col[y] in mineable_blocks:
                        col[y] = AIR

            self.generated_depth[x] = new_end
            self.update_sky_height(x)

            # Convert any newly-baked LAVA tiles in the deep range into the liquid layer
            # and wake up liquid that's now suspended over freshly-carved caves/ravines.
            self._convert_legacy_liquid_column(x)
            amt_col = self.liquid_amount.get(x)
            if amt_col:
                for y in range(max(0, old_end - 1), min(self.h - 1, new_end)):
                    amt = amt_col[y]
                    if amt <= 0:
                        continue
                    if not BLOCK_DEFS[col[y + 1]]["solid"]:
                        below_amt = amt_col[y + 1]
                        if below_amt < amt:
                            self.mark_liquid_active(x, y)

    def _carve_caves(self, x, sy, max_y, skip_above=0):
        """Carve caves in column x from sy+8 to max_y. Optionally skip above skip_above.

        Uses OpenSimplex noise (when available) for natural-looking cave networks
        with twisty tunnels, big caverns, and worm-like passages. Falls back to the
        original hash-based noise when opensimplex is not installed."""
        col = self.tile_columns.get(x)
        if not col: return
        mineable_blocks = {SANDSTONE, LIMESTONE, GRANITE, BASALT, OBSIDIAN, DIRT, MUD, SAND,
                          COAL, IRON, GOLD, DIAMOND, COPPER_ORE, TIN_ORE, SILVER_ORE,
                          MITHRIL_ORE, RUBY_ORE, SAPPHIRE_ORE, EMERALD_ORE, MARBLE, STONE}
        y_start = max(sy + 8, skip_above)
        
        if False and HAS_OPENSIMPLEX:
            # Experimental OpenSimplex cave path intentionally disabled: the
            # documented world uses the deterministic hash-value cave layers.
            # Retained below only as an inactive reference implementation.
            #
            # BUG FIX (performance): Previously this loop called `opensimplex.seed()`
            # FOUR TIMES PER TILE (4 * 200 tiles = 800 seed() calls per column).
            # Each seed() rebuilds the 256-entry permutation table, so a single
            # column took ~500 ms to carve — making the lazy world generator unable
            # to keep up with the player. From the player's perspective the world
            # appeared to "stop generating" once they outran the column budget.
            #
            # Fix: hoist the seed() calls out of the per-tile loop. Because each
            # noise pass uses a single fixed seed, the noise remains coherent in
            # (x, y) — only the (slow) seed re-initialisation is eliminated.
            # This makes column carving ~250x faster with identical output.
            y_end_excl = min(max_y, self.h - 4)

            opensimplex.seed(self.seed + 100)
            cave_vals = [opensimplex.noise2(x * 0.04, y * 0.04) for y in range(y_start, y_end_excl)]

            opensimplex.seed(self.seed + 101)
            cave2_vals = [opensimplex.noise2(x * 0.08, y * 0.08) for y in range(y_start, y_end_excl)]

            opensimplex.seed(self.seed + 200)
            cavern_vals = [opensimplex.noise2(x * 0.015, y * 0.015) for y in range(y_start, y_end_excl)]

            opensimplex.seed(self.seed + 300)
            worm_vals = [opensimplex.noise2(x * 0.025, y * 0.06) for y in range(y_start, y_end_excl)]

            for i, y in enumerate(range(y_start, y_end_excl)):
                t = col[y]
                if t not in mineable_blocks:
                    continue
                depth = y - sy

                n_cave = cave_vals[i]
                n_cave2 = cave2_vals[i]
                combined_cave = n_cave * 0.6 + n_cave2 * 0.4

                n_cavern = cavern_vals[i]
                n_worm = worm_vals[i]

                # Depth-dependent carving thresholds (caves get bigger and more common deeper)
                depth_factor = min(1.0, depth / 100.0)

                # Main caves
                cave_threshold = 0.55 - depth_factor * 0.10
                is_cave = combined_cave > cave_threshold

                # Big caverns (deeper only)
                cavern_threshold = 0.72 - depth_factor * 0.08
                is_cavern = depth > 30 and n_cavern > cavern_threshold

                # Worm tunnels
                worm_threshold = 0.62 - depth_factor * 0.08
                is_worm = depth > 10 and n_worm > worm_threshold

                if is_cave or is_cavern or is_worm:
                    col[y] = AIR
        else:
            # Original hash-based cave carving
            crng = self._column_rng(x, salt=55555)
            for y in range(y_start, min(max_y, self.h - 4)):
                t = col[y]
                if t in mineable_blocks:
                    n1 = self._noise_at(x, y, 16, 99)
                    n2 = self._noise_at(x, y, 8, 199)
                    n = n1 * 0.65 + n2 * 0.35
                    n3 = self._noise_at(x, y, 40, 299)
                    threshold = 0.66 - (0.18 if n3 > 0.7 else 0.0)
                    if n > threshold or (n > threshold - 0.06 and crng.random() < 0.3):
                        col[y] = AIR

    def _place_surface_decorations(self, x, col):
        """Place rocks, small stones, grass tufts, and bushes on the surface."""
        sy = self.surface_y[x]
        if sy < 0 or sy >= self.h: return  # safety check
        biome = self.biomes[x]
        rng = self._column_rng(x, salt=12321)
        # Surface decorations only on land biomes (not sea)
        if biome == BIOME_SEA: return
        # Skip decorations if this column has a pond (water at surface)
        if self._pond_at_column(x) is not None: return
        # Skip if the surface tile itself is water (pond filled column)
        if col[sy] == WATER: return
        # Small stones on the ground (common)
        if rng.random() < 0.08:
            if sy - 1 >= 0 and col[sy - 1] == AIR:
                col[sy - 1] = SMALL_STONE
        # Grass tufts (grassland, forest, savanna)
        if biome in (BIOME_GRASSLAND, BIOME_FOREST, BIOME_SAVANNA) and rng.random() < 0.15:
            if sy - 1 >= 0 and col[sy - 1] == AIR:
                col[sy - 1] = GRASS_TUFT
        # Rocks (boulders) - rare, solid, need pickaxe
        if rng.random() < 0.03:
            if sy - 1 >= 0 and col[sy - 1] == AIR:
                col[sy - 1] = ROCK
        # Bushes (forest, jungle, grassland)
        if biome in (BIOME_FOREST, BIOME_JUNGLE, BIOME_GRASSLAND) and rng.random() < 0.08:
            if sy - 1 >= 0 and col[sy - 1] == AIR:
                # 40% chance of fruit bush
                col[sy - 1] = BUSH_FRUIT if rng.random() < 0.4 else BUSH
        # Tall grass (forest, jungle) - 20% chance, 2 tiles tall
        if biome in (BIOME_FOREST, BIOME_JUNGLE) and rng.random() < 0.20:
            if sy - 1 >= 0 and col[sy - 1] == AIR:
                col[sy - 1] = TALL_GRASS
                if sy - 2 >= 0 and col[sy - 2] == AIR:
                    col[sy - 2] = TALL_GRASS
        # Dried grass (savanna, desert edge, grassland) - natural source for crafting
        if biome in (BIOME_SAVANNA, BIOME_GRASSLAND) and rng.random() < 0.12:
            if sy - 1 >= 0 and col[sy - 1] == AIR:
                col[sy - 1] = DRIED_GRASS
        # Dried tall grass (savanna, grassland) - 2-tile vertical
        if biome in (BIOME_SAVANNA, BIOME_GRASSLAND) and rng.random() < 0.15:
            if sy - 1 >= 0 and col[sy - 1] == AIR:
                col[sy - 1] = DRIED_TALL_GRASS
                if sy - 2 >= 0 and col[sy - 2] == AIR:
                    col[sy - 2] = DRIED_TALL_GRASS

    def _place_ores_column(self, x, max_y=None, skip_above=0):
        """Place one deterministic, low-density vein opportunity per ore and column.

        The center is chosen from the ore's complete depth band, rather than from
        the currently generated slice. Lazy deep-generation can therefore extend
        a column without rolling additional veins into that same column.
        """
        sy = self.surface_y[x]
        replaceable = {STONE, SANDSTONE, LIMESTONE, GRANITE, BASALT}

        for ore_index, (ore, probability, cluster, min_depth, max_depth) in enumerate(ORE_DISTRIBUTION):
            # Separate deterministic stream for every ore type. This keeps one
            # vein opportunity per ore and column, without repeated lazy-pass rolls.
            rng = self._column_rng(x, salt=33333 + ore_index * 1009)
            if rng.random() >= min(0.65, probability * 1.25):
                continue

            y_min = max(sy + 2, sy + min_depth)
            y_max = min(self.h - 5, sy + max_depth)
            if y_max <= y_min:
                continue

            cy = rng.randint(y_min, y_max - 1)
            # This invocation owns only its newly generated vertical slice.
            if cy < skip_above or (max_y is not None and cy >= max_y):
                continue

            # Anchor the vein at its source column, then spread its remaining
            # blocks locally. A vertical mining shaft can now actually encounter
            # the deterministic vein assigned to that column.
            for vein_block in range(cluster):
                if vein_block == 0:
                    ox, oy = x, cy
                else:
                    ox = x + rng.randint(-1, 1)
                    oy = cy + rng.randint(-1, 1)
                if not (0 <= ox < self.w and 0 <= oy < self.h):
                    continue
                if oy < skip_above or (max_y is not None and oy >= max_y):
                    continue
                if ox not in self.generated_set:
                    continue
                ocol = self.tile_columns.get(ox)
                if ocol and ocol[oy] in replaceable:
                    ocol[oy] = ore

    def _plant_tree_trunk(self, x, base_y, trunk_block, height):
        """Place just the trunk of a tree (canopy is placed by neighboring columns)."""
        col = self.tile_columns.get(x)
        if not col: return
        for i in range(height):
            yy = base_y - i
            if 0 <= yy < self.h: col[yy] = trunk_block

    def _plant_pine_trunk(self, x, base_y, height):
        """Place just the trunk of a pine tree."""
        col = self.tile_columns.get(x)
        if not col: return
        for i in range(height):
            yy = base_y - i
            if 0 <= yy < self.h: col[yy] = PINE_TRUNK

    def _plant_cactus(self, x, base_y, height):
        """Cacti are tall narrow green blocks (no canopy)."""
        col = self.tile_columns.get(x)
        if not col: return
        for i in range(height):
            yy = base_y - i
            if 0 <= yy < self.h: col[yy] = CACTUS

    def _fill_sea_column(self, x):
        col = self.tile_columns.get(x)
        if not col: return
        sy = self.surface_y[x]
        sea_depth = 15
        for y in range(sy, min(self.h, sy + sea_depth)):
            if y == sy + sea_depth - 1:
                col[y] = SAND
            elif y < sy + sea_depth - 1:
                col[y] = WATER
        for y in range(sy + sea_depth, min(self.h, sy + sea_depth + 3)):
            if col[y] in (DIRT, GRASS, STONE):
                col[y] = SAND

    def _place_biome_decorations_column(self, x, max_y=None):
        """Place vines and ice patches for this column."""
        col = self.tile_columns.get(x)
        if not col: return
        biome = self.biomes[x]
        sy = self.surface_y[x]
        limit = min(max_y, self.h) if max_y is not None else self.h
        if biome == BIOME_JUNGLE:
            rng = self._column_rng(x, salt=88888)
            for y in range(sy, min(limit, self.h - 1)):
                if (col[y] in ALL_LEAF_TYPES or col[y] == JUNGLE_GRASS) and y + 1 < limit and col[y+1] == AIR:
                    vine_len = rng.randint(1, 4)
                    for v in range(vine_len):
                        vy = y + 1 + v
                        if 0 <= vy < limit and col[vy] == AIR:
                            col[vy] = VINE
                        else: break
        if biome == BIOME_TUNDRA:
            rng = self._column_rng(x, salt=66666)
            for y in range(sy, min(limit, sy + 8)):
                if col[y] == SNOW and rng.random() < 0.15:
                    col[y] = ICE

    # ---- public API for lazy generation ----
    def ensure_generated(self, x_start, x_end):
        """Ensure all columns in [x_start, x_end) are generated."""
        x_start = max(0, x_start)
        x_end = min(self.w, x_end)
        for x in range(x_start, x_end):
            if x not in self.generated_set:
                self.generate_column(x)

    def is_generated(self, x):
        return 0 <= x < self.w and x in self.generated_set

    def get_generated_columns(self):
        """Return generated columns for saving, including their real depth.

        Columns are allocated at full world height, but lazy generation only fills
        part of each one. Persisting that depth is essential: treating a shallow
        column as fully generated after a load prevents the deep-generation pass
        from ever filling the rest of it.
        """
        result = []
        for x in sorted(self.generated_set):
            # Convert bytearray to list for JSON
            col_tiles = list(self.tile_columns[x])
            col_walls = list(self.wall_columns[x])
            generated_depth = int(self.generated_depth.get(x, 0))
            result.append((x, col_tiles, col_walls, generated_depth))
        return result

    def get_liquid_columns(self):
        """Sparse liquid save data: only columns that actually contain any liquid."""
        result = []
        for x, amt_col in self.liquid_amount.items():
            if any(amt_col):
                result.append((x, list(amt_col), list(self.liquid_type[x])))
        return result

    def load_generated_columns(self, columns_data, liquid_columns_data=None):
        """Load saved columns while preserving lazy depth."""
        for entry in columns_data:
            if len(entry) >= 4:
                x, col_tiles, col_walls, saved_depth = entry[:4]
            else:
                x, col_tiles, col_walls = entry
                saved_depth = None
            if 0 <= x < self.w:
                # Convert to bytearray and ensure correct length
                bt = bytearray(self.h)
                bw = bytearray(self.h)
                for y in range(min(self.h, len(col_tiles))):
                    bt[y] = col_tiles[y] & 0xFF
                for y in range(min(self.h, len(col_walls))):
                    bw[y] = col_walls[y] & 0xFF
                self.tile_columns[x] = bt
                self.wall_columns[x] = bw
                self.generated_set.add(x)
                if saved_depth is None:
                    # Legacy shallow columns have bottom bedrock, so use the final
                    # non-empty wall as the generated frontier instead of tile data.
                    last_wall = next((y for y in range(self.h - 1, -1, -1)
                                      if bw[y] != WALL_NONE), -1)
                    self.generated_depth[x] = max(0, min(self.h, last_wall + 1))
                else:
                    self.generated_depth[x] = max(0, min(self.h, int(saved_depth)))
                self.update_sky_height(x)
        if liquid_columns_data:
            for x, amt, typ in liquid_columns_data:
                if 0 <= x < self.w:
                    self._ensure_liquid_col(x)
                    la, lt = self.liquid_amount[x], self.liquid_type[x]
                    for y in range(min(self.h, len(amt))):
                        la[y] = amt[y] & 0xFF
                    for y in range(min(self.h, len(typ))):
                        lt[y] = typ[y] & 0xFF
        else:
            # Save predates the liquid simulation: convert any baked WATER/LAVA tiles.
            for entry in columns_data:
                x = entry[0]
                if 0 <= x < self.w:
                    self._convert_legacy_liquid_column(x)

    # ---- accessors (with bounds checking) ----
    def get(self, x, y):
        if x < 0 or x >= self.w or y < 0 or y >= self.h: return AIR
        col = self.tile_columns.get(x)
        return col[y] if col else AIR

    def get_wall(self, x, y):
        if x < 0 or x >= self.w or y < 0 or y >= self.h: return WALL_NONE
        col = self.wall_columns.get(x)
        return col[y] if col else WALL_NONE

    def set(self, x, y, block):
        if 0 <= x < self.w and 0 <= y < self.h:
            col = self.tile_columns.get(x)
            if col is None:
                col = bytearray(self.h)
                self.tile_columns[x] = col
            col[y] = block
            self.update_sky_height(x)
            self.on_block_changed(x, y)

    def set_wall(self, x, y, wall):
        if 0 <= x < self.w and 0 <= y < self.h:
            col = self.wall_columns.get(x)
            if col is None:
                col = bytearray(self.h)
                self.wall_columns[x] = col
            col[y] = wall

    def is_solid(self, x, y): return BLOCK_DEFS[self.get(x, y)]["solid"]

    def _compute_sky_heights(self):
        """Recompute sky heights for all generated columns."""
        for x in self.generated_set:
            self.update_sky_height(x)

    def update_sky_height(self, x):
        """Recompute sky height for a single column."""
        if x < 0 or x >= self.w: return
        col = self.tile_columns.get(x)
        if col is None:
            self.sky_heights[x] = self.h
            return
        sh = self.h
        for y in range(self.h):
            tile = col[y]
            if tile in BLOCK_DEFS and BLOCK_DEFS[tile]["opaque"]:
                sh = y; break
        self.sky_heights[x] = sh

    def find_spawn(self):
        rng = random.Random(self.seed * 99991 + 7)
        # Pick a random spawn column uniformly across ALL land biomes (not sea)
        land_biomes = {BIOME_TUNDRA, BIOME_GRASSLAND, BIOME_FOREST, BIOME_JUNGLE, BIOME_SAVANNA, BIOME_DESERT}
        # Try up to 500 random x positions spanning the FULL world width (0.04 to 0.96)
        for _ in range(500):
            cx = rng.randint(int(self.w * 0.04), int(self.w * 0.96))
            if self.biomes[cx] in land_biomes:
                sy = self.surface_y[cx] if cx < len(self.surface_y) else SURFACE
                return cx*TILE+TILE/2, (sy-3)*TILE
        # Fallback: random position
        cx = rng.randint(int(self.w * 0.1), int(self.w * 0.9))
        sy = self.surface_y[cx] if cx < len(self.surface_y) else SURFACE
        return cx*TILE+TILE/2, (sy-3)*TILE

    # ---- liquid simulation ----
    def _ensure_liquid_col(self, x):
        if x not in self.liquid_amount:
            self.liquid_amount[x] = bytearray(self.h)
            self.liquid_type[x] = bytearray(self.h)

    def get_liquid(self, x, y):
        """Return (type, amount) at (x, y). type is LIQUID_NONE/LIQUID_WATER/LIQUID_LAVA."""
        if x < 0 or x >= self.w or y < 0 or y >= self.h:
            return (LIQUID_NONE, 0)
        amt_col = self.liquid_amount.get(x)
        if not amt_col:
            return (LIQUID_NONE, 0)
        return (self.liquid_type[x][y], amt_col[y])

    def get_liquid_amount(self, x, y):
        return self.get_liquid(x, y)[1]

    def _set_liquid_raw(self, x, y, ltype, amount):
        if x < 0 or x >= self.w or y < 0 or y >= self.h:
            return
        amount = max(0, min(MAX_LIQUID, int(amount)))
        self._ensure_liquid_col(x)
        if amount <= 0:
            self.liquid_amount[x][y] = 0
            self.liquid_type[x][y] = LIQUID_NONE
        else:
            self.liquid_amount[x][y] = amount
            self.liquid_type[x][y] = ltype

    def _add_liquid(self, x, y, ltype, delta):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        _, cur_amt = self.get_liquid(x, y)
        new_amt = max(0, min(MAX_LIQUID, cur_amt + delta))
        if new_amt <= 0:
            self._set_liquid_raw(x, y, LIQUID_NONE, 0)
        else:
            self._set_liquid_raw(x, y, ltype, new_amt)

    def mark_liquid_active(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.active_liquids.add((x, y))

    def on_block_changed(self, x, y):
        """Called whenever a tile is placed/removed at runtime (mining, building) so nearby
        liquid wakes up and re-evaluates -- dig a channel and water flows in, dam a stream
        and it stops, place a block in water and it displaces the liquid there."""
        if self.is_solid(x, y):
            if self.get_liquid_amount(x, y) > 0:
                self._set_liquid_raw(x, y, LIQUID_NONE, 0)
        for nx, ny in ((x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            self.mark_liquid_active(nx, ny)

    def _convert_legacy_liquid_column(self, x):
        """Convert any WATER/LAVA tile placeholders in column x into the flowing-liquid layer."""
        col = self.tile_columns.get(x)
        if not col:
            return
        for y in range(self.h):
            t = col[y]
            if t == WATER:
                col[y] = AIR
                self._set_liquid_raw(x, y, LIQUID_WATER, MAX_LIQUID)
            elif t == LAVA:
                col[y] = AIR
                self._set_liquid_raw(x, y, LIQUID_LAVA, MAX_LIQUID)

    def simulate_liquids(self, max_active=LIQUID_MAX_ACTIVE_PER_TICK):
        """One tick of a falling-sand-style liquid cellular automaton. Only processes the
        active set (cells that recently changed or are still settling) so a flat, calm
        ocean costs nothing -- simulation cost tracks how much water is actually moving,
        not how much water exists. Returns a list of (x, y) where lava met water and
        turned to obsidian, so the caller can spawn a steam/particle effect there."""
        if not self.active_liquids:
            return []
        cells = list(self.active_liquids)
        if len(cells) > max_active:
            self.active_liquids = set(cells[max_active:])
            cells = cells[:max_active]
        else:
            self.active_liquids = set()

        obsidian_events = []
        next_active = set()

        for (x, y) in cells:
            if self.is_solid(x, y):
                if self.get_liquid_amount(x, y) > 0:
                    self._set_liquid_raw(x, y, LIQUID_NONE, 0)
                continue
            ltype, amount = self.get_liquid(x, y)
            if amount <= 0:
                continue

            # Lava + water contact -> obsidian (consumes both liquids at the lava's cell)
            reacted = False
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if not (0 <= nx < self.w and 0 <= ny < self.h):
                    continue
                n_type, n_amt = self.get_liquid(nx, ny)
                if n_amt > 0 and n_type != LIQUID_NONE and n_type != ltype:
                    lava_x, lava_y = (x, y) if ltype == LIQUID_LAVA else (nx, ny)
                    water_x, water_y = (nx, ny) if ltype == LIQUID_LAVA else (x, y)
                    self._set_liquid_raw(lava_x, lava_y, LIQUID_NONE, 0)
                    self._set_liquid_raw(water_x, water_y, LIQUID_NONE, 0)
                    lava_col = self.tile_columns.get(lava_x)
                    if lava_col is not None and lava_col[lava_y] == AIR:
                        lava_col[lava_y] = OBSIDIAN
                        self.update_sky_height(lava_x)
                    obsidian_events.append((lava_x, lava_y))
                    for wx, wy in ((lava_x - 1, lava_y), (lava_x + 1, lava_y),
                                   (lava_x, lava_y - 1), (lava_x, lava_y + 1),
                                   (water_x, water_y)):
                        next_active.add((wx, wy))
                    reacted = True
                    break
            if reacted:
                continue

            moved = False
            # 1. Flow downward first
            if not self.is_solid(x, y + 1):
                b_type, b_amt = self.get_liquid(x, y + 1)
                if b_type == LIQUID_NONE or b_type == ltype:
                    capacity = MAX_LIQUID - b_amt
                    if capacity > 0:
                        transfer = min(amount, capacity)
                        if transfer > 0:
                            self._add_liquid(x, y + 1, ltype, transfer)
                            amount -= transfer
                            self._set_liquid_raw(x, y, ltype, amount)
                            moved = True
                            next_active.add((x, y + 1))
                            next_active.add((x - 1, y + 1)); next_active.add((x + 1, y + 1))

            # 2. Spread sideways with whatever's left, toward the lower neighbor
            if amount > MIN_LIQUID:
                for dx in (-1, 1):
                    nx = x + dx
                    if self.is_solid(nx, y) or not self.is_generated(nx):
                        continue
                    n_type, n_amt = self.get_liquid(nx, y)
                    if n_type != LIQUID_NONE and n_type != ltype:
                        continue
                    if n_amt < amount - 1:
                        diff = amount - n_amt
                        transfer = min(diff // 2, LIQUID_FLOW_MAX, amount)
                        if transfer > 0:
                            self._add_liquid(nx, y, ltype, transfer)
                            amount -= transfer
                            self._set_liquid_raw(x, y, ltype, amount)
                            moved = True
                            next_active.add((nx, y))
                            next_active.add((nx, y - 1)); next_active.add((nx, y + 1))
            if moved:
                next_active.add((x, y))

        self.active_liquids |= next_active
        return obsidian_events

# ============================================================
# ENTITIES
# ============================================================

@dataclass
class Player:
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE*0.7; h: float = TILE*1.7
    on_ground: bool = False; facing: int = 1
    health: float = 100.0; max_health: float = 100.0
    hunger: float = 100.0; max_hunger: float = 100.0
    water: float = 100.0; max_water: float = 100.0
    invuln: float = 0.0; spawn: Tuple[float,float] = (0,0)
    in_water: bool = False
    mine_target: Optional[Tuple[int,int]] = None
    mine_progress: float = 0.0; mine_is_wall: bool = False
    attack_cd: float = 0.0
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))
    def respawn(self):
        self.x, self.y = self.spawn; self.vx = 0; self.vy = 0
        self.health = self.max_health; self.hunger = self.max_hunger
        self.water = self.max_water; self.invuln = 1.0

@dataclass
class Slime:
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE; h: float = TILE*0.8
    health: float = 30.0; max_health: float = 30.0
    jump_cd: float = 0.0; on_ground: bool = False
    color: Tuple[int,int,int] = (90,200,120)
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

@dataclass
class Zombie:
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE*0.8; h: float = TILE*1.6
    health: float = 50.0; max_health: float = 50.0
    on_ground: bool = False
    color: Tuple[int,int,int] = (90, 150, 90)
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

@dataclass
class Skeleton:
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE*0.7; h: float = TILE*1.7
    health: float = 60.0; max_health: float = 60.0
    on_ground: bool = False
    color: Tuple[int,int,int] = (200, 200, 210)
    jump_cd: float = 0.0
    shoot_cd: float = 0.0
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

@dataclass
class DemonEye:
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE*0.9; h: float = TILE*0.9
    health: float = 40.0; max_health: float = 40.0
    on_ground: bool = False
    color: Tuple[int,int,int] = (200, 50, 50)
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

@dataclass
class Fish:
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE*0.8; h: float = TILE*0.4
    health: float = 15.0; max_health: float = 15.0
    color: Tuple[int,int,int] = (80, 150, 220)
    direction: float = 1.0  # 1.0 or -1.0
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

@dataclass
class Bat:
    """Flying enemy found in caves. Small, fast, erratic movement."""
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE*0.6; h: float = TILE*0.4
    health: float = 20.0; max_health: float = 20.0
    on_ground: bool = False
    color: Tuple[int,int,int] = (80, 60, 100)
    wander_cd: float = 0.0
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

@dataclass
class Crab:
    """Coastal enemy found near water. Sideways movement, hard shell."""
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    w: float = TILE*0.9; h: float = TILE*0.5
    health: float = 35.0; max_health: float = 35.0
    on_ground: bool = False
    color: Tuple[int,int,int] = (200, 120, 60)
    direction: float = 1.0
    walk_cd: float = 0.0
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

@dataclass
class Arrow:
    x: float; y: float; vx: float; vy: float
    damage: float = 18.0
    life: float = 3.0
    @property
    def rect(self): return pygame.Rect(int(self.x-2), int(self.y-2), 4, 4)

@dataclass
class Particle:
    x: float; y: float; vx: float; vy: float
    life: float; max_life: float
    color: Tuple[int,int,int]; size: float

@dataclass
class DroppedItem:
    """A free-falling, pickable item in the world. Used for the throw gesture
    (RMB pick + LMB throw) and could later be used for general item drops on death.
    The item bounces off solid tiles, lives for `life` seconds, and is auto-picked
    up when the player walks within pickup_radius of it (with a short pickup_delay
    so the thrower doesn't instantly re-grab it)."""
    x: float; y: float; vx: float; vy: float
    item_id: int
    count: int = 1
    durability: Optional[int] = None
    life: float = 120.0
    pickup_delay: float = 0.6   # seconds before the thrower can pick it back up
    bounce_count: int = 0
    @property
    def rect(self): return pygame.Rect(int(self.x-6), int(self.y-6), 12, 12)

# ============================================================
# ANIMALS - passive creatures that spawn in biomes during day
# ============================================================

# Animal type definitions
ANIMAL_RABBIT, ANIMAL_SHEEP, ANIMAL_COW, ANIMAL_GOAT, ANIMAL_CHICKEN, ANIMAL_FROG, ANIMAL_BUTTERFLY, ANIMAL_BIRD = range(8)

ANIMAL_DEFS = {
    ANIMAL_RABBIT: {
        "name": "Rabbit", "color": (200, 180, 160), "size": (0.5, 0.5),
        "health": 8, "speed": 90, "flees": True, "flies": False,
        "drops": [(RAW_MEAT, 1, 0.5)],
        "biomes": {BIOME_GRASSLAND, BIOME_FOREST, BIOME_SAVANNA, BIOME_TUNDRA},
    },
    ANIMAL_SHEEP: {
        "name": "Sheep", "color": (240, 240, 240), "size": (0.9, 0.8),
        "health": 16, "speed": 50, "flees": True, "flies": False,
        "drops": [(WOOL, 1, 1.0), (RAW_MEAT, 1, 0.7)],
        "biomes": {BIOME_GRASSLAND, BIOME_SAVANNA},
    },
    ANIMAL_COW: {
        "name": "Cow", "color": (90, 60, 40), "size": (1.2, 1.0),
        "health": 24, "speed": 35, "flees": False, "flies": False,
        "drops": [(RAW_MEAT, 2, 1.0), (LEATHER, 1, 0.8)],
        "biomes": {BIOME_GRASSLAND, BIOME_SAVANNA},
    },
    ANIMAL_GOAT: {
        "name": "Goat", "color": (180, 170, 160), "size": (0.8, 0.9),
        "health": 18, "speed": 60, "flees": True, "flies": False,
        "drops": [(RAW_MEAT, 1, 0.8), (LEATHER, 1, 0.4)],
        "biomes": {BIOME_TUNDRA, BIOME_SAVANNA, BIOME_GRASSLAND},
    },
    ANIMAL_CHICKEN: {
        "name": "Chicken", "color": (240, 220, 180), "size": (0.5, 0.6),
        "health": 6, "speed": 70, "flees": True, "flies": False,
        "drops": [(FEATHER, 1, 1.0), (RAW_MEAT, 1, 0.6)],
        "biomes": {BIOME_GRASSLAND, BIOME_FOREST, BIOME_SAVANNA},
    },
    ANIMAL_FROG: {
        "name": "Frog", "color": (80, 160, 80), "size": (0.4, 0.4),
        "health": 4, "speed": 80, "flees": True, "flies": False,
        "drops": [],
        "biomes": {BIOME_JUNGLE, BIOME_GRASSLAND, BIOME_FOREST},
    },
    ANIMAL_BUTTERFLY: {
        "name": "Butterfly", "color": (230, 180, 60), "size": (0.3, 0.3),
        "health": 1, "speed": 40, "flees": False, "flies": True,
        "drops": [],
        "biomes": {BIOME_JUNGLE, BIOME_FOREST, BIOME_GRASSLAND},
    },
    ANIMAL_BIRD: {
        "name": "Bird", "color": (120, 160, 200), "size": (0.4, 0.4),
        "health": 5, "speed": 120, "flees": True, "flies": True,
        "drops": [(FEATHER, 2, 1.0), (RAW_MEAT, 1, 0.3)],
        "biomes": {BIOME_FOREST, BIOME_GRASSLAND, BIOME_JUNGLE, BIOME_SAVANNA, BIOME_TUNDRA},
    },
}

@dataclass
class Animal:
    animal_type: int
    x: float; y: float
    vx: float = 0.0; vy: float = 0.0
    health: float = 10.0; max_health: float = 10.0
    on_ground: bool = False
    wander_cd: float = 0.0
    facing: int = 1
    color: Tuple[int,int,int] = (200, 200, 200)
    w: float = TILE * 0.5
    h: float = TILE * 0.5
    @property
    def rect(self): return pygame.Rect(int(self.x-self.w/2), int(self.y-self.h), int(self.w), int(self.h))

# ============================================================
# SAVE / LOAD
# ============================================================

def list_saves():
    saves = []
    if not os.path.isdir(SAVES_DIR): return saves
    for fname in os.listdir(SAVES_DIR):
        if fname.endswith(".json"):
            path = os.path.join(SAVES_DIR, fname)
            try:
                with open(path, "r") as f: data = json.load(f)
                saves.append({"filename": fname, "path": path, "name": data.get("name", fname[:-5]),
                              "seed": data.get("seed", 0), "day": data.get("day_count", 1),
                              "saved_at": data.get("saved_at", 0)})
            except (json.JSONDecodeError, KeyError): continue
    saves.sort(key=lambda s: s["saved_at"], reverse=True)
    return saves

def delete_save(filename):
    path = os.path.join(SAVES_DIR, filename)
    if os.path.exists(path): os.remove(path)

def rename_save(filename, new_name):
    """Rename a save's display name and filename without changing its world data."""
    new_name = new_name.strip()[:24]
    if not new_name:
        return None
    path = os.path.join(SAVES_DIR, filename)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        data["name"] = new_name
        seed = data.get("seed", 0)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in new_name)[:32] or "World"
        new_filename = f"{safe_name}_{seed}_{int(data.get('saved_at', time.time()))}.json"
        new_path = os.path.join(SAVES_DIR, new_filename)
        with open(new_path, "w") as f:
            json.dump(data, f)
        if new_path != path:
            os.remove(path)
        return new_filename
    except (IOError, OSError, json.JSONDecodeError):
        return None

def save_world(world, player, inventory, time_of_day, day_count, name, seed, chests=None, armor=None):
    # New format: save only generated columns (much smaller file size)
    generated_columns = world.get_generated_columns()
    liquid_columns = world.get_liquid_columns()
    data = {"name": name, "seed": seed, "time": time_of_day, "day_count": day_count,
            "saved_at": time.time(), "world_w": world.w, "world_h": world.h,
            "generated_columns": generated_columns,
            "liquid_columns": liquid_columns,
            "surface_y": world.surface_y.tolist(),
            "biomes": getattr(world, "biomes", None).tolist() if getattr(world, "biomes", None) is not None else None,
            "player_x": player.x, "player_y": player.y, "player_health": player.health,
            "player_hunger": getattr(player, 'hunger', 100.0),
            "player_water": getattr(player, 'water', 100.0),
            "inventory": inventory.to_dict(),
            "chests": {k: v.to_dict() for k, v in chests.items()} if chests else {},
            "armor": [{"id": a.item_id, "count": a.count, "dur": a.durability} if a else None for a in armor] if armor else [None]*4}
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:32]
    # Delete old saves with the same name+seed to avoid duplicates
    prefix = f"{safe_name}_{seed}_"
    if os.path.isdir(SAVES_DIR):
        for old_fname in os.listdir(SAVES_DIR):
            if old_fname.startswith(prefix) and old_fname.endswith(".json"):
                try: os.remove(os.path.join(SAVES_DIR, old_fname))
                except OSError: pass
    filename = f"{safe_name}_{seed}_{int(data['saved_at'])}.json"
    path = os.path.join(SAVES_DIR, filename)
    with open(path, "w") as f: json.dump(data, f)
    return filename

def load_world_data(filename):
    path = os.path.join(SAVES_DIR, filename)
    if not os.path.exists(path): return None
    try:
        with open(path, "r") as f: return json.load(f)
    except (json.JSONDecodeError, IOError): return None

# ============================================================
# MAIN MENU
# ============================================================

class MainMenu:
    def __init__(self, screen, font, font_big, font_huge):
        self.screen = screen; self.font = font; self.font_big = font_big
        self.font_huge = font_huge
        self.state = "main"
        self.new_world_name = ""; self.new_world_seed = ""; self.input_field = "name"
        self.saves = []; self.selected_save = None; self.rename_name = None
        self.error_msg = ""; self.error_timer = 0
        # Use actual screen size for all positioning (handles fullscreen correctly)
        self.scr_w, self.scr_h = screen.get_size()
        # Scale factor from design resolution to actual screen
        self.menu_scale = self.scr_w / 1280.0
        self.font_sm = _make_font(max(11, int(11 * self.menu_scale)))
        self.menu_seed = random.randrange(1 << 30)
        self.menu_world = World(WORLD_W, WORLD_H, self.menu_seed)
        self.menu_start_x = (self.menu_seed % (WORLD_W - 80)) + 40
        self.title_anim = 0.0
        self.menu_time = 0.30  # start at dawn for a nice sky
        self.menu_time_speed = 0.02  # slow time passage for visual effect
        # Build block textures for the menu (same as in-game)
        self.block_textures = {}
        self._build_menu_block_textures()
        # Build wall (background block) textures for the menu so caves in the
        # background terrain show dirt / stone walls instead of sky color.
        self.wall_textures = {}
        self._build_menu_wall_textures()
        # Generate some stars for the menu sky (spread across full screen)
        self.stars = [(random.randint(0, self.scr_w), random.randint(0, self.scr_h // 2),
                       random.randint(150, 255)) for _ in range(100)]
        # Scroll offset for load world screen
        self.load_scroll = 0
        self.load_scroll_max = 0

    def run(self):
        clock = pygame.time.Clock()
        # WINDOW_W/H are already set to screen size by _init_fullscreen_display
        try:
            while True:
                dt = clock.tick(FPS) / 1000.0
                self.title_anim += dt
                self.menu_time = (self.menu_time + self.menu_time_speed * dt) % 1.0
                if self.error_timer > 0: self.error_timer = max(0, self.error_timer - dt)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT: return None
                    elif event.type == pygame.KEYDOWN:
                        r = self._handle_key(event)
                        if r is not None: return r
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        r = self._handle_click(event)
                        if r is not None: return r
                    elif event.type == pygame.MOUSEWHEEL:
                        if self.state == "load":
                            self.load_scroll = max(0, min(self.load_scroll_max,
                                self.load_scroll - event.y * 40))
                self._draw()
                pygame.display.flip()
        finally:
            pass  # WINDOW_W/H restored by caller

    def _handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.state == "load" and self.rename_name is not None:
                self.rename_name = None
            elif self.state == "main": return None
            else: self.state = "main"; self.error_msg = ""
        elif self.state == "main":
            if event.key == pygame.K_n: self.state = "new"; self.new_world_name = ""; self.new_world_seed = ""; self.input_field = "name"
            elif event.key == pygame.K_l: self.state = "load"; self.saves = list_saves()
            elif event.key == pygame.K_q: return None
        elif self.state == "new":
            if event.key == pygame.K_RETURN: return self._create_world()
            elif event.key == pygame.K_TAB: self.input_field = "seed" if self.input_field == "name" else "name"
            elif event.key == pygame.K_BACKSPACE:
                if self.input_field == "name": self.new_world_name = self.new_world_name[:-1]
                else: self.new_world_seed = self.new_world_seed[:-1]
            elif event.unicode and event.unicode.isprintable():
                if self.input_field == "name" and len(self.new_world_name) < 24: self.new_world_name += event.unicode
                elif self.input_field == "seed" and len(self.new_world_seed) < 10: self.new_world_seed += event.unicode
        elif self.state == "load":
            if self.rename_name is not None:
                if event.key == pygame.K_RETURN:
                    renamed = rename_save(self.selected_save["filename"], self.rename_name) if self.selected_save else None
                    if renamed:
                        self.saves = list_saves()
                        self.selected_save = next((s for s in self.saves if s["filename"] == renamed), None)
                    self.rename_name = None
                elif event.key == pygame.K_BACKSPACE:
                    self.rename_name = self.rename_name[:-1]
                elif event.unicode and event.unicode.isprintable() and len(self.rename_name) < 24:
                    self.rename_name += event.unicode
            elif event.key == pygame.K_r and self.selected_save:
                self.rename_name = self.selected_save["name"]
            elif event.key == pygame.K_d and self.selected_save:
                delete_save(self.selected_save["filename"]); self.saves = list_saves(); self.selected_save = None
            elif event.key == pygame.K_l and self.selected_save:
                return {"action": "load", "filename": self.selected_save["filename"]}
        return None

    def _handle_click(self, event):
        mx, my = event.pos
        if event.button != 1: return None
        play_sound("click", 0.3)
        if self.state == "main":
            for btn in self._main_buttons():
                if btn["rect"].collidepoint(mx, my):
                    if btn["action"] == "new": self.state = "new"; self.new_world_name = ""; self.new_world_seed = ""; self.input_field = "name"
                    elif btn["action"] == "load": self.state = "load"; self.saves = list_saves()
                    elif btn["action"] == "quit": return {"action": "quit"}
        elif self.state == "new":
            cx = self.scr_w // 2
            pw, ph = int(480 * self.menu_scale), int(340 * self.menu_scale)
            panel_y = self.scr_h // 2 - ph // 2
            fw = int(400 * self.menu_scale)
            name_rect = pygame.Rect(cx - fw // 2, panel_y + 54 + 26, fw, 40)
            seed_rect = pygame.Rect(cx - fw // 2, panel_y + 144 + 26, fw, 40)
            if name_rect.collidepoint(mx, my): self.input_field = "name"
            elif seed_rect.collidepoint(mx, my): self.input_field = "seed"
            bw = int(180 * self.menu_scale)
            bh = int(40 * self.menu_scale)
            gap = int(16 * self.menu_scale)
            btn_y = panel_y + ph - int(56 * self.menu_scale)
            create_r = pygame.Rect(cx - bw - gap // 2, btn_y, bw, bh)
            back_r   = pygame.Rect(cx + gap // 2,      btn_y, bw, bh)
            if create_r.collidepoint(mx, my): return self._create_world()
            if back_r.collidepoint(mx, my): self.state = "main"
        elif self.state == "load":
            cx = self.scr_w // 2
            pw = int(min(700, self.scr_w * 0.72) * self.menu_scale)
            list_h = int(self.scr_h * 0.58)
            panel_y = int(self.scr_h * 0.14)
            entry_h = int(80 * self.menu_scale)
            list_rect = pygame.Rect(cx - pw // 2 + 10, panel_y + 48, pw - 20, list_h - 48)
            bw_s = int(84 * self.menu_scale)
            bh_s = int(32 * self.menu_scale)
            for i, save in enumerate(self.saves):
                ey = list_rect.y + i * entry_h - self.load_scroll
                if ey + entry_h < list_rect.y or ey > list_rect.bottom:
                    continue
                card_rect = pygame.Rect(list_rect.x + 4, ey, list_rect.w - 8, entry_h - 6)
                bx_start = card_rect.right - (bw_s + 6) * 3 - 6
                btn_y_c = ey + (card_rect.h - bh_s) // 2
                load_card   = pygame.Rect(bx_start,              btn_y_c, bw_s, bh_s)
                rename_rect = pygame.Rect(bx_start + bw_s + 6,   btn_y_c, bw_s, bh_s)
                delete_card = pygame.Rect(bx_start + (bw_s+6)*2, btn_y_c, bw_s, bh_s)
                if load_card.collidepoint(mx, my): return {"action": "load", "filename": save["filename"]}
                if rename_rect.collidepoint(mx, my): self.selected_save = save; self.rename_name = save["name"]; break
                if delete_card.collidepoint(mx, my): delete_save(save["filename"]); self.saves = list_saves(); self.selected_save = None; break
                if card_rect.collidepoint(mx, my): self.selected_save = save; break
            bw2 = int(180 * self.menu_scale)
            bh2 = int(40 * self.menu_scale)
            panel_bottom = panel_y + list_h + 10
            back_rect = pygame.Rect(cx - bw2 // 2, panel_bottom + 12, bw2, bh2)
            if back_rect.collidepoint(mx, my): self.state = "main"
        return None

    def _create_world(self):
        name = self.new_world_name.strip() or "World"
        if self.new_world_seed.strip():
            try: seed = int(self.new_world_seed.strip())
            except ValueError: self.error_msg = "Seed must be a number"; self.error_timer = 3.0; return None
        else: seed = random.randint(0, 2**31 - 1)
        return {"action": "new", "name": name, "seed": seed}

    def _main_buttons(self):
        cx = self.scr_w // 2
        btn_w = int(240 * self.menu_scale)
        btn_h = int(42 * self.menu_scale)
        btn_gap = int(52 * self.menu_scale)
        start_y = int(self.scr_h * 0.44)
        return [{"label": a, "action": b,
                 "rect": pygame.Rect(cx - btn_w // 2, start_y + i * btn_gap, btn_w, btn_h)}
                for i, (a, b) in enumerate([("New World", "new"), ("Load World", "load"), ("Quit", "quit")])]

    def _build_menu_block_textures(self):
        """Build simplified block textures for the menu background.
        Uses the same visual style as in-game block_textures."""
        # Non-solid decorative blocks: do NOT fill the tile with their base color,
        # otherwise they show up as opaque colored squares in the menu (e.g. dried
        # grass as a solid yellow square, grass tuft as a solid green square).
        # Instead we give them a transparent background and a small icon-ish glyph
        # so the dirt / grass block underneath shows through, matching in-game look.
        decorative_blocks = {
            GRASS_TUFT, DRIED_GRASS, TALL_GRASS, DRIED_TALL_GRASS, BUSH, BUSH_FRUIT,
            FLOWER, FLOWER_RED, FLOWER_YELLOW, FLOWER_BLUE, FLOWER_WHITE,
            ROCK, SMALL_STONE, VINE,
        }
        for block, d in BLOCK_DEFS.items():
            if block == AIR: continue
            surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            base = d["color"]
            rng = random.Random(block * 99)
            if block in decorative_blocks:
                # Transparent background; draw a simple representative glyph so
                # the menu background doesn't have bare colored squares.
                surf.fill((0, 0, 0, 0))
                if block in (GRASS_TUFT, TALL_GRASS, DRIED_TALL_GRASS):
                    # Green blades
                    for i in range(5):
                        bx = 4 + i * 3
                        h = rng.randint(6, 11)
                        pygame.draw.line(surf, base, (bx, TILE-2), (bx, TILE-2-h), 1)
                        pygame.draw.line(surf, self._shade_menu(base, 25), (bx+1, TILE-2), (bx+1, TILE-2-h+1), 1)
                elif block == DRIED_GRASS:
                    # Yellow-tan blades on transparent bg
                    for i in range(5):
                        bx = 4 + i * 3
                        h = rng.randint(5, 10)
                        pygame.draw.line(surf, base, (bx, TILE-2), (bx, TILE-2-h), 1)
                        pygame.draw.line(surf, self._shade_menu(base, 25), (bx+1, TILE-2), (bx+1, TILE-2-h+1), 1)
                elif block in (BUSH, BUSH_FRUIT):
                    pygame.draw.ellipse(surf, self._shade_menu(base, -25), (2, 7, TILE-4, TILE-9))
                    pygame.draw.ellipse(surf, base, (3, 8, TILE-6, TILE-11))
                    pygame.draw.ellipse(surf, self._shade_menu(base, 25), (5, 9, TILE-12, TILE-15))
                    if block == BUSH_FRUIT:
                        for (bx, by) in [(7, 12), (15, 11), (11, 16), (17, 15)]:
                            pygame.draw.circle(surf, (180, 30, 40), (bx, by), 2)
                elif block == ROCK:
                    pygame.draw.ellipse(surf, self._shade_menu(base, -30), (2, 6, TILE-4, TILE-8))
                    pygame.draw.ellipse(surf, base, (3, 7, TILE-6, TILE-10))
                    pygame.draw.ellipse(surf, self._shade_menu(base, 25), (5, 9, 6, 4))
                elif block == SMALL_STONE:
                    pygame.draw.ellipse(surf, base, (5, 10, 9, 6))
                    pygame.draw.ellipse(surf, self._shade_menu(base, 25), (7, 11, 3, 2))
                    pygame.draw.ellipse(surf, self._shade_menu(base, -10), (3, 13, 5, 3))
                elif block == VINE:
                    for i in range(3):
                        bx = 5 + i * 5
                        pygame.draw.line(surf, base, (bx, 0), (bx, TILE-2), 1)
                elif block in (FLOWER, FLOWER_RED, FLOWER_YELLOW, FLOWER_BLUE, FLOWER_WHITE):
                    # Stem + colored bloom
                    pygame.draw.line(surf, (60, 120, 40), (TILE//2, TILE-2), (TILE//2, TILE//2), 1)
                    pygame.draw.circle(surf, base, (TILE//2, TILE//2 - 1), 3)
                    pygame.draw.circle(surf, self._shade_menu(base, 40), (TILE//2 - 1, TILE//2 - 2), 1)
                self.block_textures[block] = surf
                continue
            # Solid blocks: fill with base color
            surf.fill(base)
            # Leaf-like texture noise
            if block in ALL_LEAF_TYPES or block in (GRASS, JUNGLE_GRASS, SAVANNA_GRASS):
                for _ in range(10):
                    surf.set_at((rng.randint(0, TILE-1), rng.randint(0, TILE-1)),
                                self._shade_menu(base, rng.randint(-25, 25)))
            # Wood/stone bevel texture
            elif block in (DIRT, SAND, STONE, PLANK, BRICK, TREE_TRUNK, WOOD,
                           SANDSTONE, LIMESTONE, GRANITE, BASALT, PINE_TRUNK, CACTUS,
                           TREE_GIANT, TREE_DEAD, TREE_BENT):
                lighter = self._shade_menu(base, 18)
                darker = self._shade_menu(base, -18)
                for sx in range(1, TILE-1):
                    surf.set_at((sx, 0), lighter)
                for sy in range(1, TILE-1):
                    surf.set_at((0, sy), lighter)
                for sx in range(1, TILE-1):
                    surf.set_at((sx, TILE-1), darker)
                for sy in range(1, TILE-1):
                    surf.set_at((TILE-1, sy), darker)
                for _ in range(18):
                    surf.set_at((rng.randint(1, TILE-2), rng.randint(1, TILE-2)),
                                self._shade_menu(base, rng.randint(-20, 20)))
            self.block_textures[block] = surf

    def _draw_menu_sky(self):
        """Draw the sky with the same logic as in-game (day/night cycle, stars, sun/moon)."""
        t = self.menu_time
        W, H = WINDOW_W, WINDOW_H
        # Sky color based on time of day (same as in-game)
        if t < 0.20: sky = COL_SKY_NIGHT
        elif t < 0.30: sky = self._lerp_color_menu(COL_SKY_NIGHT, COL_SKY_DUSK, (t-0.20)/0.10)
        elif t < 0.40: sky = self._lerp_color_menu(COL_SKY_DUSK, COL_SKY_DAY, (t-0.30)/0.10)
        elif t < 0.60: sky = COL_SKY_DAY
        elif t < 0.70: sky = self._lerp_color_menu(COL_SKY_DAY, COL_SKY_DUSK, (t-0.60)/0.10)
        elif t < 0.80: sky = self._lerp_color_menu(COL_SKY_DUSK, COL_SKY_NIGHT, (t-0.70)/0.10)
        else: sky = COL_SKY_NIGHT
        self.screen.fill(sky)
        # Stars at night
        if t < 0.20 or t > 0.80:
            for sx, sy, br in self.stars:
                if 0 <= sx < W and 0 <= sy < H:
                    self.screen.set_at((sx, sy), (br, br, br))
        # Sun during day
        sun_angle = (t - 0.25) * math.tau
        sx = W/2 + math.cos(sun_angle) * (W*0.45)
        sy_pos = H*0.55 - math.sin(sun_angle) * (H*0.45)
        if 0.20 < t < 0.80:
            pygame.draw.circle(self.screen, (255, 230, 130), (int(sx), int(sy_pos)), 28)
            pygame.draw.circle(self.screen, (255, 200, 80), (int(sx), int(sy_pos)), 22)
        else:
            ma = sun_angle + math.pi
            mx = W/2 + math.cos(ma) * (W*0.45)
            my = H*0.55 - math.sin(ma) * (H*0.45)
            pygame.draw.circle(self.screen, (230, 230, 240), (int(mx), int(my)), 22)
            pygame.draw.circle(self.screen, sky, (int(mx)+8, int(my)-4), 18)

    def _build_menu_wall_textures(self):
        """Build simplified wall (background block) textures for the menu background.
        Mirrors Game._build_wall_textures but uses _shade_menu for consistency
        with the other menu textures. Without this, caves in the menu's background
        terrain show the sky color through them instead of dirt / stone walls."""
        for wall, d in WALL_DEFS.items():
            surf = pygame.Surface((TILE, TILE))
            base = d["color"]
            surf.fill(base)
            rng = random.Random(wall * 777)
            # Sprinkle a few darker / lighter pixels for a noisy stone / dirt feel
            for _ in range(14):
                surf.set_at((rng.randint(0, TILE-1), rng.randint(0, TILE-1)),
                            self._shade_menu(base, rng.randint(-15, 15)))
            self.wall_textures[wall] = surf.convert()

    def _draw_menu_background(self):
        """Render a randomly seeded slice of the actual game world behind the menu,
        using the same sky rendering and block textures as in-game.
        Renders at the screen's native resolution (no upscaling) for crisp pixels,
        matching the in-game zoom level.

        Two-pass draw (mirrors Game._draw_world):
          1. Walls first - only where the foreground is AIR. This is what gives
             caves their dirt / stone background instead of seeing sky through
             every hollowed-out cavern.
          2. Foreground blocks on top."""
        self._draw_menu_sky()
        sw, sh = self.screen.get_size()
        cols = sw // TILE + 3
        for tx in range(self.menu_start_x, self.menu_start_x + cols):
            if tx not in self.menu_world.generated_set:
                self.menu_world.generate_column(tx)
        anchor = int(np.median(self.menu_world.surface_y[self.menu_start_x:self.menu_start_x + cols]))
        top_y = anchor - 14
        ty_lo = top_y
        ty_hi = min(self.menu_world.h, top_y + sh // TILE + 2)
        # Pass 1: draw walls where foreground is AIR (so caves have backgrounds)
        for sx_col, tx in enumerate(range(self.menu_start_x, self.menu_start_x + cols)):
            col = self.menu_world.tile_columns.get(tx)
            if not col: continue
            wall_col = self.menu_world.wall_columns.get(tx)
            sx = sx_col * TILE
            for ty in range(ty_lo, ty_hi):
                if col[ty] != AIR: continue
                if not wall_col: continue
                wall = wall_col[ty]
                if wall == WALL_NONE: continue
                tex = self.wall_textures.get(wall)
                if tex:
                    sy = (ty - top_y) * TILE
                    self.screen.blit(tex, (sx, sy))
        # Pass 2: draw foreground blocks on top
        for sx_col, tx in enumerate(range(self.menu_start_x, self.menu_start_x + cols)):
            col = self.menu_world.tile_columns.get(tx)
            if not col: continue
            sx = sx_col * TILE
            for ty in range(ty_lo, ty_hi):
                block = col[ty]
                if block == AIR: continue
                tex = self.block_textures.get(block)
                if tex:
                    sy = (ty - top_y) * TILE
                    self.screen.blit(tex, (sx, sy))

    @staticmethod
    def _shade_menu(c, amount):
        return tuple(max(0, min(255, v + amount)) for v in c)

    @staticmethod
    def _lerp_color_menu(a, b, k):
        return (int(a[0]+(b[0]-a[0])*k), int(a[1]+(b[1]-a[1])*k), int(a[2]+(b[2]-a[2])*k))

    def _draw_panel_background(self, alpha=180):
        """Draw a semi-transparent dark overlay for create/load screens."""
        overlay = pygame.Surface((self.scr_w, self.scr_h), pygame.SRCALPHA)
        overlay.fill((10, 12, 30, alpha))
        self.screen.blit(overlay, (0, 0))

    def _draw_panel(self, rect, header_text=None):
        """Draw a clean dark-slate panel matching the game's pixel art aesthetic."""
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (22, 28, 48, 230), (0, 0, rect.w, rect.h), border_radius=8)
        self.screen.blit(surf, rect.topleft)
        pygame.draw.rect(self.screen, (75, 100, 150), rect, 2, border_radius=8)
        if header_text:
            lbl = self.font_big.render(header_text, True, (255, 230, 130))
            self.screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.y + 16))

    def _draw_button(self, rect, label, font, base_color=None, hovered=False, border_color=None):
        """Draw a clean, uniform dark-slate game button with subtle gold hover state."""
        fill = (52, 66, 102, 235) if hovered else (38, 48, 76, 215)
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, fill, (0, 0, rect.w, rect.h), border_radius=6)
        self.screen.blit(surf, rect.topleft)
        bc = (255, 215, 90) if hovered else (85, 110, 155)
        pygame.draw.rect(self.screen, bc, rect, 2, border_radius=6)
        tc = (255, 235, 140) if hovered else (240, 245, 255)
        t = font.render(label, True, tc)
        sh = font.render(label, True, (0, 0, 0))
        sh.set_alpha(150)
        self.screen.blit(sh, (rect.centerx - t.get_width() // 2 + 1, rect.centery - t.get_height() // 2 + 1))
        self.screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))

    def _draw(self):
        self._draw_menu_background()
        if self.state == "main":
            title = self.font_huge.render("BOUNDLESS STRATA", True, (255, 230, 130))
            ty = int(self.scr_h * 0.10) + math.sin(self.title_anim * 1.5) * 5
            sh = self.font_huge.render("BOUNDLESS STRATA", True, (0, 0, 0))
            cx = self.scr_w // 2
            self.screen.blit(sh, (cx - title.get_width()//2 + 3, ty + 3))
            self.screen.blit(title, (cx - title.get_width()//2, ty))
            self._draw_main()
        elif self.state == "new":
            self._draw_new()
        else:
            self._draw_load()

    def _draw_main(self):
        mx, my = pygame.mouse.get_pos()
        for b in self._main_buttons():
            r = b["rect"]
            hovered = r.collidepoint(mx, my)
            self._draw_button(r, b["label"], self.font_big, hovered=hovered)

    def _draw_new(self):
        self._draw_panel_background(200)
        cx = self.scr_w // 2
        pw, ph = int(480 * self.menu_scale), int(340 * self.menu_scale)
        panel = pygame.Rect(cx - pw // 2, self.scr_h // 2 - ph // 2, pw, ph)
        self._draw_panel(panel, header_text="Create New World")
        mx, my = pygame.mouse.get_pos()
        # Input fields
        field_configs = [
            ("World Name", "name", "e.g. World", 54),
            ("Seed  (blank for random)", "seed", "e.g. 12345", 144),
        ]
        fw = int(400 * self.menu_scale)
        for flabel, field, placeholder, fy_off in field_configs:
            fy = panel.y + fy_off
            lbl = self.font.render(flabel, True, (180, 200, 235))
            self.screen.blit(lbl, (cx - fw // 2, fy))
            inp = pygame.Rect(cx - fw // 2, fy + 26, fw, 40)
            active = self.input_field == field
            fsurf = pygame.Surface((inp.w, inp.h), pygame.SRCALPHA)
            pygame.draw.rect(fsurf, (15, 20, 36, 240), (0, 0, inp.w, inp.h), border_radius=5)
            self.screen.blit(fsurf, inp.topleft)
            bc = (255, 215, 90) if active else (70, 95, 140)
            pygame.draw.rect(self.screen, bc, inp, 2, border_radius=5)
            value = self.new_world_name if field == "name" else self.new_world_seed
            if value:
                self.screen.blit(self.font.render(value, True, (255, 255, 255)), (inp.x + 10, inp.y + 9))
            else:
                self.screen.blit(self.font.render(placeholder, True, (90, 100, 130)), (inp.x + 10, inp.y + 9))
            if active and int(self.title_anim * 2) % 2 == 0:
                cur_x = inp.x + 10 + self.font.size(value)[0]
                pygame.draw.line(self.screen, (255, 215, 90), (cur_x, inp.y + 7), (cur_x, inp.y + 33), 2)
        # Buttons
        bw = int(180 * self.menu_scale)
        bh = int(40 * self.menu_scale)
        gap = int(16 * self.menu_scale)
        btn_y = panel.y + ph - int(56 * self.menu_scale)
        create_r = pygame.Rect(cx - bw - gap // 2, btn_y, bw, bh)
        back_r   = pygame.Rect(cx + gap // 2,      btn_y, bw, bh)
        self._draw_button(create_r, "Create",     self.font_big, hovered=create_r.collidepoint(mx, my))
        self._draw_button(back_r,   "Back (ESC)", self.font_big, hovered=back_r.collidepoint(mx, my))
        if self.error_msg and self.error_timer > 0:
            err = self.font.render(self.error_msg, True, (255, 100, 100))
            self.screen.blit(err, (cx - err.get_width() // 2, btn_y - 24))

    def _draw_load(self):
        self._draw_panel_background(200)
        cx = self.scr_w // 2
        mx, my = pygame.mouse.get_pos()
        pw = int(min(700, self.scr_w * 0.72) * self.menu_scale)
        list_h = int(self.scr_h * 0.58)
        panel_y = int(self.scr_h * 0.14)
        panel = pygame.Rect(cx - pw // 2, panel_y, pw, list_h + 10)
        self._draw_panel(panel, header_text="Load World")
        entry_h = int(80 * self.menu_scale)
        list_rect = pygame.Rect(panel.x + 10, panel.y + 48, panel.w - 20, list_h - 48)
        total_content_h = len(self.saves) * entry_h
        self.load_scroll_max = max(0, total_content_h - list_rect.h + 10)
        clip_surf = pygame.Surface((list_rect.w, list_rect.h), pygame.SRCALPHA)
        for i, s in enumerate(self.saves):
            ey = i * entry_h - self.load_scroll
            if ey + entry_h < 0 or ey > list_rect.h:
                continue
            card = pygame.Rect(4, ey, list_rect.w - 8, entry_h - 6)
            is_selected = self.selected_save and self.selected_save["filename"] == s["filename"]
            csurf = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
            pygame.draw.rect(csurf, (32, 40, 64, 220) if is_selected else (22, 28, 46, 200), (0, 0, card.w, card.h), border_radius=6)
            clip_surf.blit(csurf, card.topleft)
            bc = (255, 215, 90) if is_selected else (60, 80, 125)
            pygame.draw.rect(clip_surf, bc, card, 1 if not is_selected else 2, border_radius=6)
            n = self.font_big.render(s["name"], True, (240, 245, 255))
            clip_surf.blit(n, (card.x + 14, ey + 8))
            info_txt = f"Day {s['day']}  |  Seed: {s['seed']}"
            info = self.font_sm.render(info_txt, True, (140, 160, 195))
            clip_surf.blit(info, (card.x + 14, ey + 8 + n.get_height() + 4))
            # Action buttons
            bw_s = int(84 * self.menu_scale)
            bh_s = int(32 * self.menu_scale)
            bx_start = card.right - (bw_s + 6) * 3 - 6
            btn_defs = [("Load", "load"), ("Rename", "rename"), ("Delete", "delete")]
            for bi, (blabel, baction) in enumerate(btn_defs):
                bx = bx_start + bi * (bw_s + 6)
                by = ey + (card.h - bh_s) // 2
                br = pygame.Rect(bx, by, bw_s, bh_s)
                card_mx, card_my = mx - list_rect.x, my - list_rect.y
                b_hovered = br.collidepoint(card_mx, card_my)
                fill = (52, 66, 102) if not b_hovered else (70, 88, 130)
                if baction == "delete" and b_hovered:
                    fill = (120, 40, 40)
                bsurf = pygame.Surface((bw_s, bh_s), pygame.SRCALPHA)
                pygame.draw.rect(bsurf, fill, (0, 0, bw_s, bh_s), border_radius=4)
                clip_surf.blit(bsurf, br.topleft)
                border_c = (255, 215, 90) if b_hovered else (80, 100, 140)
                pygame.draw.rect(clip_surf, border_c, br, 1, border_radius=4)
                bt = self.font_sm.render(blabel, True, (255, 255, 255) if not b_hovered else (255, 235, 140))
                clip_surf.blit(bt, (br.centerx - bt.get_width() // 2, br.centery - bt.get_height() // 2))
        self.screen.blit(clip_surf, list_rect.topleft)
        # Scrollbar
        if self.load_scroll_max > 0:
            sb_x = list_rect.right + 6
            sb_h = list_rect.h
            pygame.draw.rect(self.screen, (25, 30, 50), (sb_x, list_rect.y, 6, sb_h), border_radius=3)
            thumb_ratio = list_rect.h / max(1, total_content_h)
            thumb_h = max(24, int(sb_h * thumb_ratio))
            thumb_y = list_rect.y + int((self.load_scroll / max(1, self.load_scroll_max)) * (sb_h - thumb_h))
            pygame.draw.rect(self.screen, (90, 115, 165), (sb_x, thumb_y, 6, thumb_h), border_radius=3)
        # Back button
        bw2 = int(180 * self.menu_scale)
        bh2 = int(40 * self.menu_scale)
        panel_bottom = panel_y + list_h + 10
        back_rect = pygame.Rect(cx - bw2 // 2, panel_bottom + 12, bw2, bh2)
        self._draw_button(back_rect, "Back (ESC)", self.font_big, hovered=back_rect.collidepoint(mx, my))
        if len(self.saves) > 5:
            hint = self.font_sm.render("Scroll with mouse wheel", True, (100, 115, 145))
            self.screen.blit(hint, (cx - hint.get_width() // 2, back_rect.bottom + 6))
        if not self.saves:
            msg = self.font_big.render("No saved worlds yet.", True, (120, 130, 160))
            self.screen.blit(msg, (cx - msg.get_width() // 2, list_rect.y + list_rect.h // 2 - msg.get_height() // 2))
        if self.rename_name is not None:
            dim = pygame.Surface((self.scr_w, self.scr_h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 140))
            self.screen.blit(dim, (0, 0))
            mw, mh = int(440 * self.menu_scale), int(150 * self.menu_scale)
            modal = pygame.Rect(cx - mw // 2, self.scr_h // 2 - mh // 2, mw, mh)
            self._draw_panel(modal, header_text="Rename World")
            inp = pygame.Rect(modal.x + 20, modal.y + 54, modal.w - 40, 38)
            isurf = pygame.Surface((inp.w, inp.h), pygame.SRCALPHA)
            pygame.draw.rect(isurf, (15, 20, 36, 240), (0, 0, inp.w, inp.h), border_radius=5)
            self.screen.blit(isurf, inp.topleft)
            pygame.draw.rect(self.screen, (255, 215, 90), inp, 2, border_radius=5)
            self.screen.blit(self.font.render(self.rename_name, True, (255, 255, 255)), (inp.x + 10, inp.y + 8))
            if int(self.title_anim * 2) % 2 == 0:
                cur_x = inp.x + 10 + self.font.size(self.rename_name)[0]
                pygame.draw.line(self.screen, (255, 215, 90), (cur_x, inp.y + 6), (cur_x, inp.y + 32), 2)
            hint = self.font_sm.render("Press Enter to confirm, ESC to cancel", True, (140, 160, 200))
            self.screen.blit(hint, (cx - hint.get_width() // 2, inp.bottom + 8))

# ============================================================
# GAME
# ============================================================

class Game:
    def __init__(self, seed=None, fullscreen=True, world_data=None, world_name="World"):
        pygame.init()
        self.fullscreen = fullscreen
        self.screen_w = 1280
        self.screen_h = 720
        self.render_surface = None
        self.screen = self._init_display()
        pygame.display.set_caption("Boundless Strata")
        self.clock = pygame.time.Clock()
        self.ui_scale = ui_scale
        # Scale fonts proportionally to screen resolution
        _fs = self.screen_w / 1280.0
        self.font = _make_font(max(14, int(14 * _fs)))
        self.font_big = _make_font(max(22, int(22 * _fs)), bold=True)
        self.font_sm = _make_font(max(11, int(11 * _fs)))
        self.font_huge = _make_font(max(64, int(64 * _fs)), bold=True)
        self._slot_size = max(44, int(44 * _fs))
        self._icon_size = max(9, int(9 * _fs))
        self._icon_gap = max(1, int(1 * _fs))
        # UI layout uses design resolution (no coordinate scaling)
        self._ui_w = self.screen_w
        self._ui_h = self.screen_h
        self.world_name = world_name

        # Initialize chest storage before loading world data
        self.chests: Dict[str, Inventory] = {}
        # Seedling growth tracking
        self.seedlings: Dict[Tuple[int,int], dict] = {}

        if world_data:
            self.seed = world_data.get("seed", 0)
            self.world = World(WORLD_W, WORLD_H, self.seed)
            # Handle both old format (full tiles array) and new format (generated columns only)
            if "generated_columns" in world_data:
                # New format: load only generated columns (and liquid layer if present)
                self.world.load_generated_columns(world_data["generated_columns"], world_data.get("liquid_columns"))
            elif "tiles" in world_data:
                # Old format: full tiles array - convert to column-based storage
                old_tiles = world_data["tiles"]
                old_walls = world_data.get("walls", [])
                old_w = world_data.get("world_w", len(old_tiles[0]) if old_tiles else WORLD_W)
                old_h = world_data.get("world_h", len(old_tiles))
                # Copy old tiles into new world as bytearrays
                for x in range(min(self.world.w, old_w)):
                    col = bytearray(self.world.h)
                    wall_col = bytearray(self.world.h)
                    for y in range(min(self.world.h, old_h)):
                        if y < len(old_tiles) and x < len(old_tiles[y]):
                            col[y] = old_tiles[y][x] & 0xFF
                        if y < len(old_walls) and x < len(old_walls[y]):
                            wall_col[y] = old_walls[y][x] & 0xFF
                    self.world.tile_columns[x] = col
                    self.world.wall_columns[x] = wall_col
                    self.world.generated_set.add(x)
                    self.world.generated_depth[x] = self.world.h
                    self.world.update_sky_height(x)
                    # Convert any baked WATER/LAVA tiles into the flowing-liquid layer.
                    self.world._convert_legacy_liquid_column(x)
            if "surface_y" in world_data and len(world_data["surface_y"]) == self.world.w:
                self.world.surface_y = np.array(world_data["surface_y"], dtype=np.int32)
            if "biomes" in world_data and world_data["biomes"] is not None and len(world_data["biomes"]) == self.world.w:
                self.world.biomes = np.array(world_data["biomes"], dtype=np.uint8)
            self.player = Player(x=world_data["player_x"], y=world_data["player_y"])
            self.player.health = world_data.get("player_health", 100)
            self.player.hunger = world_data.get("player_hunger", 100)
            self.player.water = world_data.get("player_water", 100)
            spawn = self.world.find_spawn(); self.player.spawn = spawn
            self.inventory = Inventory.from_dict(world_data["inventory"])
            self.time = world_data.get("time", 0.30); self.day_count = world_data.get("day_count", 1)
            # Load armor
            if "armor" in world_data:
                self.armor = [None, None, None, None]
                for i, entry in enumerate(world_data["armor"]):
                    if entry:
                        self.armor[i] = ItemStack(entry["id"], entry.get("count", 1), entry.get("dur"))
            else:
                self.armor = [None, None, None, None]
            # Load chest data
            if "chests" in world_data:
                for key, chest_data in world_data["chests"].items():
                    chest_inv = Inventory.from_dict(chest_data)
                    # Upgrade old 30-slot chests to 50 slots
                    if len(chest_inv.slots) < 50:
                        chest_inv.slots.extend([None] * (50 - len(chest_inv.slots)))
                    self.chests[key] = chest_inv
        else:
            self.seed = seed
            self.world = World(WORLD_W, WORLD_H, seed)
            spawn = self.world.find_spawn()
            self.player = Player(x=spawn[0], y=spawn[1], spawn=spawn)
            self.inventory = Inventory(50); self.armor = [None, None, None, None]; self._give_starting_items()
            self.time = 0.30; self.day_count = 1

        self.cam_x = self.player.x - self.screen_w/2; self.cam_y = self.player.y - self.screen_h/2
        self.game_zoom = 1.0  # 0.5 to 4.0
        self._physics_accum = 0.0  # fixed timestep accumulator
        self._zoom_pan_x = 0.0  # pan offset in world pixels
        self._zoom_pan_y = 0.0
        self._middle_dragging = False
        self._middle_drag_start = (0, 0)
        self._middle_drag_cam_start = (0.0, 0.0)
        self.selected = 0
        self.slimes: List[Slime] = []; self.zombies: List[Zombie] = []
        self.skeletons: List[Skeleton] = []; self.demon_eyes: List[DemonEye] = []
        self.fish: List[Fish] = []; self.bats: List[Bat] = []; self.crabs: List[Crab] = []
        self.fish_spawn_timer = random.uniform(3.0, 6.0)
        self.bat_spawn_timer = random.uniform(4.0, 8.0)
        self.crab_spawn_timer = random.uniform(5.0, 10.0)
        self.arrows: List[Arrow] = []
        self.dropped_items: List[DroppedItem] = []  # thrown or dropped items in the world
        self.animals: List[Animal] = []
        self.animal_spawn_timer = 0.0
        self.spawn_timer = 0.0
        self.particles: List[Particle] = []; self.floats = []
        self.paused = False; self.pause_state = "main"  # pause menu state: main, help
        self.debug = False; self.slow_mo = False; self.creative_mode = False; self.creative_snapshot = None
        self.game_over = False; self.game_over_timer = 0.0; self.GAME_OVER_DELAY = 10.0; self.death_cause = ""
        self.inventory_open = False; self.workbench_open = False
        self.station_open = False; self.active_station = "workbench"
        # Furnace dedicated UI state (Minecraft-like: input slot, fuel slot, output slot, fire animation)
        self.furnace_input = None     # ItemStack or None - raw food/ore goes here
        self.furnace_fuel = None      # ItemStack or None - wood/coal/plank goes here
        self.furnace_output = None    # ItemStack or None - cooked/smelting result appears here
        self.furnace_fuel_time = 0.0  # seconds of burn time remaining in current fuel item
        self.furnace_cook_time = 0.0  # 0.0 to 1.0 - cooking progress
        self.furnace_active = False   # True when furnace is burning fuel and cooking
        self.chest_open = False; self.active_chest_pos = None; self.chest_inventory = None
        self.map_open = False; self.running = True
        self.return_to_menu = False  # set True when user picks "Save & Exit"
        self.mouse_down_left = False; self.mouse_down_right = False
        # Double-click detection for eat/drink and throw gestures.
        # We track the timestamp of the last LMB press; if two presses happen within
        # DOUBLE_CLICK_TIME seconds on the same screen region, it's a double-click.
        self._last_lmb_time = 0.0
        self._last_lmb_pos = (0, 0)
        self._last_rmb_time = 0.0
        self._last_rmb_pos = (0, 0)
        # --- Sound state ---
        # Footstep timer accumulates dt while the player is moving on the ground;
        # every FOOTSTEP_INTERVAL seconds we play a footstep sound chosen by surface type.
        self.footstep_timer = 0.0
        self.FOOTSTEP_INTERVAL = 0.32  # seconds between footsteps at full walk speed
        # Track previous water/ground state so we only fire splash / land sounds on
        # the actual transition (not every frame while in water / on ground).
        self._was_in_water = False
        self._was_on_ground = True
        self._prev_vy = 0.0  # for detecting hard landings (vy was large positive)
        # "Throw-ready" state: after RMB on a selectable inventory slot, the next LMB
        # in the world throws one item from that slot (RMB-pick + LMB-throw gesture).
        self._throw_armed = False
        self._throw_armed_slot = -1
        self._throw_armed_time = 0.0  # when armed; expires after a few seconds
        self._hotbar_rmb_slot = None  # tracks first RMB hotbar select for exchange
        # Creative inventory scroll offset (in rows). The creative panel has a fixed
        # visible area; items past the bottom are reached by scrolling with the wheel.
        self._creative_scroll = 0  # current scroll position (in rows of items)
        self._creative_scroll_target = 0  # target for smooth scrolling
        self.block_textures = self._build_block_textures()
        self.wall_textures = self._build_wall_textures()
        self.liquid_fill_surfs = self._build_liquid_textures()
        self.tool_icons = self._build_tool_icons()
        # Merge armor icons into tool_icons so _draw_item_in_slot finds them
        # (existing code already looks in tool_icons for armor pieces).
        self.tool_icons.update(self._build_armor_icons())
        self.item_icons = self._build_item_icons()
        self.light_map = None
        self._liquid_accum = 0.0
        # Keep exploration sparse, but at tile precision. The old 5x5 chunk grid
        # made the fog reveal in large square steps instead of following the player.
        self.explored_chunks: set = set()  # set of explored (tile_x, tile_y) cells
        self.explored_chunk_size = 1
        self._exploration_revision = 0
        self._exploration_mask_cache = None
        self._darkness_cache_key = None
        self._darkness_scaled = None
        self._light_revision = 0
        # OPTIMIZED: no world_surf at startup (was ~1.9GB). Build minimap lazily.
        self._minimap_surface = None  # built on-demand when TAB is pressed
        self._minimap_dirty = True  # needs rebuild
        self._map_zoom = 5.0  # default 5x so the player can actually see surroundings
        self._map_offset_x = 0.0
        self._map_offset_y = 0.0
        self._map_dragging = False
        self._map_drag_button = None  # which mouse button started the drag (1=LMB, 3=RMB)
        self._map_drag_start = (0, 0)
        self._map_drag_offset_start = (0.0, 0.0)
        self._map_drag_moved = False  # was the drag actually moved (vs. a simple click)?
        self._map_drag_grace = 0  # frames to ignore button state after opening map
        # Creative inventory categories
        self._creative_category = "all"  # current category filter
        self._creative_scroll = 0.0
        self._creative_scroll_target = 0
        # Generate initial area around spawn so the player doesn't fall through air
        self._ensure_world_generated()
        self.stars = [(random.randint(0,self.screen_w), random.randint(0,self.screen_h//2), random.random()) for _ in range(80)]
        
        # --- Weather system ---
        self.weather_type = "clear"  # "clear", "rain", "snow", "storm"
        self.weather_timer = random.uniform(120, 300)  # 2-5 min until first weather change
        self.weather_particles: List[Dict] = []  # rain drops / snow flakes
        self.weather_wind = 0.0  # wind direction for rain (-1 to 1)
        self.weather_day = -1  # track which day the weather was set (prevent multiple changes per day)
        self.lightning_timer = 0.0  # countdown to next lightning flash
        self.lightning_flash = 0.0  # remaining flash brightness
        self._update_weather_state()
        
        self._toast(f"World '{world_name}' loaded | ESC: pause menu", 4.0)

    def _init_display(self):
        """Initialize the display at native screen resolution.
        Always renders at the screen's native pixel size — no virtual surfaces."""
        global VIEW_W, VIEW_H, WINDOW_W, WINDOW_H, ui_scale
        if self.fullscreen:
            try:
                screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                self.screen_w, self.screen_h = screen.get_size()
            except (pygame.error, TypeError):
                self.fullscreen = False
        if not self.fullscreen:
            # Windowed: detect screen size, use a reasonable window (e.g. 80% of screen)
            info = pygame.display.Info()
            desktop_w = info.current_w
            desktop_h = info.current_h
            win_w = max(960, int(desktop_w * 0.8))
            win_h = max(540, int(desktop_h * 0.8))
            try:
                screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE, vsync=1)
            except (pygame.error, TypeError):
                screen = pygame.display.set_mode((win_w, win_h))
            self.screen_w, self.screen_h = screen.get_size()
        # Update all globals to match actual screen
        VIEW_W, VIEW_H = self.screen_w, self.screen_h
        WINDOW_W, WINDOW_H = self.screen_w, self.screen_h
        ui_scale = 1.0  # Always 1.0 since we render at native resolution
        self.render_surface = None
        return screen

    def _give_starting_items(self):
        pass  # Player starts with zero items in all modes

    # ---------- textures ----------
    def _build_block_textures(self):
        textures = {}
        for block, d in BLOCK_DEFS.items():
            if block == AIR: continue
            surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            base = d["color"]
            if block == WATER:
                # Wavy water with highlights and depth gradient (top lighter, bottom darker).
                # The block texture is static (no per-frame animation here), but the surface
                # waves are drawn as offset sine curves so it reads as water at a glance.
                top_col = (80, 140, 220, 200)
                bot_col = (35, 80, 180, 220)
                for y in range(TILE):
                    t = y / max(1, TILE - 1)
                    r = int(top_col[0] + (bot_col[0] - top_col[0]) * t)
                    g = int(top_col[1] + (bot_col[1] - top_col[1]) * t)
                    b = int(top_col[2] + (bot_col[2] - top_col[2]) * t)
                    a = int(top_col[3] + (bot_col[3] - top_col[3]) * t)
                    pygame.draw.line(surf, (r, g, b, a), (0, y), (TILE, y))
                # Wave caps on the top half
                rng_w = random.Random(block * 17)
                for _ in range(8):
                    wx = rng_w.randint(1, TILE - 2)
                    wy = rng_w.randint(1, TILE // 2)
                    surf.set_at((wx, wy), (200, 230, 255, 230))
                # Sine wave highlights on the top
                for x in range(0, TILE, 2):
                    y = 2 + int(math.sin(x * 0.7) * 1.5)
                    if 0 <= y < TILE:
                        surf.set_at((x, y), (220, 240, 255, 230))
            elif block == TORCH:
                # Transparent background; stick + glowing flame with halo
                surf.fill((0,0,0,0))
                # Stick (wooden handle, slightly tapered)
                pygame.draw.rect(surf, (110, 75, 40), (TILE//2-1, TILE//3, 3, int(TILE*0.66)))
                pygame.draw.rect(surf, (80, 50, 25), (TILE//2-1, TILE//3, 1, int(TILE*0.66)))
                # Flame: outer red-orange, inner yellow, white-hot core
                fcx, fcy = TILE//2, TILE//3 - 1
                pygame.draw.circle(surf, (255, 120, 30), (fcx, fcy), 5)       # outer
                pygame.draw.circle(surf, (255, 180, 50), (fcx, fcy - 1), 4)   # mid
                pygame.draw.circle(surf, (255, 220, 90), (fcx, fcy - 1), 2)   # inner
                pygame.draw.circle(surf, (255, 250, 200), (fcx, fcy - 2), 1)  # core
                # Soft halo above the flame
                halo = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
                pygame.draw.circle(halo, (255, 180, 60, 50), (fcx, fcy - 2), 8)
                surf.blit(halo, (0, 0))
            elif block == GLASS:
                surf.fill((200,230,240,90))
                pygame.draw.rect(surf, (220,240,250,200), surf.get_rect(), 1)
            elif block == WORKBENCH:
                surf.fill(base)
                pygame.draw.rect(surf, (80, 50, 25), (0, 0, TILE, 4))  # top
                pygame.draw.rect(surf, (160, 110, 60), (2, 4, TILE-4, TILE-8))  # work surface
                pygame.draw.line(surf, (60, 40, 20), (0, 6), (TILE, 6))
                pygame.draw.line(surf, (60, 40, 20), (0, TILE-4), (TILE, TILE-4))
            elif block == BOOKSHELF:
                surf.fill(base)
                pygame.draw.rect(surf, (60, 40, 20), surf.get_rect(), 2)
                for row in range(3):
                    for col in range(2):
                        bx = 3 + col * 10; by = 3 + row * 7
                        bc = random.Random(block*99 + row*10 + col).choice([(200,80,80),(80,200,80),(80,80,200),(220,220,80)])
                        pygame.draw.rect(surf, bc, (bx, by, 8, 5))
            elif block == LAMP:
                surf.fill((0,0,0,0))
                pygame.draw.rect(surf, (80, 60, 30), (TILE//2-2, 2, 4, 4))  # ceiling mount
                pygame.draw.circle(surf, (255, 240, 150), (TILE//2, TILE//2), 9)
                pygame.draw.circle(surf, (255, 255, 220), (TILE//2, TILE//2), 5)
                pygame.draw.circle(surf, (180, 180, 100), (TILE//2, TILE//2), 9, 1)
            elif block == CHEST:
                surf.fill(base)
                pygame.draw.rect(surf, (100, 70, 30), surf.get_rect(), 2)
                pygame.draw.rect(surf, (60, 40, 20), (0, TILE//2, TILE, 2))
                pygame.draw.rect(surf, (220, 180, 60), (TILE//2-2, TILE//2-1, 4, 4))  # lock
            elif block == FURNACE:
                surf.fill((80, 70, 65))
                pygame.draw.rect(surf, (50, 45, 40), surf.get_rect(), 2)
                # Furnace opening with glow
                pygame.draw.rect(surf, (30, 25, 20), (TILE//4, TILE//3, TILE//2, TILE//3))
                pygame.draw.circle(surf, (255, 120, 40), (TILE//2, TILE//2+1), 3)
                pygame.draw.circle(surf, (255, 200, 80), (TILE//2, TILE//2+1), 2)
            elif block == ANVIL:
                surf.fill((0, 0, 0, 0))
                # Anvil shape: wide top, narrow base
                pygame.draw.rect(surf, (70, 70, 80), (2, 6, TILE-4, 5))  # top
                pygame.draw.rect(surf, (90, 90, 100), (TILE//2-4, 11, 8, 6))  # neck
                pygame.draw.rect(surf, (70, 70, 80), (TILE//4, 17, TILE//2, 4))  # base
                pygame.draw.rect(surf, (50, 50, 60), (2, 6, TILE-4, 5), 1)
            elif block == CAMPFIRE:
                surf.fill((0, 0, 0, 0))
                # Logs
                pygame.draw.rect(surf, (100, 65, 35), (2, TILE-6, TILE-4, 4))
                pygame.draw.rect(surf, (80, 50, 25), (4, TILE-5, TILE-8, 2))
                # Flames
                pygame.draw.circle(surf, (255, 100, 30), (TILE//2, TILE-8), 5)
                pygame.draw.circle(surf, (255, 180, 50), (TILE//2, TILE-9), 3)
                pygame.draw.circle(surf, (255, 230, 120), (TILE//2, TILE-10), 2)
            elif block == BED:
                surf.fill((0,0,0,0))
                # Bed LEFT half (headboard side) - extends to right edge
                # Frame - full width to connect seamlessly with foot half
                pygame.draw.rect(surf, (120, 80, 50), (0, TILE//3, TILE, TILE//2+2))
                # Mattress/blanket
                pygame.draw.rect(surf, (180, 60, 80), (0, TILE//3+2, TILE, TILE//2-2))
                # Pillow on left side
                pygame.draw.rect(surf, (220, 220, 200), (1, TILE//3+2, 8, TILE//2-2))
                # Headboard on left edge
                pygame.draw.rect(surf, (100, 65, 40), (0, TILE//4, 3, TILE//2+4))
                # Blanket fold line (off-center for natural look)
                pygame.draw.line(surf, (160, 50, 70), (TILE*2//3, TILE//3+3), (TILE*2//3, TILE-4), 1)
            elif block == ROCK:
                # Boulder: multi-tone gray rounded stone with cracks + highlight
                surf.fill((0, 0, 0, 0))
                # Drop shadow underneath
                pygame.draw.ellipse(surf, (0, 0, 0, 60), (4, TILE-5, TILE-8, 4))
                # Main body (slightly darker base)
                pygame.draw.ellipse(surf, self._shade(base, -10), (3, 5, TILE-6, TILE-9))
                # Top highlight (lighter)
                pygame.draw.ellipse(surf, self._shade(base, 25), (5, 6, TILE-10, TILE-14))
                # Outline
                pygame.draw.ellipse(surf, self._shade(base, -50), (3, 5, TILE-6, TILE-9), 1)
                # Small specular dot
                pygame.draw.circle(surf, self._shade(base, 50), (TILE//2-3, 9), 1)
                # Hairline crack
                rng_r = random.Random(block * 31)
                sx0, sy0 = rng_r.randint(6, TILE-7), rng_r.randint(8, TILE-9)
                for _ in range(3):
                    sx1 = sx0 + rng_r.randint(-2, 2); sy1 = sy0 + rng_r.randint(0, 2)
                    pygame.draw.line(surf, self._shade(base, -40), (sx0, sy0), (sx1, sy1), 1)
                    sx0, sy0 = sx1, sy1
            elif block == SMALL_STONE:
                # Cluster of 2-3 small pebbles with individual shading
                surf.fill((0, 0, 0, 0))
                rng_ss = random.Random(block * 41)
                # Drop shadow
                pygame.draw.ellipse(surf, (0, 0, 0, 60), (4, TILE-5, TILE-8, 3))
                # Main pebble (larger, bottom-right)
                pygame.draw.ellipse(surf, base, (6, 10, 10, 7))
                pygame.draw.ellipse(surf, self._shade(base, -40), (6, 10, 10, 7), 1)
                pygame.draw.ellipse(surf, self._shade(base, 25), (8, 11, 4, 2))
                # Smaller pebble (top-left)
                pygame.draw.ellipse(surf, self._shade(base, -10), (3, 13, 6, 4))
                pygame.draw.ellipse(surf, self._shade(base, -40), (3, 13, 6, 4), 1)
                pygame.draw.ellipse(surf, self._shade(base, 20), (4, 13, 2, 1))
                # Tiny pebble (top-right)
                pygame.draw.ellipse(surf, self._shade(base, -5), (15, 7, 5, 3))
                pygame.draw.ellipse(surf, self._shade(base, -40), (15, 7, 5, 3), 1)
            elif block == GRASS_TUFT:
                # Grass blades: taller, multi-tone, slightly drooping
                surf.fill((0, 0, 0, 0))
                rng_gt = random.Random(block * 53)
                for i in range(5):
                    bx = 4 + i * 3
                    h = rng_gt.randint(7, 11)
                    # Dark back-blade
                    pygame.draw.line(surf, self._shade(base, -20), (bx, TILE-2), (bx-1, TILE-h-1), 2)
                    # Light front-blade
                    pygame.draw.line(surf, self._shade(base, 25), (bx+1, TILE-2), (bx+1, TILE-h), 1)
                    # Tip
                    surf.set_at((bx, TILE-h-1), self._shade(base, 40))
            elif block == TALL_GRASS:
                # Tall grass BOTTOM half: stems extend to top edge (y=0)
                surf.fill((0, 0, 0, 0))
                rng_tg = random.Random(block * 71)
                for i in range(7):
                    bx = 2 + i * 2
                    lean = rng_tg.randint(-2, 2)
                    # Stem from bottom to top edge (y=0) to connect with top half
                    pygame.draw.line(surf, self._shade(base, -30), (bx, TILE-2), (bx+lean, 0), 2)
                    # Light blade
                    pygame.draw.line(surf, self._shade(base, 15), (bx+1, TILE-2), (bx+1+lean, 1), 1)
            elif block == DRIED_TALL_GRASS:
                # Dried tall grass BOTTOM half - same shape as tall grass but yellowish-brown
                surf.fill((0, 0, 0, 0))
                rng_dtg = random.Random(block * 73)
                for i in range(6):
                    bx = 3 + i * 2
                    lean = rng_dtg.randint(-1, 1)
                    # Dried stems - more rigid, less lean
                    pygame.draw.line(surf, self._shade(base, -25), (bx, TILE-2), (bx+lean, 0), 2)
                    pygame.draw.line(surf, self._shade(base, 10), (bx+1, TILE-2), (bx+1+lean, 1), 1)
            elif block == BUSH:
                # Bush: dense green clump with multi-tone leaf clusters
                surf.fill((0, 0, 0, 0))
                rng_b = random.Random(block * 67)
                # Drop shadow
                pygame.draw.ellipse(surf, (0, 0, 0, 70), (4, TILE-5, TILE-8, 4))
                # Dark base (back layer)
                pygame.draw.ellipse(surf, self._shade(base, -35), (2, 7, TILE-4, TILE-9))
                # Main mid-tone body
                pygame.draw.ellipse(surf, base, (3, 8, TILE-6, TILE-11))
                # Light highlight (top-left)
                pygame.draw.ellipse(surf, self._shade(base, 25), (5, 9, TILE-12, TILE-15))
                # Leaf bumps around the perimeter (small circles)
                for _ in range(8):
                    cx = rng_b.randint(3, TILE-4)
                    cy = rng_b.randint(8, TILE-4)
                    pygame.draw.circle(surf, self._shade(base, rng_b.randint(-20, 30)), (cx, cy), 2)
                # Outline
                pygame.draw.ellipse(surf, self._shade(base, -50), (2, 7, TILE-4, TILE-9), 1)
            elif block == BUSH_FRUIT:
                # Bush with red berries scattered across the leafy body
                surf.fill((0, 0, 0, 0))
                rng_bf = random.Random(block * 83)
                # Drop shadow
                pygame.draw.ellipse(surf, (0, 0, 0, 70), (4, TILE-5, TILE-8, 4))
                # Dark base
                pygame.draw.ellipse(surf, self._shade(base, -35), (2, 7, TILE-4, TILE-9))
                # Main body
                pygame.draw.ellipse(surf, base, (3, 8, TILE-6, TILE-11))
                # Light highlight
                pygame.draw.ellipse(surf, self._shade(base, 25), (5, 9, TILE-12, TILE-15))
                # Leaf bumps
                for _ in range(6):
                    cx = rng_bf.randint(3, TILE-4)
                    cy = rng_bf.randint(8, TILE-4)
                    pygame.draw.circle(surf, self._shade(base, rng_bf.randint(-20, 30)), (cx, cy), 2)
                # Berries (red with highlight)
                berry_positions = [(7, 12), (15, 11), (11, 16), (17, 15), (5, 15)]
                for (bx, by) in berry_positions:
                    pygame.draw.circle(surf, (180, 30, 40), (bx, by), 2)
                    pygame.draw.circle(surf, (240, 80, 90), (bx-1, by-1), 1)
                # Outline
                pygame.draw.ellipse(surf, self._shade(base, -50), (2, 7, TILE-4, TILE-9), 1)
            elif block == DRIED_GRASS:
                # Transparent background (like GRASS_TUFT) so the underlying dirt /
                # grass block shows through. Previously this called `surf.fill(base)`
                # which painted the entire tile solid yellow-tan and made dried-grass
                # tufts look like opaque yellow squares.
                surf.fill((0, 0, 0, 0))
                rng_dg = random.Random(block * 99)
                # Five dried blades, each with a darker back-stroke and lighter tip
                # so the cluster reads as grass rather than a flat color block.
                for i in range(5):
                    bx = 4 + i * 6
                    bh = rng_dg.randint(5, 11)
                    # Darker back-blade (shadow side)
                    back_col = self._shade(base, -25)
                    pygame.draw.line(surf, back_col, (bx, TILE-2), (bx-1, TILE-2-bh), 2)
                    # Lighter front-blade (sun side)
                    front_col = self._shade(base, 25)
                    pygame.draw.line(surf, front_col, (bx+1, TILE-2), (bx+1, TILE-2-bh+1), 1)
                    # Highlight tip
                    surf.set_at((bx, TILE-2-bh-1), self._shade(base, 45))
                # A few loose straw bits scattered near the base for texture
                for _ in range(4):
                    px = rng_dg.randint(2, TILE-3)
                    py = rng_dg.randint(TILE-6, TILE-2)
                    surf.set_at((px, py), self._shade(base, rng_dg.randint(-15, 25)))
            elif block in ALL_SEEDLING_TYPES:
                surf.fill((0, 0, 0, 0))
                pygame.draw.ellipse(surf, (134, 87, 56), (TILE//2-6, TILE-6, 12, 6))
                stem_h = random.Random(block*77).randint(8, 14)
                pygame.draw.line(surf, (60, 120, 40), (TILE//2, TILE-4), (TILE//2, TILE-4-stem_h), 2)
                pygame.draw.circle(surf, (80, 160, 60), (TILE//2, TILE-4-stem_h), 3)
                pygame.draw.circle(surf, (70, 140, 50), (TILE//2-3, TILE-4-stem_h+2), 2)
            else:
                surf.fill(base)
                rng = random.Random(block*99)
                if block == LAVA:
                    # Glowing lava with bubbles
                    surf.fill((230, 90, 30))
                    for _ in range(8):
                        pygame.draw.circle(surf, (255, 180, 60), (rng.randint(2,TILE-3), rng.randint(2,TILE-3)), rng.randint(1,3))
                    for _ in range(4):
                        pygame.draw.circle(surf, (255, 230, 120), (rng.randint(4,TILE-5), rng.randint(4,TILE-5)), 1)
                elif block in (GRASS, LEAVES, LEAVES_DARK, LEAVES_AUTUMN, LEAVES_RED, LEAVES_YELLOW, LEAVES_CHERRY, JUNGLE_GRASS, SAVANNA_GRASS):
                    for _ in range(10): surf.set_at((rng.randint(0,TILE-1), rng.randint(0,TILE-1)), self._shade(base, rng.randint(-25,25)))
                    if block == GRASS or block == JUNGLE_GRASS or block == SAVANNA_GRASS:
                        for sx in range(TILE):
                            if rng.random() < 0.7: surf.set_at((sx, 0), self._shade(base, 40))
                elif block in (DIRT, SAND, STONE, PLANK, BRICK, TREE_TRUNK, WOOD,
                              SANDSTONE, LIMESTONE, GRANITE, BASALT, OBSIDIAN, BEDROCK,
                              MUD, SNOW, ICE, MARBLE, PINE_TRUNK, CACTUS):
                    # Subtle inner bevel: lighter top-left edges, darker bottom-right
                    lighter = self._shade(base, 18)
                    darker = self._shade(base, -18)
                    # Top edge highlight
                    for sx in range(1, TILE-1):
                        surf.set_at((sx, 0), lighter)
                    # Left edge highlight
                    for sy in range(1, TILE-1):
                        surf.set_at((0, sy), lighter)
                    # Bottom edge shadow
                    for sx in range(1, TILE-1):
                        surf.set_at((sx, TILE-1), darker)
                    # Right edge shadow
                    for sy in range(1, TILE-1):
                        surf.set_at((TILE-1, sy), darker)
                    # Random noise for texture
                    for _ in range(18): surf.set_at((rng.randint(1,TILE-2), rng.randint(1,TILE-2)), self._shade(base, rng.randint(-20,20)))
                    if block == TREE_TRUNK or block == PINE_TRUNK:
                        for bx in [3, TILE//2, TILE-4]:
                            for by in range(TILE): surf.set_at((bx, by), self._shade(base, -30))
                    if block == TREE_GIANT:
                        for bx in [2, TILE//3, 2*TILE//3, TILE-3]:
                            for by in range(TILE): surf.set_at((bx, by), self._shade(base, -35))
                        for _ in range(4):
                            pygame.draw.circle(surf, self._shade(base, -25), (rng.randint(3,TILE-4), rng.randint(3,TILE-4)), 2)
                    if block == TREE_DEAD:
                        for bx in [4, TILE//2, TILE-5]:
                            for by in range(TILE): surf.set_at((bx, by), self._shade(base, -20))
                        for _ in range(2):
                            pygame.draw.circle(surf, self._shade(base, -40), (rng.randint(4,TILE-5), rng.randint(4,TILE-5)), 2)
                    if block == TREE_BENT:
                        for by in range(TILE):
                            offset = int(3 * math.sin(by * 0.5))
                            if 0 <= TILE//2 + offset < TILE:
                                surf.set_at((TILE//2 + offset, by), self._shade(base, -30))
                    if block == STONE or block == GRANITE or block == BASALT:
                        for _ in range(3):
                            cx, cy = rng.randint(3,TILE-4), rng.randint(3,TILE-4)
                            for _ in range(5):
                                if 1 <= cx < TILE-1 and 1 <= cy < TILE-1: surf.set_at((cx, cy), self._shade(base, -30))
                                cx += rng.randint(-1,1); cy += rng.randint(-1,1)
                        # Small cracks
                        for _ in range(2):
                            sx, sy = rng.randint(3, TILE-4), rng.randint(3, TILE-4)
                            for _ in range(rng.randint(2,4)):
                                ex, ey = sx + rng.randint(-2,2), sy + rng.randint(-2,2)
                                if 0 <= ex < TILE and 0 <= ey < TILE:
                                    pygame.draw.line(surf, self._shade(base, -25), (sx, sy), (ex, ey), 1)
                                sx, sy = ex, ey
                    if block == DIRT or block == MUD:
                        # Small pebbles
                        for _ in range(3):
                            px, py = rng.randint(2,TILE-3), rng.randint(2,TILE-3)
                            surf.set_at((px, py), self._shade(base, -20))
                            surf.set_at((px+1, py), self._shade(base, -15))
                    if block == SAND:
                        # Subtle dot pattern
                        for _ in range(6):
                            surf.set_at((rng.randint(1,TILE-2), rng.randint(1,TILE-2)), self._shade(base, 12))
                    if block == SNOW:
                        # Sparkle
                        for _ in range(3):
                            surf.set_at((rng.randint(1,TILE-2), rng.randint(1,TILE-2)), (240, 245, 255))
                    if block == ICE:
                        # Crack lines
                        pygame.draw.line(surf, self._shade(base, 15), (4, 4), (TILE-5, TILE//2), 1)
                        pygame.draw.line(surf, self._shade(base, 15), (TILE//2, TILE//2), (TILE-4, TILE-5), 1)
                    if block == SANDSTONE:
                        # Sedimentary lines
                        for yy in [5, 10, 16, 21]:
                            for sx in range(1, TILE-1): surf.set_at((sx, yy), self._shade(base, -22))
                    if block == LIMESTONE:
                        # Fossil-like specks
                        for _ in range(6): surf.set_at((rng.randint(1,TILE-2), rng.randint(1,TILE-2)), (180, 170, 150))
                    if block == PLANK:
                        for yy in [TILE//2-1, TILE//2]:
                            for sx in range(1, TILE-1): surf.set_at((sx, yy), self._shade(base, -30))
                        # Wood grain
                        for yy in range(2, TILE-2, 3):
                            surf.set_at((TILE//3, yy), self._shade(base, -12))
                    if block == BRICK:
                        # Brick pattern: horizontal + vertical mortar lines
                        for sx in range(TILE): surf.set_at((sx, TILE//2-1), self._shade(base, -35))
                        for sy in range(TILE): surf.set_at((TILE//2, sy), self._shade(base, -35))
                        # Offset mortar on second row
                        for sx in range(TILE):
                            surf.set_at((sx, TILE//4), self._shade(base, -30))
                    if block == OBSIDIAN:
                        # Glassy shine
                        pygame.draw.line(surf, (80, 70, 100), (3, 3), (TILE-4, TILE-4), 1)
                        pygame.draw.line(surf, (90, 80, 110), (5, 3), (TILE-4, TILE-6), 1)
                    if block == BEDROCK:
                        # Rough chaotic pattern
                        for _ in range(8):
                            surf.set_at((rng.randint(0,TILE-1), rng.randint(0,TILE-1)), self._shade(base, rng.randint(-35, -10)))
                    if block == MARBLE:
                        # Veining
                        for _ in range(2):
                            sx, sy = rng.randint(2, TILE-3), rng.randint(2, TILE-3)
                            for _ in range(3):
                                ex = sx + rng.randint(-2, 2)
                                ey = sy + rng.randint(0, 3)
                                if 0 <= ex < TILE and 0 <= ey < TILE:
                                    pygame.draw.line(surf, self._shade(base, 20), (sx, sy), (ex, ey), 1)
                                sx, sy = ex, ey
                    if block == CACTUS:
                        # Spines
                        for yy in range(2, TILE-2, 4):
                            surf.set_at((TILE//2-1, yy), (240, 230, 180))
                            surf.set_at((TILE//2+1, yy), (240, 230, 180))
                    if block == GRANITE:
                        # Speckled pattern
                        for _ in range(5):
                            surf.set_at((rng.randint(1,TILE-2), rng.randint(1,TILE-2)), self._shade(base, 25))
                    if block == BASALT:
                        # Columnar joints
                        for sx in [6, 12, 18]:
                            if sx < TILE:
                                for sy in range(0, TILE, 3):
                                    surf.set_at((sx, sy), self._shade(base, -15))
                elif block in (COAL, IRON, GOLD, DIAMOND, COPPER_ORE, TIN_ORE, SILVER_ORE,
                              MITHRIL_ORE, RUBY_ORE, SAPPHIRE_ORE, EMERALD_ORE):
                    # Ores: stone base with bevel + colored chunks
                    stone_base = BLOCK_DEFS[STONE]["color"]
                    surf.fill(stone_base)
                    # Stone bevel
                    lighter = self._shade(stone_base, 18)
                    darker = self._shade(stone_base, -18)
                    for sx in range(1, TILE-1): surf.set_at((sx, 0), lighter)
                    for sy in range(1, TILE-1): surf.set_at((0, sy), lighter)
                    for sx in range(1, TILE-1): surf.set_at((sx, TILE-1), darker)
                    for sy in range(1, TILE-1): surf.set_at((TILE-1, sy), darker)
                    for _ in range(6): surf.set_at((rng.randint(1,TILE-2), rng.randint(1,TILE-2)), self._shade(stone_base, rng.randint(-15,15)))
                    # Ore chunks
                    for _ in range(6):
                        pygame.draw.circle(surf, base, (rng.randint(2,TILE-3), rng.randint(2,TILE-3)), rng.randint(2,3))
                    # Ore highlight
                    for _ in range(2):
                        pygame.draw.circle(surf, self._shade(base, 30), (rng.randint(3,TILE-4), rng.randint(3,TILE-4)), 1)
                elif block == VINE:
                    surf.fill((0, 0, 0, 0))  # transparent background
                    # Thin organic vine with dangling tendrils and small leaves
                    rng_v = random.Random(block * 59)
                    # Main central vine strand (thin, slightly wavy)
                    vine_x = TILE // 2
                    prev_x = vine_x
                    for vy in range(0, TILE):
                        wave = int(math.sin(vy * 0.4 + rng_v.random() * 0.3) * 2)
                        draw_x = max(2, min(TILE - 3, vine_x + wave))
                        pygame.draw.line(surf, base, (prev_x, vy - 1 if vy > 0 else 0), (draw_x, vy), 1)
                        prev_x = draw_x
                    # Side tendrils with tiny leaves
                    for side in [-1, 1]:
                        tendril_x = vine_x + side * 4
                        for vy in range(3, TILE - 2, 5):
                            if rng_v.random() < 0.5:
                                # Small tendril segment
                                end_x = tendril_x + side * rng_v.randint(1, 3)
                                end_y = vy + rng_v.randint(2, 5)
                                pygame.draw.line(surf, self._shade(base, 15), (tendril_x, vy), (end_x, min(end_y, TILE-1)), 1)
                                # Tiny leaf at end
                                if 0 < end_x < TILE - 1:
                                    pygame.draw.circle(surf, self._shade(base, 25), (end_x, min(end_y, TILE-2)), 1)
                elif block == FLOWER:
                    surf.fill((0, 0, 0, 0))  # transparent background
                    # Generic pink flower: green stem + leaf + 5-petal bloom with yellow center
                    rng_fl = random.Random(block * 71)
                    stem_x = TILE//2 + rng_fl.randint(-1, 1)
                    # Stem
                    pygame.draw.line(surf, (40, 110, 50), (stem_x, TILE-1), (TILE//2, TILE//2+2), 2)
                    # Leaf
                    pygame.draw.ellipse(surf, (60, 140, 50), (TILE//2+1, TILE//2+5, 5, 3))
                    # Petals (teardrop-shaped)
                    center = (TILE//2, TILE//2-1)
                    for angle_i in range(5):
                        angle = angle_i * (2 * math.pi / 5) - math.pi / 2
                        px = center[0] + int(math.cos(angle) * 5)
                        py = center[1] + int(math.sin(angle) * 5)
                        # Teardrop petal
                        pygame.draw.circle(surf, base, (px, py), 3)
                        # Petal highlight
                        pygame.draw.circle(surf, self._shade(base, 30), (px, py), 2)
                    # Center
                    pygame.draw.circle(surf, (255, 230, 80), center, 2)
                    pygame.draw.circle(surf, (255, 250, 150), center, 1)
                elif block == FLOWER_RED:
                    surf.fill((0, 0, 0, 0))  # transparent background
                    # Red rose: larger rounded petals, darker red
                    rng_fl = random.Random(block * 73)
                    stem_x = TILE//2 + rng_fl.randint(-1, 1)
                    pygame.draw.line(surf, (40, 100, 45), (stem_x, TILE-1), (TILE//2, TILE//2+3), 2)
                    # Thorn on stem
                    pygame.draw.line(surf, (60, 80, 40), (TILE//2+1, TILE//2+6), (TILE//2+3, TILE//2+5), 1)
                    # Leaf
                    pygame.draw.ellipse(surf, (50, 130, 45), (TILE//2-4, TILE//2+5, 5, 3))
                    # Rose bloom - layered petals
                    center = (TILE//2, TILE//2 - 2)
                    # Outer petals (darker)
                    for angle_i in range(6):
                        angle = angle_i * (2 * math.pi / 6)
                        px = center[0] + int(math.cos(angle) * 5)
                        py = center[1] + int(math.sin(angle) * 5)
                        pygame.draw.circle(surf, self._shade(base, -20), (px, py), 3)
                    # Inner petals (brighter)
                    for angle_i in range(5):
                        angle = angle_i * (2 * math.pi / 5) + 0.3
                        px = center[0] + int(math.cos(angle) * 3)
                        py = center[1] + int(math.sin(angle) * 3)
                        pygame.draw.circle(surf, base, (px, py), 2)
                    # Center
                    pygame.draw.circle(surf, (200, 180, 60), center, 2)
                elif block == FLOWER_YELLOW:
                    surf.fill((0, 0, 0, 0))  # transparent background
                    # Sunflower: ring of small petals around large center
                    rng_fl = random.Random(block * 79)
                    stem_x = TILE//2 + rng_fl.randint(-1, 1)
                    pygame.draw.line(surf, (40, 100, 40), (stem_x, TILE-1), (TILE//2, TILE//2+1), 2)
                    # Large leaf
                    pygame.draw.ellipse(surf, (50, 120, 40), (TILE//2-5, TILE//2+4, 7, 4))
                    # Sunflower head
                    center = (TILE//2, TILE//2 - 2)
                    # Petals (elongated, radial)
                    for angle_i in range(10):
                        angle = angle_i * (2 * math.pi / 10)
                        px = center[0] + int(math.cos(angle) * 6)
                        py = center[1] + int(math.sin(angle) * 6)
                        # Elongated petal
                        ex = center[0] + int(math.cos(angle) * 8)
                        ey = center[1] + int(math.sin(angle) * 8)
                        pygame.draw.line(surf, base, (px, py), (ex, ey), 2)
                        pygame.draw.circle(surf, self._shade(base, 20), (ex, ey), 1)
                    # Dark center disk
                    pygame.draw.circle(surf, (80, 60, 20), center, 4)
                    pygame.draw.circle(surf, (100, 80, 30), center, 3)
                    # Seed dots
                    for _ in range(4):
                        sx_d = center[0] + rng_fl.randint(-2, 2)
                        sy_d = center[1] + rng_fl.randint(-2, 2)
                        pygame.draw.circle(surf, (60, 45, 15), (sx_d, sy_d), 1)
                elif block == FLOWER_BLUE:
                    surf.fill((0, 0, 0, 0))  # transparent background
                    # Bluebell: small bell-shaped flower, drooping
                    rng_fl = random.Random(block * 83)
                    stem_x = TILE//2 + rng_fl.randint(-1, 1)
                    # Curved stem (drooping)
                    pygame.draw.line(surf, (40, 100, 45), (stem_x, TILE-1), (TILE//2, TILE//2+3), 2)
                    # Bell shape (drooping)
                    bell_top = (TILE//2, TILE//2)
                    bell_w, bell_h = 8, 7
                    # Bell body
                    pygame.draw.ellipse(surf, base, (bell_top[0]-bell_w//2, bell_top[1], bell_w, bell_h))
                    # Bell highlight
                    pygame.draw.ellipse(surf, self._shade(base, 30), (bell_top[0]-bell_w//2+1, bell_top[1]+1, bell_w-2, bell_h-3))
                    # Bell rim (lighter)
                    pygame.draw.arc(surf, self._shade(base, 40), (bell_top[0]-bell_w//2, bell_top[1]+bell_h-3, bell_w, 4), 0, math.pi, 2)
                    # Small leaf
                    pygame.draw.ellipse(surf, (50, 120, 40), (TILE//2+2, TILE//2+5, 4, 3))
                elif block == FLOWER_WHITE:
                    surf.fill((0, 0, 0, 0))  # transparent background
                    # White daisy: many thin petals around yellow center
                    rng_fl = random.Random(block * 89)
                    stem_x = TILE//2 + rng_fl.randint(-1, 1)
                    pygame.draw.line(surf, (40, 100, 45), (stem_x, TILE-1), (TILE//2, TILE//2+2), 1)
                    # Two small leaves
                    pygame.draw.ellipse(surf, (50, 120, 40), (TILE//2-5, TILE//2+5, 4, 2))
                    pygame.draw.ellipse(surf, (50, 120, 40), (TILE//2+2, TILE//2+4, 4, 2))
                    # Many thin white petals
                    center = (TILE//2, TILE//2 - 1)
                    for angle_i in range(12):
                        angle = angle_i * (2 * math.pi / 12) + rng_fl.uniform(-0.1, 0.1)
                        px = center[0] + int(math.cos(angle) * 5)
                        py = center[1] + int(math.sin(angle) * 5)
                        ex = center[0] + int(math.cos(angle) * 7)
                        ey = center[1] + int(math.sin(angle) * 7)
                        pygame.draw.line(surf, base, (px, py), (ex, ey), 1)
                    # Yellow center
                    pygame.draw.circle(surf, (255, 220, 60), center, 3)
                    pygame.draw.circle(surf, (255, 240, 100), center, 2)
            # Store the texture for this block (covers all branches: WATER, TORCH, GLASS,
            # WORKBENCH, BOOKSHELF, LAMP, CHEST, FURNACE, ANVIL, CAMPFIRE, BED, ROCK,
            # SMALL_STONE, GRASS_TUFT, BUSH, BUSH_FRUIT, and the generic else branch).
            textures[block] = surf.convert_alpha()
        # Safety net: ensure every block has a texture
        for block in BLOCK_DEFS:
            if block != AIR and block not in textures:
                s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
                s.fill(BLOCK_DEFS[block]["color"])
                textures[block] = s.convert_alpha()
        # Bed foot (right half) texture - starts from left edge for seamless connection
        bed_foot = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        bed_foot.fill((0, 0, 0, 0))
        pygame.draw.rect(bed_foot, (120, 80, 50), (0, TILE//3, TILE, TILE//2+2))
        pygame.draw.rect(bed_foot, (180, 60, 80), (0, TILE//3+2, TILE, TILE//2-2))
        pygame.draw.rect(bed_foot, (100, 65, 40), (TILE-3, TILE//4, 3, TILE//2+4))
        pygame.draw.line(bed_foot, (160, 50, 70), (TILE//3, TILE//3+3), (TILE//3, TILE-4), 1)
        textures['_BED_FOOT'] = bed_foot.convert_alpha()
        # Tall grass TOP half - stems start from bottom edge (y=TILE-1)
        tg_top = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        tg_top.fill((0, 0, 0, 0))
        tg_base = (60, 150, 40)
        rng_tg_top = random.Random(TALL_GRASS * 71 + 999)
        for i in range(7):
            bx = 2 + i * 2
            lean = rng_tg_top.randint(-2, 2)
            # Stem from bottom edge up to near top
            pygame.draw.line(tg_top, self._shade(tg_base, -30), (bx+lean, TILE-1), (bx+lean*2, 6), 2)
            pygame.draw.line(tg_top, self._shade(tg_base, 25), (bx+lean+1, TILE-1), (bx+lean*2+1, 8), 1)
            tip_x = max(0, min(TILE-1, bx+lean*2))
            tg_top.set_at((tip_x, 5), self._shade(tg_base, 40))
        textures['_TALL_GRASS_TOP'] = tg_top.convert_alpha()
        # Dried tall grass TOP half
        dtg_top = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        dtg_top.fill((0, 0, 0, 0))
        dtg_base = (170, 150, 60)
        rng_dtg_top = random.Random(DRIED_TALL_GRASS * 73 + 999)
        for i in range(6):
            bx = 3 + i * 2
            lean = rng_dtg_top.randint(-1, 1)
            pygame.draw.line(dtg_top, self._shade(dtg_base, -25), (bx+lean, TILE-1), (bx+lean*2, 6), 2)
            pygame.draw.line(dtg_top, self._shade(dtg_base, 10), (bx+lean+1, TILE-1), (bx+lean*2+1, 8), 1)
            tip_x = max(0, min(TILE-1, bx+lean*2))
            dtg_top.set_at((tip_x, 5), self._shade(dtg_base, 30))
        textures['_DRIED_TALL_GRASS_TOP'] = dtg_top.convert_alpha()
        return textures

    def _build_wall_textures(self):
        textures = {}
        for wall, d in WALL_DEFS.items():
            surf = pygame.Surface((TILE, TILE))
            base = d["color"]; surf.fill(base)
            rng = random.Random(wall*777)
            for _ in range(12): surf.set_at((rng.randint(0,TILE-1), rng.randint(0,TILE-1)), self._shade(base, rng.randint(-12,12)))
            textures[wall] = surf.convert()
        return textures

    def _build_liquid_textures(self):
        """Precompute one partial-fill surface per pixel-height for water and lava, so drawing
        a flowing liquid tile at runtime is just a blit (plus one cheap highlight line) instead
        of allocating a new Surface every tile, every frame."""
        surfs = {LIQUID_WATER: [], LIQUID_LAVA: []}
        for h in range(TILE + 1):
            hh = max(1, h)
            sw = pygame.Surface((TILE, hh), pygame.SRCALPHA)
            sw.fill((50, 110, 210, 175))
            surfs[LIQUID_WATER].append(sw)
            sl = pygame.Surface((TILE, hh), pygame.SRCALPHA)
            sl.fill((230, 90, 30, 255))
            surfs[LIQUID_LAVA].append(sl)
        return surfs

    def _build_tool_icons(self):
        icons = {}
        for tool_id, tool in TOOL_DEFS.items():
            surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            color = TIER_COLORS[tool["tier"]]
            cx, cy = TILE//2, TILE//2
            ttype = tool["type"]
            if ttype == "pickaxe":
                # Handle
                pygame.draw.line(surf, (100,65,35), (cx-7, cy+7), (cx+4, cy-4), 3)
                pygame.draw.line(surf, (80,50,25), (cx-7, cy+7), (cx+4, cy-4), 1)
                # Pick head - two prongs
                pygame.draw.line(surf, color, (cx-2, cy-8), (cx+9, cy-4), 4)
                pygame.draw.line(surf, self._shade(color, 25), (cx-1, cy-8), (cx+8, cy-5), 2)
                # Points
                pygame.draw.polygon(surf, color, [(cx-2, cy-8), (cx-5, cy-10), (cx-1, cy-7)])
                pygame.draw.polygon(surf, color, [(cx+9, cy-4), (cx+11, cy-6), (cx+8, cy-3)])
                pygame.draw.line(surf, self._shade(color,-50), (cx-2, cy-8), (cx+9, cy-4), 1)
            elif ttype == "axe":
                pygame.draw.line(surf, (80,50,30), (cx, cy+7), (cx, cy-5), 2)
                pygame.draw.polygon(surf, color, [(cx,cy-5),(cx+8,cy-7),(cx+8,cy+1),(cx+1,cy-2)])
                pygame.draw.polygon(surf, self._shade(color,-50), [(cx,cy-5),(cx+8,cy-7),(cx+8,cy+1),(cx+1,cy-2)], 1)
            elif ttype == "sword":
                pygame.draw.rect(surf, color, (cx-1, cy-8, 3, 11))
                pygame.draw.rect(surf, self._shade(color,-50), (cx-1, cy-8, 3, 11), 1)
                pygame.draw.rect(surf, (100,70,40), (cx-5, cy+2, 11, 2))
                pygame.draw.rect(surf, (80,50,30), (cx-1, cy+4, 3, 5))
            elif ttype == "hammer":
                pygame.draw.line(surf, (80,50,30), (cx, cy+7), (cx, cy-2), 2)
                pygame.draw.rect(surf, color, (cx-6, cy-7, 13, 6))
                pygame.draw.rect(surf, self._shade(color,-50), (cx-6, cy-7, 13, 6), 1)
            icons[tool_id] = surf.convert_alpha()
        # Bow icon
        bow_surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.arc(bow_surf, (120, 80, 40), (4, 4, TILE-8, TILE-8), -math.pi/3, math.pi/3, 3)
        pygame.draw.line(bow_surf, (240, 240, 240), (TILE//2, 5), (TILE//2, TILE-5), 1)
        icons[BOW] = bow_surf.convert_alpha()
        # Arrow icon
        arr_surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.line(arr_surf, (160, 110, 60), (4, TILE//2), (TILE-6, TILE//2), 2)
        pygame.draw.polygon(arr_surf, (200, 200, 200), [(TILE-6, TILE//2-3), (TILE-2, TILE//2), (TILE-6, TILE//2+3)])
        pygame.draw.line(arr_surf, (240, 240, 240), (4, TILE//2-2), (4, TILE//2+2), 2)
        icons[ARROW] = arr_surf.convert_alpha()
        return icons

    def _build_item_icons(self):
        """Build icons for food and misc items."""
        icons = {}
        # Apple
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.circle(s, (220, 60, 60), (TILE//2, TILE//2+2), 7)
        pygame.draw.circle(s, (255, 150, 150), (TILE//2-2, TILE//2), 2)
        pygame.draw.rect(s, (100, 70, 30), (TILE//2-1, 4, 2, 4))
        pygame.draw.line(s, (80, 160, 60), (TILE//2, 6), (TILE//2+4, 3), 2)
        icons[APPLE] = s.convert_alpha()
        # Bread
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (230, 190, 100), (3, 6, TILE-6, 14))
        pygame.draw.ellipse(s, (180, 140, 60), (3, 6, TILE-6, 14), 1)
        for _ in range(4): s.set_at((random.randint(6, TILE-6), random.randint(8, 18)), (160, 110, 50))
        icons[BREAD] = s.convert_alpha()
        # Cooked Meat
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (180, 90, 60), (3, 6, TILE-6, 12))
        pygame.draw.ellipse(s, (120, 60, 40), (3, 6, TILE-6, 12), 1)
        pygame.draw.rect(s, (220, 220, 220), (4, 8, 3, 2))
        icons[COOKED_MEAT] = s.convert_alpha()
        # Raw Meat (redder)
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (200, 60, 60), (3, 6, TILE-6, 12))
        pygame.draw.ellipse(s, (140, 30, 30), (3, 6, TILE-6, 12), 1)
        pygame.draw.rect(s, (240, 220, 200), (4, 8, 3, 2))
        icons[RAW_MEAT] = s.convert_alpha()
        # Stick
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.line(s, (160, 110, 60), (4, TILE-4), (TILE-4, 4), 3)
        icons[STICK] = s.convert_alpha()
        # Paper
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(s, (240, 240, 220), (5, 3, 14, 18))
        pygame.draw.rect(s, (180, 180, 160), (5, 3, 14, 18), 1)
        for i in range(4): pygame.draw.line(s, (200, 200, 180), (7, 6+i*3), (17, 6+i*3), 1)
        icons[PAPER] = s.convert_alpha()
        # Wool - fluffy white ball
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.circle(s, (240, 240, 240), (TILE//2, TILE//2), 8)
        pygame.draw.circle(s, (220, 220, 220), (TILE//2-3, TILE//2-2), 2)
        pygame.draw.circle(s, (220, 220, 220), (TILE//2+3, TILE//2-2), 2)
        pygame.draw.circle(s, (220, 220, 220), (TILE//2, TILE//2+3), 2)
        icons[WOOL] = s.convert_alpha()
        # Leather - brown hide shape
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (120, 80, 50), (4, 5, TILE-8, TILE-10))
        pygame.draw.ellipse(s, (90, 60, 35), (4, 5, TILE-8, TILE-10), 2)
        icons[LEATHER] = s.convert_alpha()
        # Feather
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.line(s, (200, 200, 180), (TILE//2, TILE-3), (TILE//2+4, 4), 1)
        for i in range(6):
            yy = 5 + i * 3
            pygame.draw.line(s, (220, 220, 200), (TILE//2+i//2, yy), (TILE//2-2, yy), 1)
            pygame.draw.line(s, (220, 220, 200), (TILE//2+i//2, yy), (TILE//2+3, yy), 1)
        icons[FEATHER] = s.convert_alpha()
        # Berry
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.circle(s, (180, 40, 80), (TILE//2-3, TILE//2), 3)
        pygame.draw.circle(s, (180, 40, 80), (TILE//2+3, TILE//2-1), 3)
        pygame.draw.circle(s, (180, 40, 80), (TILE//2, TILE//2+3), 3)
        pygame.draw.circle(s, (220, 80, 120), (TILE//2-3, TILE//2-1), 1)
        pygame.draw.circle(s, (220, 80, 120), (TILE//2+3, TILE//2-2), 1)
        icons[BERRY] = s.convert_alpha()
        # Small stone (item icon)
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (140, 140, 150), (8, 10, 8, 6))
        pygame.draw.ellipse(s, (100, 100, 110), (8, 10, 8, 6), 1)
        icons[SMALL_STONE] = s.convert_alpha()
        # Grass tuft (item icon)
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        for i in range(4):
            bx = 6 + i * 4
            pygame.draw.line(s, (80, 160, 60), (bx, TILE-4), (bx, 4), 2)
        icons[GRASS_TUFT] = s.convert_alpha()
        # Rope (item icon) - coiled rope
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.circle(s, (160, 140, 100), (TILE//2, TILE//2), 7, 2)
        pygame.draw.circle(s, (160, 140, 100), (TILE//2, TILE//2), 3, 2)
        icons[ROPE] = s.convert_alpha()
        # Tree seeds (item icons)
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (80, 120, 40), (TILE//2-4, TILE//2-3, 8, 6))
        pygame.draw.ellipse(s, (60, 90, 30), (TILE//2-4, TILE//2-3, 8, 6), 1)
        icons[TREE_SEED] = s.convert_alpha()
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (50, 100, 55), (TILE//2-4, TILE//2-3, 8, 6))
        pygame.draw.ellipse(s, (40, 80, 40), (TILE//2-4, TILE//2-3, 8, 6), 1)
        icons[PINE_SEED] = s.convert_alpha()
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (100, 140, 60), (TILE//2-5, TILE//2-4, 10, 8))
        pygame.draw.ellipse(s, (70, 100, 40), (TILE//2-5, TILE//2-4, 10, 8), 1)
        icons[GIANT_SEED] = s.convert_alpha()
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (140, 120, 80), (TILE//2-4, TILE//2-3, 8, 6))
        pygame.draw.ellipse(s, (110, 90, 60), (TILE//2-4, TILE//2-3, 8, 6), 1)
        icons[DEAD_SEED] = s.convert_alpha()
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (110, 100, 60), (TILE//2-4, TILE//2-3, 8, 6))
        pygame.draw.ellipse(s, (80, 70, 40), (TILE//2-4, TILE//2-3, 8, 6), 1)
        icons[BENT_SEED] = s.convert_alpha()
        # Water Bottle (empty) - glass bottle shape with cork stopper, no water inside
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        # Bottle body (slightly tapered: narrow neck at top, wider body at bottom)
        pygame.draw.polygon(s, (200, 220, 230, 180),
                            [(TILE//2-2, 4), (TILE//2+2, 4),    # neck top
                             (TILE//2+2, 8), (TILE//2+5, 10),    # shoulder
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4),  # body bottom
                             (TILE//2-5, 10), (TILE//2-2, 8)])   # shoulder
        pygame.draw.polygon(s, (140, 170, 200, 220),
                            [(TILE//2-2, 4), (TILE//2+2, 4),
                             (TILE//2+2, 8), (TILE//2+5, 10),
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4),
                             (TILE//2-5, 10), (TILE//2-2, 8)], 1)
        # Cork stopper
        pygame.draw.rect(s, (140, 90, 50), (TILE//2-3, 2, 6, 3))
        pygame.draw.rect(s, (90, 55, 30), (TILE//2-3, 2, 6, 3), 1)
        # Glass highlight
        pygame.draw.line(s, (255, 255, 255, 180), (TILE//2-3, 12), (TILE//2-3, TILE-6), 1)
        icons[WATER_BOTTLE] = s.convert_alpha()
        # Water Bottle (Filled) - same bottle shape but with blue water inside
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        # Bottle outline (empty glass)
        pygame.draw.polygon(s, (200, 220, 230, 180),
                            [(TILE//2-2, 4), (TILE//2+2, 4),
                             (TILE//2+2, 8), (TILE//2+5, 10),
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4),
                             (TILE//2-5, 10), (TILE//2-2, 8)])
        # Water fill inside the bottle (slightly smaller than the body)
        pygame.draw.polygon(s, (80, 130, 200, 230),
                            [(TILE//2-4, 13), (TILE//2+4, 13),
                             (TILE//2+4, TILE-5), (TILE//2-4, TILE-5)])
        # Water surface line
        pygame.draw.line(s, (160, 200, 240, 255), (TILE//2-4, 13), (TILE//2+4, 13), 1)
        # Bottle outline on top
        pygame.draw.polygon(s, (140, 170, 200, 220),
                            [(TILE//2-2, 4), (TILE//2+2, 4),
                             (TILE//2+2, 8), (TILE//2+5, 10),
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4),
                             (TILE//2-5, 10), (TILE//2-2, 8)], 1)
        # Cork stopper
        pygame.draw.rect(s, (140, 90, 50), (TILE//2-3, 2, 6, 3))
        pygame.draw.rect(s, (90, 55, 30), (TILE//2-3, 2, 6, 3), 1)
        # Glass highlight
        pygame.draw.line(s, (255, 255, 255, 180), (TILE//2-3, 12), (TILE//2-3, TILE-6), 1)
        icons[WATER_BOTTLE_FILLED] = s.convert_alpha()
        # Wooden Bottle (empty) - simple wood cup shape
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.polygon(s, (160, 110, 60, 220),
                            [(TILE//2-5, 6), (TILE//2+5, 6),
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4)])
        pygame.draw.polygon(s, (110, 75, 40),
                            [(TILE//2-5, 6), (TILE//2+5, 6),
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4)], 1)
        # Wood grain
        pygame.draw.line(s, (130, 90, 50), (TILE//2-3, 8), (TILE//2-3, TILE-6), 1)
        pygame.draw.rect(s, (120, 80, 45), (TILE//2-6, 3, 12, 4))
        icons[WOODEN_BOTTLE] = s.convert_alpha()
        # Wooden Bottle (Filled)
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.polygon(s, (160, 110, 60, 220),
                            [(TILE//2-5, 6), (TILE//2+5, 6),
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4)])
        # Water fill
        pygame.draw.polygon(s, (80, 130, 200, 230),
                            [(TILE//2-4, 13), (TILE//2+4, 13),
                             (TILE//2+4, TILE-5), (TILE//2-4, TILE-5)])
        pygame.draw.polygon(s, (110, 75, 40),
                            [(TILE//2-5, 6), (TILE//2+5, 6),
                             (TILE//2+5, TILE-4), (TILE//2-5, TILE-4)], 1)
        pygame.draw.line(s, (130, 90, 50), (TILE//2-3, 8), (TILE//2-3, TILE-6), 1)
        pygame.draw.rect(s, (120, 80, 45), (TILE//2-6, 3, 12, 4))
        icons[WOODEN_BOTTLE_FILLED] = s.convert_alpha()
        # Ore item icons (bars/gems)
        ore_item_data = {
            COAL_ITEM: (45, 45, 45),
            IRON_ITEM: (200, 200, 210),
            GOLD_ITEM: (240, 200, 80),
            DIAMOND_ITEM: (120, 230, 230),
            COPPER_ITEM: (200, 130, 80),
            TIN_ITEM: (190, 190, 185),
            SILVER_ITEM: (220, 220, 230),
            MITHRIL_ITEM: (130, 180, 230),
            RUBY_ITEM: (220, 40, 60),
            SAPPHIRE_ITEM: (40, 80, 220),
            EMERALD_ITEM: (40, 200, 100),
        }
        for ore_id, ore_color in ore_item_data.items():
            s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            if ore_id in (RUBY_ITEM, SAPPHIRE_ITEM, EMERALD_ITEM, DIAMOND_ITEM):
                # Gem shape
                cx, cy = TILE//2, TILE//2
                pygame.draw.polygon(s, ore_color, [(cx, cy-7), (cx+6, cy-2), (cx+4, cy+6), (cx-4, cy+6), (cx-6, cy-2)])
                highlight = tuple(min(255, c + 60) for c in ore_color)
                pygame.draw.polygon(s, highlight, [(cx, cy-7), (cx+3, cy-3), (cx-3, cy-3)])
                pygame.draw.polygon(s, tuple(max(0, c - 40) for c in ore_color),
                                    [(cx, cy-7), (cx+6, cy-2), (cx+4, cy+6), (cx-4, cy+6), (cx-6, cy-2)], 1)
            else:
                # Bar shape
                pygame.draw.rect(s, ore_color, (3, TILE//2-3, TILE-6, 7))
                pygame.draw.rect(s, tuple(max(0, c - 40) for c in ore_color), (3, TILE//2-3, TILE-6, 7), 1)
                # Highlight on top edge
                highlight = tuple(min(255, c + 40) for c in ore_color)
                pygame.draw.line(s, highlight, (3, TILE//2-3), (TILE-3, TILE//2-3), 1)
            icons[ore_id] = s.convert_alpha()
        # New flower block icons
        flower_colors = {
            FLOWER: (220, 80, 120),
            FLOWER_RED: (220, 50, 50),
            FLOWER_YELLOW: (240, 220, 50),
            FLOWER_BLUE: (80, 100, 230),
            FLOWER_WHITE: (240, 240, 245),
        }
        for flower_id, fcolor in flower_colors.items():
            s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            s.fill((0, 0, 0, 0))  # transparent background
            pygame.draw.line(s, (40, 110, 50), (TILE//2, TILE-1), (TILE//2, TILE//2+2), 2)
            center = (TILE//2, TILE//2-1)
            for ai in range(5):
                angle = ai * (2 * math.pi / 5) - math.pi / 2
                px = center[0] + int(math.cos(angle) * 4)
                py = center[1] + int(math.sin(angle) * 4)
                pygame.draw.circle(s, fcolor, (px, py), 3)
            pygame.draw.circle(s, (255, 230, 80), center, 2)
            icons[flower_id] = s.convert_alpha()
        return icons

    def _build_armor_icons(self):
        """Build icons for all armor pieces (helmet/chestplate/leggings/boots x 5 tiers).
        Stored in the same dict the rest of the code uses for tool icons (tool_icons),
        so no other changes are needed -- _draw_item_in_slot already looks there for armor."""
        icons = {}
        # Tier color map (already defined as TIER_COLORS, but we re-read it here for clarity)
        tier_colors = TIER_COLORS
        # Shape templates indexed by (slot_type) -> polygon/rect in a TILE x TILE canvas
        # slot_type = 0 (helmet), 1 (chestplate), 2 (leggings), 3 (boots)
        for armor_id, adef in ARMOR_DEFS.items():
            tier = adef["tier"]
            color = tier_colors.get(tier, (160, 160, 160))
            dark = self._shade(color, -50)
            light = self._shade(color, 25)
            slot_type = (armor_id - 155) % 4
            s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            if slot_type == 0:  # Helmet - dome shape with face opening
                pygame.draw.ellipse(s, color, (3, 4, TILE-6, TILE-8))
                pygame.draw.ellipse(s, dark, (3, 4, TILE-6, TILE-8), 1)
                # Face opening (cut a darker arc out of the front)
                pygame.draw.rect(s, (30, 30, 40), (5, 8, TILE-10, 4))
                # Top highlight
                pygame.draw.arc(s, light, (5, 5, TILE-10, TILE-10), math.pi*0.2, math.pi*0.8, 2)
                # Side rivets
                pygame.draw.circle(s, dark, (5, 10), 1)
                pygame.draw.circle(s, dark, (TILE-6, 10), 1)
            elif slot_type == 1:  # Chestplate - torso shape with shoulder pads
                # Main torso
                pygame.draw.polygon(s, color,
                    [(TILE//2-7, 6), (TILE//2+7, 6),    # shoulders
                     (TILE//2+8, TILE-4), (TILE//2-8, TILE-4)])  # bottom
                pygame.draw.polygon(s, dark,
                    [(TILE//2-7, 6), (TILE//2+7, 6),
                     (TILE//2+8, TILE-4), (TILE//2-8, TILE-4)], 1)
                # Neck opening
                pygame.draw.rect(s, (30, 30, 40), (TILE//2-3, 4, 6, 3))
                # Center seam
                pygame.draw.line(s, dark, (TILE//2, 8), (TILE//2, TILE-5), 1)
                # Shoulder highlight
                pygame.draw.line(s, light, (TILE//2-6, 7), (TILE//2-3, 7), 1)
                pygame.draw.line(s, light, (TILE//2+3, 7), (TILE//2+6, 7), 1)
            elif slot_type == 2:  # Leggings - two pant legs
                # Left leg
                pygame.draw.rect(s, color, (TILE//2-6, 5, 5, TILE-8))
                pygame.draw.rect(s, dark, (TILE//2-6, 5, 5, TILE-8), 1)
                # Right leg
                pygame.draw.rect(s, color, (TILE//2+1, 5, 5, TILE-8))
                pygame.draw.rect(s, dark, (TILE//2+1, 5, 5, TILE-8), 1)
                # Belt
                pygame.draw.rect(s, dark, (TILE//2-7, 3, 14, 3))
                pygame.draw.rect(s, (200, 160, 60), (TILE//2-1, 3, 2, 3))  # buckle
                # Highlights
                pygame.draw.line(s, light, (TILE//2-5, 7), (TILE//2-5, TILE-5), 1)
                pygame.draw.line(s, light, (TILE//2+2, 7), (TILE//2+2, TILE-5), 1)
            elif slot_type == 3:  # Boots - two shoe shapes
                # Left boot
                pygame.draw.rect(s, color, (TILE//2-7, 9, 5, TILE-12))  # shaft
                pygame.draw.rect(s, color, (TILE//2-9, TILE-5, 7, 4))   # foot
                pygame.draw.rect(s, dark, (TILE//2-7, 9, 5, TILE-12), 1)
                pygame.draw.rect(s, dark, (TILE//2-9, TILE-5, 7, 4), 1)
                # Right boot
                pygame.draw.rect(s, color, (TILE//2+2, 9, 5, TILE-12))
                pygame.draw.rect(s, color, (TILE//2+2, TILE-5, 7, 4))
                pygame.draw.rect(s, dark, (TILE//2+2, 9, 5, TILE-12), 1)
                pygame.draw.rect(s, dark, (TILE//2+2, TILE-5, 7, 4), 1)
                # Top cuff highlight
                pygame.draw.line(s, light, (TILE//2-6, 10), (TILE//2-3, 10), 1)
                pygame.draw.line(s, light, (TILE//2+3, 10), (TILE//2+6, 10), 1)
            icons[armor_id] = s.convert_alpha()
        return icons

    @staticmethod
    def _shade(c, a): return (max(0,min(255,c[0]+a)), max(0,min(255,c[1]+a)), max(0,min(255,c[2]+a)))

    def _build_minimap_surface(self):
        """Build minimap surface lazily - only from generated columns.
        Uses numpy pixel array for fast batch rendering instead of set_at().
        Surface is 1 pixel per tile (world.w x world.h).
        Uninitialized pixels default to sky color."""
        global _BLOCK_COLOR_LOOKUP, _WALL_COLOR_LOOKUP
        if _BLOCK_COLOR_LOOKUP is None:
            _BLOCK_COLOR_LOOKUP = np.zeros((NUM_BLOCKS, 3), dtype=np.uint8)
            for bid, bdef in BLOCK_DEFS.items():
                if bid < NUM_BLOCKS:
                    _BLOCK_COLOR_LOOKUP[bid] = bdef["color"][:3]
            _WALL_COLOR_LOOKUP = {}
            for wid, wdef in WALL_DEFS.items():
                _WALL_COLOR_LOOKUP[wid] = wdef["color"][:3]
        
        # Create surface and fill with sky color
        surf = pygame.Surface((self.world.w, self.world.h))
        surf.fill((100, 150, 200))
        
        # Pre-compute liquid colors
        LIQ_COLOR_WATER = np.array([50, 100, 200], dtype=np.uint8)
        LIQ_COLOR_LAVA  = np.array([230, 90, 30], dtype=np.uint8)
        
        try:
            pxa = pygame.surfarray.pixels3d(surf)
            gen_xs = sorted(self.world.generated_set)
            for x in gen_xs:
                col = self.world.tile_columns.get(x)
                wall_col = self.world.wall_columns.get(x)
                if col is None:
                    continue
                col_arr = np.frombuffer(col, dtype=np.uint8)
                colors = _BLOCK_COLOR_LOOKUP[col_arr]
                air_mask = col_arr == AIR
                if wall_col is not None and np.any(air_mask):
                    wall_arr = np.frombuffer(wall_col, dtype=np.uint8)
                    for wy, wc in _WALL_COLOR_LOOKUP.items():
                        wall_mask = air_mask & (wall_arr == wy)
                        if np.any(wall_mask):
                            colors[wall_mask] = wc
                if np.any(air_mask):
                    if wall_col is not None:
                        wall_arr = np.frombuffer(wall_col, dtype=np.uint8)
                        no_wall_mask = air_mask & (wall_arr == WALL_NONE)
                    else:
                        no_wall_mask = air_mask
                    colors[no_wall_mask] = [100, 150, 200]
                amt_col = self.world.liquid_amount.get(x)
                if amt_col is not None:
                    amt_arr = np.frombuffer(amt_col, dtype=np.uint8)
                    has_liq = amt_arr > 0
                    if np.any(has_liq):
                        type_col = self.world.liquid_type[x]
                        type_arr = np.frombuffer(type_col, dtype=np.uint8)
                        water_mask = has_liq & (type_arr == LIQUID_WATER)
                        lava_mask  = has_liq & (type_arr == LIQUID_LAVA)
                        if np.any(water_mask):
                            colors[water_mask] = LIQ_COLOR_WATER
                        if np.any(lava_mask):
                            colors[lava_mask] = LIQ_COLOR_LAVA
                pxa[x, :, :] = colors
            del pxa
        except Exception:
            for x in sorted(self.world.generated_set):
                self._update_minimap_column(surf, x)
        
        # Apply fog of war on minimap: black out underground in unexplored chunks.
        # Surface/sky always visible. Uses per-chunk rect approach — much less
        # memory than building a 100k×5k boolean array.
        if self.explored_chunks:
            cs = self.explored_chunk_size
            ww, wh = surf.get_size()
            ncx = (ww + cs - 1) // cs
            ncy = (wh + cs - 1) // cs
            explored_set = set(self.explored_chunks)
            # Only process unexplored chunks that are near explored ones (boundary)
            boundary = set()
            for (cx, cy) in self.explored_chunks:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < ncx and 0 <= ny < ncy and (nx, ny) not in explored_set:
                            boundary.add((nx, ny))
            try:
                pxa = pygame.surfarray.pixels3d(surf)
                surf_y_arr = self.world.surface_y
                max_w = min(ww, self.world.w) - 1
                for (ccx, ccy) in boundary:
                    px0 = ccx * cs
                    py0 = ccy * cs
                    px1 = min(px0 + cs, ww)
                    py1 = min(py0 + cs, wh)
                    # For each column in chunk, find surface_y and black out below it
                    for fx in range(px0, min(px1, max_w + 1)):
                        sy = int(surf_y_arr[fx]) + 3
                        fy_start = max(py0, sy)
                        if fy_start < py1:
                            pxa[fx, fy_start:py1] = [0, 0, 0]
                del pxa
            except Exception:
                pass

        self._minimap_dirty = False
        return surf
    
    def _update_minimap_at(self, tx, ty):
        """Mark minimap as dirty when a tile changes (lazy rebuild)."""
        self._minimap_dirty = True
    
    def _update_minimap_at_col(self, tx):
        """Mark minimap as dirty when a column is generated."""
        self._minimap_dirty = True
    
    def _update_minimap_column(self, surf, x):
        """Update a single column on the minimap surface (fallback method)."""
        if not (0 <= x < self.world.w): return
        col = self.world.tile_columns.get(x)
        if not col: return
        wall_col = self.world.wall_columns.get(x)
        col_surf = pygame.Surface((1, self.world.h))
        col_surf.fill((100, 150, 200))
        for y in range(self.world.h):
            block = col[y]
            if block == AIR:
                wall = wall_col[y] if wall_col else WALL_NONE
                if wall != WALL_NONE:
                    wc = _WALL_COLOR_LOOKUP.get(wall, (30, 30, 30)) if _WALL_COLOR_LOOKUP else (30, 30, 30)
                    col_surf.set_at((0, y), wc)
            else:
                color = BLOCK_DEFS.get(block, {}).get("color", (100, 100, 100))[:3]
                col_surf.set_at((0, y), color)
        surf.blit(col_surf, (x, 0))

    def _update_world_surface_at(self, tx, ty):
        # OPTIMIZED: just mark minimap dirty instead of updating 1.9GB surface
        self._minimap_dirty = True

    def _update_world_surface_at_col(self, tx):
        # OPTIMIZED: just mark minimap dirty instead of updating 1.9GB surface
        self._minimap_dirty = True

    def _toast(self, text, duration=2.0):
        self.floats.append({"text": text, "t": duration, "max": duration, "big": True})
    def _float_at(self, text, x, y, color=(255,255,255)):
        self.floats.append({"text": text, "t": 1.0, "max": 1.0, "x": x, "y": y, "color": color, "big": False})

    # ---------- main loop ----------
    def run(self):
        while self.running:
            raw_dt = self.clock.tick(FPS) / 1000.0
            dt = min(raw_dt, 1.0/30)
            if self.slow_mo: dt *= 0.2
            self._handle_events()
            if not self.paused and not self.map_open and not self.game_over: self._update(dt)
            if self.game_over:
                self.game_over_timer += raw_dt
                if self.game_over_timer >= self.GAME_OVER_DELAY:
                    self.player.respawn()
                    self.game_over = False
                    self.game_over_timer = 0.0
                    self._toast("Respawned", 1.0)
            self._draw()
            pygame.display.flip()
        # Restore original mouse.get_pos before quitting (no-op if not patched)
        # FIX #2: Only quit pygame if NOT returning to menu
        if not self.return_to_menu:
            pygame.quit()

    # ---------- events ----------
    def _convert_mouse_pos(self, pos):
        """Mouse position is already at native resolution — no conversion needed."""
        return pos

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.running = False
            elif event.type == pygame.KEYDOWN: self._handle_keydown(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mpos = event.pos
                # Map mode: LMB/RMB start a pan drag, MMB resets, no click closes the map.
                if self.map_open:
                    if event.button == 2 and self._map_drag_grace <= 0:
                        # Middle-click: start drag panning
                        self._map_dragging = True
                        self._map_drag_button = 2
                        self._map_drag_start = mpos
                        self._map_drag_offset_start = (self._map_offset_x, self._map_offset_y)
                        self._map_drag_moved = False
                else:
                    event.pos = mpos
                    self._handle_mousedown(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                # Map drag: stop on button release
                if self.map_open and self._map_dragging and event.button == self._map_drag_button:
                    # If MMB was clicked without moving, reset view to player
                    if event.button == 2 and not self._map_drag_moved:
                        self._map_zoom = 5.0
                        self._map_offset_x = 0.0
                        self._map_offset_y = 0.0
                    self._map_dragging = False
                    self._map_drag_button = None
                elif not self.map_open:
                    if event.button == 1: self.mouse_down_left = False
                    elif event.button == 3: self.mouse_down_right = False
            elif event.type == pygame.MOUSEMOTION:
                pass  # Map panning uses drag state updated each frame in _draw_map
            elif event.type == pygame.VIDEORESIZE:
                # Window resized — update dimensions
                if not self.fullscreen:
                    self.screen_w, self.screen_h = event.w, event.h
                    global VIEW_W, VIEW_H, WINDOW_W, WINDOW_H, ui_scale
                    VIEW_W, VIEW_H = self.screen_w, self.screen_h
                    WINDOW_W, WINDOW_H = self.screen_w, self.screen_h
                    ui_scale = 1.0
            elif event.type == pygame.MOUSEWHEEL:
                if self.map_open:
                    # Zoom the map
                    old_zoom = self._map_zoom
                    self._map_zoom *= 1.15 if event.y > 0 else (1/1.15)
                    self._map_zoom = max(0.5, min(30.0, self._map_zoom))
                    # Zoom toward mouse position
                    mx, my = pygame.mouse.get_pos()
                    cx, cy = float(self.screen_w) / 2, float(self.screen_h) / 2
                    # Zoom toward mouse position (offset is in screen pixels)
                    scale = old_zoom / self._map_zoom
                    self._map_offset_x = self._map_offset_x * scale + (cx - mx) * (1 - scale)
                    self._map_offset_y = self._map_offset_y * scale + (cy - my) * (1 - scale)
                elif self.inventory_open and self.creative_mode:
                    # Scroll the creative inventory grid (wheel up = scroll up, wheel down = scroll down).
                    # Each notch moves 2 rows for faster navigation through the long item list.
                    self._creative_scroll_target = max(0, self._creative_scroll_target - event.y * 2)
                elif not self.inventory_open and not self.workbench_open and not self.station_open and not self.chest_open:
                    pass  # mouse wheel hotbar cycling removed

    def _handle_keydown(self, key):
        if self.game_over:
            if key == pygame.K_ESCAPE:
                self.return_to_menu = True; self.running = False
            return
        if self.paused:
            # Pause menu handles its own keys
            if key == pygame.K_ESCAPE:
                if self.pause_state == "help": self.pause_state = "main"
                else: self.paused = False
            return
        if key == pygame.K_ESCAPE:
            if self.inventory_open: self.inventory_open = False
            elif self.workbench_open: self.workbench_open = False
            elif self.station_open: self.station_open = False
            elif self.chest_open: self.chest_open = False; self.active_chest_pos = None
            elif self.map_open: self.map_open = False
            else: self.paused = True; self.pause_state = "main"
        elif key == pygame.K_e:
            if self.creative_mode:
                # In creative mode, E opens a creative inventory with all items
                self.inventory_open = not self.inventory_open
                if self.inventory_open:
                    self.workbench_open = False; self.station_open = False
                    self.chest_open = False; self.map_open = False
            else:
                self.inventory_open = not self.inventory_open
                if self.inventory_open:
                    self.workbench_open = False; self.station_open = False
                    self.chest_open = False; self.map_open = False
        elif key == pygame.K_TAB:
            self.map_open = not self.map_open
            if not self.map_open:
                # OPTIMIZED: free ~1.9GB minimap surface when map is closed
                self._minimap_surface = None
            if self.map_open:
                self.inventory_open = False; self.workbench_open = False
                self.station_open = False; self.chest_open = False
                # Reset drag state and clear mouse buttons so stale clicks don't interfere.
                # Also set a grace period so the stale physical LMB state (e.g. the player
                # was mid-mining when they hit TAB) doesn't immediately start a false drag.
                self._map_dragging = False
                self._map_drag_button = None
                self._map_drag_grace = 4  # ignore button state for this many frames after opening
                self.mouse_down_left = False
                self.mouse_down_right = False
        elif key == pygame.K_r:
            if self.creative_mode:
                self.player.respawn(); self._toast("Respawned", 1.0)
            else:
                self._toast("Respawn is only available in Creative mode", 2.0)
        elif key == pygame.K_t:
            if self.creative_mode:
                self.time = 0.5 if self.time < 0.25 or self.time > 0.75 else 0.0
                self._toast("Time toggled", 1.0)
            else:
                self._toast("Time toggle is only available in Creative mode", 2.0)
        elif key == pygame.K_f:
            self._eat_food()
        elif key == pygame.K_F1: self.debug = not self.debug
        elif key == pygame.K_F2:
            if self.creative_mode:
                self.slow_mo = not self.slow_mo
                self._toast("Slow motion " + ("ON" if self.slow_mo else "OFF"), 1.0)
            else:
                self._toast("Slow motion is only available in Creative mode", 2.0)
        elif key == pygame.K_F11: self.fullscreen = not self.fullscreen; self.screen = self._init_display()
        # Zoom in/out with Ctrl+= and Ctrl+-
        elif key == pygame.K_EQUALS and (pygame.key.get_mods() & pygame.KMOD_CTRL):
            self.game_zoom = min(4.0, self.game_zoom * 1.25)
            self._toast(f"Zoom: {self.game_zoom:.2f}x", 1.0)
        elif key == pygame.K_MINUS and (pygame.key.get_mods() & pygame.KMOD_CTRL):
            self.game_zoom = max(0.25, self.game_zoom / 1.25)
            self._toast(f"Zoom: {self.game_zoom:.2f}x", 1.0)
        elif key == pygame.K_F12: self._debug_give_all()
        elif key == pygame.K_F5:
            fname = save_world(self.world, self.player, self.inventory, self.time, self.day_count, self.world_name, self.seed, self.chests, self.armor)
            self._toast(f"Saved: {self.world_name}", 2.0)
        elif pygame.K_1 <= key <= pygame.K_9:
            self.selected = key - pygame.K_1
        elif key == pygame.K_0:
            self.selected = 9

    def _handle_mousedown(self, event):
        # If paused, handle pause menu clicks
        if self.paused:
            self._handle_pause_click(event)
            return
        # Inventory / workbench / station / chest / map take priority
        if self.inventory_open:
            if self._handle_hotbar_click(event): return
            if self.creative_mode:
                self._handle_creative_click(event); return
            self._handle_inventory_click(event); return
        if self.workbench_open:
            if self._handle_hotbar_click(event): return
            self._handle_workbench_click(event); return
        if self.station_open:
            if self._handle_hotbar_click(event): return
            self._handle_station_click(event); return
        if self.chest_open:
            if self._handle_hotbar_click(event): return
            self._handle_chest_click(event); return
        # Note: map clicks are now intercepted directly in _handle_events (LMB/RMB
        # start a pan drag, MMB resets zoom). The map only closes via ESC or TAB.
        # Hotbar click? (handles LMB-select, LMB-place-held, RMB-pick-up, and
        # RMB-arm-throw when no panel is open and a slot has a stackable item)
        if self._handle_hotbar_click(event): return
        # World interaction
        if event.button == 1:
            import time as _t
            now = _t.perf_counter()
            # Throw: if throw is armed (from double-click), throw one item at cursor
            if self._throw_armed and (now - self._throw_armed_time) < THROW_ARM_TTL:
                slot_idx = self._throw_armed_slot
                if 0 <= slot_idx < len(self.inventory.slots) and self.inventory.slots[slot_idx]:
                    self._throw_item_from_slot(slot_idx, event.pos)
                    # Keep throw armed for continuous throwing until stack is empty
                    if not self.inventory.slots[slot_idx]:
                        self._throw_armed = False
                        self._throw_armed_slot = -1
                    else:
                        self._throw_armed_time = now
                else:
                    self._throw_armed = False
                    self._throw_armed_slot = -1
                return
            # Detect double-click to arm throw mode
            mx, my = event.pos
            dist = math.hypot(mx - self._last_lmb_pos[0], my - self._last_lmb_pos[1])
            if (now - self._last_lmb_time) < DOUBLE_CLICK_TIME and dist < 20:
                # Double-click detected: arm throw mode for selected slot
                item = self._get_selected_item()
                if item and item.item_id not in NON_STACKABLE and item.count > 0:
                    self._throw_armed = True
                    self._throw_armed_slot = self.selected
                    self._throw_armed_time = now
                    self._toast("Throw mode - click to throw", 1.0)
                    self._last_lmb_time = 0.0  # reset to avoid triple-trigger
                    return
            self._last_lmb_time = now
            self._last_lmb_pos = event.pos
            # 1) Single-LMB on food/filled bottle: eat/drink immediately
            item = self._get_selected_item()
            if item and (is_food(item.item_id) or item.item_id in (WATER_BOTTLE_FILLED, WOODEN_BOTTLE_FILLED)):
                self._eat_food()
                return
            # 2) Default: mining/attacking/collecting/placing
            self.mouse_down_left = True
        elif event.button == 3:
            # Right click: disarm throw mode first
            self._throw_armed = False
            self._throw_armed_slot = -1
            # Interact with blocks (workbench, chest, furnace, anvil, campfire, bed)
            mx, my = event.pos
            wx, wy = mx + self.cam_x, my + self.cam_y
            tx, ty = int(wx // TILE), int(wy // TILE)
            block = self.world.get(tx, ty)
            bdef = BLOCK_DEFS.get(block, {})
            if bdef.get("interactable") and self._player_near(tx, ty):
                station = bdef.get("station", "workbench")
                if block == CHEST:
                    self._open_chest(tx, ty)
                    play_sound("door", 0.35)
                elif station == "workbench":
                    self.workbench_open = True
                    play_sound("door", 0.35)
                elif station == "bed":
                    if self._is_night():
                        self.time = 0.30
                        self._toast("You slept through the night. Dawn breaks!", 2.0)
                    else:
                        self.time = 0.72
                        self._toast("You rested through the day. Dusk falls...", 2.0)
                else:
                    self.active_station = station
                    self.station_open = True
                    # Furnace gets its own fire-whoosh; other stations use the door creak
                    if station == "furnace":
                        play_sound("furnace", 0.4)
                    else:
                        play_sound("door", 0.35)
                return
            # Right click: fill water bottle at targeted water tile
            item = self._get_selected_item()
            if item and item.item_id in (WATER_BOTTLE, WOODEN_BOTTLE):
                if self._try_fill_water_bottle(event.pos):
                    return
            # Right click: pick up & swap hotbar items
            self.mouse_down_right = True

    def _player_near(self, tx, ty):
        px = self.player.x; py = self.player.y - self.player.h * 0.5
        cx = tx * TILE + TILE/2; cy = ty * TILE + TILE/2
        return math.hypot(cx - px, cy - py) <= REACH

    def _handle_pause_click(self, event):
        if event.button != 1: return
        mx, my = event.pos
        if self.pause_state == "main":
            for b in self._pause_menu_buttons():
                if b["rect"].collidepoint(mx, my):
                    act = b["action"]
                    if act == "resume":
                        self.paused = False
                    elif act == "save":
                        try:
                            save_world(self.world, self.player, self.inventory, self.time, self.day_count, self.world_name, self.seed, self.chests, self.armor)
                            self._toast(f"Saved: {self.world_name}", 1.5)
                        except Exception as e:
                            print(f"Save failed: {e}")
                            self._toast("Save failed!", 2.0)
                        self.return_to_menu = True; self.running = False
                    elif act == "help":
                        self.pause_state = "help"
                    elif act == "quit":
                        self.running = False
                    return
        elif self.pause_state == "help":
            panel = pygame.Rect(self.screen_w//2 - 440, 90, 880, self.screen_h - 160)
            r = pygame.Rect(panel.centerx - 80, panel.bottom - 44, 160, 36)
            if r.collidepoint(mx, my): self.pause_state = "main"; return

    def _handle_hotbar_click(self, event) -> bool:
        mx, my = event.pos
        slot, gap = 44, 4
        total = 10*slot + 9*gap
        hx = (self.screen_w - total) // 2; hy = self.screen_h - slot - 14
        if not (hy <= my <= hy + slot): return False
        # Track RMB on the hotbar for the throw gesture (only when no panel is open).
        no_panel = not (self.inventory_open or self.workbench_open or self.station_open or self.chest_open or self.map_open)
        import time as _t
        for i in range(10):
            x = hx + i*(slot+gap)
            if x <= mx <= x + slot:
                # Shift+click: swap this slot with the currently selected slot
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    inv = self.inventory
                    if i != self.selected:
                        inv.slots[i], inv.slots[self.selected] = inv.slots[self.selected], inv.slots[i]
                    return True
                if event.button == 1:
                    # Left click: if holding something, place it; otherwise select
                    inv = self.inventory
                    if inv.held:
                        if inv.slots[i] and inv.slots[i].item_id == inv.held.item_id and inv.held.item_id not in NON_STACKABLE:
                            add = min(inv.held.count, inv.slots[i].max_stack() - inv.slots[i].count)
                            inv.slots[i].count += add; inv.held.count -= add
                            if inv.held.count <= 0: inv.held = None
                        else:
                            inv.slots[i], inv.held = inv.held, inv.slots[i]
                    else:
                        self.selected = i
                    # Any LMB on the hotbar cancels a previous throw arm from a different slot
                    if no_panel and self._throw_armed_slot != i:
                        pass  # keep the new arm from above
                    self._hotbar_rmb_slot = None  # LMB resets RMB exchange tracking
                elif event.button == 3:
                    inv = self.inventory
                    if inv.held:
                        # Swap positions
                        inv.slots[i], inv.held = inv.held, inv.slots[i]
                    elif no_panel and inv.slots[i] is not None and inv.slots[i].count > 0:
                        # RMB on a hotbar slot: select it first, or exchange with previously selected
                        if self._hotbar_rmb_slot is not None and self._hotbar_rmb_slot != i:
                            # Second RMB on different slot: exchange the two slots
                            inv.slots[self._hotbar_rmb_slot], inv.slots[i] = inv.slots[i], inv.slots[self._hotbar_rmb_slot]
                            self._hotbar_rmb_slot = None
                        else:
                            # First RMB: select this slot
                            self.selected = i
                            self._hotbar_rmb_slot = i
                    else:
                        if inv.slots[i]:
                            inv.held = inv.slots[i]; inv.slots[i] = None
                        else:
                            self.selected = i
                return True
        return False

    def _handle_inventory_click(self, event):
        mx, my = event.pos
        slot_size, gap = 44, 2
        cols, rows = 10, 5
        sw = self.screen_w
        grid_w = cols*slot_size + (cols-1)*gap
        grid_x = (sw - grid_w)//2 - 120; grid_y = 120
        # Check armor slot clicks
        armor_x = grid_x - 70
        for ai in range(4):
            ax = armor_x
            ay = grid_y + ai * (slot_size + gap)
            if ax <= mx <= ax + slot_size and ay <= my <= ay + slot_size:
                inv = self.inventory
                if event.button == 1:
                    if inv.held:
                        if is_armor(inv.held.item_id):
                            held_type = (inv.held.item_id - 155) % 4
                            if held_type == ai:
                                old = self.armor[ai]
                                self.armor[ai] = inv.held
                                inv.held = old
                            else:
                                self._toast("Wrong armor slot for this piece!", 1.5)
                        else:
                            old = self.armor[ai]
                            self.armor[ai] = inv.held
                            inv.held = old
                    else:
                        if self.armor[ai]:
                            inv.held = self.armor[ai]
                            self.armor[ai] = None
                elif event.button == 3:
                    # Right-click: quick equip
                    if inv.held and is_armor(inv.held.item_id):
                        held_type = (inv.held.item_id - 155) % 4
                        if held_type == ai:
                            old = self.armor[ai]
                            self.armor[ai] = inv.held
                            inv.held = old
                return
        for row in range(rows):
            for col in range(cols):
                sx = grid_x + col*(slot_size+gap); sy = grid_y + row*(slot_size+gap)
                if sx <= mx <= sx+slot_size and sy <= my <= sy+slot_size:
                    self._click_slot(row*cols+col, event.button); return
        # Recipes
        recipe_x = grid_x + cols*(slot_size+gap) + 30
        for i, recipe in enumerate(RECIPES_BASIC):
            rx = recipe_x + (i%2)*230; ry = grid_y + (i//2)*36
            if rx <= mx <= rx+226 and ry <= my <= ry+33:
                self._craft(recipe); return

    def _handle_workbench_click(self, event):
        mx, my = event.pos
        slot_size, gap = 44, 2
        cols, rows = 10, 5
        sw = self.screen_w
        grid_w = cols*slot_size + (cols-1)*gap
        grid_x = (sw - grid_w)//2 - 120; grid_y = 120
        # Clicks on inventory grid
        for row in range(rows):
            for col in range(cols):
                sx = grid_x + col*(slot_size+gap); sy = grid_y + row*(slot_size+gap)
                if sx <= mx <= sx+slot_size and sy <= my <= sy+slot_size:
                    self._click_slot(row*cols+col, event.button); return
        # Recipe clicks
        recipe_x = grid_x + cols*(slot_size+gap) + 30
        for i, recipe in enumerate(RECIPES_WORKBENCH):
            rx = recipe_x + (i%2)*230; ry = grid_y + (i//2)*36
            if rx <= mx <= rx+226 and ry <= my <= ry+33:
                self._craft(recipe); return

    def _handle_station_click(self, event):
        """Handle clicks in station UI (furnace/anvil/campfire)."""
        mx, my = event.pos
        # Furnace has its own dedicated UI
        if self.active_station == "furnace":
            if event.button == 1:
                self._handle_furnace_click(mx, my)
            return
        slot_size, gap = 44, 2
        cols, rows = 10, 5
        grid_w = cols*slot_size + (cols-1)*gap
        grid_x = (self.screen_w - grid_w)//2 - 120; grid_y = 120
        for row in range(rows):
            for col in range(cols):
                sx = grid_x + col*(slot_size+gap); sy = grid_y + row*(slot_size+gap)
                if sx <= mx <= sx+slot_size and sy <= my <= sy+slot_size:
                    self._click_slot(row*cols+col, event.button); return
        recipe_x = grid_x + cols*(slot_size+gap) + 30
        recipes = {"furnace": RECIPES_FURNACE, "anvil": RECIPES_ANVIL, "campfire": RECIPES_CAMPFIRE,
                   "workbench": RECIPES_WORKBENCH}.get(self.active_station, RECIPES_WORKBENCH)
        for i, recipe in enumerate(recipes):
            rx = recipe_x + (i%2)*230; ry = grid_y + (i//2)*36
            if rx <= mx <= rx+226 and ry <= my <= ry+33:
                self._craft(recipe); return

    def _open_chest(self, tx, ty):
        """Open a chest at (tx, ty), creating storage if needed."""
        key = f"{tx},{ty}"
        if key not in self.chests:
            self.chests[key] = Inventory(50)  # chests have 50 slots (5 rows)
        self.chest_open = True
        self.active_chest_pos = (tx, ty)
        self.chest_inventory = self.chests[key]

    def _handle_chest_click(self, event):
        """Handle clicks in chest UI - can move items between player inventory and chest."""
        mx, my = event.pos
        slot_size, gap = 44, 2
        cols = 10
        # Player inventory grid (bottom)
        grid_w = cols*slot_size + (cols-1)*gap
        grid_x = (self.screen_w - grid_w)//2 - 120; grid_y = 390
        for row in range(5):
            for col in range(cols):
                sx = grid_x + col*(slot_size+gap); sy = grid_y + row*(slot_size+gap)
                if sx <= mx <= sx+slot_size and sy <= my <= sy+slot_size:
                    self._click_slot(row*cols+col, event.button); return
        # Chest inventory grid (top)
        chest_grid_y = 120
        chest_cols = 10; chest_rows = 5
        for row in range(chest_rows):
            for col in range(chest_cols):
                sx = grid_x + col*(slot_size+gap); sy = chest_grid_y + row*(slot_size+gap)
                if sx <= mx <= sx+slot_size and sy <= my <= sy+slot_size:
                    self._click_chest_slot(row*chest_cols+col, event.button); return

    def _click_slot(self, idx, button):
        inv = self.inventory; slot = inv.slots[idx]
        if button == 1:
            if inv.held:
                if slot and slot.item_id == inv.held.item_id and inv.held.item_id not in NON_STACKABLE:
                    add = min(inv.held.count, slot.max_stack()-slot.count)
                    slot.count += add; inv.held.count -= add
                    if inv.held.count <= 0: inv.held = None
                elif slot is None: inv.slots[idx] = inv.held; inv.held = None
                else: inv.slots[idx], inv.held = inv.held, slot
            else:
                if slot: inv.held = slot; inv.slots[idx] = None
        elif button == 3:
            # Right click: swap or pick up entire stack
            if inv.held:
                # Swap positions
                inv.slots[idx], inv.held = inv.held, slot
            else:
                if slot: inv.held = slot; inv.slots[idx] = None

    def _click_chest_slot(self, idx, button):
        """Click a chest slot - moves items between chest and held (player's hand)."""
        if not self.chest_inventory: return
        if idx >= len(self.chest_inventory.slots): return
        inv = self.chest_inventory; slot = inv.slots[idx]
        if button == 1:
            if self.inventory.held:
                if slot and slot.item_id == self.inventory.held.item_id and self.inventory.held.item_id not in NON_STACKABLE:
                    add = min(self.inventory.held.count, slot.max_stack()-slot.count)
                    slot.count += add; self.inventory.held.count -= add
                    if self.inventory.held.count <= 0: self.inventory.held = None
                elif slot is None: inv.slots[idx] = self.inventory.held; self.inventory.held = None
                else: inv.slots[idx], self.inventory.held = self.inventory.held, slot
            else:
                if slot: self.inventory.held = slot; inv.slots[idx] = None
        elif button == 3:
            if self.inventory.held:
                inv.slots[idx], self.inventory.held = self.inventory.held, slot
            else:
                if slot: self.inventory.held = slot; inv.slots[idx] = None

    def _craft(self, recipe):
        inv = self.inventory
        if not inv.has_materials(recipe["materials"]):
            self._toast("Not enough materials!", 1.0); return
        result_id, result_count = recipe["result"]
        inv.consume_materials(recipe["materials"])
        leftover = inv.add(result_id, result_count)
        if leftover > 0: self._toast("Inventory full!", 1.0)
        else: self._toast(f"Crafted {recipe['name']}", 1.0)
        play_sound("craft", 0.4)

    def _eat_food(self):
        """Eat the currently selected food item or drink a filled water bottle.
        Restores health + hunger (food) or water (filled bottle)."""
        item = self.inventory.slots[self.selected]
        if not item: return
        # Food items
        if is_food(item.item_id):
            heal = FOOD_DEFS[item.item_id]["heal"]
            # Allow eating even at full health so the player can still top up hunger.
            self.player.health = min(self.player.max_health, self.player.health + heal)
            self.player.hunger = min(self.player.max_hunger, self.player.hunger + heal * 0.8)
            # Watery fruits also restore water bar
            water_restore = FOOD_DEFS[item.item_id].get("water", 0)
            if water_restore > 0:
                self.player.water = min(self.player.max_water, self.player.water + water_restore)
                self._float_at(f"+{water_restore} water", self.player.x, self.player.y - self.player.h - 12, (80, 180, 240))
            self._float_at(f"+{heal} HP", self.player.x, self.player.y - self.player.h, (80, 220, 80))
            self._spawn_particles(self.player.x, self.player.y - self.player.h*0.5, 6, FOOD_DEFS[item.item_id]["color"], speed=80, life=0.6)
            play_sound("eat", 0.45)
            item.count -= 1
            if item.count <= 0: self.inventory.slots[self.selected] = None
            return
        # Filled water bottle -> drink and leave the empty bottle in the slot
        if item.item_id in (WATER_BOTTLE_FILLED, WOODEN_BOTTLE_FILLED):
            drink = MISC_DEFS[item.item_id].get("drink", 35)
            if self.player.water >= self.player.max_water:
                self._toast("Not thirsty right now", 1.0); return
            self.player.water = min(self.player.max_water, self.player.water + drink)
            self._float_at(f"+{drink} water", self.player.x, self.player.y - self.player.h, (80, 180, 240))
            self._spawn_particles(self.player.x, self.player.y - self.player.h*0.5, 6, (120, 180, 240), speed=70, life=0.6)
            play_sound("drink", 0.45)
            empty_type = WOODEN_BOTTLE if item.item_id == WOODEN_BOTTLE_FILLED else WATER_BOTTLE
            item.count -= 1
            if item.count <= 0:
                self.inventory.slots[self.selected] = ItemStack(empty_type, 1)
            else:
                self.inventory.add(empty_type, 1)
            return
        if item.item_id in (WATER_BOTTLE, WOODEN_BOTTLE):
            self._toast("Bottle is empty - fill it at a pond/sea first", 1.5); return

    def _try_fill_water_bottle(self, screen_pos):
        """If the player has an empty WATER_BOTTLE selected and clicks on a tile that
        contains water liquid (or a baked WATER block from old saves), fill the bottle.
        Returns True if a bottle was filled, False otherwise."""
        item = self._get_selected_item()
        if not item or item.item_id not in (WATER_BOTTLE, WOODEN_BOTTLE): return False
        mx, my = screen_pos
        wx, wy = mx * ui_scale + self.cam_x, my * ui_scale + self.cam_y
        tx, ty = int(wx // TILE), int(wy // TILE)
        # Check the flowing-liquid layer first (modern water), then fall back to a baked
        # WATER block (old saves / seas that haven't been converted yet).
        ltype, lamt = self.world.get_liquid(tx, ty)
        is_water = (ltype == LIQUID_WATER and lamt > 0) or (self.world.get(tx, ty) == WATER)
        if not is_water: return False
        # Consume one empty bottle and add one filled bottle.
        filled_type = WOODEN_BOTTLE_FILLED if item.item_id == WOODEN_BOTTLE else WATER_BOTTLE_FILLED
        item.count -= 1
        if item.count <= 0:
            self.inventory.slots[self.selected] = ItemStack(filled_type, 1)
        else:
            self.inventory.add(filled_type, 1)
        self._float_at("+1 Filled Bottle", tx*TILE+TILE/2, ty*TILE, (120, 180, 240))
        self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 6, (120, 180, 240), speed=60, life=0.5)
        return True

    def _destroy_tree(self, tx, ty, tree_type):
        """When a tree trunk block is mined, destroy only THIS tree (not nearby trees).
        Uses upward-tracing BFS: only follows trunk blocks going UP from the mined block.
        This prevents nearby trees with touching trunks from being destroyed together."""
        trunk_types = {TREE_TRUNK, PINE_TRUNK, TREE_GIANT, TREE_DEAD, TREE_BENT}

        # Phase 1: Find all connected trunk blocks going UPWARD from the mined block.
        # We trace both up AND down from the mined block, but restrict horizontal
        # spread to only follow blocks of the SAME type as tree_type. This prevents
        # two different trees planted next to each other from being linked.
        trunk_visited = set()
        trunk_queue = deque([(tx, ty)])
        trunk_blocks = []
        while trunk_queue:
            cx, cy = trunk_queue.popleft()
            if (cx, cy) in trunk_visited: continue
            trunk_visited.add((cx, cy))
            if cx < 0 or cx >= self.world.w or cy < 0 or cy >= self.world.h: continue
            block = self.world.get(cx, cy)
            if block not in trunk_types: continue
            # Only allow horizontal connections between same-type trunks.
            # This prevents two different trees planted next to each other from
            # linking together via touching trunk blocks.
            trunk_blocks.append((cx, cy, block))
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = cx + dx, cy + dy
                # Allow vertical movement freely (tree grows up/down)
                if dy != 0:
                    trunk_queue.append((nx, ny))
                else:
                    # Horizontal: only if same block type (same tree species)
                    if 0 <= nx < self.world.w and 0 <= ny < self.world.h:
                        if self.world.get(nx, ny) == block:
                            trunk_queue.append((nx, ny))

        # Phase 2: Find leaves connected to these trunk blocks (start within 4 tiles of any trunk)
        # Leaves can spread up to 3-4 tiles from trunk due to canopy generation.
        # IMPORTANT (bug 1): do NOT pre-mark initial leaves as visited here - the BFS
        # below relies on popping a leaf and THEN marking it visited. Pre-marking
        # caused every leaf to be skipped by the `if (cx, cy) in leaf_visited:
        # continue` check, which meant leaves were never added to to_destroy and
        # never got destroyed when a tree was chopped down.
        # IMPORTANT (bug 2): trunk_visited above is polluted - it contains every
        # tile the trunk BFS touched, including the AIR / leaf tile directly above
        # the topmost trunk and the dirt tile directly below the bottommost trunk
        # (because the trunk BFS adds to visited BEFORE the "is this a trunk?"
        # check). Reusing trunk_visited as leaf_visited would skip the leaf
        # directly above the topmost trunk, leaving a single floating leaf after
        # the tree is chopped. We therefore seed leaf_visited from trunk_blocks
        # (actual trunk tile coordinates) instead.
        leaf_visited = set((bx, by) for bx, by, _ in trunk_blocks)
        leaf_queue = deque()
        for bx, by, bb in trunk_blocks:
            for dx in range(-4, 5):
                for dy in range(-4, 5):
                    nx, ny = bx + dx, by + dy
                    if (nx, ny) in leaf_visited: continue
                    if 0 <= nx < self.world.w and 0 <= ny < self.world.h:
                        if self.world.get(nx, ny) in ALL_LEAF_TYPES:
                            leaf_queue.append((nx, ny))

        # BFS from initial leaves to find the full canopy (leaves connect to leaves)
        to_destroy = list(trunk_blocks)
        while leaf_queue:
            cx, cy = leaf_queue.popleft()
            if (cx, cy) in leaf_visited: continue
            leaf_visited.add((cx, cy))
            if cx < 0 or cx >= self.world.w or cy < 0 or cy >= self.world.h: continue
            block = self.world.get(cx, cy)
            if block not in ALL_LEAF_TYPES: continue
            to_destroy.append((cx, cy, block))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in leaf_visited:
                    leaf_queue.append((nx, ny))

        # Determine the seed to drop based on tree type
        seed_map = {
            TREE_TRUNK: TREE_SEED, PINE_TRUNK: PINE_SEED,
            TREE_GIANT: GIANT_SEED, TREE_DEAD: DEAD_SEED, TREE_BENT: BENT_SEED
        }
        seed_id = seed_map.get(tree_type, TREE_SEED)

        # Destroy all found blocks and drop items
        wood_count = 0
        leaf_count = 0
        for cx, cy, block in to_destroy:
            self.world.set(cx, cy, AIR)
            if block in (TREE_TRUNK, PINE_TRUNK, TREE_DEAD, TREE_BENT):
                wood_count += 1
            elif block == TREE_GIANT:
                wood_count += 2
            elif block in ALL_LEAF_TYPES:
                leaf_count += 1
                if random.random() < 0.15:
                    self._drop_item_at(cx * TILE + TILE // 2, cy * TILE, APPLE, 1)
            self._spawn_particles(cx*TILE+TILE/2, cy*TILE+TILE/2, 3, BLOCK_DEFS[block]["color"], speed=40, life=0.3)

        # Tree-fall sound: volume scales with tree size (giant trees = louder crash)
        if wood_count > 0:
            tree_vol = min(0.7, 0.35 + wood_count * 0.05)
            play_sound("tree_fall", tree_vol)

        # Update surface for all modified columns
        modified_cols = set(cx for cx, cy, b in to_destroy)
        for cx in modified_cols:
            self._update_world_surface_at_col(cx)

        # Drop items
        if wood_count > 0:
            self._drop_item_at(tx * TILE + TILE // 2, ty * TILE, WOOD, wood_count)
        if leaf_count > 0 and random.random() < 0.4:
            self._drop_item_at(tx * TILE + TILE // 2 + 8, ty * TILE, STICK, max(1, leaf_count // 3))
        # Drop tree seed (1 per tree destroyed)
        self._drop_item_at(tx * TILE + TILE // 2 - 8, ty * TILE, seed_id, 1)

    def _drop_item_at(self, wx, wy, item_id, count=1):
        """Drop an item as a DroppedItem at world coordinates (wx, wy).
        The item falls with physics and can be picked up by the player."""
        for _ in range(min(count, 10)):  # Cap at 10 separate drops to avoid lag
            drop_count = min(count, max(1, count // 10 + (1 if count % 10 > 0 else 0)))
            count -= drop_count
            dropped = DroppedItem(
                x=wx + random.uniform(-8, 8),
                y=wy + random.uniform(-16, -4),
                vx=random.uniform(-60, 60),
                vy=random.uniform(-200, -80),
                item_id=item_id,
                count=drop_count,
                life=120.0,
                pickup_delay=0.6,
            )
            self.dropped_items.append(dropped)

    def _break_block_above(self, tx, ty, max_cascade=30):
        """When a block at (tx, ty) is broken, check blocks above it.
        If a block above has no solid support (left, right, or above it),
        destroy it and drop it as an item, then continue cascading upward."""
        no_fall = {AIR, BEDROCK, LAVA}
        for offset in range(1, max_cascade + 1):
            ay = ty - offset
            if ay < 0: break
            above = self.world.get(tx, ay)
            if above in no_fall or above == AIR: break
            d = BLOCK_DEFS.get(above, {})
            if not d.get("mineable", False): break
            # Check if this block has any support (solid neighbor left, right, or above)
            has_support = False
            if tx > 0 and self.world.is_solid(tx - 1, ay):
                has_support = True
            if tx + 1 < self.world.w and self.world.is_solid(tx + 1, ay):
                has_support = True
            if ay > 0 and self.world.is_solid(tx, ay - 1):
                has_support = True
            if not has_support:
                # Handle multi-tile blocks
                if above == BED:
                    is_bed_left = (tx == 0 or self.world.get(tx - 1, ay) != BED)
                    if is_bed_left:
                        for dx in range(2):
                            ntx = tx + dx
                            if ntx < self.world.w and self.world.get(ntx, ay) == BED:
                                self.world.set(ntx, ay, AIR)
                                self._update_world_surface_at(ntx, ay)
                        self._drop_item_at(tx * TILE + TILE // 2, ay * TILE, BED, 1)
                elif above in (TALL_GRASS, DRIED_TALL_GRASS):
                    # Handle 2-tile vertical grass
                    if ay + 1 < self.world.h and self.world.get(tx, ay + 1) == above:
                        self.world.set(tx, ay + 1, AIR)
                        self._update_world_surface_at(tx, ay + 1)
                    if ay - 1 >= 0 and self.world.get(tx, ay - 1) == above:
                        self.world.set(tx, ay - 1, AIR)
                        self._update_world_surface_at(tx, ay - 1)
                    drops = d.get("drops")
                    if drops is not None:
                        self._drop_item_at(tx * TILE + TILE // 2, ay * TILE, drops, 1)
                else:
                    self.world.set(tx, ay, AIR)
                    self._update_world_surface_at(tx, ay)
                    drops = d.get("drops")
                    if drops is not None:
                        self._drop_item_at(tx * TILE + TILE // 2, ay * TILE, drops, 1)
                self._spawn_particles(tx*TILE+TILE/2, ay*TILE+TILE/2, 4, d["color"], speed=60, life=0.3)
            else:
                break

    def _throw_item_from_slot(self, slot_idx, screen_pos):
        """Throw one item from the given inventory slot toward screen_pos.
        The item leaves the inventory and becomes a free-falling DroppedItem in the world."""
        inv = self.inventory
        item = inv.slots[slot_idx] if 0 <= slot_idx < len(inv.slots) else None
        if not item or item.count <= 0: return
        # Player position (feet at player.y, mid-body at player.y - h/2)
        px = self.player.x
        py = self.player.y - self.player.h * 0.5
        mx, my = screen_pos
        wx, wy = mx * ui_scale + self.cam_x, my * ui_scale + self.cam_y
        dx = wx - px; dy = wy - py
        dist = math.hypot(dx, dy)
        if dist < 1:
            vx, vy = 0.0, -THROW_SPEED * 0.5
        else:
            vx = dx / dist * THROW_SPEED
            vy = dy / dist * THROW_SPEED - 80.0  # slight upward bias for a nice arc
        # Spawn the dropped item just above the player's mid-body so it doesn't
        # instantly collide with the player's own hitbox.
        dropped = DroppedItem(
            x=px, y=py - 4.0,
            vx=vx, vy=vy,
            item_id=item.item_id,
            count=1,
            durability=item.durability,
            life=120.0,
            pickup_delay=0.6,
        )
        self.dropped_items.append(dropped)
        # Consume one from the source stack
        item.count -= 1
        if item.count <= 0: inv.slots[slot_idx] = None
        self._spawn_particles(px, py, 4, get_item_color(item.item_id), speed=50, life=0.3)
        self._float_at(f"Threw {get_item_name(dropped.item_id)}", px, py - 16, (220, 220, 220))

    def _update_dropped_items(self, dt):
        """Physics + pickup for thrown/dropped items in the world."""
        if not self.dropped_items: return
        p = self.player
        keep = []
        for d in self.dropped_items:
            d.life -= dt
            if d.pickup_delay > 0: d.pickup_delay -= dt
            # Physics: gravity + horizontal slowdown (air drag)
            d.vy += THROW_GRAVITY * dt
            d.vx *= (1.0 - min(1.0, 0.5 * dt))  # mild air drag
            # Sub-step the movement to avoid tunneling through 1-tile walls at high speed.
            steps = max(1, int(max(abs(d.vx), abs(d.vy)) * dt / (TILE * 0.4)) + 1)
            sdt = dt / steps
            for _ in range(steps):
                # Horizontal
                d.x += d.vx * sdt
                if self.world.is_solid(int(d.x // TILE), int(d.y // TILE)):
                    # Push back to edge of the tile and bounce.
                    if d.vx > 0:
                        d.x = int(d.x // TILE) * TILE - 1
                    else:
                        d.x = (int(d.x // TILE) + 1) * TILE + 1
                    d.vx = -d.vx * 0.35
                    d.bounce_count += 1
                # Vertical
                d.y += d.vy * sdt
                if self.world.is_solid(int(d.x // TILE), int(d.y // TILE)):
                    if d.vy > 0:
                        d.y = int(d.y // TILE) * TILE - 1
                    else:
                        d.y = (int(d.y // TILE) + 1) * TILE + 1
                    d.vy = -d.vy * 0.30
                    d.vx *= 0.6  # friction on landing
                    d.bounce_count += 1
            # Auto-pickup by player after the pickup delay expires.
            if d.pickup_delay <= 0:
                pdx = d.x - p.x
                pdy = d.y - (p.y - p.h * 0.5)
                if pdx*pdx + pdy*pdy < (1.6 * TILE) ** 2:
                    leftover = self.inventory.add(d.item_id, d.count, d.durability)
                    if leftover == 0:
                        self._float_at(f"+{d.count} {get_item_name(d.item_id)}",
                                       d.x, d.y - 8, (255, 230, 130))
                        play_sound("pickup", 0.3)
                        continue  # picked up; don't keep
                    else:
                        d.count = leftover  # partial pickup; keep the remainder
            # Cull expired items
            if d.life > 0:
                keep.append(d)
            else:
                self._spawn_particles(d.x, d.y, 3, get_item_color(d.item_id), speed=40, life=0.4)
        self.dropped_items = keep

    def _draw_dropped_items(self):
        """Draw all thrown/dropped items as small floating icons."""
        for d in self.dropped_items:
            sx = int(d.x - self.cam_x)
            sy = int(d.y - self.cam_y)
            # Bobbing animation based on life timer
            bob = math.sin(d.life * 4.0) * 1.5
            sy += int(bob)
            # Draw a small shadow ellipse below the item
            pygame.draw.ellipse(self.screen, (0, 0, 0, 80), (sx - 6, sy + 6, 12, 4))
            # Draw the item icon (16x16 scaled from the source texture/icon)
            icon = None
            if is_tool(d.item_id) or is_weapon(d.item_id) or is_ammo(d.item_id):
                icon = self.tool_icons.get(d.item_id)
            elif is_food(d.item_id) or is_misc(d.item_id):
                icon = self.item_icons.get(d.item_id)
            elif is_armor(d.item_id):
                icon = self.tool_icons.get(d.item_id)  # armor icons are stored in tool_icons
            else:
                icon = self.block_textures.get(d.item_id)
            if icon:
                self.screen.blit(pygame.transform.scale(icon, (16, 16)), (sx - 8, sy - 8))
            else:
                # Fallback: colored square
                col = get_item_color(d.item_id)
                pygame.draw.rect(self.screen, col, (sx - 6, sy - 6, 12, 12))
            # Count badge if >1
            if d.count > 1:
                ct = self.font_sm.render(str(d.count), True, (255, 255, 255))
                self.screen.blit(ct, (sx + 4, sy + 2))

    def _debug_give_all(self):
        """Toggle debug/creative mode on/off."""
        if self.creative_mode:
            # Turn OFF: remove all items that were added
            self._remove_debug_items()
            self.creative_mode = False
            self._toast("Creative mode OFF", 2.0)
        else:
            self.creative_mode = True
            self.creative_snapshot = self._snapshot_inventory()
            self._toast("Creative mode ON - all items accessible via inventory", 3.0)

    def _snapshot_inventory(self):
        """Take a snapshot of current inventory state for restoring later."""
        snap = []
        for s in self.inventory.slots:
            if s:
                snap.append((s.item_id, s.count, s.durability))
            else:
                snap.append(None)
        return snap

    def _remove_debug_items(self):
        """Remove all items that were added during creative mode."""
        if not hasattr(self, 'creative_snapshot') or not self.creative_snapshot:
            # Fallback: just clear inventory
            self.inventory.slots = [None] * len(self.inventory.slots)
            return
        # Restore to the snapshot taken when creative was enabled
        self.inventory.held = None
        for i, entry in enumerate(self.creative_snapshot):
            if i < len(self.inventory.slots):
                if entry:
                    self.inventory.slots[i] = ItemStack(entry[0], entry[1], entry[2])
                else:
                    self.inventory.slots[i] = None
        self.creative_snapshot = None

    # ---------- update ----------
    def _damage_player(self, dmg, invuln_time=0.8, cause="Enemy"):
        """Apply damage to player, skipping in creative mode."""
        if self.creative_mode:
            return
        self.player.health -= dmg
        self.player.invuln = invuln_time
        self.death_cause = cause

    def _update(self, dt):
        self._update_time(dt)
        # Fixed-timestep physics: accumulate time, step at 60 Hz for consistent behavior
        PHYSICS_DT = 1.0 / 60.0
        self._physics_accum += dt
        steps = 0
        while self._physics_accum >= PHYSICS_DT and steps < 5:
            # Collision must never run against a lazy, missing column. The normal
            # generator is camera-budgeted and runs later in this method, which
            # allowed a fresh spawn (or a fast-moving player) to fall into AIR.
            self._ensure_player_collision_area()
            self._update_player(PHYSICS_DT)
            self._physics_accum -= PHYSICS_DT
            steps += 1
        if self._physics_accum > PHYSICS_DT * 5:
            self._physics_accum = 0  # prevent spiral of death
        # Lazy world generation: ensure columns near the player are generated
        self._ensure_world_generated()
        if not self.inventory_open and not self.map_open and not self.workbench_open and not self.station_open and not self.chest_open:
            self._update_mining_building()
            # Use fixed step for mining to be FPS-independent
            mine_dt = min(dt, PHYSICS_DT)
            self._process_mining(mine_dt)
        else:
            self.player.mine_target = None; self.player.mine_progress = 0.0
        # Update hunger and water (slower drain: ~3 meals/day when full)
        p = self.player
        # Hunger and water drain (not in creative)
        if not self.creative_mode:
            p.hunger = max(0, p.hunger - dt * 0.055)  # ~100/(0.055*3600) ≈ 30 min to empty
            if p.in_water:
                p.water = min(p.max_water, p.water + dt * 8)  # refill in water
            else:
                p.water = max(0, p.water - dt * 0.07)  # ~100/(0.07*3600) ≈ 24 min to empty
        else:
            p.hunger = p.max_hunger
            p.water = p.max_water
        # Low hunger/water damages player (not in creative)
        if not self.creative_mode:
            if p.hunger <= 0:
                self.death_cause = "Starvation"
                p.health = max(0, p.health - dt * 2)
            if p.water <= 0:
                self.death_cause = "Dehydration"
                p.health = max(0, p.health - dt * 3)
        # Running drains hunger slightly faster (not in creative)
        if not self.creative_mode and abs(p.vx) > MOVE_SPEED * 0.8:
            p.hunger = max(0, p.hunger - dt * 0.05)
        # Grow seedlings after 7+ game days
        self._update_seedlings()
        self._update_camera(dt)
        ent_dt = min(dt, PHYSICS_DT)  # cap entity updates for consistency
        self._update_enemies(ent_dt); self._update_animals(ent_dt)
        self._update_arrows(dt)
        self._update_dropped_items(dt)
        self._update_particles(dt); self._update_floats(dt)
        self._update_liquids(dt)
        self._update_exploration()
        # Furnace cooking (only when furnace UI is open)
        if self.station_open and self.active_station == "furnace":
            self._update_furnace(dt)
        # Lighting every 4 frames for performance (was every 2)
        if not hasattr(self, '_light_frame'): self._light_frame = 0
        self._light_frame += 1
        # Only recompute if camera moved significantly or on scheduled frame
        cam_moved = False
        if not hasattr(self, '_last_light_cam_x'): self._last_light_cam_x = -9999; self._last_light_cam_y = -9999
        if abs(self.cam_x - self._last_light_cam_x) > TILE * 4 or abs(self.cam_y - self._last_light_cam_y) > TILE * 4:
            cam_moved = True
        if self._light_frame % 4 == 0 or cam_moved:
            self._compute_lighting()
            self._last_light_cam_x = self.cam_x
            self._last_light_cam_y = self.cam_y
        self._update_weather(dt)
        # Decrement map drag grace counter each frame
        if self._map_drag_grace > 0:
            self._map_drag_grace -= 1

    def _update_liquids(self, dt):
        """Fixed-step liquid simulation so flow speed doesn't depend on framerate."""
        self._liquid_accum += dt
        steps = 0
        while self._liquid_accum >= LIQUID_TICK and steps < 4:
            self._liquid_accum -= LIQUID_TICK
            obsidian_spots = self.world.simulate_liquids()
            for ox, oy in obsidian_spots:
                self._spawn_particles(ox*TILE+TILE/2, oy*TILE+TILE/2, 10, (200, 200, 220), speed=90, life=0.5)
                self._spawn_particles(ox*TILE+TILE/2, oy*TILE+TILE/2, 4, (255, 255, 255), speed=40, life=0.3)
            steps += 1

    def _ensure_player_collision_area(self):
        """Synchronously make a narrow solid-generation safety strip for physics.

        Rendering can remain time-budgeted, but the player and the tiles directly
        beneath them must be generated before collision is evaluated. This prevents
        new worlds from developing a vertical void when camera generation lags.
        """
        player_x = max(0, min(self.world.w - 1, int(self.player.x // TILE)))
        player_depth = int(self.player.y // TILE) + 96
        for x in range(max(0, player_x - 2), min(self.world.w, player_x + 3)):
            # Keep the regular surface generation depth as a minimum so this
            # safety path cannot leave a thin, partially initialized column.
            target_depth = min(self.world.h, max(int(self.world.surface_y[x]) + 200,
                                                 player_depth))
            if x not in self.world.generated_set:
                self.world.generate_column(x, y_end=target_depth)
                self._update_world_surface_at_col(x)
            elif target_depth > self.world.generated_depth.get(x, 0):
                self.world.generate_column(x, y_end=target_depth)

    def _ensure_world_generated(self):
        """Generate columns near the player, using a time budget to avoid lag.
        Generates columns closest to the player first, stops after ~8ms.
        Also extends already-generated columns downward when the player goes
        deep underground (deep-phase generation)."""
        import time as _time
        margin = 20
        x_start = max(0, int((self.cam_x - margin * TILE) // TILE))
        x_end = min(self.world.w, int((self.cam_x + self.screen_w + margin * TILE) // TILE) + 1)
        player_x = int(self.player.x // TILE)
        player_y = int(self.player.y // TILE)

        # Collect ungenerated columns (surface phase)
        columns_to_gen = []
        # Collect columns that need deep-phase extension
        columns_to_extend = []

        for x in range(x_start, x_end):
            if x not in self.world.generated_set:
                columns_to_gen.append(x)
            else:
                # Check if this column needs deep-phase extension
                current_depth = self.world.generated_depth.get(x, 0)
                # Extend if the player (or camera) is below the current generated depth
                needed_depth = min(player_y + 80, self.world.h)
                if needed_depth > current_depth:
                    columns_to_extend.append((x, needed_depth))

        if not columns_to_gen and not columns_to_extend:
            return

        # Sort by distance to player (closest first)
        columns_to_gen.sort(key=lambda x: abs(x - player_x))
        columns_to_extend.sort(key=lambda item: abs(item[0] - player_x))

        # Time-budgeted generation: stop after ~8ms to maintain 60+ FPS
        max_per_frame = 8  # hard cap for new columns
        max_extend = 16    # hard cap for deep extensions (cheaper per column)
        time_budget = 0.008  # 8ms
        t0 = _time.perf_counter()

        # Generate new columns (surface phase)
        for x in columns_to_gen[:max_per_frame]:
            self.world.generate_column(x)
            self._update_world_surface_at_col(x)
            if _time.perf_counter() - t0 > time_budget:
                break

        # Extend existing columns (deep phase)
        for x, needed_depth in columns_to_extend[:max_extend]:
            self.world.generate_column(x, y_end=needed_depth)
            if _time.perf_counter() - t0 > time_budget:
                break

    def _update_time(self, dt):
        prev = self.time
        self.time = (self.time + dt/DAY_LENGTH) % 1.0
        if prev < 0.5 <= self.time:
            self.day_count += 1; self._toast(f"Day {self.day_count}", 2.0)
        if prev < 0.22 <= self.time:
            if self.zombies or self.slimes or self.skeletons or self.demon_eyes or self.bats or self.crabs:
                self.zombies.clear(); self.slimes.clear()
                self.skeletons.clear(); self.demon_eyes.clear()
                self.bats.clear(); self.crabs.clear()
                self._toast("The enemies retreat from the dawn.", 2.0)

    def _day_light_factor(self):
        """Brighter overall: outside is always fully visible at day, dim but visible at night.
        Weather darkens the sky. Lightning provides momentary bright flashes."""
        t = self.time
        base = 0.0
        if t < 0.20 or t > 0.80: base = 0.55  # brighter night
        elif t < 0.30: base = 0.55 + 0.45*(t-0.20)/0.10
        elif t < 0.70: base = 1.0
        else: base = 0.55 + 0.45*(0.80-t)/0.10
        # Weather darkens the sky
        if self.weather_type == "storm":
            base *= 0.6
        elif self.weather_type == "rain":
            base *= 0.75
        elif self.weather_type == "snow":
            base *= 0.85
        # Lightning flash temporarily boosts
        if self.lightning_flash > 0:
            base = min(1.0, base + self.lightning_flash * 1.5)
        return base

    def _is_night(self): return self.time < 0.22 or self.time > 0.78

    def _update_player(self, dt):
        p = self.player; keys = pygame.key.get_pressed()
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        jump = keys[pygame.K_w] or keys[pygame.K_SPACE] or keys[pygame.K_UP]
        target = 0.0
        if left and not right: target = -MOVE_SPEED; p.facing = -1
        elif right and not left: target = MOVE_SPEED; p.facing = 1
        if target != 0:
            accel = AIR_ACCEL if not p.on_ground else AIR_ACCEL*1.5
            if p.vx < target: p.vx = min(target, p.vx+accel*dt)
            elif p.vx > target: p.vx = max(target, p.vx-accel*dt)
        else:
            fric = GROUND_FRICTION if p.on_ground else AIR_FRICTION
            if p.vx > 0: p.vx = max(0, p.vx-fric*dt)
            elif p.vx < 0: p.vx = min(0, p.vx+fric*dt)
        if jump and p.on_ground:
            p.vy = JUMP_VEL; p.on_ground = False
            play_sound("jump", 0.25)
        p.in_water = self._player_in_water()
        if p.in_water:
            p.vy = min(p.vy + GRAVITY*0.35*dt, 220)
            if jump and p.on_ground: p.vy = -180
            elif jump and not p.on_ground: p.vy -= 300*dt
            p.vx *= 0.85 ** (dt * 60)
        else: p.vy = min(p.vy + GRAVITY*dt, MAX_FALL)
        # Capture downward velocity before move so we can detect a hard landing
        # (used for the "land" thud sound when the player hits the ground fast).
        fall_vy_before = p.vy
        self._move_player(dt)
        # --- Water entry / exit splash ---
        if p.in_water and not self._was_in_water:
            play_sound("splash", 0.45)
        # --- Hard landing thud (only on the frame we transition from air → ground) ---
        if p.on_ground and not self._was_on_ground and fall_vy_before > 350:
            # Scale volume by impact speed: 350 px/s = soft, 1000+ px/s = loud
            vol = min(0.6, 0.2 + (fall_vy_before - 350) / 1300.0)
            play_sound("land", vol)
        # --- Footsteps while walking on the ground ---
        if p.on_ground and abs(p.vx) > 30 and not p.in_water:
            # Footstep interval scales inversely with speed (faster walk = quicker steps)
            speed_frac = min(1.0, abs(p.vx) / MOVE_SPEED)
            interval = self.FOOTSTEP_INTERVAL / max(0.5, speed_frac)
            self.footstep_timer += dt
            if self.footstep_timer >= interval:
                self.footstep_timer = 0.0
                self._play_footstep_for_surface()
        else:
            # Reset when airborne / in water so the next step fires immediately on land
            self.footstep_timer = self.FOOTSTEP_INTERVAL * 0.6
        # Track state for next-frame transitions
        self._was_in_water = p.in_water
        self._was_on_ground = p.on_ground
        self._prev_vy = p.vy
        if p.y > self.world.h*TILE+200:
            if not self.creative_mode: self.death_cause = "Fell into the void"; p.health = 0
        # Lava damage (not in creative)
        if not self.creative_mode and self._player_in_lava():
            self.death_cause = "Burned in lava"
            p.health -= 30 * dt  # 30 DPS
            p.vy = min(p.vy + GRAVITY*0.2*dt, 200)  # less buoyancy in lava
            if int(p.invuln * 10) % 2 == 0:
                self._spawn_particles(p.x, p.y - p.h*0.5, 2, (255, 120, 30), speed=60, life=0.4)
        if p.health <= 0:
            if self.creative_mode:
                p.respawn(); self._toast("Respawned", 1.0)
            else:
                self.game_over = True
                self.game_over_timer = 0.0
                p.health = 0
        if p.invuln > 0: p.invuln = max(0, p.invuln-dt)
        if p.attack_cd > 0: p.attack_cd = max(0, p.attack_cd-dt)

    def _play_footstep_for_surface(self):
        """Pick the right footstep sound based on the block the player is standing on.
        Samples the tile just below the player's feet and dispatches to the matching
        surface-variant sound. Falls back to the default dirt/grass footstep."""
        p = self.player
        # Tile directly below the player's center
        tx = int(p.x // TILE)
        ty = int((p.y + 2) // TILE)  # +2 to nudge into the block below the feet
        if not (0 <= tx < self.world.w and 0 <= ty < self.world.h):
            play_sound("footstep", 0.25)
            return
        # Check liquid layer first — if standing in shallow water, play water step
        ltype, lamt = self.world.get_liquid(tx, ty)
        if ltype == LIQUID_WATER and lamt > 0:
            play_sound("footstep_water", 0.3)
            return
        block = self.world.get(tx, ty)
        if block in (STONE, SANDSTONE, LIMESTONE, GRANITE, BASALT, OBSIDIAN, BEDROCK, MARBLE, BRICK):
            play_sound("footstep_stone", 0.28)
        elif block in (SAND,):
            play_sound("footstep_sand", 0.25)
        elif block in (SNOW, ICE):
            play_sound("footstep_snow", 0.25)
        elif block in (PLANK, WOOD, TREE_TRUNK, PINE_TRUNK, TREE_GIANT, TREE_DEAD, TREE_BENT,
                       WORKBENCH, BOOKSHELF, CHEST, FURNACE, ANVIL, CAMPFIRE):
            play_sound("footstep_stone", 0.22)  # wood = harder thud (reuse stone variant)
        else:
            # Default: dirt / grass / mud / generic natural surface
            play_sound("footstep", 0.25)

    def _player_in_water(self):
        p = self.player
        ltype, amt = self.world.get_liquid(int(p.x//TILE), int((p.y-p.h*0.5)//TILE))
        return ltype == LIQUID_WATER and amt >= 32

    def _player_in_lava(self):
        p = self.player
        ltype, amt = self.world.get_liquid(int(p.x//TILE), int((p.y-p.h*0.5)//TILE))
        return ltype == LIQUID_LAVA and amt >= 32

    def _move_player(self, dt):
        p = self.player
        p.x += p.vx*dt; rect = p.rect
        for tx, ty in self._tiles_overlapping(rect):
            if self.world.is_solid(tx, ty):
                tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if rect.colliderect(tr):
                    if p.vx > 0: p.x = tr.left - p.w/2 - 0.01
                    elif p.vx < 0: p.x = tr.right + p.w/2 + 0.01
                    p.vx = 0; rect = p.rect
        p.y += p.vy*dt; p.on_ground = False; rect = p.rect
        for tx, ty in self._tiles_overlapping(rect):
            if self.world.is_solid(tx, ty):
                tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if rect.colliderect(tr):
                    if p.vy > 0: p.y = tr.top - 0.01; p.on_ground = True
                    elif p.vy < 0: p.y = tr.bottom + p.h + 0.01
                    p.vy = 0; rect = p.rect

    @staticmethod
    def _tiles_overlapping(rect):
        x0 = max(0, rect.left//TILE); x1 = rect.right//TILE
        y0 = max(0, rect.top//TILE); y1 = rect.bottom//TILE
        for ty in range(y0, y1+1):
            for tx in range(x0, x1+1): yield tx, ty

    # ---------- mining & building ----------
    def _get_selected_item(self): return self.inventory.slots[self.selected]
    def _get_selected_tool(self):
        item = self._get_selected_item()
        if item and is_tool(item.item_id): return item
        return None

    def _update_mining_building(self):
        p = self.player; mx, my = pygame.mouse.get_pos()
        wx, wy = mx + self.cam_x, my + self.cam_y
        tx, ty = int(wx//TILE), int(wy//TILE)
        dist = math.hypot(wx - p.x, wy - (p.y - p.h*0.5))
        in_reach = dist <= REACH
        tool = self._get_selected_tool()
        # Bow shooting
        if self.mouse_down_left and in_reach:
            item = self._get_selected_item()
            if item and is_weapon(item.item_id) and item.item_id == BOW:
                if self.player.attack_cd <= 0 and self.inventory.count(ARROW) > 0:
                    self._shoot_arrow(wx, wy, item)
                return
        if self.mouse_down_left and in_reach:
            item = self._get_selected_item()
            # If holding a placeable block, try to place it instead of mining
            if (item and is_block(item.item_id) and item.item_id != AIR
                and not is_tool(item.item_id) and not is_weapon(item.item_id)
                and not is_ammo(item.item_id) and not is_food(item.item_id)
                and not is_misc(item.item_id) and item.count > 0):
                self._try_place(tx, ty)
                return  # Don't mine while trying to place
            block = self.world.get(tx, ty); d = BLOCK_DEFS.get(block, BLOCK_DEFS[AIR])
            # Instantly collect blocks marked collect_lclick (grass tufts, bushes)
            if d.get("collect_lclick"):
                self._collect_block(tx, ty, block)
                return
            # Normal mining
            wall = self.world.get_wall(tx, ty)
            if tool and TOOL_DEFS[tool.item_id]["type"] == "hammer" and block == AIR and wall != WALL_NONE:
                if p.mine_target != (tx,ty) or not p.mine_is_wall:
                    p.mine_target = (tx,ty); p.mine_progress = 0.0; p.mine_is_wall = True
            elif d["mineable"]:
                if p.mine_target != (tx,ty) or p.mine_is_wall:
                    p.mine_target = (tx,ty); p.mine_progress = 0.0; p.mine_is_wall = False
            else:
                p.mine_target = None; p.mine_progress = 0.0
            self._maybe_attack(wx, wy, tool)
        else:
            p.mine_target = None; p.mine_progress = 0.0
        # Right click: collect small stones / berry fruits (placing moved to left click)
        if self.mouse_down_right and in_reach:
            block = self.world.get(tx, ty)
            d = BLOCK_DEFS.get(block, BLOCK_DEFS[AIR])
            if d.get("collect_rclick"):
                self._collect_block_rclick(tx, ty, block)
            elif block == BUSH_FRUIT:
                self._collect_fruit(tx, ty)

    def _collect_block(self, tx, ty, block):
        """Instantly collect a block (left-click collectables like grass tufts, bushes)."""
        d = BLOCK_DEFS[block]
        drop = d.get("drops")
        if drop is not None:
            self._drop_item_at(tx * TILE + TILE // 2, ty * TILE, drop, 1)
        # TALL_GRASS / DRIED_TALL_GRASS: 2-tile vertical - destroy both halves
        if block in (TALL_GRASS, DRIED_TALL_GRASS):
            if ty - 1 >= 0 and self.world.get(tx, ty - 1) == block:
                self.world.set(tx, ty - 1, AIR)
                self._update_world_surface_at(tx, ty - 1)
            if ty + 1 < self.world.h and self.world.get(tx, ty + 1) == block:
                self.world.set(tx, ty + 1, AIR)
                self._update_world_surface_at(tx, ty + 1)
        self.world.set(tx, ty, AIR)
        self._update_world_surface_at(tx, ty)
        self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 5, d["color"], speed=60, life=0.3)

    def _collect_block_rclick(self, tx, ty, block):
        """Collect a block via right-click (small stones)."""
        d = BLOCK_DEFS[block]
        drop = d.get("drops")
        if drop is not None:
            self._drop_item_at(tx * TILE + TILE // 2, ty * TILE, drop, 1)
        self.world.set(tx, ty, AIR)
        self._update_world_surface_at(tx, ty)
        self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 5, d["color"], speed=60, life=0.3)

    def _collect_fruit(self, tx, ty):
        """Collect fruit from a berry bush, converting it to a regular bush."""
        # Drop berries as world items
        self._drop_item_at(tx * TILE + TILE // 2, ty * TILE, BERRY, 2)
        # Convert berry bush to regular bush
        self.world.set(tx, ty, BUSH)
        self._update_world_surface_at(tx, ty)
        self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 4, (200, 40, 50), speed=50, life=0.4)

    def _shoot_arrow(self, wx, wy, bow_item):
        self.player.attack_cd = 0.5
        self.inventory.remove(ARROW, 1)
        px = self.player.x; py = self.player.y - self.player.h * 0.5
        dx = wx - px; dy = wy - py
        dist = math.hypot(dx, dy)
        if dist < 1: return
        speed = 600
        vx = dx / dist * speed; vy = dy / dist * speed
        self.arrows.append(Arrow(x=px, y=py, vx=vx, vy=vy, damage=WEAPON_DEFS[BOW]["damage"]))
        play_sound("bow_shoot", 0.4)
        bow_item.durability -= 1
        if bow_item.durability <= 0:
            self._toast("Bow broke!", 2.0); self.inventory.slots[self.selected] = None
            play_sound("break_tool", 0.5)

    def _maybe_attack(self, wx, wy, tool):
        p = self.player
        if p.attack_cd > 0: return
        damage = TOOL_DEFS[tool.item_id]["damage"] if tool else 2
        for s in self.slimes:
            if s.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                s.health -= damage; p.attack_cd = 0.35
                # Mining-hit sound intentionally disabled.
                dx = s.x - p.x
                if dx != 0: s.vx = math.copysign(180 + damage*5, dx)
                s.vy = -200
                self._float_at(f"-{damage}", s.x, s.y-s.h, (255,80,80))
                self._spawn_particles(s.x, s.y-s.h*0.5, 8, s.color)
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return
        for z in self.zombies:
            if z.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                z.health -= damage; p.attack_cd = 0.35
                # Mining-hit sound intentionally disabled.
                dx = z.x - p.x
                if dx != 0: z.vx = math.copysign(150 + damage*5, dx)
                z.vy = -200
                self._float_at(f"-{damage}", z.x, z.y-z.h, (255,80,80))
                self._spawn_particles(z.x, z.y-z.h*0.5, 8, z.color)
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return
        for sk in self.skeletons:
            if sk.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                sk.health -= damage; p.attack_cd = 0.35
                # Mining-hit sound intentionally disabled.
                dx = sk.x - p.x
                if dx != 0: sk.vx = math.copysign(160 + damage*5, dx)
                sk.vy = -200
                self._float_at(f"-{damage}", sk.x, sk.y-sk.h, (255,80,80))
                self._spawn_particles(sk.x, sk.y-sk.h*0.5, 8, sk.color)
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return
        for de in self.demon_eyes:
            if de.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                de.health -= damage; p.attack_cd = 0.35
                # Mining-hit sound intentionally disabled.
                dx = de.x - p.x
                if dx != 0: de.vx = math.copysign(140 + damage*5, dx)
                de.vy = -200
                self._float_at(f"-{damage}", de.x, de.y-de.h, (255,80,80))
                self._spawn_particles(de.x, de.y-de.h*0.5, 8, de.color)
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return
        for fi in self.fish:
            if fi.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                fi.health -= damage; p.attack_cd = 0.35
                # Mining-hit sound intentionally disabled.
                dx = fi.x - p.x
                if dx != 0: fi.vx = math.copysign(80 + damage*3, dx)
                self._float_at(f"-{damage}", fi.x, fi.y-fi.h, (255,80,80))
                self._spawn_particles(fi.x, fi.y-fi.h*0.5, 5, fi.color)
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return
        for b in self.bats:
            if b.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                b.health -= damage; p.attack_cd = 0.35
                # Mining-hit sound intentionally disabled.
                dx = b.x - p.x
                if dx != 0: b.vx = math.copysign(120 + damage*4, dx)
                b.vy = -150
                self._float_at(f"-{damage}", b.x, b.y-b.h, (255,80,80))
                self._spawn_particles(b.x, b.y-b.h*0.5, 5, b.color)
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return
        for c in self.crabs:
            if c.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                c.health -= damage; p.attack_cd = 0.35
                # Mining-hit sound intentionally disabled.
                dx = c.x - p.x
                if dx != 0: c.vx = math.copysign(130 + damage*4, dx)
                c.vy = -150
                self._float_at(f"-{damage}", c.x, c.y-c.h, (255,80,80))
                self._spawn_particles(c.x, c.y-c.h*0.5, 6, c.color)
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return
        # Try animals (passive creatures)
        for a in self.animals:
            if a.rect.collidepoint(wx, wy):
                play_sound("sword_swing", 0.4)
                self._damage_animal(a, damage); p.attack_cd = 0.35
                dx = a.x - p.x
                if dx != 0: a.vx = math.copysign(180, dx)
                a.vy = -200
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        play_sound("break_tool", 0.45)
                        self.inventory.slots[self.selected] = None
                return

    def _try_place(self, tx, ty):
        p = self.player; item = self._get_selected_item()
        if not item or is_tool(item.item_id) or is_weapon(item.item_id) or is_ammo(item.item_id) or is_food(item.item_id) or item.count <= 0: return
        # Handle tree seed placement
        if item.item_id in SEED_TO_SEEDLING:
            if self.world.get(tx, ty) != AIR: return
            if not self.world.is_solid(tx, ty + 1): return
            tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
            if p.rect.colliderect(tr): return
            seedling = SEED_TO_SEEDLING[item.item_id]
            self.world.set(tx, ty, seedling)
            self._update_world_surface_at(tx, ty)
            play_sound("place", 0.3)
            item.count -= 1
            if item.count <= 0: self.inventory.slots[self.selected] = None
            self._toast("Planted a seed! It will grow in 7 days.", 2.0)
            self.seedlings[(tx, ty)] = {"plant_day": self.day_count, "seedling_type": seedling}
            return
        if is_misc(item.item_id): return
        block = item.item_id
        if not is_block(block) or block == AIR: return
        if self.world.get(tx, ty) != AIR: return
        # Bed needs 2 tiles wide - check the second tile too
        if block == BED and (tx + 1 >= self.world.w or self.world.get(tx + 1, ty) != AIR):
            self._toast("Bed needs 2 tiles of space!", 1.0); return
        tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
        if p.rect.colliderect(tr) and BLOCK_DEFS[block]["solid"]: return
        if block == TORCH:
            wall = self.world.get_wall(tx, ty)
            has_neighbor = any([self.world.is_solid(tx-1,ty), self.world.is_solid(tx+1,ty),
                                self.world.is_solid(tx,ty-1), self.world.is_solid(tx,ty+1),
                                self.world.get(tx-1,ty) != AIR, self.world.get(tx+1,ty) != AIR,
                                self.world.get(tx,ty-1) != AIR, self.world.get(tx,ty+1) != AIR])
            if wall == WALL_NONE and not has_neighbor:
                self._toast("Torch needs a wall or block behind it!", 1.0); return
        else:
            neighbors = [self.world.is_solid(tx-1,ty), self.world.is_solid(tx+1,ty),
                         self.world.is_solid(tx,ty-1), self.world.is_solid(tx,ty+1),
                         self.world.get(tx-1,ty)!=AIR, self.world.get(tx+1,ty)!=AIR,
                         self.world.get(tx,ty-1)!=AIR, self.world.get(tx,ty+1)!=AIR]
            if not any(neighbors) and BLOCK_DEFS[block]["solid"]: return
        self.world.set(tx, ty, block)
        self._update_world_surface_at(tx, ty)
        play_sound("place", 0.4)
        # Multi-tile placement: BED is 2 tiles wide
        if block == BED:
            for dx in range(1, 2):
                ntx = tx + dx
                if ntx < self.world.w and self.world.get(ntx, ty) == AIR:
                    ntr = pygame.Rect(ntx*TILE, ty*TILE, TILE, TILE)
                    if not p.rect.colliderect(ntr):  # don't place where player stands
                        self.world.set(ntx, ty, BED)
                        self._update_world_surface_at(ntx, ty)
        item.count -= 1
        if item.count <= 0: self.inventory.slots[self.selected] = None

    def _process_mining(self, dt):
        p = self.player
        if p.mine_target is None: return
        tx, ty = p.mine_target
        tool = self._get_selected_tool()
        mine_mult = TOOL_DEFS[tool.item_id]["mine_mult"] if tool else 1.0
        if p.mine_is_wall:
            wall = self.world.get_wall(tx, ty)
            if wall == WALL_NONE: p.mine_target = None; p.mine_progress = 0.0; return
            hardness = WALL_HARDNESS.get(wall, 0.5)
            p.mine_progress += dt * mine_mult
            if random.random() < 0.3:
                self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 1, WALL_DEFS[wall]["color"], speed=40, life=0.3)
            if p.mine_progress >= hardness:
                self.world.set_wall(tx, ty, WALL_NONE)
                self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 8, WALL_DEFS[wall]["color"], speed=80, life=0.4)
                p.mine_target = None; p.mine_progress = 0.0
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        # Mining-related audio intentionally disabled.
                        self.inventory.slots[self.selected] = None
        else:
            block = self.world.get(tx, ty); d = BLOCK_DEFS[block]
            if not d["mineable"]:
                p.mine_target = None; p.mine_progress = 0.0; return
            if tool and TOOL_DEFS[tool.item_id]["type"] == "axe" and block in (TREE_TRUNK, PINE_TRUNK, TREE_GIANT, TREE_DEAD, TREE_BENT, WOOD, PLANK, WORKBENCH, BOOKSHELF, CHEST):
                mine_mult *= 1.5
            p.mine_progress += dt * mine_mult
            # Mining hit sound removed at user request (was too repetitive / harsh).
            # Particle feedback is kept so the player still sees progress visually.
            if random.random() < 0.4:
                self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 1, d["color"], speed=40, life=0.3)
            if p.mine_progress >= d["hardness"]:
                # BED: multi-tile handling - check if this is the leftmost tile
                is_bed_leftmost = (block == BED and (tx == 0 or self.world.get(tx - 1, ty) != BED))
                is_bed_continuation = (block == BED and not is_bed_leftmost)
                # Tree self-destruct: MUST happen BEFORE clearing the block to AIR,
                # so _destroy_tree can BFS from the mined block's neighbors
                tree_trunk_blocks = {TREE_TRUNK, PINE_TRUNK, TREE_GIANT, TREE_DEAD, TREE_BENT}
                if block in tree_trunk_blocks:
                    self._destroy_tree(tx, ty, block)
                    # After tree falls, cascade-break unsupported blocks above
                    self._break_block_above(tx, ty)
                else:
                    # Non-tree blocks: clear and drop normally
                    self.world.set(tx, ty, AIR)
                    self._update_world_surface_at(tx, ty)
                    # Cascade: break unsupported blocks above
                    if not is_bed_continuation:
                        self._break_block_above(tx, ty)
                    if is_bed_leftmost:
                        # Also clear continuation tiles to the right
                        for dx in range(1, 2):
                            ntx = tx + dx
                            if ntx < self.world.w and self.world.get(ntx, ty) == BED:
                                self.world.set(ntx, ty, AIR)
                                self._update_world_surface_at(ntx, ty)
                        # Only drop one BED item as a world drop
                        self._drop_item_at(tx * TILE + TILE // 2, ty * TILE, BED, 1)
                    elif not is_bed_continuation and d["drops"] is not None:
                        # TALL_GRASS / DRIED_TALL_GRASS: 2-tile vertical - destroy both halves
                        if block in (TALL_GRASS, DRIED_TALL_GRASS):
                            if ty - 1 >= 0 and self.world.get(tx, ty - 1) == block:
                                self.world.set(tx, ty - 1, AIR)
                                self._update_world_surface_at(tx, ty - 1)
                            if ty + 1 < self.world.h and self.world.get(tx, ty + 1) == block:
                                self.world.set(tx, ty + 1, AIR)
                                self._update_world_surface_at(tx, ty + 1)
                        self._drop_item_at(tx * TILE + TILE // 2, ty * TILE, d["drops"], 1)
                self._spawn_particles(tx*TILE+TILE/2, ty*TILE+TILE/2, 10, d["color"], speed=120, life=0.5)
                # Block-break sound removed at user request (mining audio was unpleasant).
                # Particle burst still gives strong visual feedback that the block broke.
                p.mine_target = None; p.mine_progress = 0.0
                if tool:
                    tool.durability -= 1
                    if tool.durability <= 0:
                        self._toast(f"{TOOL_DEFS[tool.item_id]['name']} broke!", 2.0)
                        # Mining-related audio intentionally disabled.
                        self.inventory.slots[self.selected] = None


    def _update_seedlings(self):
        """Check planted seedlings and grow them into full trees after 7 game days."""
        grown = []
        for (tx, ty), info in self.seedlings.items():
            if self.day_count - info["plant_day"] >= 7:
                if self.world.get(tx, ty) == info["seedling_type"]:
                    self._grow_seedling_into_tree(tx, ty, info["seedling_type"])
                    grown.append((tx, ty))
            elif self.world.get(tx, ty) != info["seedling_type"]:
                grown.append((tx, ty))
        for key in grown:
            self.seedlings.pop(key, None)

    def _grow_seedling_into_tree(self, tx, ty, seedling_type):
        """Grow a seedling into a full tree."""
        trunk_type = SEEDLING_TO_TRUNK.get(seedling_type)
        if trunk_type is None: return
        rng = random.Random(tx * 7919 + ty * 104729 + self.seed)
        if trunk_type == TREE_GIANT:
            height = rng.randint(12, 18)
        elif trunk_type == PINE_TRUNK:
            height = rng.randint(8, 14)
        elif trunk_type == TREE_DEAD:
            height = rng.randint(5, 9)
        elif trunk_type == TREE_BENT:
            height = rng.randint(5, 8)
        else:
            height = rng.randint(6, 12)
        self.world.set(tx, ty, AIR)
        surface_y = ty
        for i in range(height):
            yy = surface_y - i
            if 0 <= yy < self.world.h:
                self.world.set(tx, yy, trunk_type)
        top_y = surface_y - height
        leaf_type_map = {
            TREE_TRUNK: LEAVES, PINE_TRUNK: LEAVES_DARK,
            TREE_GIANT: LEAVES, TREE_DEAD: LEAVES_AUTUMN, TREE_BENT: LEAVES,
        }
        leaf_type = leaf_type_map.get(trunk_type, LEAVES)
        if trunk_type == TREE_GIANT:
            spread, density = 4, 0.85
        elif trunk_type == PINE_TRUNK:
            spread, density = 3, 0.8
        elif trunk_type == TREE_DEAD:
            spread, density = 2, 0.35
        else:
            spread, density = 3, 0.8
        for dy in range(-spread, spread + 1):
            for dx in range(-spread, spread + 1):
                if abs(dx) + abs(dy) <= spread + 1:
                    lx, ly = tx + dx, top_y + dy
                    if 0 <= lx < self.world.w and 0 <= ly < self.world.h:
                        if self.world.get(lx, ly) == AIR:
                            if rng.random() < density:
                                self.world.set(lx, ly, leaf_type)
        for dx in range(-spread - 1, spread + 2):
            nx = tx + dx
            if 0 <= nx < self.world.w:
                self._update_world_surface_at_col(nx)
        self._spawn_particles(tx*TILE+TILE/2, (surface_y - height//2)*TILE, 15, (80, 200, 80), speed=80, life=0.6)
        self._float_at("Your tree has grown!", tx*TILE+TILE/2, surface_y*TILE - 20, (100, 255, 100))

    def _update_camera(self, dt):
        # Camera follows player at native resolution
        zoom = self.game_zoom
        vw = self.screen_w / zoom
        vh = self.screen_h / zoom
        tx = self.player.x - vw/2 + self._zoom_pan_x
        ty = self.player.y - vh/2 + self._zoom_pan_y
        tx = max(0, min(self.world.w*TILE - vw, tx))
        ty = max(0, min(self.world.h*TILE - vh, ty))
        lerp = 1.0 - math.exp(-dt*8.0)
        self.cam_x += (tx - self.cam_x) * lerp
        self.cam_y += (ty - self.cam_y) * lerp

    # ---------- enemies & arrows ----------
    def _total_defense(self):
        total = 0
        for a in self.armor:
            if a and is_armor(a.item_id):
                total += ARMOR_DEFS[a.item_id]["defense"]
        return total

    def _update_enemies(self, dt):
        self.spawn_timer -= dt
        is_night = self._is_night()
        max_enemies = 15 if is_night else 0
        current = len(self.slimes) + len(self.zombies) + len(self.skeletons) + len(self.demon_eyes) + len(self.bats) + len(self.crabs)
        if is_night and self.spawn_timer <= 0 and current < max_enemies:
            self.spawn_timer = 2.5; self._spawn_night_enemy()
        # Slimes
        for s in self.slimes:
            s.vy = min(s.vy + GRAVITY*dt, MAX_FALL); s.jump_cd -= dt
            if s.on_ground and s.jump_cd <= 0:
                dirx = self.player.x - s.x
                s.vx = math.copysign(120, dirx) + random.uniform(-30,30) if abs(dirx) > 4 else random.uniform(-60,60)
                s.vy = -360; s.on_ground = False; s.jump_cd = random.uniform(0.8, 1.8)
            s.x += s.vx*dt; self._collide_enemy_x(s)
            s.y += s.vy*dt; s.on_ground = False; self._collide_enemy_y(s)
            s.vx *= 0.995
            if s.rect.colliderect(self.player.rect) and self.player.invuln <= 0 and not self.creative_mode:
                dmg = max(1, 10 - self._total_defense()); self._damage_player(dmg, cause="Slime")
                play_sound("hurt", 0.5)
                dx = self.player.x - s.x
                if dx != 0: self.player.vx = math.copysign(280, dx)
                self.player.vy = -300
                self._float_at(f"-{dmg}", self.player.x, self.player.y-self.player.h, (255,80,80))
        # Zombies
        for z in self.zombies:
            z.vy = min(z.vy + GRAVITY*dt, MAX_FALL)
            dirx = self.player.x - z.x
            if abs(dirx) > 4:
                target_vx = math.copysign(80, dirx)
                accel = 4 if z.on_ground else 1
                z.vx += (target_vx - z.vx) * accel * dt
            else: z.vx *= 0.9
            if z.on_ground:
                front_x = int((z.x + math.copysign(z.w, dirx)) // TILE)
                foot_y = int(z.y // TILE)
                if self.world.is_solid(front_x, foot_y) or self.world.is_solid(front_x, foot_y - 1):
                    z.vy = -420
            z.x += z.vx*dt; self._collide_enemy_x(z)
            z.y += z.vy*dt; z.on_ground = False; self._collide_enemy_y(z)
            if z.rect.colliderect(self.player.rect) and self.player.invuln <= 0 and not self.creative_mode:
                dmg = max(1, 14 - self._total_defense()); self._damage_player(dmg, cause="Zombie")
                play_sound("hurt", 0.5)
                dx = self.player.x - z.x
                if dx != 0: self.player.vx = math.copysign(320, dx)
                self.player.vy = -300
                self._float_at(f"-{dmg}", self.player.x, self.player.y-self.player.h, (255,80,80))
        # Skeletons — like zombies but faster and can jump more
        for sk in self.skeletons:
            sk.vy = min(sk.vy + GRAVITY*dt, MAX_FALL); sk.jump_cd -= dt
            dirx = self.player.x - sk.x
            if abs(dirx) > 4:
                target_vx = math.copysign(100, dirx)
                sk.vx += (target_vx - sk.vx) * 3 * dt
            else: sk.vx *= 0.9
            if sk.on_ground:
                front_x = int((sk.x + math.copysign(sk.w, dirx)) // TILE)
                foot_y = int(sk.y // TILE)
                if self.world.is_solid(front_x, foot_y) or self.world.is_solid(front_x, foot_y - 1):
                    if sk.jump_cd <= 0:
                        sk.vy = -450; sk.jump_cd = random.uniform(0.5, 1.2)
                elif sk.jump_cd <= 0 and random.random() < 0.02:
                    sk.vy = -380; sk.jump_cd = random.uniform(1.0, 2.0)
            sk.x += sk.vx*dt; self._collide_enemy_x(sk)
            sk.y += sk.vy*dt; sk.on_ground = False; self._collide_enemy_y(sk)
            if sk.rect.colliderect(self.player.rect) and self.player.invuln <= 0 and not self.creative_mode:
                dmg = max(1, 18 - self._total_defense()); self._damage_player(dmg, cause="Skeleton")
                play_sound("hurt", 0.5)
                dx = self.player.x - sk.x
                if dx != 0: self.player.vx = math.copysign(350, dx)
                self.player.vy = -320
                self._float_at(f"-{dmg}", self.player.x, self.player.y-self.player.h, (255,80,80))
        # Demon Eyes — flying enemies that hover toward player
        for de in self.demon_eyes:
            dirx = self.player.x - de.x
            diry = (self.player.y - de.h/2) - de.y
            dist = math.sqrt(dirx*dirx + diry*diry) + 0.01
            speed = 90
            de.vx += (dirx/dist * speed - de.vx) * 2 * dt
            de.vy += (diry/dist * speed - de.vy) * 2 * dt
            de.x += de.vx*dt; de.y += de.vy*dt
            if de.rect.colliderect(self.player.rect) and self.player.invuln <= 0 and not self.creative_mode:
                dmg = max(1, 12 - self._total_defense()); self._damage_player(dmg, cause="Demon Eye")
                play_sound("hurt", 0.5)
                dx = self.player.x - de.x
                if dx != 0: self.player.vx = math.copysign(250, dx)
                self.player.vy = -280
                self._float_at(f"-{dmg}", self.player.x, self.player.y-self.player.h, (255,80,80))
        # Fish — spawn in water, swim around
        self.fish_spawn_timer -= dt
        if len(self.fish) < 8 and self.fish_spawn_timer <= 0:
            self.fish_spawn_timer = random.uniform(3.0, 6.0)
            self._spawn_fish()
        for f in self.fish:
            # Check if still in water
            ftx = int(f.x // TILE)
            fty = int(f.y // TILE)
            liq = self.world.liquid_amount.get(ftx)
            in_water = liq and 0 <= fty < len(liq) and liq[fty] >= 32
            if not in_water:
                f.health = 0  # die if out of water
                continue
            # Swim toward player slowly, or wander
            dirx = self.player.x - f.x
            if abs(dirx) > 3 and random.random() < 0.3:
                f.direction = 1.0 if dirx > 0 else -1.0
            elif random.random() < 0.02:
                f.direction = random.choice([-1.0, 1.0])
            f.vx = f.direction * 60
            f.vy = random.uniform(-20, 20)  # gentle vertical drift
            f.x += f.vx * dt; f.y += f.vy * dt
            # Keep in water bounds
            if f.x < 0 or f.x > self.world.w * TILE: f.health = 0
            if f.rect.colliderect(self.player.rect) and self.player.invuln <= 0 and not self.creative_mode:
                dmg = max(1, 5 - self._total_defense()); self._damage_player(dmg, cause="Fish")
                dx = self.player.x - f.x
                if dx != 0: self.player.vx = math.copysign(100, dx)
        # Bats — spawn underground/caves, fly erratically
        self.bat_spawn_timer -= dt
        is_underground = self._is_player_underground()
        if is_underground and len(self.bats) < 6 and self.bat_spawn_timer <= 0:
            self.bat_spawn_timer = random.uniform(4.0, 8.0)
            self._spawn_bat()
        for b in self.bats:
            b.wander_cd -= dt
            if b.wander_cd <= 0:
                dirx = self.player.x - b.x
                if abs(dirx) > 3:
                    b.vx = math.copysign(random.uniform(80, 160), dirx) + random.uniform(-40, 40)
                else:
                    b.vx = random.uniform(-100, 100)
                b.vy = random.uniform(-120, 60)
                b.wander_cd = random.uniform(0.5, 1.5)
            b.x += b.vx * dt; b.y += b.vy * dt
            b.vy = min(b.vy + GRAVITY * 0.2 * dt, 100)
            if b.x < 0 or b.x > self.world.w * TILE: b.health = 0
            if b.y < 0: b.vy = abs(b.vy)
            if b.rect.colliderect(self.player.rect) and self.player.invuln <= 0 and not self.creative_mode:
                dmg = max(1, 6 - self._total_defense()); self._damage_player(dmg, 0.6, cause="Bat")
                dx = self.player.x - b.x
                if dx != 0: self.player.vx = math.copysign(150, dx)
                self.player.vy = -200
                play_sound("hurt", 0.4)
        # Crabs — spawn near water/coast, walk sideways
        self.crab_spawn_timer -= dt
        if len(self.crabs) < 5 and self.crab_spawn_timer <= 0:
            self.crab_spawn_timer = random.uniform(5.0, 10.0)
            self._spawn_crab()
        for c in self.crabs:
            c.vy = min(c.vy + GRAVITY * dt, MAX_FALL)
            c.walk_cd -= dt
            if c.on_ground and c.walk_cd <= 0:
                c.direction = random.choice([-1.0, 1.0])
                c.vx = c.direction * random.uniform(40, 80)
                c.walk_cd = random.uniform(1.0, 3.0)
            c.x += c.vx * dt
            self._collide_enemy_x(c)
            c.y += c.vy * dt; c.on_ground = False
            self._collide_enemy_y(c)
            if c.x < 0 or c.x > self.world.w * TILE: c.health = 0
            if c.rect.colliderect(self.player.rect) and self.player.invuln <= 0 and not self.creative_mode:
                dmg = max(1, 8 - self._total_defense()); self._damage_player(dmg, cause="Crab")
                dx = self.player.x - c.x
                if dx != 0: self.player.vx = math.copysign(180, dx)
                play_sound("hurt", 0.4)
        # Cull dead/offscreen enemies
        self.slimes = [s for s in self.slimes if s.health > 0 and s.y < self.world.h*TILE+200]
        self.zombies = [z for z in self.zombies if z.health > 0 and z.y < self.world.h*TILE+200]
        self.skeletons = [s for s in self.skeletons if s.health > 0 and s.y < self.world.h*TILE+200]
        self.demon_eyes = [d for d in self.demon_eyes if d.health > 0]
        self.fish = [f for f in self.fish if f.health > 0]
        self.bats = [b for b in self.bats if b.health > 0]
        self.crabs = [c for c in self.crabs if c.health > 0]

    # ---------- animals ----------
    def _update_animals(self, dt):
        """Spawn passive animals during the day, and update their AI."""
        self.animal_spawn_timer -= dt
        is_day = not self._is_night()
        # Cap animal count
        if is_day and self.animal_spawn_timer <= 0 and len(self.animals) < 15:
            self.animal_spawn_timer = 4.0
            self._spawn_animal()
        # At night, animals flee/despawn gradually
        if not is_day:
            for a in self.animals:
                a.wander_cd = 0  # keep moving
        for a in self.animals:
            adef = ANIMAL_DEFS[a.animal_type]
            # Flying animals (butterflies) hover and drift
            if adef["flies"]:
                a.vy = math.sin(pygame.time.get_ticks() * 0.003 + a.x * 0.01) * 30
                a.wander_cd -= dt
                if a.wander_cd <= 0:
                    a.vx = random.uniform(-adef["speed"], adef["speed"])
                    a.wander_cd = random.uniform(1.5, 3.0)
                    a.facing = 1 if a.vx > 0 else -1
                a.x += a.vx * dt; a.y += a.vy * dt
                # Keep within world bounds and above ground
                if a.x < 10 or a.x > self.world.w * TILE - 10: a.vx *= -1
                continue
            # Ground animals - apply gravity
            a.vy = min(a.vy + GRAVITY * dt, MAX_FALL)
            a.wander_cd -= dt
            # Check distance to player for flee behavior
            dist_to_player = abs(a.x - self.player.x)
            if adef["flees"] and dist_to_player < 8 * TILE:
                # Flee away from player
                dirx = a.x - self.player.x
                if abs(dirx) > 2:
                    a.vx = math.copysign(adef["speed"], dirx)
                    a.facing = 1 if a.vx > 0 else -1
            elif a.wander_cd <= 0:
                # Random wander
                if random.random() < 0.5:
                    a.vx = random.uniform(-adef["speed"]*0.4, adef["speed"]*0.4)
                    a.facing = 1 if a.vx > 0 else -1
                else:
                    a.vx = 0
                a.wander_cd = random.uniform(1.5, 4.0)
            # Frogs and all ground animals: jump over obstacles
            if a.on_ground and abs(a.vx) > 5:
                front_x = int((a.x + math.copysign(a.w/2 + 2, a.vx)) // TILE)
                foot_y = int((a.y - 1) // TILE)
                head_y = int((a.y - a.h) // TILE)
                blocked = (self.world.is_solid(front_x, foot_y) or
                           self.world.is_solid(front_x, head_y))
                if blocked:
                    if a.animal_type == ANIMAL_FROG:
                        a.vy = -300  # frogs jump higher
                    else:
                        a.vy = -350  # other animals: clear 1-block obstacles
                    a.on_ground = False
            # Move and collide
            a.x += a.vx * dt; self._collide_animal_x(a)
            a.y += a.vy * dt; a.on_ground = False; self._collide_animal_y(a)
            # Friction
            a.vx *= 0.95 if a.on_ground else 0.99
            # Occasional soft footstep when the animal is walking on the ground.
            # Only plays if the animal is close enough to the player to be audible
            # (avoids a cacophony of off-screen animals stamping around).
            if a.on_ground and abs(a.vx) > 20:
                a.step_timer = getattr(a, 'step_timer', 0.0) - dt
                if a.step_timer <= 0:
                    a.step_timer = random.uniform(0.35, 0.55)
                    if abs(a.x - self.player.x) < 12 * TILE:
                        play_sound("step_animal", 0.15)
        # Remove dead or out-of-bounds animals
        self.animals = [a for a in self.animals if a.health > 0 and a.y < self.world.h*TILE+200]

    def _collide_animal_x(self, a):
        rect = a.rect
        for tx, ty in self._tiles_overlapping(rect):
            if self.world.is_solid(tx, ty):
                tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if rect.colliderect(tr):
                    if a.vx > 0: a.x = tr.left - a.w/2 - 0.01
                    elif a.vx < 0: a.x = tr.right + a.w/2 + 0.01
                    a.vx = 0; rect = a.rect

    def _collide_animal_y(self, a):
        rect = a.rect
        for tx, ty in self._tiles_overlapping(rect):
            if self.world.is_solid(tx, ty):
                tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if rect.colliderect(tr):
                    if a.vy > 0: a.y = tr.top - 0.01; a.on_ground = True
                    elif a.vy < 0: a.y = tr.bottom + a.h + 0.01
                    a.vy = 0; rect = a.rect

    def _spawn_animal(self):
        """Spawn a biome-appropriate animal just off-screen during the day."""
        side = random.choice([-1, 1])
        xw = (self.cam_x - random.uniform(60, 300)) if side == -1 else (self.cam_x + self.screen_w + random.uniform(60, 300))
        tx = max(2, min(self.world.w - 3, int(xw // TILE)))
        # Determine biome at this x
        biome = self.world.biomes[tx]
        # Find animal types that can spawn here
        valid_types = [t for t, d in ANIMAL_DEFS.items() if biome in d["biomes"]]
        if not valid_types: return
        atype = random.choice(valid_types)
        adef = ANIMAL_DEFS[atype]
        sy = self.world.surface_y[tx]
        # Spawn on surface (or in air for butterflies)
        spawn_y = sy * TILE - 5 if not adef["flies"] else (sy - 5) * TILE
        a = Animal(
            animal_type=atype,
            x=tx*TILE + TILE/2,
            y=spawn_y,
            health=adef["health"], max_health=adef["health"],
            color=adef["color"],
            w=TILE*adef["size"][0], h=TILE*adef["size"][1],
        )
        self.animals.append(a)

    def _damage_animal(self, a, damage):
        """Apply damage to an animal, kill if health <= 0, drop loot."""
        a.health -= damage
        adef = ANIMAL_DEFS[a.animal_type]
        self._float_at(f"-{damage}", a.x, a.y - a.h, (255, 80, 80))
        self._spawn_particles(a.x, a.y - a.h * 0.5, 6, adef["color"])
        if a.health <= 0:
            # Drop loot
            for item_id, qty, chance in adef["drops"]:
                if random.random() < chance:
                    self.inventory.add(item_id, qty)
                    self._float_at(f"+{qty} {get_item_name(item_id)}", a.x, a.y - a.h, (255, 230, 130))
            self._spawn_particles(a.x, a.y - a.h*0.5, 12, adef["color"], speed=80, life=0.6)

    def _update_arrows(self, dt):
        for a in self.arrows:
            a.vy += GRAVITY * 0.3 * dt
            a.x += a.vx * dt; a.y += a.vy * dt
            a.life -= dt
            # Check enemy hits
            for s in self.slimes:
                if s.rect.collidepoint(a.x, a.y):
                    s.health -= a.damage
                    self._float_at(f"-{int(a.damage)}", s.x, s.y-s.h, (255,80,80))
                    self._spawn_particles(a.x, a.y, 6, s.color)
                    play_sound("arrow_hit", 0.4)
                    a.life = 0; break
            for z in self.zombies:
                if z.rect.collidepoint(a.x, a.y):
                    z.health -= a.damage
                    self._float_at(f"-{int(a.damage)}", z.x, z.y-z.h, (255,80,80))
                    self._spawn_particles(a.x, a.y, 6, z.color)
                    play_sound("arrow_hit", 0.4)
                    a.life = 0; break
            for sk in self.skeletons:
                if sk.rect.collidepoint(a.x, a.y):
                    sk.health -= a.damage
                    self._float_at(f"-{int(a.damage)}", sk.x, sk.y-sk.h, (255,80,80))
                    self._spawn_particles(a.x, a.y, 6, sk.color)
                    play_sound("arrow_hit", 0.4)
                    a.life = 0; break
            for de in self.demon_eyes:
                if de.rect.collidepoint(a.x, a.y):
                    de.health -= a.damage
                    self._float_at(f"-{int(a.damage)}", de.x, de.y-de.h, (255,80,80))
                    self._spawn_particles(a.x, a.y, 6, de.color)
                    play_sound("arrow_hit", 0.4)
                    a.life = 0; break
            for b in self.bats:
                if b.rect.collidepoint(a.x, a.y):
                    b.health -= a.damage
                    self._float_at(f"-{int(a.damage)}", b.x, b.y-b.h, (255,80,80))
                    self._spawn_particles(a.x, a.y, 4, b.color)
                    play_sound("arrow_hit", 0.4)
                    a.life = 0; break
            for c in self.crabs:
                if c.rect.collidepoint(a.x, a.y):
                    c.health -= a.damage
                    self._float_at(f"-{int(a.damage)}", c.x, c.y-c.h, (255,80,80))
                    self._spawn_particles(a.x, a.y, 5, c.color)
                    play_sound("arrow_hit", 0.4)
                    a.life = 0; break
            # Check tile collision
            if self.world.is_solid(int(a.x//TILE), int(a.y//TILE)):
                play_sound("arrow_thud", 0.3)
                a.life = 0
        self.arrows = [a for a in self.arrows if a.life > 0]

    def _collide_enemy_x(self, e):
        rect = e.rect
        for tx, ty in self._tiles_overlapping(rect):
            if self.world.is_solid(tx, ty):
                tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if rect.colliderect(tr):
                    if e.vx > 0: e.x = tr.left - e.w/2 - 0.01
                    elif e.vx < 0: e.x = tr.right + e.w/2 + 0.01
                    e.vx = 0; rect = e.rect

    def _collide_enemy_y(self, e):
        rect = e.rect
        for tx, ty in self._tiles_overlapping(rect):
            if self.world.is_solid(tx, ty):
                tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if rect.colliderect(tr):
                    if e.vy > 0: e.y = tr.top - 0.01; e.on_ground = True
                    elif e.vy < 0: e.y = tr.bottom + e.h + 0.01
                    e.vy = 0; rect = e.rect

    def _spawn_night_enemy(self):
        side = random.choice([-1, 1])
        xw = (self.cam_x - random.uniform(40, 200)) if side == -1 else (self.cam_x + self.screen_w + random.uniform(40, 200))
        tx = max(2, min(self.world.w - 3, int(xw // TILE)))
        sy = self.world.surface_y[tx]
        r = random.random()
        if r < 0.25:
            self.zombies.append(Zombie(x=tx*TILE+TILE/2, y=sy*TILE-10, color=(110, 160, 100)))
        elif r < 0.50:
            self.slimes.append(Slime(x=tx*TILE+TILE/2, y=sy*TILE-10,
                                     color=random.choice([(90,200,120),(120,180,220),(200,120,180)])))
        elif r < 0.70:
            self.skeletons.append(Skeleton(x=tx*TILE+TILE/2, y=sy*TILE-10))
        else:
            self.demon_eyes.append(DemonEye(x=tx*TILE+TILE/2, y=sy*TILE-20))

    def _spawn_fish(self):
        """Spawn a fish in a nearby water body."""
        side = random.choice([-1, 1])
        xw = (self.cam_x - random.uniform(40, 150)) if side == -1 else (self.cam_x + self.screen_w + random.uniform(40, 150))
        tx = max(2, min(self.world.w - 3, int(xw // TILE)))
        # Find water surface at this x
        liq_col = self.world.liquid_amount.get(tx)
        if not liq_col: return
        sy = self.world.surface_y[tx]
        for check_y in range(max(0, sy - 3), min(self.world.h, sy + 50)):
            if liq_col[check_y] >= 32:
                # Found water — spawn fish here
                fish_colors = [(80, 150, 220), (60, 180, 200), (100, 130, 190), (70, 200, 180)]
                self.fish.append(Fish(
                    x=tx*TILE+TILE/2,
                    y=check_y*TILE+TILE/2,
                    color=random.choice(fish_colors),
                    direction=random.choice([-1.0, 1.0]),
                ))
                return

    def _spawn_bat(self):
        """Spawn a bat near the player when underground."""
        side = random.choice([-1, 1])
        xw = (self.cam_x - random.uniform(20, 100)) if side == -1 else (self.cam_x + self.screen_w + random.uniform(20, 100))
        tx = max(2, min(self.world.w - 3, int(xw // TILE)))
        ptx = int(self.player.x // TILE)
        pty = int(self.player.y // TILE)
        # Find a spawn point in nearby cave space (AIR underground)
        for attempt in range(20):
            stx = tx + random.randint(-5, 5)
            sty = pty + random.randint(-10, 10)
            if 0 <= stx < self.world.w and 0 <= sty < self.world.h:
                if not self.world.is_solid(stx, sty) and not self.world.is_solid(stx, sty - 1):
                    bat_colors = [(80, 60, 100), (60, 40, 80), (100, 70, 120), (50, 50, 70)]
                    self.bats.append(Bat(
                        x=stx*TILE+TILE/2, y=sty*TILE+TILE/2,
                        color=random.choice(bat_colors),
                    ))
                    return

    def _spawn_crab(self):
        """Spawn a crab near water on the surface."""
        side = random.choice([-1, 1])
        xw = (self.cam_x - random.uniform(40, 150)) if side == -1 else (self.cam_x + self.screen_w + random.uniform(40, 150))
        tx = max(2, min(self.world.w - 3, int(xw // TILE)))
        sy = self.world.surface_y[tx]
        # Check for nearby water (within 10 tiles)
        has_water = False
        for check_x in range(max(0, tx - 10), min(self.world.w, tx + 10)):
            liq_col = self.world.liquid_amount.get(check_x)
            if liq_col:
                for check_y in range(max(0, sy - 3), min(self.world.h, sy + 5)):
                    if liq_col[check_y] >= 32:
                        has_water = True; break
            if has_water: break
        if has_water:
            crab_colors = [(200, 120, 60), (180, 100, 50), (220, 140, 80), (160, 90, 40)]
            self.crabs.append(Crab(
                x=tx*TILE+TILE/2, y=sy*TILE-6,
                color=random.choice(crab_colors),
                direction=random.choice([-1.0, 1.0]),
            ))

    def _spawn_particles(self, x, y, n, color, speed=100, life=0.5):
        for _ in range(n):
            ang = random.uniform(0, math.tau); spd = random.uniform(speed*0.3, speed)
            self.particles.append(Particle(x=x, y=y, vx=math.cos(ang)*spd, vy=math.sin(ang)*spd-40,
                                           life=life, max_life=life, color=color, size=random.uniform(1.5,3.5)))

    def _update_particles(self, dt):
        for p in self.particles:
            p.vy += GRAVITY*0.4*dt; p.x += p.vx*dt; p.y += p.vy*dt; p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0]

    def _update_floats(self, dt):
        for f in self.floats:
            f["t"] -= dt
            if "x" in f: f["y"] -= 30*dt
        self.floats = [f for f in self.floats if f["t"] > 0]

    def _update_exploration(self):
        """Reveal an exact circular area around the player without square chunks."""
        px, py = int(self.player.x//TILE), int(self.player.y//TILE)
        r = 8
        cs = self.explored_chunk_size
        changed = False
        for ty in range(py - r, py + r + 1):
            for tx in range(px - r, px + r + 1):
                if (tx - px)**2 + (ty - py)**2 <= r*r and 0 <= tx < self.world.w and 0 <= ty < self.world.h:
                    cell = (tx // cs, ty // cs)
                    if cell not in self.explored_chunks:
                        self.explored_chunks.add(cell)
                        changed = True
        if changed:
            self._exploration_revision += 1
            self._exploration_mask_cache = None
            self._darkness_cache_key = None
            self._minimap_dirty = True

    # ---------- weather ----------
    def _update_weather_state(self):
        """Set weather based on current biome and randomness."""
        player_tx = int(self.player.x // TILE)
        biome = int(self.world.biomes[min(max(0, player_tx), self.world.w - 1)])
        # Biome-appropriate weather weights
        if biome == BIOME_TUNDRA:
            weights = [("clear", 0.25), ("snow", 0.50), ("storm", 0.25)]
        elif biome == BIOME_DESERT:
            weights = [("clear", 0.80), ("storm", 0.20)]  # sandstorm
        elif biome == BIOME_JUNGLE:
            weights = [("clear", 0.30), ("rain", 0.45), ("storm", 0.25)]
        elif biome == BIOME_SEA:
            weights = [("clear", 0.25), ("rain", 0.40), ("storm", 0.35)]
        else:  # grassland, forest, savanna
            weights = [("clear", 0.45), ("rain", 0.35), ("snow", 0.05), ("storm", 0.15)]
        # Weighted random choice
        r = random.random()
        cumulative = 0.0
        for wtype, weight in weights:
            cumulative += weight
            if r < cumulative:
                self.weather_type = wtype
                break
        else:
            self.weather_type = "clear"
        # Set wind
        self.weather_wind = random.uniform(-0.6, 0.6)
        if self.weather_type == "storm":
            self.weather_wind = random.choice([-1, 1]) * random.uniform(0.5, 1.0)

    def _is_player_underground(self):
        """Check if the player is below the surface (underground)."""
        player_tile_x = int(self.player.x // TILE)
        player_tile_x = max(0, min(player_tile_x, self.world.w - 1))
        surface_at_player = int(self.world.surface_y[player_tile_x])
        player_tile_y = int(self.player.y // TILE)
        return player_tile_y > surface_at_player + 5  # 5-tile buffer below surface

    def _update_weather(self, dt):
        """Update weather timer, spawn/despawn weather particles.
        Weather changes at most ONCE per day. The weather is set at dawn
        and persists for the entire day until the next dawn."""
        # Check if a new day has started — update weather once per day
        current_day = self.day_count
        if current_day != self.weather_day:
            self.weather_day = current_day
            self._update_weather_state()
        
        # Lightning for storms
        if self.weather_type == "storm":
            self.lightning_timer -= dt
            if self.lightning_timer <= 0:
                self.lightning_flash = 0.3  # flash duration
                self.lightning_timer = random.uniform(3, 12)
                # Lightning crack sound - only audible when above ground (underground
                # would muffle it). Slight random delay simulates sound travel time
                # from the strike to the player.
                if not self._is_player_underground():
                    play_sound("lightning", 0.5)
        if self.lightning_flash > 0:
            self.lightning_flash = max(0, self.lightning_flash - dt)
        
        # Only spawn and update weather particles when player is above ground
        underground = self._is_player_underground()

        # Rain/storm ambient sound
        if not underground and self.weather_type in ("rain", "storm") and _SOUNDS_ENABLED:
            rain_snd = _SOUNDS.get("rain")
            if rain_snd:
                ch = rain_snd.play(loops=-1)
                if ch:
                    ch.set_volume(0.25 if self.weather_type == "storm" else 0.15)
        else:
            # Stop rain sound when clear/underground
            rain_snd = _SOUNDS.get("rain") if _SOUNDS_ENABLED else None
            if rain_snd:
                rain_snd.stop()

        # Spawn weather particles (only when above ground)
        if not underground:
            if self.weather_type in ("rain", "storm"):
                # Spawn rate proportional to intensity
                spawn_rate = 12 if self.weather_type == "storm" else 6
                for _ in range(spawn_rate):
                    x = random.uniform(-20, VIEW_W + 20)
                    y = random.uniform(-40, -5)
                    speed = random.uniform(500, 700) if self.weather_type == "storm" else random.uniform(350, 500)
                    wind = self.weather_wind * random.uniform(80, 200)
                    self.weather_particles.append({
                        "x": x, "y": y, "vx": wind, "vy": speed,
                        "type": "rain", "life": random.uniform(1.0, 2.5),
                    })
            elif self.weather_type == "snow":
                for _ in range(3):
                    x = random.uniform(-20, VIEW_W + 20)
                    y = random.uniform(-30, -5)
                    speed = random.uniform(40, 90)
                    wind = self.weather_wind * random.uniform(20, 60)
                    self.weather_particles.append({
                        "x": x, "y": y, "vx": wind, "vy": speed,
                        "type": "snow", "life": random.uniform(3.0, 8.0),
                        "wobble": random.uniform(1.5, 4.0),  # horizontal wobble frequency
                        "wobble_amp": random.uniform(15, 40),  # horizontal wobble amplitude
                    })
        
        # Update existing weather particles
        keep = []
        for p in self.weather_particles:
            p["life"] -= dt
            if p["life"] <= 0:
                continue
            if p["type"] == "snow":
                # Snow wobbles horizontally
                wobble_dx = math.sin(pygame.time.get_ticks() * 0.001 * p["wobble"]) * p["wobble_amp"] * dt
                p["x"] += p["vx"] * dt + wobble_dx
            else:
                p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            # Check if particle hit a solid tile (rain/snow stops at ground)
            wx = int((p["x"] + self.cam_x) // TILE)
            wy = int((p["y"] + self.cam_y) // TILE)
            if self.world.is_solid(wx, wy):
                # Splash particle for rain
                if p["type"] == "rain" and random.random() < 0.3:
                    self._spawn_particles(p["x"] + self.cam_x, p["y"] + self.cam_y, 
                                         2, (150, 180, 220), speed=30, life=0.2)
                continue  # particle absorbed
            # Kill particles that have gone below the surface (underground)
            if 0 <= wx < self.world.w:
                surface_at_x = int(self.world.surface_y[wx])
                if wy > surface_at_x:
                    continue  # particle is underground, remove it
            # Keep if still on screen
            if p["y"] < VIEW_H + 10 and -20 < p["x"] < VIEW_W + 20:
                keep.append(p)
        self.weather_particles = keep[-600:]  # cap particle count

    def _draw_weather(self):
        """Draw rain drops and snow flakes. Skips rendering when player is underground."""
        # Don't draw weather effects if the player is underground
        if self._is_player_underground():
            # Still clear any remaining particles so they don't accumulate
            self.weather_particles.clear()
            return
        for p in self.weather_particles:
            sx, sy = int(p["x"]), int(p["y"])
            if p["type"] == "rain":
                # Rain: short diagonal line
                end_x = sx + int(self.weather_wind * 3)
                end_y = sy + 8
                alpha = min(200, int(150 * min(1.0, p["life"])))
                color = (140, 170, 220)
                pygame.draw.line(self.screen, color, (sx, sy), (end_x, end_y), 1)
            elif p["type"] == "snow":
                # Snow: small white dot
                alpha = min(220, int(180 * min(1.0, p["life"])))
                size = random.choice([1, 1, 2])
                color = (230, 235, 245)
                pygame.draw.circle(self.screen, color, (sx, sy), size)
        
        # Lightning flash overlay
        if self.lightning_flash > 0:
            flash_surf = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
            flash_alpha = int(120 * (self.lightning_flash / 0.3))
            flash_surf.fill((255, 255, 255, flash_alpha))
            self.screen.blit(flash_surf, (0, 0))

    # ---------- lighting ----------
    def _compute_lighting(self):
        """Improved lighting with flood-fill propagation for realistic light bleeding
        through open spaces. Light flows from sky, torches, lava, and the player,
        spreading through air and weakening over distance through solid blocks."""
        W = VIEW_W
        H = VIEW_H
        x0 = max(0, int(self.cam_x//TILE)); x1 = min(self.world.w, int((self.cam_x+W)//TILE)+1)
        y0 = max(0, int(self.cam_y//TILE)); y1 = min(self.world.h, int((self.cam_y+H)//TILE)+1)
        day = self._day_light_factor()
        w = x1 - x0; h = y1 - y0
        light = np.zeros((h, w), dtype=np.float32)
        depth_below = np.zeros((h, w), dtype=np.float32)

        # Sky light: tiles above first opaque block are fully lit
        for x in range(x0, x1):
            sh = int(self.world.sky_heights[x])
            row_start = max(0, y0)
            row_end = min(y1, sh)
            if row_end > row_start:
                light[row_start - y0:row_end - y0, x - x0] = day
            # Depth below surface
            for y in range(max(y0, sh), y1):
                depth_below[y - y0, x - x0] = min(1.0, (y - sh) / 200.0)

        # --- Flood-fill light propagation from sky into caves ---
        # Light bleeds into open air below the surface, dimming with distance
        max_propagation = 8  # max tiles light travels from sky into ground
        queue = deque()
        visited = set()
        # Seed the queue: for each column, the first air tile below sky height
        for x in range(x0, x1):
            sh = int(self.world.sky_heights[x])
            for y in range(max(y0, sh), min(y0 + h, sh + max_propagation)):
                lx, ly = x - x0, y - y0
                if 0 <= lx < w and 0 <= ly < h:
                    tile = self.world.get(x, y)
                    if tile == AIR and light[ly, lx] < 0.01:
                        dist_from_sky = y - sh
                        if dist_from_sky < max_propagation:
                            sky_light = day * max(0, 1.0 - dist_from_sky / max_propagation)
                            if sky_light > 0.05:
                                light[ly, lx] = sky_light
                                queue.append((x, y, sky_light))
                                visited.add((x, y))
        # BFS flood fill
        air_atten = 0.82  # light attenuation per tile of air
        solid_atten = 0.45  # light attenuation per solid tile
        while queue:
            cx, cy, cur_light = queue.popleft()
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                nx, ny = cx+dx, cy+dy
                if (nx, ny) in visited: continue
                if nx < x0 or nx >= x1 or ny < y0 or ny >= y1: continue
                lx, ly = nx - x0, ny - y0
                tile = self.world.get(nx, ny)
                is_solid = BLOCK_DEFS[tile]["solid"] and tile != TORCH and tile != LAMP and tile != CAMPFIRE
                if is_solid:
                    new_light = cur_light * solid_atten
                else:
                    new_light = cur_light * air_atten
                if new_light > 0.03 and new_light > light[ly, lx]:
                    light[ly, lx] = max(light[ly, lx], new_light)
                    visited.add((nx, ny))
                    queue.append((nx, ny, new_light))

        # Torch/lava/campfire light with colored tinting
        light_r = np.zeros_like(light)
        light_g = np.zeros_like(light)
        light_b = np.zeros_like(light)
        # Performance: only scan visible tiles for light sources (no margin needed)
        light_sources = []
        for ty in range(y0, y1):
            for tx in range(x0, x1):
                block = self.world.get(tx, ty)
                if block in (TORCH, LAMP, CAMPFIRE, LAVA):
                    light_sources.append((tx, ty, block))
                elif self.world.get_liquid(tx, ty)[0] == LIQUID_LAVA:
                    light_sources.append((tx, ty, LAVA))
        for src_tx, src_ty, block in light_sources:
            radius = BLOCK_DEFS[block].get("light", 10) if block != LAVA else 10
            radius_sq = radius * radius
            if block == LAVA:
                tint_r, tint_g, tint_b = 1.0, 0.6, 0.2
            elif block == TORCH or block == CAMPFIRE:
                tint_r, tint_g, tint_b = 1.0, 0.8, 0.4
            else:  # LAMP
                tint_r, tint_g, tint_b = 0.9, 0.9, 1.0
            eff_radius = min(radius, 8)  # cap effective radius for performance
            for dy in range(-eff_radius, eff_radius+1):
                for dx in range(-eff_radius, eff_radius+1):
                    dist_sq = dx*dx + dy*dy
                    if dist_sq <= radius_sq:
                        lx, ly = src_tx+dx, src_ty+dy
                        if x0 <= lx < x1 and y0 <= ly < y1:
                            l = (1 - math.sqrt(dist_sq)/radius) * 1.0
                            if l > light[ly-y0, lx-x0]:
                                light[ly-y0, lx-x0] = l
                            light_r[ly-y0, lx-x0] = max(light_r[ly-y0, lx-x0], l * tint_r)
                            light_g[ly-y0, lx-x0] = max(light_g[ly-y0, lx-x0], l * tint_g)
                            light_b[ly-y0, lx-x0] = max(light_b[ly-y0, lx-x0], l * tint_b)

        # Player light
        plx, ply = int(self.player.x//TILE), int((self.player.y - self.player.h*0.5)//TILE)
        pr = 5  # player light radius (was 6, reduced for perf)
        for dy in range(-pr, pr+1):
            for dx in range(-pr, pr+1):
                dist = math.sqrt(dx*dx + dy*dy)
                if dist <= pr:
                    lx, ly = plx+dx, ply+dy
                    if x0 <= lx < x1 and y0 <= ly < y1:
                        l = (1 - dist/pr) * 0.7
                        if l > light[ly-y0, lx-x0]: light[ly-y0, lx-x0] = l
                        light_r[ly-y0, lx-x0] = max(light_r[ly-y0, lx-x0], l * 0.9)
                        light_g[ly-y0, lx-x0] = max(light_g[ly-y0, lx-x0], l * 0.85)
                        light_b[ly-y0, lx-x0] = max(light_b[ly-y0, lx-x0], l * 1.0)

        self.light_map = light; self._light_x0 = x0; self._light_y0 = y0
        self._depth_below = depth_below
        self._light_r = light_r; self._light_g = light_g; self._light_b = light_b
        self._light_revision += 1
        self._darkness_cache_key = None

    # ---------- draw ----------
    def _draw(self):
        # Render everything at native screen resolution (no scaling).
        # UI and world use actual screen dimensions directly.
        try:
            zoom = self.game_zoom
            if zoom != 1.0 and not self.map_open and not self.paused:
                # Zoomed view: render world to a smaller surface, then scale to screen
                vw = max(TILE*8, int(self.screen_w / zoom))
                vh = max(TILE*8, int(self.screen_h / zoom))
                zoom_surf = pygame.Surface((vw, vh))
                old_screen = self.screen
                self.screen = zoom_surf
                self._draw_world_view()
                self.screen = old_screen
                # Scale zoomed world to fill screen
                scaled = pygame.transform.scale(zoom_surf, (self.screen_w, self.screen_h))
                self.screen.blit(scaled, (0, 0))
                # Draw UI on top at native resolution
                self._draw_ui()
            else:
                # Normal (zoom=1.0): render everything directly to screen
                self._draw_internal()
        finally:
            pass

    def _draw_world_view(self):
        """Draw sky, background, world, entities, and darkness overlay."""
        self._draw_sky()
        # Skip parallax when underground for FPS boost
        if not self._is_player_underground():
            self._draw_parallax_background()
        self._draw_world()
        self._draw_liquids()
        self._draw_particles(); self._draw_arrows(); self._draw_dropped_items(); self._draw_enemies(); self._draw_player()
        self._draw_mining_overlay(); self._draw_reach_indicator()
        self._draw_weather()
        self._draw_darkness()

    def _draw_ui(self):
        """Draw HUD directly to screen at native resolution.
        Fonts use fixed sizes (no scaling) so text stays crisp in fullscreen.
        UI coordinates are adjusted to stay anchored correctly."""
        self._draw_hud(); self._draw_floats()
        if self.inventory_open:
            if self.creative_mode:
                self._draw_creative_inventory()
            else:
                self._draw_inventory_panel(RECIPES_BASIC, "Inventory & Crafting")
        elif self.workbench_open: self._draw_inventory_panel(RECIPES_WORKBENCH, "Workbench")
        elif self.station_open:
            if self.active_station == "furnace":
                self._draw_furnace_ui()
            else:
                recipes = {"anvil": RECIPES_ANVIL, "campfire": RECIPES_CAMPFIRE}.get(self.active_station, [])
                station_name = {"anvil": "Anvil", "campfire": "Campfire"}.get(self.active_station, "Station")
                self._draw_inventory_panel(recipes, station_name)
        elif self.chest_open: self._draw_chest_ui()
        if self.paused: self._draw_pause_menu()
        if self.game_over: self._draw_game_over_screen()
        if self.debug: self._draw_debug()

    def _draw_internal(self):
        if self.map_open:
            self._draw_map(); return
        self._draw_world_view()
        self._draw_ui()

    # Biome sky tints (subtle color shifts per biome)
    BIOME_SKY_TINT = {
        BIOME_SEA:      ((20, 30, 50),   (5, 10, 20)),     # bluer day, deeper night
        BIOME_TUNDRA:   ((30, 30, 40),   (15, 15, 20)),    # greyer/whiter
        BIOME_GRASSLAND:((0, 0, 0),       (0, 0, 0)),       # neutral (default)
        BIOME_FOREST:   ((-10, 5, -15),  (-3, 2, -5)),     # greener day, deeper night
        BIOME_JUNGLE:   ((-15, 10, -20), (-5, 5, -8)),     # strong green tint
        BIOME_SAVANNA:  ((25, 15, -20),  (8, 5, -7)),      # warmer/yellower
        BIOME_DESERT:   ((35, 20, -30),  (12, 7, -10)),    # warm orange tint
    }

    def _draw_sky(self):
        W = VIEW_W
        H = VIEW_H
        t = self.time
        # Determine player's current biome for sky tinting
        player_tx = int(self.player.x // TILE)
        player_biome = int(self.world.biomes[player_tx]) if 0 <= player_tx < self.world.w else BIOME_GRASSLAND
        day_tint, night_tint = self.BIOME_SKY_TINT.get(player_biome, ((0,0,0),(0,0,0)))
        # Blend tint based on time of day
        if t < 0.20 or t > 0.80:
            tint = night_tint
        elif t < 0.30:
            k = (t - 0.20) / 0.10
            tint = tuple(int(night_tint[i] + (day_tint[i] - night_tint[i]) * k) for i in range(3))
        elif t < 0.70:
            tint = day_tint
        else:
            k = (t - 0.70) / 0.10
            tint = tuple(int(day_tint[i] + (night_tint[i] - day_tint[i]) * k) for i in range(3))
        if t < 0.20: sky = COL_SKY_NIGHT
        elif t < 0.30: sky = self._lerp_color(COL_SKY_NIGHT, COL_SKY_DUSK, (t-0.20)/0.10)
        elif t < 0.40: sky = self._lerp_color(COL_SKY_DUSK, COL_SKY_DAY, (t-0.30)/0.10)
        elif t < 0.60: sky = COL_SKY_DAY
        elif t < 0.70: sky = self._lerp_color(COL_SKY_DAY, COL_SKY_DUSK, (t-0.60)/0.10)
        elif t < 0.80: sky = self._lerp_color(COL_SKY_DUSK, COL_SKY_NIGHT, (t-0.70)/0.10)
        else: sky = COL_SKY_NIGHT
        # Apply biome tint
        sky = (max(0, min(255, sky[0]+tint[0])), max(0, min(255, sky[1]+tint[1])), max(0, min(255, sky[2]+tint[2])))
        # Weather darkens the sky
        if self.weather_type == "storm":
            sky = (max(0, sky[0]-60), max(0, sky[1]-50), max(0, sky[2]-30))
        elif self.weather_type == "rain":
            sky = (max(0, sky[0]-30), max(0, sky[1]-25), max(0, sky[2]-15))
        elif self.weather_type == "snow":
            sky = (min(255, sky[0]+15), min(255, sky[1]+15), min(255, sky[2]+20))
        self.screen.fill(sky)
        # Stars only visible on clear or light-snow nights
        if (t < 0.20 or t > 0.80) and self.weather_type in ("clear", "snow"):
            for sx, sy, br in self.stars:
                if 0 <= sx < W and 0 <= sy < H: self.screen.set_at((sx, sy), (255,255,255))
        sun_angle = (t - 0.25) * math.tau
        sx = W/2 + math.cos(sun_angle) * (W*0.45)
        sy = H*0.55 - math.sin(sun_angle) * (H*0.45)
        if 0.20 < t < 0.80:
            # Sun less visible in rain/storm
            sun_alpha = 1.0 if self.weather_type == "clear" else (0.4 if self.weather_type == "storm" else 0.7)
            sun_col = (int(255*sun_alpha), int(230*sun_alpha), int(130*sun_alpha))
            pygame.draw.circle(self.screen, sun_col, (int(sx),int(sy)), 28)
            pygame.draw.circle(self.screen, (int(255*sun_alpha), int(200*sun_alpha), int(80*sun_alpha)), (int(sx),int(sy)), 22)
        else:
            ma = sun_angle + math.pi
            mx = W/2 + math.cos(ma) * (W*0.45)
            my = H*0.55 - math.sin(ma) * (H*0.45)
            pygame.draw.circle(self.screen, (230,230,240), (int(mx),int(my)), 22)
            pygame.draw.circle(self.screen, sky, (int(mx)+8, int(my)-4), 18)
        
        # Draw clouds during weather
        if self.weather_type in ("rain", "storm", "snow"):
            cloud_col = (80, 85, 95) if self.weather_type == "storm" else (160, 165, 175)
            t_ms = pygame.time.get_ticks()
            for i in range(8):
                cx = (i * 180 + int(t_ms * 0.008 * (1 + i * 0.1))) % (W + 200) - 100
                cy = 20 + (i * 17) % 60
                cw = 120 + (i * 37) % 80
                ch = 25 + (i * 13) % 20
                cloud_surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
                pygame.draw.ellipse(cloud_surf, (*cloud_col, 140), (0, 0, cw, ch))
                pygame.draw.ellipse(cloud_surf, (*cloud_col, 120), (cw//4, -ch//3, cw//2, ch))
                self.screen.blit(cloud_surf, (int(cx), int(cy)))

    @staticmethod
    def _lerp_color(a, b, k):
        return (int(a[0]+(b[0]-a[0])*k), int(a[1]+(b[1]-a[1])*k), int(a[2]+(b[2]-a[2])*k))

    def _draw_parallax_background(self):
        """Draw a parallax background terrain silhouette that matches the world.
        Uses numpy for fast per-pixel rendering, creating a smooth terrain
        background colored by biome with proper vegetation silhouettes."""
        W = VIEW_W
        H = VIEW_H
        parallax = 0.4
        bg_cam_x = self.cam_x * parallax
        bg_cam_y = self.cam_y * parallax

        # Biome colors (slightly muted for depth effect)
        BG_BIOME_SURFACE = {
            BIOME_SEA: np.array([40, 70, 110], dtype=np.uint8),
            BIOME_TUNDRA: np.array([140, 160, 180], dtype=np.uint8),
            BIOME_GRASSLAND: np.array([55, 105, 45], dtype=np.uint8),
            BIOME_FOREST: np.array([35, 85, 30], dtype=np.uint8),
            BIOME_JUNGLE: np.array([20, 70, 18], dtype=np.uint8),
            BIOME_SAVANNA: np.array([110, 100, 45], dtype=np.uint8),
            BIOME_DESERT: np.array([130, 115, 65], dtype=np.uint8),
        }
        BG_BIOME_SUBSURFACE = {
            BIOME_SEA: np.array([30, 55, 85], dtype=np.uint8),
            BIOME_TUNDRA: np.array([100, 90, 75], dtype=np.uint8),
            BIOME_GRASSLAND: np.array([80, 55, 35], dtype=np.uint8),
            BIOME_FOREST: np.array([70, 48, 30], dtype=np.uint8),
            BIOME_JUNGLE: np.array([45, 35, 22], dtype=np.uint8),
            BIOME_SAVANNA: np.array([90, 70, 40], dtype=np.uint8),
            BIOME_DESERT: np.array([110, 95, 55], dtype=np.uint8),
        }
        BG_BIOME_DEEP = {
            BIOME_SEA: np.array([20, 40, 70], dtype=np.uint8),
            BIOME_TUNDRA: np.array([70, 70, 65], dtype=np.uint8),
            BIOME_GRASSLAND: np.array([60, 60, 55], dtype=np.uint8),
            BIOME_FOREST: np.array([55, 55, 50], dtype=np.uint8),
            BIOME_JUNGLE: np.array([40, 38, 30], dtype=np.uint8),
            BIOME_SAVANNA: np.array([70, 60, 40], dtype=np.uint8),
            BIOME_DESERT: np.array([90, 80, 45], dtype=np.uint8),
        }
        default_surf = BG_BIOME_SURFACE[BIOME_GRASSLAND]
        default_sub = BG_BIOME_SUBSURFACE[BIOME_GRASSLAND]
        default_deep = BG_BIOME_DEEP[BIOME_GRASSLAND]

        surface_y_arr = self.world.surface_y
        biomes_arr = self.world.biomes
        ww = self.world.w

        # Build a numpy pixel array (W x H x 3) - fill with colorkey color (magenta = transparent)
        CKEY = (255, 0, 255)
        bg_array = np.full((W, H, 3), CKEY, dtype=np.uint8)

        # For each screen column, compute the world tile and surface Y
        tile_per_px = 1.0 / (TILE * parallax)  # world tiles per screen pixel
        # Vectorized: compute world_x for all screen columns at once
        sx_range = np.arange(W)
        world_xs = ((bg_cam_x + sx_range) * tile_per_px).astype(np.int32)
        world_xs = np.clip(world_xs, 0, ww - 1)

        # Look up surface heights and biomes (vectorized)
        sy_values = surface_y_arr[world_xs].astype(np.float64)
        biome_values = biomes_arr[world_xs].astype(np.int32)

        # Smooth surface heights with 2-neighbor average
        wx_left = np.clip(world_xs - 2, 0, ww - 1)
        wx_right = np.clip(world_xs + 2, 0, ww - 1)
        sy_left = surface_y_arr[wx_left].astype(np.float64)
        sy_right = surface_y_arr[wx_right].astype(np.float64)
        sy_smooth = ((sy_left + sy_values + sy_right) / 3.0)

        # Screen Y of surface for each column
        screen_sy = (sy_smooth * TILE * parallax - bg_cam_y + H * 0.1).astype(np.int32)

        surface_h = max(6, int(TILE * 4 * parallax))
        sub_h = max(8, int(TILE * 10 * parallax))

        # Build color lookup arrays for each screen column
        surf_colors = np.zeros((W, 3), dtype=np.uint8)
        sub_colors = np.zeros((W, 3), dtype=np.uint8)
        deep_colors = np.zeros((W, 3), dtype=np.uint8)
        light_colors = np.zeros((W, 3), dtype=np.uint8)

        for i in range(W):
            b = int(biome_values[i])
            sc = BG_BIOME_SURFACE.get(b, default_surf)
            sbc = BG_BIOME_SUBSURFACE.get(b, default_sub)
            dc = BG_BIOME_DEEP.get(b, default_deep)
            surf_colors[i] = sc
            sub_colors[i] = sbc
            deep_colors[i] = dc
            light_colors[i] = np.minimum(255, sc + np.array([35, 35, 25], dtype=np.uint8))

        # Render terrain using fully vectorized numpy operations
        # Create Y index array for masking
        y_arr = np.arange(H)  # shape (H,)

        for sx in range(W):
            ssy = int(screen_sy[sx])
            if ssy >= H:
                bg_array[sx, :, :] = deep_colors[sx]
                continue
            # Surface highlight line
            if 0 <= ssy < H:
                bg_array[sx, ssy, :] = light_colors[sx]
            # Surface strip
            s_end = min(H, ssy + surface_h)
            if s_end > max(ssy + 1, 0):
                bg_array[sx, max(ssy+1, 0):s_end, :] = surf_colors[sx]
            # Subsurface strip
            sub_start = ssy + surface_h
            sub_end = min(H, sub_start + sub_h)
            if sub_end > max(sub_start, 0):
                bg_array[sx, max(sub_start, 0):sub_end, :] = sub_colors[sx]
            # Deep underground
            deep_start = min(H, sub_start + sub_h)
            if deep_start < H:
                bg_array[sx, deep_start:H, :] = deep_colors[sx]

        # Convert numpy array to surface and blit
        bg_surf = pygame.surfarray.make_surface(bg_array)
        bg_surf.set_colorkey(CKEY)  # magenta = transparent (sky shows through)
        self.screen.blit(bg_surf, (0, 0))

        # Draw vegetation silhouettes using pygame.draw (only for visible tree positions)
        # Use deterministic seeding so trees don't flicker
        step = max(1, int(TILE * parallax))  # check every ~tile-width of screen pixels
        for sx in range(0, W, step):
            wx = int(world_xs[sx])
            ssy = int(screen_sy[sx])
            biome = int(biome_values[sx])
            sc = tuple(int(c) for c in surf_colors[sx])

            if biome in (BIOME_FOREST, BIOME_JUNGLE, BIOME_GRASSLAND, BIOME_TUNDRA, BIOME_SAVANNA):
                tree_rng = random.Random(self.world.seed * 555 + wx * 1111)
                if tree_rng.random() < 0.12:
                    tree_h = tree_rng.randint(12, 24)
                    tree_top = ssy - tree_h
                    if 2 < tree_top < H:
                        trunk_col = tuple(max(0, c-15) for c in sc)
                        canopy_col = (max(0, sc[0]-10), min(255, sc[1]+8), max(0, sc[2]-10))
                        # Trunk
                        trunk_w = max(2, step // 3)
                        pygame.draw.rect(self.screen, trunk_col,
                                        (sx - trunk_w//2, tree_top + tree_h//3, trunk_w, ssy - tree_top - tree_h//3))
                        # Canopy
                        canopy_r = max(4, step // 2)
                        pygame.draw.circle(self.screen, canopy_col, (sx, tree_top + tree_h//4), canopy_r)
                elif tree_rng.random() < 0.06 and biome == BIOME_TUNDRA:
                    pine_h = tree_rng.randint(14, 26)
                    pine_top = ssy - pine_h
                    if 2 < pine_top < H:
                        pine_col = (20, 60 + tree_rng.randint(0, 20), 20)
                        half_w = max(3, step // 2)
                        tip = (sx, pine_top)
                        bl = (sx - half_w, ssy)
                        br = (sx + half_w, ssy)
                        pygame.draw.polygon(self.screen, pine_col, [tip, bl, br])

            if biome == BIOME_DESERT:
                cact_rng = random.Random(self.world.seed * 777 + wx * 333)
                if cact_rng.random() < 0.08:
                    cact_h = cact_rng.randint(10, 18)
                    cact_top = ssy - cact_h
                    if 2 < cact_top < H:
                        cact_col = (60, 100 + cact_rng.randint(0, 30), 40)
                        cw = max(2, step // 4)
                        pygame.draw.rect(self.screen, cact_col, (sx - cw//2, cact_top, cw, cact_h))

        # Add subtle depth fade at bottom
        if H > 100:
            fade_h = min(80, H // 3)
            fade_surf = pygame.Surface((W, fade_h), pygame.SRCALPHA)
            for i in range(fade_h):
                alpha = int(100 * (i / fade_h) ** 1.5)
                pygame.draw.line(fade_surf, (0, 0, 0, alpha), (0, fade_h - 1 - i), (W, fade_h - 1 - i))
            self.screen.blit(fade_surf, (0, H - fade_h))

    def _draw_world(self):
        W = VIEW_W
        H = VIEW_H
        x0 = max(0, int(self.cam_x//TILE)); x1 = min(self.world.w, int((self.cam_x + W) // TILE) + 1)
        y0 = max(0, int(self.cam_y//TILE)); y1 = min(self.world.h, int((self.cam_y+H)//TILE)+1)
        cam_x, cam_y = int(self.cam_x), int(self.cam_y)
        # Cache column references for fast access (avoid dict lookups per tile)
        # Draw walls first (only where foreground is AIR)
        for tx in range(x0, x1):
            col = self.world.tile_columns.get(tx)
            if not col: continue
            wall_col = self.world.wall_columns.get(tx)
            sx = tx*TILE - cam_x
            for ty in range(y0, y1):
                if col[ty] == AIR:
                    wall = wall_col[ty] if wall_col else WALL_NONE
                    if wall != WALL_NONE:
                        self.screen.blit(self.wall_textures[wall], (sx, ty*TILE - cam_y))
        # Draw foreground blocks with ambient occlusion (simple edge darkening)
        for tx in range(x0, x1):
            col = self.world.tile_columns.get(tx)
            if not col: continue
            sx = tx*TILE - cam_x
            for ty in range(y0, y1):
                block = col[ty]
                if block == AIR: continue
                tex = self.block_textures.get(block)
                if block == BED and tex:
                    # Left half (head) if no BED to the left, else right half (foot)
                    is_head = (tx == 0 or self.world.get(tx - 1, ty) != BED)
                    if not is_head:
                        tex = self.block_textures.get('_BED_FOOT', tex)
                elif block in (TALL_GRASS, DRIED_TALL_GRASS) and tex:
                    # Top half if same grass type below, bottom half otherwise
                    grass_below = self.world.get(tx, ty + 1) if ty + 1 < self.world.h else AIR
                    if grass_below == block:
                        tex_key = '_DRIED_TALL_GRASS_TOP' if block == DRIED_TALL_GRASS else '_TALL_GRASS_TOP'
                        tex = self.block_textures.get(tex_key, tex)
                if tex: self.screen.blit(tex, (sx, ty*TILE - cam_y))

    def _draw_liquids(self):
        """Draw flowing liquid: fill height follows the simulated amount (so a half-full
        cell looks half full), with an animated wavy highlight line on cells exposed to
        open air above -- water gets a light foam line, lava a pulsing glow line."""
        W = VIEW_W
        H = VIEW_H
        x0 = max(0, int(self.cam_x//TILE)); x1 = min(self.world.w, int((self.cam_x+W)//TILE)+1)
        y0 = max(0, int(self.cam_y//TILE)); y1 = min(self.world.h, int((self.cam_y+H)//TILE)+1)
        cam_x, cam_y = int(self.cam_x), int(self.cam_y)
        t = pygame.time.get_ticks() / 1000.0
        for tx in range(x0, x1):
            amt_col = self.world.liquid_amount.get(tx)
            if not amt_col: continue
            type_col = self.world.liquid_type[tx]
            sx = tx*TILE - cam_x
            for ty in range(y0, y1):
                amount = amt_col[ty]
                if amount <= 0: continue
                ltype = type_col[ty]
                fill_h = max(1, int(TILE * amount / MAX_LIQUID))
                top_open = ty == 0 or amt_col[ty-1] == 0
                surf = self.liquid_fill_surfs[ltype][fill_h]
                draw_y = ty*TILE - cam_y + (TILE - fill_h)
                self.screen.blit(surf, (sx, draw_y))
                if top_open:
                    if ltype == LIQUID_WATER:
                        wobble = math.sin(t*2.2 + tx*0.6) * 1.5
                        col = (190, 225, 255)
                    else:
                        wobble = math.sin(t*3.0 + tx*0.4) * 1.0
                        glow = 150 + int(60 * (0.5 + 0.5*math.sin(t*3.3 + tx*0.7)))
                        col = (255, min(255, glow), 60)
                    ly = int(draw_y + wobble)
                    pygame.draw.line(self.screen, col, (sx, ly), (sx+TILE, ly), 2)

    def _draw_darkness(self):
        """Apply darkness overlay with colored light tinting.
        Two-tier system:
        - Surface shadowed areas: softer darkness (max alpha ~80)
        - Deep underground: pitch black (max alpha ~245)
        Colored light: torches tint darkness warm orange, lava red-orange, lamps white.
        Blur at tile resolution, then upscale to screen pixels for full-tile coverage."""
        if self.light_map is None: return
        x0, y0 = self._light_x0, self._light_y0
        rows, cols = self.light_map.shape
        if rows == 0 or cols == 0: return

        cache_key = (x0, y0, rows, cols, self._light_revision, self._exploration_revision)
        if self._darkness_cache_key == cache_key and self._darkness_scaled is not None:
            self.screen.blit(self._darkness_scaled, (x0 * TILE - int(self.cam_x), y0 * TILE - int(self.cam_y)))
            return

        # Two-tier max alpha based on depth below surface
        depth = getattr(self, '_depth_below', None)
        if depth is not None and depth.shape == self.light_map.shape:
            # Surface shadowed: max alpha 80, Deep underground: max alpha 245
            max_alpha = (80 + (245 - 80) * np.clip(depth, 0, 1)).astype(np.float32)
        else:
            max_alpha = 245.0

        alpha_arr = ((1.0 - self.light_map) * max_alpha).clip(0, 255).astype(np.uint8)

        if self.explored_chunks:
            tile_xs = np.arange(x0, x0 + cols)
            tile_ys = np.arange(y0, y0 + rows)
            explored = np.array([(tx, ty) in self.explored_chunks for ty in tile_ys for tx in tile_xs], dtype=bool).reshape(rows, cols)
            surface = self.world.surface_y[np.clip(tile_xs, 0, self.world.w - 1)] + 4
            underground = tile_ys[:, None] >= surface[None, :]
            alpha_arr[underground & ~explored] = np.maximum(alpha_arr[underground & ~explored], 205)
        
        
        # Blur at tile resolution for smooth edges
        padded = np.pad(alpha_arr.astype(np.float32), 1, mode='edge')
        blurred = (padded[:-2,:-2] + padded[1:-1,:-2] + padded[2:,:-2] +
                   padded[:-2,1:-1] + padded[1:-1,1:-1] + padded[2:,1:-1] +
                   padded[:-2,2:] + padded[1:-1,2:] + padded[2:,2:]) / 9.0
        alpha_arr = blurred.astype(np.uint8)
        
        # --- Colored light tinting ---
        # Build a tint color per tile: darkness is tinted toward the dominant light color
        # This makes torch-lit areas glow warm orange, lava glow red, etc.
        light_r = getattr(self, '_light_r', None)
        light_g = getattr(self, '_light_g', None)
        light_b = getattr(self, '_light_b', None)
        has_color = (light_r is not None and light_g is not None and light_b is not None
                     and light_r.shape == self.light_map.shape)
        
        if has_color:
            # Default darkness color: pure black (0,0,0). 
            # Where colored light is present, shift the darkness tint toward the light color.
            # The stronger the colored light, the more the tint.
            tint_strength = 0.3  # how much the light color affects the darkness overlay
            max_lr = np.max(light_r) if np.max(light_r) > 0 else 1.0
            max_lg = np.max(light_g) if np.max(light_g) > 0 else 1.0
            max_lb = np.max(light_b) if np.max(light_b) > 0 else 1.0
            # Normalize and compute tint color (0-255)
            tint_r = np.clip(light_r / max(max_lr, 0.01) * 255 * tint_strength, 0, 80).astype(np.uint8)
            tint_g = np.clip(light_g / max(max_lg, 0.01) * 255 * tint_strength, 0, 50).astype(np.uint8)
            tint_b = np.clip(light_b / max(max_lb, 0.01) * 255 * tint_strength, 0, 30).astype(np.uint8)
        else:
            tint_r = tint_g = tint_b = None
        
        # OPTIMIZED: Build darkness at tile resolution then scale up (much faster than np.repeat)
        # Build a small RGBA surface at tile resolution
        small_w, small_h = cols, rows
        if small_w <= 0 or small_h <= 0: return
        
        if not hasattr(self, '_dark_small') or self._dark_small is None or self._dark_small.get_size() != (small_w, small_h):
            self._dark_small = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
        dark_small = self._dark_small
        dark_small.fill((0, 0, 0, 0))
        
        # Build RGBA array at tile resolution using surfarray
        try:
            px3 = pygame.surfarray.pixels3d(dark_small)
            pxa = pygame.surfarray.pixels_alpha(dark_small)
            # alpha_arr is (rows, cols) = (small_h, small_w), surfarray is (small_w, small_h)
            pxa[:, :] = alpha_arr.T
            if has_color:
                # Stack RGB channels: each is (rows, cols), need (small_w, small_h, 3)
                rgb_small = np.stack([tint_r.T, tint_g.T, tint_b.T], axis=-1)
                px3[:, :, :] = rgb_small
            else:
                px3[:, :, :] = 0
            del px3; del pxa
        except Exception:
            # Fallback: set pixels manually (slower but reliable)
            for row in range(rows):
                for col in range(cols):
                    a = int(alpha_arr[row, col])
                    if a > 0:
                        r = int(tint_r[row, col]) if has_color and tint_r is not None else 0
                        g = int(tint_g[row, col]) if has_color and tint_g is not None else 0
                        b = int(tint_b[row, col]) if has_color and tint_b is not None else 0
                        dark_small.set_at((col, row), (r, g, b, a))
        
        # Scale up to screen area and blit at correct offset
        DW = VIEW_W
        DH = VIEW_H
        target_w = cols * TILE
        target_h = rows * TILE
        if target_w > 0 and target_h > 0:
            scaled = pygame.transform.scale(dark_small, (target_w, target_h))
            # Convert to per-pixel alpha for proper blending
            scaled = scaled.convert_alpha()
            sx_start = x0 * TILE - int(self.cam_x)
            sy_start = y0 * TILE - int(self.cam_y)
            self._darkness_scaled = scaled
            self._darkness_cache_key = cache_key
            self.screen.blit(scaled, (sx_start, sy_start))

    def _draw_particles(self):
        # OPTIMIZED: pre-create a shared particle surface instead of allocating per particle
        max_size = 16  # max particle radius
        _psurf = pygame.Surface((max_size*2, max_size*2), pygame.SRCALPHA)
        for p in self.particles:
            alpha = max(0, min(255, int(255 * (p.life/p.max_life))))
            sx, sy = int(p.x-self.cam_x), int(p.y-self.cam_y)
            if 0 <= sx < VIEW_W and 0 <= sy < VIEW_H:
                size = max(1, int(p.size))
                _psurf.fill((0, 0, 0, 0))
                pygame.draw.circle(_psurf, (p.color[0], p.color[1], p.color[2], alpha), (max_size, max_size), size)
                self.screen.blit(_psurf, (sx-max_size, sy-max_size))

    def _draw_arrows(self):
        for a in self.arrows:
            sx, sy = int(a.x - self.cam_x), int(a.y - self.cam_y)
            angle = math.atan2(a.vy, a.vx)
            # Simple arrow: line + tip
            tip_x = sx + int(math.cos(angle) * 8)
            tip_y = sy + int(math.sin(angle) * 8)
            tail_x = sx - int(math.cos(angle) * 6)
            tail_y = sy - int(math.sin(angle) * 6)
            pygame.draw.line(self.screen, (160, 110, 60), (tail_x, tail_y), (tip_x, tip_y), 2)
            pygame.draw.circle(self.screen, (220, 220, 220), (tip_x, tip_y), 2)

    def _draw_enemies(self):
        for s in self.slimes:
            sx, sy = int(s.x-self.cam_x), int(s.y-self.cam_y)
            w, h = int(s.w), int(s.h)
            br = pygame.Rect(sx-w//2, sy-h, w, h)
            pygame.draw.ellipse(self.screen, s.color, br)
            pygame.draw.ellipse(self.screen, self._shade(s.color,-40), br, 2)
            ey = sy - int(h*0.7)
            pygame.draw.circle(self.screen, (255,255,255), (sx-6, ey), 3)
            pygame.draw.circle(self.screen, (255,255,255), (sx+6, ey), 3)
            pygame.draw.circle(self.screen, (20,20,20), (sx-5, ey), 2)
            pygame.draw.circle(self.screen, (20,20,20), (sx+7, ey), 2)
            if s.health < s.max_health:
                bw = 30
                pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h-8, bw, 4))
                pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h-8, int(bw*s.health/s.max_health), 4))
        for z in self.zombies:
            sx, sy = int(z.x-self.cam_x), int(z.y-self.cam_y)
            w, h = int(z.w), int(z.h)
            pygame.draw.rect(self.screen, z.color, (sx-w//2, sy-int(h*0.8), w, int(h*0.5)))
            hs = int(h*0.3)
            pygame.draw.rect(self.screen, self._shade(z.color, 20), (sx-hs//2, sy-h, hs, hs))
            pygame.draw.rect(self.screen, self._shade(z.color,-30), (sx-w//2, sy-int(h*0.3), w//2-1, int(h*0.3)))
            pygame.draw.rect(self.screen, self._shade(z.color,-30), (sx+1, sy-int(h*0.3), w//2-1, int(h*0.3)))
            pygame.draw.circle(self.screen, (255, 50, 50), (sx-3, sy-h+hs//2), 1)
            pygame.draw.circle(self.screen, (255, 50, 50), (sx+3, sy-h+hs//2), 1)
            pygame.draw.rect(self.screen, (20,30,20), (sx-w//2, sy-h, w, h), 1)
            if z.health < z.max_health:
                bw = 30
                pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h-8, bw, 4))
                pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h-8, int(bw*z.health/z.max_health), 4))
        # Skeletons
        for sk in self.skeletons:
            sx, sy = int(sk.x-self.cam_x), int(sk.y-self.cam_y)
            w, h = int(sk.w), int(sk.h)
            # Body (ribcage look)
            pygame.draw.rect(self.screen, sk.color, (sx-w//2, sy-int(h*0.6), w, int(h*0.6)))
            pygame.draw.rect(self.screen, self._shade(sk.color, -40), (sx-w//2, sy-int(h*0.6), w, int(h*0.6)), 1)
            # Skull
            hs = int(h*0.35)
            pygame.draw.rect(self.screen, self._shade(sk.color, 15), (sx-hs//2, sy-h, hs, hs))
            # Eyes (dark sockets)
            pygame.draw.circle(self.screen, (40, 0, 0), (sx-3, sy-h+hs//2), 2)
            pygame.draw.circle(self.screen, (40, 0, 0), (sx+3, sy-h+hs//2), 2)
            # Red glow in eyes
            pygame.draw.circle(self.screen, (255, 80, 80), (sx-3, sy-h+hs//2), 1)
            pygame.draw.circle(self.screen, (255, 80, 80), (sx+3, sy-h+hs//2), 1)
            if sk.health < sk.max_health:
                bw = 30
                pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h-8, bw, 4))
                pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h-8, int(bw*sk.health/sk.max_health), 4))
        # Demon Eyes — floating red eyeballs
        for de in self.demon_eyes:
            sx, sy = int(de.x-self.cam_x), int(de.y-self.cam_y)
            w, h = int(de.w), int(de.h)
            # Outer eye (veined red)
            pygame.draw.ellipse(self.screen, de.color, (sx-w//2, sy-h//2, w, h))
            pygame.draw.ellipse(self.screen, self._shade(de.color, -30), (sx-w//2, sy-h//2, w, h), 1)
            # Veins
            pygame.draw.line(self.screen, self._shade(de.color, -50), (sx, sy-h//2), (sx-w//4, sy), 1)
            pygame.draw.line(self.screen, self._shade(de.color, -50), (sx, sy-h//2), (sx+w//4, sy), 1)
            # Pupil (vertical slit like a cat)
            pygame.draw.ellipse(self.screen, (20, 0, 0), (sx-2, sy-h//3, 4, h*2//3))
            if de.health < de.max_health:
                bw = 30
                pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h//2-10, bw, 4))
                pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h//2-10, int(bw*de.health/de.max_health), 4))
        # Fish — simple fish shapes
        for fi in self.fish:
            sx, sy = int(fi.x-self.cam_x), int(fi.y-self.cam_y)
            w, h = int(fi.w), int(fi.h)
            # Body (ellipse)
            body_rect = pygame.Rect(sx-w//2, sy-h//2, w, h)
            pygame.draw.ellipse(self.screen, fi.color, body_rect)
            pygame.draw.ellipse(self.screen, self._shade(fi.color, -30), body_rect, 1)
            # Tail
            tail_dir = -1 if fi.direction > 0 else 1
            tx_pts = [(sx + tail_dir * w//2, sy),
                      (sx + tail_dir * (w//2 + 6), sy - 4),
                      (sx + tail_dir * (w//2 + 6), sy + 4)]
            pygame.draw.polygon(self.screen, self._shade(fi.color, -20), tx_pts)
            # Eye
            eye_x = sx - int(fi.direction * w * 0.25)
            pygame.draw.circle(self.screen, (255, 255, 255), (eye_x, sy - 1), 2)
            pygame.draw.circle(self.screen, (0, 0, 0), (eye_x, sy - 1), 1)
            if fi.health < fi.max_health:
                bw = 20
                pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h//2-6, bw, 3))
                pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h//2-6, int(bw*fi.health/fi.max_health), 3))
        # Bats — small wing shapes
        for b in self.bats:
            sx, sy = int(b.x - self.cam_x), int(b.y - self.cam_y)
            w, h = int(b.w), int(b.h)
            # Body
            pygame.draw.ellipse(self.screen, b.color, (sx-w//2, sy-h//2, w, h))
            # Wings (triangular flaps on each side)
            wing_spread = int(8 + 4 * math.sin(pygame.time.get_ticks() * 0.015))
            pygame.draw.polygon(self.screen, self._shade(b.color, 15),
                                [(sx, sy), (sx - wing_spread, sy - 4), (sx - 2, sy + 2)])
            pygame.draw.polygon(self.screen, self._shade(b.color, 15),
                                [(sx, sy), (sx + wing_spread, sy - 4), (sx + 2, sy + 2)])
            # Eyes (tiny red dots)
            pygame.draw.circle(self.screen, (255, 100, 100), (sx - 2, sy - 1), 1)
            pygame.draw.circle(self.screen, (255, 100, 100), (sx + 2, sy - 1), 1)
            if b.health < b.max_health:
                bw = 20
                pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h//2-6, bw, 3))
                pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h//2-6, int(bw*b.health/b.max_health), 3))
        # Crabs — flat body with claws
        for c in self.crabs:
            sx, sy = int(c.x - self.cam_x), int(c.y - self.cam_y)
            w, h = int(c.w), int(c.h)
            # Shell (oval body)
            shell_rect = pygame.Rect(sx - w//2, sy - h, w, h)
            pygame.draw.ellipse(self.screen, c.color, shell_rect)
            pygame.draw.ellipse(self.screen, self._shade(c.color, -30), shell_rect, 1)
            # Claws (small circles on sides)
            claw_y = sy - int(h * 0.7)
            pygame.draw.circle(self.screen, self._shade(c.color, 20), (sx - w//2 - 3, claw_y), 3)
            pygame.draw.circle(self.screen, self._shade(c.color, 20), (sx + w//2 + 3, claw_y), 3)
            # Eyes (on stalks)
            pygame.draw.line(self.screen, self._shade(c.color, -20), (sx - 3, sy - h), (sx - 4, sy - h - 4), 1)
            pygame.draw.line(self.screen, self._shade(c.color, -20), (sx + 3, sy - h), (sx + 4, sy - h - 4), 1)
            pygame.draw.circle(self.screen, (20, 20, 20), (sx - 4, sy - h - 5), 1)
            pygame.draw.circle(self.screen, (20, 20, 20), (sx + 4, sy - h - 5), 1)
            # Legs (tiny lines below)
            for lx_off in [-4, -2, 2, 4]:
                pygame.draw.line(self.screen, self._shade(c.color, -20),
                                 (sx + lx_off, sy - 2), (sx + lx_off + (2 if lx_off > 0 else -2), sy + 1), 1)
            if c.health < c.max_health:
                bw = 24
                pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h-8, bw, 3))
                pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h-8, int(bw*c.health/c.max_health), 3))
        # Draw animals
        for a in self.animals:
            self._draw_animal(a)

    def _draw_animal(self, a):
        sx, sy = int(a.x - self.cam_x), int(a.y - self.cam_y)
        w, h = int(a.w), int(a.h)
        atype = a.animal_type
        c = a.color
        dark = self._shade(c, -40)
        if atype == ANIMAL_RABBIT:
            # Small brown body + ears
            pygame.draw.ellipse(self.screen, c, (sx-w//2, sy-h+2, w, h-2))
            pygame.draw.ellipse(self.screen, dark, (sx-w//2, sy-h+2, w, h-2), 1)
            # Ears
            ear_x = sx + a.facing * 2
            pygame.draw.ellipse(self.screen, c, (ear_x-2, sy-h-3, 3, 5))
            pygame.draw.ellipse(self.screen, c, (ear_x+1, sy-h-3, 3, 5))
            # Eye
            pygame.draw.circle(self.screen, (20,20,20), (sx + a.facing*2, sy-h+5), 1)
        elif atype == ANIMAL_SHEEP:
            # Fluffy white body
            pygame.draw.ellipse(self.screen, c, (sx-w//2, sy-h+3, w, h-3))
            # Head (dark)
            head_x = sx + a.facing * (w//3)
            pygame.draw.circle(self.screen, (60, 50, 40), (head_x, sy-h+5), 4)
            # Fluff dots
            pygame.draw.circle(self.screen, (220,220,220), (sx-3, sy-h+5), 2)
            pygame.draw.circle(self.screen, (220,220,220), (sx+3, sy-h+5), 2)
            # Legs
            pygame.draw.rect(self.screen, (60, 50, 40), (sx-w//3, sy-2, 2, 3))
            pygame.draw.rect(self.screen, (60, 50, 40), (sx+w//3-2, sy-2, 2, 3))
        elif atype == ANIMAL_COW:
            # Big brown body with white spots
            pygame.draw.ellipse(self.screen, c, (sx-w//2, sy-h+2, w, h-2))
            pygame.draw.ellipse(self.screen, dark, (sx-w//2, sy-h+2, w, h-2), 1)
            # White spots
            pygame.draw.circle(self.screen, (240,240,240), (sx-3, sy-h+6), 2)
            pygame.draw.circle(self.screen, (240,240,240), (sx+3, sy-h+8), 2)
            # Head
            head_x = sx + a.facing * (w//2)
            pygame.draw.circle(self.screen, c, (head_x, sy-h+4), 4)
            # Horns
            pygame.draw.circle(self.screen, (240,240,240), (head_x-2, sy-h+1), 1)
            pygame.draw.circle(self.screen, (240,240,240), (head_x+2, sy-h+1), 1)
            # Legs
            pygame.draw.rect(self.screen, dark, (sx-w//3-1, sy-2, 2, 3))
            pygame.draw.rect(self.screen, dark, (sx+w//3-1, sy-2, 2, 3))
        elif atype == ANIMAL_GOAT:
            # Gray-brown body
            pygame.draw.ellipse(self.screen, c, (sx-w//2, sy-h+2, w, h-2))
            pygame.draw.ellipse(self.screen, dark, (sx-w//2, sy-h+2, w, h-2), 1)
            # Head with horns
            head_x = sx + a.facing * (w//2)
            pygame.draw.circle(self.screen, c, (head_x, sy-h+3), 3)
            # Curved horns
            pygame.draw.line(self.screen, (220,210,200), (head_x-2, sy-h+1), (head_x-3, sy-h-2), 1)
            pygame.draw.line(self.screen, (220,210,200), (head_x+2, sy-h+1), (head_x+3, sy-h-2), 1)
            # Beard
            pygame.draw.line(self.screen, c, (head_x, sy-h+6), (head_x, sy-h+9), 1)
            # Legs
            pygame.draw.rect(self.screen, dark, (sx-w//3, sy-2, 2, 3))
            pygame.draw.rect(self.screen, dark, (sx+w//3-2, sy-2, 2, 3))
        elif atype == ANIMAL_CHICKEN:
            # Yellow-white body
            pygame.draw.ellipse(self.screen, c, (sx-w//2, sy-h+3, w, h-3))
            # Head
            head_x = sx + a.facing * (w//3)
            pygame.draw.circle(self.screen, c, (head_x, sy-h+3), 3)
            # Beak (orange)
            pygame.draw.polygon(self.screen, (240, 160, 40),
                                [(head_x + a.facing*3, sy-h+3), (head_x + a.facing*5, sy-h+4), (head_x + a.facing*3, sy-h+5)])
            # Comb (red)
            pygame.draw.rect(self.screen, (220, 50, 50), (head_x-1, sy-h, 2, 2))
            # Legs
            pygame.draw.rect(self.screen, (240, 160, 40), (sx-2, sy-2, 1, 3))
            pygame.draw.rect(self.screen, (240, 160, 40), (sx+1, sy-2, 1, 3))
        elif atype == ANIMAL_FROG:
            # Green body, squat
            pygame.draw.ellipse(self.screen, c, (sx-w//2, sy-h+2, w, h-2))
            pygame.draw.ellipse(self.screen, dark, (sx-w//2, sy-h+2, w, h-2), 1)
            # Eyes (bulging on top)
            pygame.draw.circle(self.screen, (240, 240, 100), (sx-3, sy-h+2), 2)
            pygame.draw.circle(self.screen, (240, 240, 100), (sx+3, sy-h+2), 2)
            pygame.draw.circle(self.screen, (20, 20, 20), (sx-3, sy-h+2), 1)
            pygame.draw.circle(self.screen, (20, 20, 20), (sx+3, sy-h+2), 1)
        elif atype == ANIMAL_BUTTERFLY:
            # Butterfly: 4 wings + body
            wing_offset = int(math.sin(pygame.time.get_ticks() * 0.02) * 2)
            # Upper wings
            pygame.draw.ellipse(self.screen, c, (sx-wing_offset-5, sy-5, 5, 6))
            pygame.draw.ellipse(self.screen, c, (sx+wing_offset, sy-5, 5, 6))
            # Lower wings
            lower_c = self._shade(c, -30)
            pygame.draw.ellipse(self.screen, lower_c, (sx-wing_offset-4, sy, 4, 5))
            pygame.draw.ellipse(self.screen, lower_c, (sx+wing_offset, sy, 4, 5))
            # Body
            pygame.draw.rect(self.screen, (40, 30, 20), (sx-1, sy-4, 2, 8))
        elif atype == ANIMAL_BIRD:
            # Bird body (elliptical)
            pygame.draw.ellipse(self.screen, c, (sx-w//2, sy-h+3, w, h-4))
            pygame.draw.ellipse(self.screen, dark, (sx-w//2, sy-h+3, w, h-4), 1)
            # Wings (flapping animation)
            wing_y = int(math.sin(pygame.time.get_ticks() * 0.015 + a.x * 0.1) * 3)
            pygame.draw.ellipse(self.screen, self._shade(c, 20), (sx-w//2-4, sy-h+2+wing_y, 5, 3))
            pygame.draw.ellipse(self.screen, self._shade(c, 20), (sx+w//2-1, sy-h+2-wing_y, 5, 3))
            # Head
            head_x = sx + a.facing * (w//3)
            pygame.draw.circle(self.screen, c, (head_x, sy-h+3), 3)
            # Beak (orange triangle)
            pygame.draw.polygon(self.screen, (240, 180, 40),
                [(head_x + a.facing*3, sy-h+3), (head_x + a.facing*5, sy-h+4), (head_x + a.facing*3, sy-h+5)])
            # Eye
            pygame.draw.circle(self.screen, (20, 20, 20), (head_x + a.facing, sy-h+3), 1)
            # Tail feathers
            pygame.draw.line(self.screen, self._shade(c, -20), (sx - a.facing*(w//3), sy-h+5), (sx - a.facing*(w//2+3), sy-h+3), 2)
        # Health bar if injured
        if a.health < a.max_health:
            bw = 24
            pygame.draw.rect(self.screen, (40,40,40), (sx-bw//2, sy-h-6, bw, 3))
            pygame.draw.rect(self.screen, (220,60,60), (sx-bw//2, sy-h-6, int(bw*a.health/a.max_health), 3))

    def _draw_player(self):
        p = self.player; sx, sy = int(p.x-self.cam_x), int(p.y-self.cam_y)
        w, h = int(p.w), int(p.h)
        if p.invuln > 0 and int(p.invuln*20) % 2 == 0: return
        bc, lc, hc = (60,130,220), (40,40,80), (235,200,170)
        pygame.draw.rect(self.screen, lc, (sx-w//2, sy-int(h*0.4), w//2-1, int(h*0.4)))
        pygame.draw.rect(self.screen, lc, (sx+1, sy-int(h*0.4), w//2-1, int(h*0.4)))
        pygame.draw.rect(self.screen, bc, (sx-w//2, sy-int(h*0.75), w, int(h*0.4)))
        hs = int(h*0.30)
        pygame.draw.rect(self.screen, hc, (sx-hs//2, sy-h, hs, hs))
        ex, ey = sx+p.facing*2, sy-h+hs//2
        pygame.draw.circle(self.screen, (20,20,20), (ex, ey), 2)
        ax = sx + p.facing*(w//2)
        pygame.draw.rect(self.screen, self._shade(bc,-30), (ax-2, sy-int(h*0.7), 4, int(h*0.35)))
        pygame.draw.rect(self.screen, (20,20,30), (sx-w//2, sy-h, w, h), 1)

    def _draw_mining_overlay(self):
        p = self.player
        if p.mine_target is None: return
        tx, ty = p.mine_target
        sx, sy = int(tx*TILE-self.cam_x), int(ty*TILE-self.cam_y)
        if p.mine_is_wall:
            wall = self.world.get_wall(tx, ty); hardness = WALL_HARDNESS.get(wall, 0.5)
            progress = p.mine_progress / max(0.01, hardness)
        else:
            block = self.world.get(tx, ty); d = BLOCK_DEFS[block]
            progress = p.mine_progress / max(0.01, d["hardness"])
        overlay = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        overlay.fill((255,255,255,30))
        rng = random.Random(tx*100003 + ty)
        for _ in range(int(progress*6)):
            x0, y0 = rng.randint(2,TILE-3), rng.randint(2,TILE-3)
            x1, y1 = x0+rng.randint(-6,6), y0+rng.randint(-6,6)
            pygame.draw.line(overlay, (0,0,0,200), (x0,y0), (x1,y1), 1)
        self.screen.blit(overlay, (sx, sy))
        pygame.draw.rect(self.screen, (0,0,0), (sx, sy-5, TILE, 3))
        pygame.draw.rect(self.screen, (220,220,80), (sx, sy-5, int(TILE*progress), 3))

    def _draw_reach_indicator(self):
        mx, my = pygame.mouse.get_pos()
        wx, wy = mx + self.cam_x, my + self.cam_y
        if math.hypot(wx-self.player.x, wy-(self.player.y-self.player.h*0.5)) > REACH: return
        tx, ty = int(wx//TILE), int(wy//TILE)
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(s, (255,255,255,70), s.get_rect(), 1)
        self.screen.blit(s, (int(tx*TILE-self.cam_x), int(ty*TILE-self.cam_y)))

    def _draw_hud(self):
        # In creative mode, hide status bars (health, hunger, thirst, armor)
        if not self.creative_mode:
            self._draw_status_bars()
        # Hotbar
        self._draw_hotbar()
        # Weather indicator (top-right corner)
        self._draw_weather_indicator()
        # Day counter (top-left)
        self._draw_day_indicator()
        # Draw held item on main screen when not in any panel
        if self.inventory.held and not self.inventory_open and not self.workbench_open and not self.station_open and not self.chest_open:
            mx, my = pygame.mouse.get_pos()
            slot_size = 44
            self._draw_item_in_slot(self.inventory.held, mx - slot_size//2, my - slot_size//2, slot_size)

    def _draw_weather_indicator(self):
        """Draw a small weather icon in the top-right corner."""
        x, y = self.screen_w - 80, 10
        if self.weather_type == "clear":
            icon = "Clear"
            col = (255, 230, 130)
        elif self.weather_type == "rain":
            icon = "Rain"
            col = (140, 170, 220)
        elif self.weather_type == "snow":
            icon = "Snow"
            col = (200, 210, 230)
        elif self.weather_type == "storm":
            icon = "Storm!"
            col = (255, 100, 100)
        else:
            return
        # Dim the indicator when underground to show weather is on the surface
        if self._is_player_underground():
            col = tuple(max(60, c // 2) for c in col)
        txt = self.font.render(icon, True, col)
        self.screen.blit(txt, (x, y))

    def _draw_day_indicator(self):
        """Draw day count and time in the top-left corner."""
        t = self.time
        phase = "Night" if (t < 0.22 or t > 0.78) else ("Dawn" if t < 0.32 else ("Day" if t < 0.68 else "Dusk"))
        txt = self.font.render(f"Day {self.day_count} - {phase}", True, (200, 200, 220))
        self.screen.blit(txt, (10, 10))

    def _draw_status_bars(self):
        """Draw HP hearts, armor shields, hunger drumsticks, and thirst drops above the hotbar (Minecraft-style)."""
        p = self.player
        slot, gap = 44, 4
        sw, sh = self.screen_w, self.screen_h
        hx = (sw - (10*slot + 9*gap)) // 2
        hotbar_w = 10*slot + 9*gap
        bar_y = sh - slot - 14 - 20  # 20px above hotbar
        icon_size = 9
        icon_gap = 1
        icon_step = icon_size + icon_gap  # 10px per icon
        num_icons = 10

        # --- Row of icons: HP | Armor | Hunger | Thirst ---
        # Each group: num_icons * icon_step = 100px, gap between groups = 8px
        # Total width: 4*100 + 3*8 = 424px, centered above hotbar
        group_w = num_icons * icon_step - icon_gap  # 99px
        total_w = 4 * group_w + 3 * 10  # 426px
        start_x = hx + (hotbar_w - total_w) // 2

        # Flash timer for low stats
        flash = int(pygame.time.get_ticks() / 300) % 2

        # ---- HP Hearts (left) ----
        hp_x = start_x
        max_hp = p.max_health
        hearts = 10
        hp_per_heart = max_hp / hearts
        for i in range(hearts):
            ix = hp_x + i * icon_step
            heart_val = (i + 1) * hp_per_heart
            if p.health >= heart_val:
                # Full heart - red
                self._draw_heart(ix, bar_y, icon_size, (220, 40, 40), (255, 80, 80))
            elif p.health >= heart_val - hp_per_heart * 0.5:
                # Half heart
                self._draw_heart(ix, bar_y, icon_size, (60, 20, 20), (220, 40, 40), half=True)
            else:
                # Empty heart
                self._draw_heart(ix, bar_y, icon_size, (60, 20, 20), (80, 30, 30))
        # Flash when low HP
        if p.health < max_hp * 0.2 and flash:
            flash_s = pygame.Surface((group_w, icon_size + 2), pygame.SRCALPHA)
            flash_s.fill((255, 0, 0, 60))
            self.screen.blit(flash_s, (hp_x, bar_y))

        # ---- Armor Shields ----
        armor_x = hp_x + group_w + 10
        defense = self._total_defense()
        max_def = 40
        def_per_shield = max_def / hearts
        for i in range(hearts):
            ix = armor_x + i * icon_step
            shield_val = (i + 1) * def_per_shield
            if defense >= shield_val:
                self._draw_shield(ix, bar_y, icon_size, (60, 100, 200), (100, 160, 255))
            elif defense >= shield_val - def_per_shield * 0.5:
                self._draw_shield(ix, bar_y, icon_size, (30, 50, 100), (60, 100, 200), half=True)
            else:
                self._draw_shield(ix, bar_y, icon_size, (30, 30, 45), (50, 50, 70))

        # ---- Hunger Drumsticks ----
        hunger_x = armor_x + group_w + 10
        hunger_per = p.max_hunger / hearts
        for i in range(hearts):
            ix = hunger_x + i * icon_step
            seg_val = (i + 1) * hunger_per
            if p.hunger >= seg_val:
                self._draw_drumstick(ix, bar_y, icon_size, (180, 120, 50), (210, 150, 70))
            elif p.hunger >= seg_val - hunger_per * 0.5:
                self._draw_drumstick(ix, bar_y, icon_size, (100, 70, 30), (180, 120, 50), half=True)
            else:
                self._draw_drumstick(ix, bar_y, icon_size, (50, 35, 20), (70, 50, 30))
        if p.hunger < p.max_hunger * 0.2 and flash:
            flash_s = pygame.Surface((group_w, icon_size + 2), pygame.SRCALPHA)
            flash_s.fill((255, 60, 60, 60))
            self.screen.blit(flash_s, (hunger_x, bar_y))

        # ---- Thirst Water Drops ----
        water_x = hunger_x + group_w + 10
        water_per = p.max_water / hearts
        for i in range(hearts):
            ix = water_x + i * icon_step
            seg_val = (i + 1) * water_per
            if p.water >= seg_val:
                self._draw_drop(ix, bar_y, icon_size, (40, 100, 200), (60, 140, 240))
            elif p.water >= seg_val - water_per * 0.5:
                self._draw_drop(ix, bar_y, icon_size, (25, 60, 120), (40, 100, 200), half=True)
            else:
                self._draw_drop(ix, bar_y, icon_size, (20, 25, 40), (35, 40, 60))
        if p.water < p.max_water * 0.2 and flash:
            flash_s = pygame.Surface((group_w, icon_size + 2), pygame.SRCALPHA)
            flash_s.fill((255, 60, 60, 60))
            self.screen.blit(flash_s, (water_x, bar_y))

    def _draw_heart(self, x, y, s, dark_col, light_col, half=False):
        """Draw a small heart icon (Minecraft-style)."""
        # Simple pixel heart: two circles on top, triangle bottom
        r = s // 4
        cx1, cy1 = x + s//4, y + s//4
        cx2, cy2 = x + 3*s//4, y + s//4
        # Dark outline/background
        pygame.draw.circle(self.screen, dark_col, (cx1, cy1), r)
        pygame.draw.circle(self.screen, dark_col, (cx2, cy2), r)
        pts_d = [(x + 1, cy1 + 1), (x + s//2, y + s), (x + s - 1, cy1 + 1)]
        pygame.draw.polygon(self.screen, dark_col, pts_d)
        if not half:
            # Full: light fill
            pygame.draw.circle(self.screen, light_col, (cx1, cy1), r)
            pygame.draw.circle(self.screen, light_col, (cx2, cy2), r)
            pts_l = [(x + 2, cy1), (x + s//2, y + s - 1), (x + s - 2, cy1)]
            pygame.draw.polygon(self.screen, light_col, pts_l)
        else:
            # Half: fill left half only
            pygame.draw.circle(self.screen, light_col, (cx1, cy1), r)
            # Left half of right circle
            pygame.draw.circle(self.screen, light_col, (cx2, cy2), r)
            # Cover right half with dark
            cover = pygame.Surface((s//2 + 1, s), pygame.SRCALPHA)
            cover.fill((*dark_col, 255))
            self.screen.blit(cover, (x + s//2, y))
            # Re-draw left circle to be safe
            pygame.draw.circle(self.screen, light_col, (cx1, cy1), r)
            pts_l = [(x + 2, cy1), (x + s//2, y + s - 1), (x + s//2, cy1)]
            pygame.draw.polygon(self.screen, light_col, pts_l)

    def _draw_shield(self, x, y, s, dark_col, light_col, half=False):
        """Draw a small shield icon for armor."""
        # Shield shape: wider at top, pointed at bottom
        pts_d = [(x + 1, y), (x + s - 1, y), (x + s - 1, y + s//2),
                 (x + s//2, y + s), (x + 1, y + s//2)]
        pygame.draw.polygon(self.screen, dark_col, pts_d)
        if not half:
            pts_l = [(x + 2, y + 1), (x + s - 2, y + 1), (x + s - 2, y + s//2),
                     (x + s//2, y + s - 1), (x + 2, y + s//2)]
            pygame.draw.polygon(self.screen, light_col, pts_l)
        else:
            # Half: only top portion filled
            mid_y = y + s // 2
            pts_l = [(x + 2, y + 1), (x + s - 2, y + 1), (x + s - 2, mid_y), (x + 2, mid_y)]
            pygame.draw.polygon(self.screen, light_col, pts_l)

    def _draw_drumstick(self, x, y, s, dark_col, light_col, half=False):
        """Draw a small drumstick icon for hunger."""
        # Simple bone + meat shape
        # Bone (horizontal line at bottom)
        pygame.draw.line(self.screen, dark_col, (x + 1, y + s - 2), (x + s - 2, y + s - 2), 1)
        # Knobs
        pygame.draw.circle(self.screen, dark_col, (x + 2, y + s - 3), 1)
        pygame.draw.circle(self.screen, dark_col, (x + s - 2, y + s - 3), 1)
        # Meat (rounded rectangle on top-left)
        meat_rect = pygame.Rect(x + 1, y + 1, s * 2 // 3, s * 2 // 3)
        pygame.draw.ellipse(self.screen, dark_col, meat_rect)
        if not half:
            inner = pygame.Rect(x + 2, y + 2, s * 2 // 3 - 2, s * 2 // 3 - 2)
            pygame.draw.ellipse(self.screen, light_col, inner)
        else:
            inner = pygame.Rect(x + 2, y + 2, (s * 2 // 3 - 2) // 2 + 1, s * 2 // 3 - 2)
            pygame.draw.ellipse(self.screen, light_col, inner)

    def _draw_drop(self, x, y, s, dark_col, light_col, half=False):
        """Draw a small water drop icon for thirst."""
        # Teardrop shape: circle at bottom, point at top
        cx, cy = x + s // 2, y + s * 2 // 3
        r = s // 3
        pygame.draw.circle(self.screen, dark_col, (cx, cy), r)
        # Top point
        pts_d = [(x + s // 2, y), (cx - r, cy - 1), (cx + r, cy - 1)]
        pygame.draw.polygon(self.screen, dark_col, pts_d)
        if not half:
            pygame.draw.circle(self.screen, light_col, (cx, cy), r - 1)
            pts_l = [(x + s // 2, y + 2), (cx - r + 2, cy - 1), (cx + r - 2, cy - 1)]
            pygame.draw.polygon(self.screen, light_col, pts_l)
        else:
            # Half: bottom half filled
            cover = pygame.Surface((s + 2, s // 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(cover, light_col, (r, s // 2 + 1), r - 1)
            self.screen.blit(cover, (cx - r, cy))

    def _draw_hotbar(self):
        slot, gap = 44, 4
        sw, sh = self.screen_w, self.screen_h
        hx = (sw - (10*slot + 9*gap)) // 2; hy = sh - slot - 14
        mx, my = pygame.mouse.get_pos()
        hovered_item = None
        for i in range(10):
            x = hx + i*(slot+gap); r = pygame.Rect(x, hy, slot, slot)
            hovered = r.collidepoint(mx, my)
            bg = (90,110,200) if i==self.selected else ((60,80,120) if hovered else (40,40,60))
            pygame.draw.rect(self.screen, bg, r, border_radius=4)
            pygame.draw.rect(self.screen, (180,180,200), r, 2, border_radius=4)
            item = self.inventory.slots[i]
            if item: self._draw_item_in_slot(item, x, hy, slot)
            if hovered and item:
                hovered_item = item
        if hovered_item:
            self._draw_tooltip(hovered_item, mx, my)

    def _draw_tooltip(self, item, mx, my):
        """Draw a Minecraft-style tooltip near the mouse cursor."""
        if not item:
            return
        iid = item.item_id
        lines = []  # (text, color)
        # Title
        lines.append((get_item_name(iid), (255, 255, 255)))
        # Stats
        if is_tool(iid):
            td = TOOL_DEFS[iid]
            lines.append((f"Tier: {td['tier'].capitalize()}", (170, 170, 200)))
            ttype = td["type"].capitalize()
            lines.append((f"Type: {ttype}", (170, 170, 200)))
            lines.append((f"Damage: {td['damage']}", (100, 255, 100)))
            lines.append((f"Mining Power: {td['mine_mult']}x", (100, 255, 100)))
            if item.durability is not None:
                lines.append((f"Durability: {item.durability}/{td['durability']}", (220, 220, 120)))
        elif is_weapon(iid):
            wd = WEAPON_DEFS[iid]
            lines.append((f"Damage: {wd['damage']}", (100, 255, 100)))
            if item.durability is not None:
                lines.append((f"Durability: {item.durability}/{wd['durability']}", (220, 220, 120)))
            lines.append((f"Ammo: {get_item_name(wd['ammo'])}", (170, 170, 200)))
        elif is_armor(iid):
            ad = ARMOR_DEFS[iid]
            lines.append((f"Defense: +{ad['defense']}", (100, 255, 100)))
            lines.append((f"Tier: {ad['tier'].capitalize()}", (170, 170, 200)))
            slot_names = {0: "Head", 1: "Chest", 2: "Legs", 3: "Feet"}
            slot_type = (iid - 155) % 4
            lines.append((f"Slot: {slot_names.get(slot_type, '?')}", (170, 170, 200)))
        elif is_food(iid):
            fd = FOOD_DEFS[iid]
            lines.append((f"Heals: {fd['heal']} HP", (100, 255, 100)))
        elif is_block(iid):
            bd = BLOCK_DEFS.get(iid, {})
            if bd.get("hardness", 0) > 0:
                lines.append((f"Hardness: {bd['hardness']}", (170, 170, 200)))
            tags = []
            if bd.get("solid"): tags.append("Solid")
            if bd.get("opaque"): tags.append("Opaque")
            if tags:
                lines.append((", ".join(tags), (140, 140, 170)))
        elif is_ammo(iid):
            lines.append(("Ammo for Bow", (170, 170, 200)))
        elif is_misc(iid):
            pass  # just name
        # Stack count
        if item.count > 1:
            lines.append((f"Stack: {item.count}", (130, 130, 155)))
        if len(lines) <= 1:
            return
        # Measure
        pad = 8
        lh = 17
        max_w = 0
        rendered = []
        for text, color in lines:
            s = self.font.render(text, True, color)
            rendered.append(s)
            max_w = max(max_w, s.get_width())
        bg_w = max_w + pad * 2
        bg_h = len(rendered) * lh + pad * 2
        # Position: prefer upper-right of cursor
        tx = mx + 18
        ty = my - bg_h - 6
        if tx + bg_w > self.screen_w: tx = mx - bg_w - 18
        if ty < 0: ty = my + 22
        # Draw background + border
        bg_surf = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        bg_surf.fill((18, 6, 36, 225))
        self.screen.blit(bg_surf, (tx, ty))
        pygame.draw.rect(self.screen, (70, 170, 255), (tx, ty, bg_w, bg_h), 1)
        # Draw text lines
        for i, s in enumerate(rendered):
            self.screen.blit(s, (tx + pad, ty + pad + i * lh))

    def _draw_item_in_slot(self, item, x, y, slot):
        if is_tool(item.item_id) or is_weapon(item.item_id):
            icon = self.tool_icons.get(item.item_id)
            if icon: self.screen.blit(pygame.transform.scale(icon, (28,28)), (x+8, y+8))
            if item.durability is not None:
                max_dur = (TOOL_DEFS[item.item_id]["durability"] if is_tool(item.item_id)
                           else WEAPON_DEFS[item.item_id]["durability"])
                dw = slot - 8
                pygame.draw.rect(self.screen, (40,40,40), (x+4, y+slot-8, dw, 3))
                ratio = max(0, item.durability/max_dur)
                dcol = (80,220,80) if ratio > 0.5 else ((230,200,70) if ratio > 0.2 else (230,70,70))
                pygame.draw.rect(self.screen, dcol, (x+4, y+slot-8, int(dw*ratio), 3))
        elif is_ammo(item.item_id):
            icon = self.tool_icons.get(item.item_id)
            if icon: self.screen.blit(pygame.transform.scale(icon, (28,28)), (x+8, y+8))
        elif is_armor(item.item_id):
            icon = self.tool_icons.get(item.item_id)
            if icon: self.screen.blit(pygame.transform.scale(icon, (28,28)), (x+8, y+8))
        elif is_food(item.item_id) or is_misc(item.item_id):
            icon = self.item_icons.get(item.item_id)
            if icon: self.screen.blit(pygame.transform.scale(icon, (28,28)), (x+8, y+8))
        else:
            tex = self.block_textures.get(item.item_id)
            if tex: self.screen.blit(pygame.transform.scale(tex, (28,28)), (x+8, y+8))
        if item.count > 1:
            ct = self.font.render(str(item.count), True, (255,255,255))
            self.screen.blit(ct, (x+slot-ct.get_width()-4, y+slot-ct.get_height()-2))

    def _get_creative_items(self, category="all"):
        """Return a sorted list of all item IDs available in creative mode, optionally filtered by category."""
        items = []
        if category in ("all", "blocks"):
            for bid in range(1, NUM_BLOCKS):
                bdef = BLOCK_DEFS.get(bid, {})
                if bdef.get("mineable") or bdef.get("solid") or bid in (TORCH, FLOWER, VINE, CACTUS):
                    items.append(bid)
        if category in ("all", "tools"):
            for tid in TOOL_DEFS: items.append(tid)
        if category in ("all", "weapons"):
            items.append(BOW); items.append(ARROW)
        if category in ("all", "foods"):
            for fid in FOOD_DEFS: items.append(fid)
        if category in ("all", "misc"):
            for mid in MISC_DEFS: items.append(mid)
        if category in ("all", "armors"):
            for aid in ARMOR_DEFS: items.append(aid)
        if category == "all":
            items.append(BED)
        return items

    CREATIVE_CATEGORIES = [
        ("all", "All"),
        ("blocks", "Blocks"),
        ("tools", "Tools"),
        ("armors", "Armor"),
        ("weapons", "Weapons"),
        ("foods", "Food"),
        ("misc", "Misc"),
    ]

    def _draw_creative_inventory(self):
        """Draw the creative mode inventory with title on top, category tabs below it, proper gaps."""
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160)); self.screen.blit(overlay, (0, 0))

        mx, my = pygame.mouse.get_pos()

        # --- Title at the very top ---
        title = self.font_big.render("Creative Inventory", True, (130, 255, 130))
        title_y = 10
        self.screen.blit(title, (self.screen_w//2 - title.get_width()//2, title_y))

        # --- Category buttons below the title ---
        tab_y = title_y + title.get_height() + 12  # 12px gap below title
        tab_h = 28
        tab_gap = 6
        # Draw category tabs
        total_tab_w = 0
        tab_rects = []
        for cat_id, cat_name in self.CREATIVE_CATEGORIES:
            tw = self.font.render(cat_name, True, (255,255,255)).get_width() + 20
            tab_rects.append((cat_id, cat_name, tw))
            total_tab_w += tw + tab_gap
        total_tab_w -= tab_gap  # remove trailing gap
        tab_x = (self.screen_w - total_tab_w) // 2
        for cat_id, cat_name, tw in tab_rects:
            r = pygame.Rect(tab_x, tab_y, tw, tab_h)
            hovered = r.collidepoint(mx, my)
            active = self._creative_category == cat_id
            bg = (80, 140, 80) if active else ((60, 90, 60) if hovered else (35, 50, 35))
            pygame.draw.rect(self.screen, bg, r, border_radius=5)
            border_col = (160, 255, 160) if active else (90, 130, 90)
            pygame.draw.rect(self.screen, border_col, r, 2 if active else 1, border_radius=5)
            txt = self.font.render(cat_name, True, (255, 255, 255))
            self.screen.blit(txt, (r.centerx - txt.get_width()//2, r.centery - txt.get_height()//2))
            tab_x += tw + tab_gap

        # --- Item grid below category tabs with proper gap ---
        section_gap = 16  # gap between category tabs and item grid
        all_items = self._get_creative_items(self._creative_category)
        slot_size, gap = 36, 2
        cols = 20
        grid_w = cols * (slot_size + gap) - gap
        grid_x = (self.screen_w - grid_w) // 2
        grid_y = tab_y + tab_h + section_gap
        # 5 visible rows
        visible_rows = 5
        visible_h = visible_rows * (slot_size + gap) - gap
        total_rows = (len(all_items) + cols - 1) // cols
        max_scroll = max(0, total_rows - visible_rows)
        self._creative_scroll_target = max(0, min(max_scroll, self._creative_scroll_target))
        self._creative_scroll += (self._creative_scroll_target - self._creative_scroll) * 0.25
        scroll_y = self._creative_scroll * (slot_size + gap)

        hovered_item = None

        # Panel background
        panel_rect = pygame.Rect(grid_x - 6, grid_y - 6, grid_w + 12, visible_h + 12)
        pygame.draw.rect(self.screen, (25, 35, 25), panel_rect, border_radius=6)
        pygame.draw.rect(self.screen, (90, 130, 90), panel_rect, 2, border_radius=6)
        # Clip
        prev_clip = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(grid_x, grid_y, grid_w, visible_h))

        first_row = max(0, int(self._creative_scroll) - 1)
        last_row = min(total_rows, int(self._creative_scroll) + visible_rows + 1)
        for row in range(first_row, last_row):
            for col in range(cols):
                i = row * cols + col
                if i >= len(all_items): break
                item_id = all_items[i]
                sx = grid_x + col * (slot_size + gap)
                sy = grid_y + row * (slot_size + gap) - int(scroll_y)
                r = pygame.Rect(sx, sy, slot_size, slot_size)
                if sy + slot_size < grid_y or sy > grid_y + visible_h:
                    continue
                hovered = r.collidepoint(mx, my)
                bg = (70, 100, 70) if hovered else (40, 55, 40)
                pygame.draw.rect(self.screen, bg, r, border_radius=3)
                pygame.draw.rect(self.screen, (100, 160, 100), r, 1, border_radius=3)
                if is_tool(item_id) or is_weapon(item_id) or is_ammo(item_id) or is_armor(item_id):
                    icon = self.tool_icons.get(item_id)
                    if icon: self.screen.blit(pygame.transform.scale(icon, (22, 22)), (sx + 7, sy + 7))
                elif is_food(item_id) or is_misc(item_id):
                    icon = self.item_icons.get(item_id)
                    if icon: self.screen.blit(pygame.transform.scale(icon, (22, 22)), (sx + 7, sy + 7))
                else:
                    tex = self.block_textures.get(item_id)
                    if tex: self.screen.blit(pygame.transform.scale(tex, (22, 22)), (sx + 7, sy + 7))
                if hovered:
                    hovered_item = ItemStack(item_id, 1)

        self.screen.set_clip(prev_clip)

        # Scroll bar
        if total_rows > visible_rows:
            bar_x = grid_x + grid_w + 10
            bar_y_pos = grid_y
            bar_h = visible_h
            pygame.draw.rect(self.screen, (40, 50, 40), (bar_x, bar_y_pos, 8, bar_h), border_radius=4)
            thumb_h = max(20, int(bar_h * visible_rows / total_rows))
            thumb_y = bar_y_pos + int((bar_h - thumb_h) * (self._creative_scroll / max(1, max_scroll)))
            pygame.draw.rect(self.screen, (130, 200, 130), (bar_x, thumb_y, 8, thumb_h), border_radius=4)

        # Item count label
        count_txt = self.font_sm.render(f"{len(all_items)} items", True, (180, 220, 180))
        self.screen.blit(count_txt, (grid_x + grid_w - count_txt.get_width(), grid_y - 18))

        # Player inventory at bottom
        inv_label = self.font.render("Your Inventory", True, (255, 230, 130))
        inv_section_gap = 36  # proper gap between item grid and player inventory
        inv_y = grid_y + visible_h + inv_section_gap
        self.screen.blit(inv_label, (grid_x, inv_y - 20))
        slot_size2, gap2 = 44, 2; cols2, rows2 = 10, 5
        for row in range(rows2):
            for col in range(cols2):
                idx = row * cols2 + col
                sx = grid_x + col * (slot_size2 + gap2)
                sy = inv_y + row * (slot_size2 + gap2)
                r = pygame.Rect(sx, sy, slot_size2, slot_size2)
                hovered = r.collidepoint(mx, my)
                bg2 = (60, 60, 90) if idx < 10 else ((70, 70, 100) if hovered else (50, 50, 70))
                pygame.draw.rect(self.screen, bg2, r, border_radius=4)
                pygame.draw.rect(self.screen, (120, 120, 150), r, 2, border_radius=4)
                item = self.inventory.slots[idx]
                if item:
                    self._draw_item_in_slot(item, sx, sy, slot_size2)
                    if hovered: hovered_item = item

        # Held item
        if self.inventory.held:
            mx2, my2 = pygame.mouse.get_pos()
            self._draw_item_in_slot(self.inventory.held, mx2 - slot_size2 // 2, my2 - slot_size2 // 2, slot_size2)
            if hovered_item is None: hovered_item = self.inventory.held
        if hovered_item:
            mx3, my3 = pygame.mouse.get_pos()
            self._draw_tooltip(hovered_item, mx3, my3)

        hint = self.font.render("LMB: pick up stack | RMB: pick up 1 | Wheel: scroll | E: close", True, (200, 200, 200))
        sw, sh = self.screen_w, self.screen_h
        self.screen.blit(hint, (sw // 2 - hint.get_width() // 2, sh - 30))
        cm = self.font.render("[CREATIVE MODE - F12 to exit]", True, (130, 255, 130))
        self.screen.blit(cm, (sw // 2 - cm.get_width() // 2, sh - 50))

    def _handle_creative_click(self, event):
        """Handle clicks in the creative inventory."""
        mx, my = event.pos

        # Check category tab clicks first (must match _draw_creative_inventory layout)
        title = self.font_big.render("Creative Inventory", True, (130, 255, 130))
        title_y = 10
        tab_y = title_y + title.get_height() + 12
        tab_h = 28
        tab_gap = 6
        total_tab_w = 0
        tab_rects = []
        for cat_id, cat_name in self.CREATIVE_CATEGORIES:
            tw = self.font.render(cat_name, True, (255,255,255)).get_width() + 20
            tab_rects.append((cat_id, cat_name, tw))
            total_tab_w += tw + tab_gap
        total_tab_w -= tab_gap
        tab_x = (self.screen_w - total_tab_w) // 2
        for cat_id, cat_name, tw in tab_rects:
            r = pygame.Rect(tab_x, tab_y, tw, tab_h)
            if r.collidepoint(mx, my):
                if self._creative_category != cat_id:
                    self._creative_category = cat_id
                    self._creative_scroll = 0.0
                    self._creative_scroll_target = 0
                return
            tab_x += tw + tab_gap

        all_items = self._get_creative_items(self._creative_category)
        slot_size, gap = 36, 2
        cols = 20
        grid_w = cols * (slot_size + gap) - gap
        grid_x = (self.screen_w - grid_w) // 2
        section_gap = 16
        grid_y = tab_y + tab_h + section_gap
        visible_rows = 5
        visible_h = visible_rows * (slot_size + gap) - gap
        scroll_y = self._creative_scroll * (slot_size + gap)

        # Click on the scroll bar?
        bar_x = grid_x + grid_w + 10
        if len(all_items) > visible_rows * cols and bar_x <= mx <= bar_x + 8 and grid_y <= my <= grid_y + visible_h:
            total_rows = (len(all_items) + cols - 1) // cols
            max_scroll = max(0, total_rows - visible_rows)
            thumb_h = max(20, int(visible_h * visible_rows / total_rows))
            t = (my - grid_y - thumb_h / 2) / max(1, visible_h - thumb_h)
            self._creative_scroll_target = max(0, min(max_scroll, int(t * max_scroll)))
            return

        # Click inside the scrollable grid?
        if grid_x <= mx <= grid_x + grid_w and grid_y <= my <= grid_y + visible_h:
            col = (mx - grid_x) // (slot_size + gap)
            row_in_view = (my - grid_y + int(scroll_y)) // (slot_size + gap)
            i = row_in_view * cols + col
            if 0 <= i < len(all_items):
                item_id = all_items[i]
                if event.button == 1:
                    qty = 99 if item_id not in NON_STACKABLE else 1
                    dur = None
                    if is_tool(item_id):
                        dur = TOOL_DEFS[item_id]["durability"]
                    elif is_weapon(item_id):
                        dur = WEAPON_DEFS[item_id]["durability"]
                    elif is_armor(item_id):
                        dur = 999
                    self.inventory.held = ItemStack(item_id, qty, dur)
                elif event.button == 3:
                    dur = None
                    if is_tool(item_id):
                        dur = TOOL_DEFS[item_id]["durability"]
                    elif is_weapon(item_id):
                        dur = WEAPON_DEFS[item_id]["durability"]
                    elif is_armor(item_id):
                        dur = 999
                    self.inventory.held = ItemStack(item_id, 1, dur)
                return

        # Check player inventory clicks (bottom section)
        inv_section_gap = 36
        inv_y = grid_y + visible_h + inv_section_gap
        slot_size2, gap2 = 44, 2; cols2, rows2 = 10, 5
        for row in range(rows2):
            for col in range(cols2):
                idx = row * cols2 + col
                sx = grid_x + col * (slot_size2 + gap2)
                sy = inv_y + row * (slot_size2 + gap2)
                if sx <= mx <= sx + slot_size2 and sy <= my <= sy + slot_size2:
                    self._click_slot(idx, event.button)
                    return

    def _draw_inventory_panel(self, recipes, title_text):
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((0,0,0,160)); self.screen.blit(overlay, (0,0))
        title = self.font_big.render(f"{title_text} - {self.world_name}", True, (255,255,255))
        self.screen.blit(title, (self.screen_w//2 - title.get_width()//2, 60))
        slot_size, gap = 44, 2; cols, rows = 10, 5
        grid_w = cols*slot_size + (cols-1)*gap
        sw = self.screen_w
        grid_x = (sw - grid_w)//2 - 120; grid_y = 120
        mx, my = pygame.mouse.get_pos()
        hovered_item = None
        # Armor slots (left side) - Minecraft style
        armor_x = grid_x - 70
        armor_label = self.font.render("Armor", True, (255, 230, 130))
        self.screen.blit(armor_label, (armor_x, grid_y - 22))
        armor_names = ["Helmet", "Chest", "Legs", "Boots"]
        for ai in range(4):
            ax = armor_x
            ay = grid_y + ai * (slot_size + gap)
            ar = pygame.Rect(ax, ay, slot_size, slot_size)
            a_hovered = ar.collidepoint(mx, my)
            bg = (70, 70, 100) if a_hovered else (50, 50, 70)
            pygame.draw.rect(self.screen, bg, ar, border_radius=4)
            pygame.draw.rect(self.screen, (120, 120, 150), ar, 2, border_radius=4)
            if self.armor[ai]:
                self._draw_item_in_slot(self.armor[ai], ax, ay, slot_size)
                if a_hovered: hovered_item = self.armor[ai]
            # Slot label
            al = self.font_sm.render(armor_names[ai][:3], True, (150, 150, 170))
            self.screen.blit(al, (ax + 2, ay + slot_size - 12))
        for row in range(rows):
            for col in range(cols):
                idx = row*cols + col
                sx = grid_x + col*(slot_size+gap); sy = grid_y + row*(slot_size+gap)
                r = pygame.Rect(sx, sy, slot_size, slot_size)
                hovered = r.collidepoint(mx, my)
                bg = (60,60,90) if idx < 10 else ((70,70,100) if hovered else (50,50,70))
                pygame.draw.rect(self.screen, bg, r, border_radius=4)
                pygame.draw.rect(self.screen, (120,120,150), r, 2, border_radius=4)
                item = self.inventory.slots[idx]
                if item:
                    self._draw_item_in_slot(item, sx, sy, slot_size)
                    if hovered: hovered_item = item
        recipe_x = grid_x + cols*(slot_size+gap) + 30
        self.screen.blit(self.font.render("Crafting", True, (255,255,255)), (recipe_x, grid_y-22))
        for i, recipe in enumerate(recipes):
            rx = recipe_x + (i%2)*230; ry = grid_y + (i//2)*36; rw, rh = 226, 33
            craftable = self.inventory.has_materials(recipe["materials"])
            pygame.draw.rect(self.screen, (30,80,30) if craftable else (60,30,30), (rx,ry,rw,rh), border_radius=3)
            pygame.draw.rect(self.screen, (150,150,180), (rx,ry,rw,rh), 1, border_radius=3)
            rid, rcnt = recipe["result"]
            if is_tool(rid) or is_weapon(rid) or is_ammo(rid) or is_armor(rid):
                icon = self.tool_icons.get(rid)
                if icon: self.screen.blit(pygame.transform.scale(icon, (20,20)), (rx+4, ry+6))
            elif is_food(rid) or is_misc(rid):
                icon = self.item_icons.get(rid)
                if icon: self.screen.blit(pygame.transform.scale(icon, (20,20)), (rx+4, ry+6))
            else:
                tex = self.block_textures.get(rid)
                if tex: self.screen.blit(pygame.transform.scale(tex, (20,20)), (rx+4, ry+6))
            name = recipe["name"] + (f" x{rcnt}" if rcnt > 1 else "")
            max_name_w = rw - 32
            name_surf = self.font.render(name, True, (255,255,255))
            if name_surf.get_width() > max_name_w:
                while name_surf.get_width() > max_name_w - 10 and len(name) > 4:
                    name = name[:-4] + ".."
                    name_surf = self.font.render(name, True, (255,255,255))
            self.screen.blit(name_surf, (rx+28, ry+3))
            mats = " ".join(f"{get_item_name(m)}x{q}" for m,q in recipe["materials"])
            mats_surf = self.font_sm.render(mats, True, (200,200,200))
            if mats_surf.get_width() > max_name_w:
                while mats_surf.get_width() > max_name_w - 10 and len(mats) > 4:
                    mats = mats[:-4] + ".."
                    mats_surf = self.font_sm.render(mats, True, (200,200,200))
            self.screen.blit(mats_surf, (rx+28, ry+18))
        if self.inventory.held:
            mx2, my2 = pygame.mouse.get_pos()
            self._draw_item_in_slot(self.inventory.held, mx2-slot_size//2, my2-slot_size//2, slot_size)
            if hovered_item is None: hovered_item = self.inventory.held
        if hovered_item:
            mx3, my3 = pygame.mouse.get_pos()
            self._draw_tooltip(hovered_item, mx3, my3)
        hint = self.font.render("LMB: pick up / place | RMB: interact/swap | Click recipe: craft | E: close", True, (200,200,200))
        self.screen.blit(hint, (self.screen_w//2 - hint.get_width()//2, self.screen_h-30))

    # ---------- Furnace UI (Minecraft-like) ----------
    def _is_fuel(self, item_id):
        """Check if an item can be used as furnace fuel."""
        return item_id in FUEL_BURN_TIME and FUEL_BURN_TIME[item_id] > 0

    def _find_furnace_recipe(self, input_item_id):
        """Find a furnace recipe that matches the input item. Returns (result_id, result_count) or None."""
        for recipe in RECIPES_FURNACE:
            mat_id, mat_qty = recipe["materials"][0]
            if mat_id == input_item_id:
                return recipe["result"]
        return None

    def _update_furnace(self, dt):
        """Update furnace cooking state. Called from _update when furnace UI is open."""
        # If no input, stop cooking
        if self.furnace_input is None:
            self.furnace_active = False
            self.furnace_cook_time = 0.0
            return

        # Check if there's a valid recipe for the input
        recipe_result = self._find_furnace_recipe(self.furnace_input.item_id)
        if recipe_result is None:
            self.furnace_active = False
            self.furnace_cook_time = 0.0
            return

        result_id, result_count = recipe_result

        # Check if output slot can accept the result
        if self.furnace_output is not None:
            if self.furnace_output.item_id != result_id:
                self.furnace_active = False
                return  # output blocked by different item
            if self.furnace_output.count >= 99:
                self.furnace_active = False
                return  # output full

        # Need fuel to cook
        if self.furnace_fuel_time <= 0:
            # Try to consume fuel
            if self.furnace_fuel is not None and self._is_fuel(self.furnace_fuel.item_id):
                burn_time = FUEL_BURN_TIME.get(self.furnace_fuel.item_id, 0)
                self.furnace_fuel_time = burn_time
                self.furnace_fuel.count -= 1
                if self.furnace_fuel.count <= 0:
                    self.furnace_fuel = None
            else:
                self.furnace_active = False
                return

        # Furnace is active - burn fuel and cook
        self.furnace_active = True
        self.furnace_fuel_time -= dt
        self.furnace_cook_time += dt / FURNACE_COOK_TIME

        # When cooking is complete
        if self.furnace_cook_time >= 1.0:
            self.furnace_cook_time = 0.0
            # Consume one input item
            self.furnace_input.count -= 1
            if self.furnace_input.count <= 0:
                self.furnace_input = None
            # Produce output
            if self.furnace_output is None:
                self.furnace_output = ItemStack(result_id, result_count)
            else:
                self.furnace_output.count += result_count

    def _draw_furnace_ui(self):
        """Draw Minecraft-like furnace UI with input slot, fuel slot, fire animation, output slot,
        and player inventory grid below."""
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((0,0,0,160)); self.screen.blit(overlay, (0,0))

        title = self.font_big.render("Furnace", True, (255,255,255))
        self.screen.blit(title, (self.screen_w//2 - title.get_width()//2, 50))

        slot_size = 44; gap = 2
        # Furnace interface layout:
        #   [Input]  [Fire]  [Output]
        #   [Fuel ]
        furnace_x = self.screen_w//2 - 100
        furnace_y = 100
        mx, my = pygame.mouse.get_pos()
        hovered_item = None

        # --- Furnace slots ---
        slot_bg = (50, 45, 40)
        slot_border = (180, 140, 80)

        # Input slot (top-left)
        input_rect = pygame.Rect(furnace_x, furnace_y, slot_size, slot_size)
        inp_hover = input_rect.collidepoint(mx, my)
        pygame.draw.rect(self.screen, (70, 60, 50) if inp_hover else slot_bg, input_rect, border_radius=4)
        pygame.draw.rect(self.screen, slot_border, input_rect, 2, border_radius=4)
        lbl = self.font_sm.render("Input", True, (200, 180, 130))
        self.screen.blit(lbl, (input_rect.x + 4, input_rect.y + slot_size + 2))
        if self.furnace_input:
            self._draw_item_in_slot(self.furnace_input, input_rect.x, input_rect.y, slot_size)
            if inp_hover: hovered_item = self.furnace_input

        # Fire animation (center, between input and output)
        fire_x = furnace_x + slot_size + 10
        fire_y = furnace_y
        fire_rect = pygame.Rect(fire_x, fire_y, 30, slot_size)
        pygame.draw.rect(self.screen, (40, 35, 30), fire_rect, border_radius=3)
        if self.furnace_active and self.furnace_fuel_time > 0:
            # Animated fire
            t = pygame.time.get_ticks() / 1000.0
            fire_h = int(slot_size * 0.7 * (0.7 + 0.3 * math.sin(t * 8)))
            # Fuel bar background
            pygame.draw.rect(self.screen, (30, 25, 20), (fire_x+4, fire_y+4, 22, slot_size-8))
            # Fuel bar fill
            fuel_frac = min(1.0, self.furnace_fuel_time / 15.0)
            bar_h = int((slot_size - 8) * fuel_frac)
            pygame.draw.rect(self.screen, (200, 100, 30), (fire_x+4, fire_y + slot_size - 4 - bar_h, 22, bar_h))
            # Fire flames
            for i in range(3):
                fx = fire_x + 8 + i * 5
                fy_base = fire_y + slot_size - 8
                fh = fire_h // 3 + int(math.sin(t * 10 + i * 2) * 3)
                # Outer flame (red-orange)
                pygame.draw.polygon(self.screen, (255, 120 + int(30 * math.sin(t*6+i)), 30),
                    [(fx, fy_base), (fx+3, fy_base - fh), (fx+6, fy_base)])
                # Inner flame (yellow)
                pygame.draw.polygon(self.screen, (255, 220, 60),
                    [(fx+1, fy_base), (fx+3, fy_base - fh//2), (fx+5, fy_base)])
        else:
            # Empty fire slot indicator
            pygame.draw.rect(self.screen, (50, 45, 40), (fire_x+4, fire_y+4, 22, slot_size-8))

        # Output slot (top-right)
        output_rect = pygame.Rect(fire_x + 36, furnace_y, slot_size, slot_size)
        out_hover = output_rect.collidepoint(mx, my)
        pygame.draw.rect(self.screen, (70, 60, 50) if out_hover else slot_bg, output_rect, border_radius=4)
        pygame.draw.rect(self.screen, slot_border, output_rect, 2, border_radius=4)
        # Arrow from fire to output
        arrow_y = furnace_y + slot_size // 2
        pygame.draw.polygon(self.screen, (180, 160, 120),
            [(fire_x + 32, arrow_y - 4), (fire_x + 36, arrow_y), (fire_x + 32, arrow_y + 4)])
        lbl = self.font_sm.render("Output", True, (200, 180, 130))
        self.screen.blit(lbl, (output_rect.x, output_rect.y + slot_size + 2))
        if self.furnace_output:
            self._draw_item_in_slot(self.furnace_output, output_rect.x, output_rect.y, slot_size)
            if out_hover: hovered_item = self.furnace_output

        # Fuel slot (below input)
        fuel_rect = pygame.Rect(furnace_x, furnace_y + slot_size + 20, slot_size, slot_size)
        fuel_hover = fuel_rect.collidepoint(mx, my)
        pygame.draw.rect(self.screen, (70, 60, 50) if fuel_hover else slot_bg, fuel_rect, border_radius=4)
        pygame.draw.rect(self.screen, slot_border, fuel_rect, 2, border_radius=4)
        lbl = self.font_sm.render("Fuel", True, (200, 180, 130))
        self.screen.blit(lbl, (fuel_rect.x + 6, fuel_rect.y + slot_size + 2))
        if self.furnace_fuel:
            self._draw_item_in_slot(self.furnace_fuel, fuel_rect.x, fuel_rect.y, slot_size)
            if fuel_hover: hovered_item = self.furnace_fuel

        # Cook progress bar (below fire/output area)
        if self.furnace_active:
            prog_x = furnace_x
            prog_y = furnace_y + 2 * (slot_size + 20) + 4
            prog_w = 2 * slot_size + 46
            prog_h = 8
            pygame.draw.rect(self.screen, (40, 35, 30), (prog_x, prog_y, prog_w, prog_h), border_radius=3)
            fill_w = int(prog_w * self.furnace_cook_time)
            if fill_w > 0:
                pygame.draw.rect(self.screen, (220, 160, 60), (prog_x, prog_y, fill_w, prog_h), border_radius=3)
            pygame.draw.rect(self.screen, slot_border, (prog_x, prog_y, prog_w, prog_h), 1, border_radius=3)

        # --- Player inventory grid (below furnace) ---
        cols, rows = 10, 5
        grid_w = cols * slot_size + (cols - 1) * gap
        grid_x = (self.screen_w - grid_w) // 2 - 50
        grid_y = furnace_y + 2 * (slot_size + 20) + 30
        player_label = self.font.render("Your Inventory", True, (255, 230, 130))
        self.screen.blit(player_label, (grid_x, grid_y - 22))
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                sx = grid_x + col * (slot_size + gap)
                sy = grid_y + row * (slot_size + gap)
                r = pygame.Rect(sx, sy, slot_size, slot_size)
                hovered = r.collidepoint(mx, my)
                bg = (60, 60, 90) if idx < 10 else ((70, 70, 100) if hovered else (50, 50, 70))
                pygame.draw.rect(self.screen, bg, r, border_radius=4)
                pygame.draw.rect(self.screen, (120, 120, 150), r, 2, border_radius=4)
                item = self.inventory.slots[idx]
                if item:
                    self._draw_item_in_slot(item, sx, sy, slot_size)
                    if hovered: hovered_item = item

        # Held item follows cursor
        if self.inventory.held:
            mx2, my2 = pygame.mouse.get_pos()
            self._draw_item_in_slot(self.inventory.held, mx2 - slot_size // 2, my2 - slot_size // 2, slot_size)
            if hovered_item is None: hovered_item = self.inventory.held

        # Tooltip
        if hovered_item:
            mx3, my3 = pygame.mouse.get_pos()
            self._draw_tooltip(hovered_item, mx3, my3)

        hint = self.font.render("Click slots to move items | Fuel: wood, coal, planks, sticks | ESC: close", True, (200, 200, 200))
        self.screen.blit(hint, (self.screen_w // 2 - hint.get_width() // 2, self.screen_h - 30))

    def _handle_furnace_click(self, mx, my):
        """Handle mouse clicks in the furnace UI. Returns True if click was consumed."""
        slot_size = 44
        furnace_x = self.screen_w // 2 - 100
        furnace_y = 100
        fire_x = furnace_x + slot_size + 10

        input_rect = pygame.Rect(furnace_x, furnace_y, slot_size, slot_size)
        fuel_rect = pygame.Rect(furnace_x, furnace_y + slot_size + 20, slot_size, slot_size)
        output_rect = pygame.Rect(fire_x + 36, furnace_y, slot_size, slot_size)

        held = self.inventory.held

        # Click on output slot - take output
        if output_rect.collidepoint(mx, my):
            if self.furnace_output and held is None:
                self.inventory.held = self.furnace_output
                self.furnace_output = None
            elif self.furnace_output and held and held.item_id == self.furnace_output.item_id:
                total = held.count + self.furnace_output.count
                if not (held.item_id in NON_STACKABLE):
                    held.count = min(99, total)
                    leftover = total - held.count
                    self.furnace_output.count = leftover
                    if leftover <= 0: self.furnace_output = None
            return True

        # Click on input slot
        if input_rect.collidepoint(mx, my):
            if held is None and self.furnace_input:
                # Pick up input
                self.inventory.held = self.furnace_input
                self.furnace_input = None
            elif held and self.furnace_input is None:
                # Place held into input if it's a valid furnace input
                if self._find_furnace_recipe(held.item_id) is not None:
                    self.furnace_input = held
                    self.inventory.held = None
            elif held and self.furnace_input and held.item_id == self.furnace_input.item_id and held.item_id not in NON_STACKABLE:
                # Stack
                total = held.count + self.furnace_input.count
                self.furnace_input.count = min(99, total)
                held.count = total - self.furnace_input.count
                if held.count <= 0: self.inventory.held = None
            return True

        # Click on fuel slot
        if fuel_rect.collidepoint(mx, my):
            if held is None and self.furnace_fuel:
                self.inventory.held = self.furnace_fuel
                self.furnace_fuel = None
            elif held and self.furnace_fuel is None:
                # Place held into fuel if it's valid fuel
                if self._is_fuel(held.item_id):
                    self.furnace_fuel = held
                    self.inventory.held = None
            elif held and self.furnace_fuel and held.item_id == self.furnace_fuel.item_id and held.item_id not in NON_STACKABLE:
                total = held.count + self.furnace_fuel.count
                self.furnace_fuel.count = min(99, total)
                held.count = total - self.furnace_fuel.count
                if held.count <= 0: self.inventory.held = None
            return True

        # Check player inventory grid clicks
        cols, rows_inv = 10, 5
        gap = 2
        grid_w = cols * slot_size + (cols - 1) * gap
        grid_x = (self.screen_w - grid_w) // 2 - 50
        grid_y = furnace_y + 2 * (slot_size + 20) + 30
        for row in range(rows_inv):
            for col in range(cols):
                idx = row * cols + col
                sx = grid_x + col * (slot_size + gap)
                sy = grid_y + row * (slot_size + gap)
                r = pygame.Rect(sx, sy, slot_size, slot_size)
                if r.collidepoint(mx, my):
                    if held is None:
                        # Pick up
                        item = self.inventory.slots[idx]
                        if item:
                            self.inventory.held = item
                            self.inventory.slots[idx] = None
                    else:
                        # Place/swap
                        existing = self.inventory.slots[idx]
                        if existing is None:
                            self.inventory.slots[idx] = held
                            self.inventory.held = None
                        elif existing.item_id == held.item_id and held.item_id not in NON_STACKABLE:
                            total = existing.count + held.count
                            existing.count = min(99, total)
                            held.count = total - existing.count
                            if held.count <= 0: self.inventory.held = None
                        else:
                            self.inventory.slots[idx] = held
                            self.inventory.held = existing
                    return True
        return False

    def _draw_chest_ui(self):
        """Draw the chest storage UI with chest slots on top and player inventory on bottom."""
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((0,0,0,160)); self.screen.blit(overlay, (0,0))
        title = self.font_big.render("Chest Storage", True, (255,255,255))
        self.screen.blit(title, (self.screen_w//2 - title.get_width()//2, 80))
        slot_size, gap = 44, 2
        cols = 10
        grid_w = cols*slot_size + (cols-1)*gap
        grid_x = (self.screen_w - grid_w)//2 - 120
        mx, my = pygame.mouse.get_pos()
        hovered_item = None
        # Chest inventory (top, 5 rows = 50 slots)
        chest_label = self.font.render("Chest", True, (255,230,130))
        self.screen.blit(chest_label, (grid_x, 100))
        chest_y = 120; chest_rows = 5
        for row in range(chest_rows):
            for col in range(cols):
                idx = row*cols + col
                sx = grid_x + col*(slot_size+gap); sy = chest_y + row*(slot_size+gap)
                r = pygame.Rect(sx, sy, slot_size, slot_size)
                hovered = r.collidepoint(mx, my)
                pygame.draw.rect(self.screen, (70,60,40) if hovered else (55,45,30), r, border_radius=4)
                pygame.draw.rect(self.screen, (180,150,80), r, 2, border_radius=4)
                citem = self.chest_inventory.slots[idx] if (self.chest_inventory and idx < len(self.chest_inventory.slots)) else None
                if citem:
                    self._draw_item_in_slot(citem, sx, sy, slot_size)
                    if hovered: hovered_item = citem
        # Player inventory (bottom, 5 rows)
        player_label = self.font.render("Your Inventory", True, (255,230,130))
        self.screen.blit(player_label, (grid_x, 370))
        player_y = 390; player_rows = 5
        for row in range(player_rows):
            for col in range(cols):
                idx = row*cols + col
                sx = grid_x + col*(slot_size+gap); sy = player_y + row*(slot_size+gap)
                r = pygame.Rect(sx, sy, slot_size, slot_size)
                hovered = r.collidepoint(mx, my)
                bg = (60,60,90) if idx < 10 else ((70,70,100) if hovered else (50,50,70))
                pygame.draw.rect(self.screen, bg, r, border_radius=4)
                pygame.draw.rect(self.screen, (120,120,150), r, 2, border_radius=4)
                item = self.inventory.slots[idx]
                if item:
                    self._draw_item_in_slot(item, sx, sy, slot_size)
                    if hovered: hovered_item = item
        # Held item
        if self.inventory.held:
            mx2, my2 = pygame.mouse.get_pos()
            self._draw_item_in_slot(self.inventory.held, mx2-slot_size//2, my2-slot_size//2, slot_size)
            if hovered_item is None: hovered_item = self.inventory.held
        if hovered_item:
            mx3, my3 = pygame.mouse.get_pos()
            self._draw_tooltip(hovered_item, mx3, my3)
        hint = self.font.render("Click items to move between chest and inventory | ESC: close", True, (200,200,200))
        self.screen.blit(hint, (self.screen_w//2 - hint.get_width()//2, self.screen_h-30))

    def _draw_map(self):
        # ── Apply drag offset each frame (set by event handlers) ──
        if self._map_dragging and self._map_drag_button is not None:
            mx, my = pygame.mouse.get_pos()
            dx = (mx - self._map_drag_start[0]) / self._map_zoom
            dy = (my - self._map_drag_start[1]) / self._map_zoom
            if abs(mx - self._map_drag_start[0]) + abs(my - self._map_drag_start[1]) > 3:
                self._map_drag_moved = True
            self._map_offset_x = self._map_drag_offset_start[0] - dx
            self._map_offset_y = self._map_drag_offset_start[1] - dy

        # ── Rebuild minimap ONLY when not dragging (avoids frame-blocking) ──
        if (self._minimap_dirty or self._minimap_surface is None) and not self._map_dragging:
            self._minimap_surface = self._build_minimap_surface()

        ms = self._minimap_surface
        if ms is None:
            # First frame: no surface yet, show loading
            self.screen.fill((20, 20, 30))
            txt = self.font_big.render("Building map...", True, (200, 200, 200))
            self.screen.blit(txt, (self.screen_w//2 - txt.get_width()//2, self.screen_h//2 - 10))
            return

        ww, wh = ms.get_size()  # = (world.w, world.h) in pixels (1px per tile)
        zoom = self._map_zoom

        # ── View center in tile coordinates ──
        # _map_offset is in screen-pixel units at current zoom, convert to tile units
        center_tx = self.player.x / TILE - self._map_offset_x / zoom
        center_ty = self.player.y / TILE - self._map_offset_y / zoom

        # How many tiles fit on screen at current zoom
        # At zoom=1: 1 tile = 1 pixel on screen, so VIEW_W tiles fit horizontally
        view_tiles_x = VIEW_W / zoom
        view_tiles_y = VIEW_H / zoom

        # Source rect in minimap pixel coords (1px = 1 tile)
        src_w = max(1, min(ww, int(view_tiles_x)))
        src_h = max(1, min(wh, int(view_tiles_y)))
        src_cx = int(center_tx)
        src_cy = int(center_ty)

        src_x = src_cx - src_w // 2
        src_y = src_cy - src_h // 2

        # Clamp to minimap bounds
        src_x = max(0, min(ww - src_w, src_x))
        src_y = max(0, min(wh - src_h, src_y))

        # Scale the visible region to fill the screen
        try:
            src_rect = pygame.Rect(src_x, src_y, src_w, src_h)
            surf_rect = ms.get_rect()
            src_rect.clamp_ip(surf_rect)
            src_rect = src_rect.clip(surf_rect)
            if src_rect.w > 0 and src_rect.h > 0:
                scaled = pygame.transform.scale(ms.subsurface(src_rect), (VIEW_W, VIEW_H))
                self.screen.blit(scaled, (0, 0))
            else:
                self.screen.fill((0, 0, 0))
        except Exception:
            self.screen.fill((0, 0, 0))

        # ── Player marker ──
        player_tx = int(self.player.x / TILE)
        player_ty = int(self.player.y / TILE)
        screen_px = int((player_tx - src_x) / src_w * VIEW_W)
        screen_py = int((player_ty - src_y) / src_h * VIEW_H)
        if 0 <= screen_px < VIEW_W and 0 <= screen_py < VIEW_H:
            r = max(3, int(6 * min(zoom, 5)))
            pygame.draw.circle(self.screen, (255, 50, 50), (screen_px, screen_py), r)
            pygame.draw.circle(self.screen, (255, 255, 255), (screen_px, screen_py), r, 2)

        # ── Title bar ──
        title_bg = pygame.Surface((VIEW_W, 36), pygame.SRCALPHA)
        title_bg.fill((0, 0, 0, 160))
        self.screen.blit(title_bg, (0, 0))
        title = self.font_big.render(
            f"World Map - {self.world_name} (Seed: {self.seed}) | Zoom: {zoom:.1f}x",
            True, (255, 255, 255))
        self.screen.blit(title, (VIEW_W // 2 - title.get_width() // 2, 8))
        hint = self.font_sm.render(
            "Scroll: zoom | MMB drag: pan | MMB click: reset | ESC: close",
            True, (180, 180, 200))
        self.screen.blit(hint, (VIEW_W // 2 - hint.get_width() // 2, VIEW_H - 22))

        if not self.map_open:
            self._minimap_surface = None

    def _draw_floats(self):
        for f in self.floats:
            alpha = max(0, min(1, f["t"]/f["max"]))
            if f.get("big"):
                txt = self.font_big.render(f["text"], True, (255,255,255))
                r = txt.get_rect(center=(self.screen_w//2, 60))
                sh = self.font_big.render(f["text"], True, (0,0,0))
                sh.set_alpha(int(180*alpha)); txt.set_alpha(int(255*alpha))
                self.screen.blit(sh, (r.x+1, r.y+1)); self.screen.blit(txt, r)
            else:
                txt = self.font.render(f["text"], True, f.get("color", (255,255,255)))
                sx, sy = int(f["x"]-self.cam_x), int(f["y"]-self.cam_y)
                txt.set_alpha(int(255*alpha))
                self.screen.blit(txt, (sx - txt.get_width()//2, sy))

    def _pause_menu_buttons(self):
        cx, cy = self.screen_w // 2, self.screen_h // 2
        bw, bh, gap = 300, 44, 14
        btn_labels = [
            ("Resume", "resume"),
            ("Save & Exit", "save"),
            ("Help", "help"),
            ("Quit to Desktop", "quit")
        ]
        total_h = len(btn_labels) * bh + (len(btn_labels) - 1) * gap
        start_y = cy - total_h // 2 + 20
        return [{"label": label, "action": act, "rect": pygame.Rect(cx - bw // 2, start_y + i * (bh + gap), bw, bh)}
                for i, (label, act) in enumerate(btn_labels)]

    def _draw_pause_menu(self):
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        cx = self.screen_w // 2
        if self.pause_state == "main":
            mx, my = pygame.mouse.get_pos()
            title = self.font_huge.render("PAUSED", True, (255, 255, 255))
            sh_surf = self.font_huge.render("PAUSED", True, (0, 0, 0))
            sh_surf.set_alpha(150)
            ty = int(self.screen_h * 0.16)
            self.screen.blit(sh_surf, (cx - title.get_width() // 2 + 2, ty + 2))
            self.screen.blit(title, (cx - title.get_width() // 2, ty))
            for b in self._pause_menu_buttons():
                r = b["rect"]
                hovered = r.collidepoint(mx, my)
                fill = (52, 66, 102, 235) if hovered else (38, 48, 76, 215)
                bsurf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                pygame.draw.rect(bsurf, fill, (0, 0, r.w, r.h), border_radius=6)
                self.screen.blit(bsurf, r.topleft)
                bc = (255, 215, 90) if hovered else (85, 110, 155)
                pygame.draw.rect(self.screen, bc, r, 2, border_radius=6)
                tc = (255, 235, 140) if hovered else (240, 245, 255)
                txt = self.font_big.render(b["label"], True, tc)
                sh2 = self.font_big.render(b["label"], True, (0, 0, 0))
                sh2.set_alpha(150)
                self.screen.blit(sh2, (r.centerx - txt.get_width() // 2 + 1, r.centery - txt.get_height() // 2 + 1))
                self.screen.blit(txt, (r.centerx - txt.get_width() // 2, r.centery - txt.get_height() // 2))
        elif self.pause_state == "help":
            # FIX #1: proper panel sizing so nothing overlaps
            panel = pygame.Rect(self.screen_w//2 - 440, 90, 880, self.screen_h - 160)
            pygame.draw.rect(self.screen, (20, 25, 45), panel, border_radius=8)
            pygame.draw.rect(self.screen, (120, 140, 180), panel, 2, border_radius=8)
            title = self.font_big.render("Controls & Help", True, (255, 230, 130))
            self.screen.blit(title, (panel.centerx - title.get_width()//2, panel.y + 10))
            # Two-column layout: (header_text) | (key, description) pairs.
            # Keys render at panel.x + 24, descriptions at panel.x + 260 so every
            # description starts at the same X regardless of key length. This fixes
            # the inconsistent-gap problem caused by manual space padding + proportional
            # fonts. An entry with key=None marks a header line; an entry with
            # key="" and desc=None marks a blank spacer line.
            help_entries = [
                ("MOVEMENT", None),
                ("", None),
                ("A / D or Left/Right Arrows", "Move left / right"),
                ("W / Space / Up", "Jump"),
                ("R", "Respawn (Creative mode only)"),
                ("", None),
                ("MINING & COLLECTING", None),
                ("", None),
                ("Left Click", "Mine blocks / attack enemies"),
                ("Right Click", "Place blocks / collect items"),
                ("Reach", "Limited to ~5 tiles"),
                ("", None),
                ("NATURAL BLOCKS", None),
                ("", None),
                ("Rock (boulder)", "Solid, mine with pickaxe"),
                ("Small Stone", "Right-click to collect"),
                ("Grass Tuft", "Left-click to collect"),
                ("Bush / Berry Bush", "Left/right click to collect"),
                ("", None),
                ("TOOLS & COMBAT", None),
                ("", None),
                ("Pickaxe / Axe / Sword / Hammer", "Different tools for different tasks"),
                ("Bow", "Hold LMB to shoot arrows"),
                ("Durability", "Tools lose durability and break"),
                ("", None),
                ("CRAFTING STATIONS  (right-click to open)", None),
                ("", None),
                ("Workbench", "4 planks - advanced tools, bricks, glass"),
                ("Furnace", "8 stone + 1 coal - smelt, cook, bake"),
                ("Anvil", "5 iron - (future: tool repair)"),
                ("Campfire", "3 wood + 2 sticks - cook, torches, light"),
                ("Chest", "8 planks - 20-slot storage"),
                ("", None),
                ("INVENTORY & CRAFTING", None),
                ("", None),
                ("1-9, 0", "Select hotbar"),
                ("E", "Inventory + crafting (LMB/RMB: pick up / swap)"),
                ("Right Click on water", "Fill water bottle"),
                ("", None),
                ("FOOD & HEALING", None),
                ("", None),
                ("F", "Eat selected food (Berry 8 / Apple 15 / Bread 30 / Meat 40)"),
                ("", None),
                ("WORLD & TIME (Creative only)", None),
                ("", None),
                ("TAB", "World map"),
                ("T", "Toggle time (Creative only)"),
                ("F1", "Debug overlay"),
                ("F2", "Slow motion (Creative only)"),
                ("F5", "Quick save"),
                ("F11", "Fullscreen"),
                ("ESC", "Pause menu"),
                ("", None),
                ("World", "100,000 x 5,000 tiles - generates as you explore"),
                ("Weather", "Rain, snow, storms with lightning"),
                ("Saves", "Stored in ~/.boundless_strata_saves/"),
            ]
            # X positions for the two columns. Description column is anchored at a
            # fixed X so every description aligns vertically regardless of key width.
            key_x = panel.x + 24
            desc_x = panel.x + 280
            header_color = (255, 230, 130)
            key_color = (180, 220, 255)
            desc_color = (220, 220, 240)
            y = panel.y + 36
            bottom_limit = panel.y + panel.h - 50
            for key_text, desc_text in help_entries:
                # Blank spacer line: empty key with no description
                if not key_text and desc_text is None:
                    y += 6
                    continue
                # Header line: non-empty key with no description
                if desc_text is None and key_text:
                    txt = self.font.render(key_text, True, header_color)
                    if y + txt.get_height() > bottom_limit: break
                    self.screen.blit(txt, (key_x, y))
                    y += 18
                    continue
                # Key + description row (two columns at fixed X positions)
                key_surf = self.font_sm.render(key_text, True, key_color)
                desc_surf = self.font_sm.render(desc_text, True, desc_color)
                if y + max(key_surf.get_height(), desc_surf.get_height()) > bottom_limit: break
                self.screen.blit(key_surf, (key_x, y))
                self.screen.blit(desc_surf, (desc_x, y))
                y += 15
            # Back button - placed inside the panel at the bottom
            mx, my = pygame.mouse.get_pos()
            back_rect = pygame.Rect(panel.centerx - 80, panel.bottom - 44, 160, 36)
            hovered = back_rect.collidepoint(mx, my)
            pygame.draw.rect(self.screen, (100, 60, 60) if hovered else (80, 40, 40), back_rect, border_radius=6)
            pygame.draw.rect(self.screen, (180, 140, 140), back_rect, 1, border_radius=6)
            bt = self.font.render("Back (ESC)", True, (255, 255, 255))
            self.screen.blit(bt, (back_rect.centerx - bt.get_width()//2, back_rect.centery - bt.get_height()//2))

    def _draw_game_over_screen(self):
        """Draw a Terraria/Minecraft-style Game Over overlay with a respawn countdown."""
        sw, sh = self.screen_w, self.screen_h
        # Dark red-tinted overlay
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((80, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        # "Game Over" title
        go_font = _make_font(max(48, int(48 * sw / 1280)), bold=True)
        title = go_font.render("Game Over", True, (220, 30, 30))
        shadow = go_font.render("Game Over", True, (40, 0, 0))
        tx = sw // 2 - title.get_width() // 2
        ty = sh // 2 - 80
        self.screen.blit(shadow, (tx + 3, ty + 3))
        self.screen.blit(title, (tx, ty))
        # Score/info line
        info_font = _make_font(max(20, int(20 * sw / 1280)))
        day_text = info_font.render(f"Day {self.day_count}", True, (200, 180, 180))
        self.screen.blit(day_text, (sw // 2 - day_text.get_width() // 2, ty + title.get_height() + 20))
        # Countdown timer
        remaining = max(0, self.GAME_OVER_DELAY - self.game_over_timer)
        timer_font = _make_font(max(28, int(28 * sw / 1280)), bold=True)
        timer_text = timer_font.render(f"Respawning in {int(remaining) + 1}s...", True, (255, 220, 180))
        self.screen.blit(timer_text, (sw // 2 - timer_text.get_width() // 2, ty + title.get_height() + 60))
        # Death cause
        if self.death_cause:
            cause_text = info_font.render(f"Cause: {self.death_cause}", True, (200, 130, 130))
            self.screen.blit(cause_text, (sw // 2 - cause_text.get_width() // 2, ty + title.get_height() + 100))
        # Hint
        hint_font = _make_font(max(16, int(16 * sw / 1280)))
        hint = hint_font.render("Press R to respawn now (Creative mode only)" if self.creative_mode else "You will respawn shortly...", True, (160, 140, 140))
        self.screen.blit(hint, (sw // 2 - hint.get_width() // 2, sh - 80))

    def _draw_debug(self):
        p = self.player
        t = self.time
        phase = "Night" if (t < 0.22 or t > 0.78) else ("Dawn" if t < 0.32 else ("Day" if t < 0.68 else "Dusk"))
        biome = biome_at(int(p.x // TILE), self.world.w)
        biome_name = BIOME_NAMES.get(biome, "?")
        lines = [
            f"FPS: {self.clock.get_fps():.1f}",
            f"Day {self.day_count} - {phase}  (Time: {t:.3f})",
            f"Biome: {biome_name}",
            f"Player: ({p.x:.0f}, {p.y:.0f})  Tile: ({int(p.x//TILE)}, {int(p.y//TILE)})",
            f"Velocity: ({p.vx:.0f}, {p.vy:.0f})",
            f"On ground: {p.on_ground}  |  In water: {p.in_water}",
            f"Particles: {len(self.particles)}  |  Slimes: {len(self.slimes)}  |  Zombies: {len(self.zombies)}  |  Arrows: {len(self.arrows)}",
            f"Night: {self._is_night()}  |  Slow-mo: {self.slow_mo}  |  Weather: {self.weather_type}",
            f"Seed: {self.seed}  |  Generated cols: {len(self.world.generated_set)}",
        ]
        item = self._get_selected_item()
        if item:
            name = get_item_name(item.item_id)
            if is_tool(item.item_id): name += f" (dur: {item.durability})"
            lines.append(f"Selected: {name} x{item.count}")
        # Draw background panel for readability
        max_w = max(self.font.size(l)[0] for l in lines) + 20
        panel_h = len(lines) * 22 + 16
        panel = pygame.Surface((max_w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 140))
        self.screen.blit(panel, (8, 42))
        y = 50
        for line in lines:
            self.screen.blit(self.font.render(line, True, (255,255,0)), (16, y)); y += 22


# ============================================================
# ENTRY POINT (with restart-to-menu support)
# ============================================================

def _restart_to_menu():
    """No-op: the main() loop handles returning to the menu via game.return_to_menu."""
    pass


def _init_fullscreen_display():
    """Initialize display at native resolution for the main menu."""
    global WINDOW_W, WINDOW_H
    try:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        sw, sh = screen.get_size()
        WINDOW_W, WINDOW_H = sw, sh
        return screen, sw, sh
    except (pygame.error, TypeError):
        pass
    # Fallback: windowed mode
    try:
        screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.RESIZABLE, vsync=1)
    except (pygame.error, TypeError):
        screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    sw, sh = screen.get_size()
    WINDOW_W, WINDOW_H = sw, sh
    return screen, sw, sh


def main():
    pygame.init()
    _init_sounds()  # generate procedural sounds
    while True:
        # Menu runs at native resolution
        screen, sw, sh = _init_fullscreen_display()
        pygame.display.set_caption("Boundless Strata")
        # Scale fonts proportionally to screen resolution
        menu_scale = sw / 1280.0
        font = _make_font(max(14, int(14 * menu_scale)))
        font_big = _make_font(max(22, int(22 * menu_scale)), bold=True)
        font_huge = _make_font(max(64, int(64 * menu_scale)), bold=True)

        menu = MainMenu(screen, font, font_big, font_huge)
        result = menu.run()
        if result is None or (isinstance(result, dict) and result.get("action") == "quit"):
            pygame.quit(); sys.exit(0)

        # Game runs in fullscreen
        if result["action"] == "new":
            seed = result["seed"]; name = result["name"]
            print(f"Creating new world '{name}' with seed {seed}")
            game = Game(seed=seed, fullscreen=True, world_name=name)
            game.run()
            if not game.return_to_menu: return
        elif result["action"] == "load":
            filename = result["filename"]
            data = load_world_data(filename)
            if data is None:
                print(f"Failed to load save: {filename}"); continue
            name = data.get("name", "World")
            print(f"Loading world '{name}' from {filename}")
            game = Game(fullscreen=True, world_data=data, world_name=name)
            game.run()
            if not game.return_to_menu: return


if __name__ == "__main__":
    main()
