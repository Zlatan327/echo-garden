"""Generate Echo Garden audio assets with ElevenLabs.

Usage:
    1. pip install -r requirements.txt
    2. Set ELEVENLABS_API_KEY in your environment (or create a .env file):
           ELEVENLABS_API_KEY=your_key_here
    3. Run: py -3.13 generate_audio.py

Generates in assets/sounds/:
  Sound effects (text-to-sound-effects):
    - rotate_organic.mp3        tile rotation click
    - connection_chime.mp3      pipe connected chime
    - success_bloom.mp3         level complete bloom
    - ambient_garden.mp3        looping background music

  TTS narration (Bella voice, eleven_multilingual_v2):
    - narration_level_0.mp3     Petal Circuit intro
    - narration_level_1.mp3     Vine Mandala intro
    - narration_level_2.mp3     Root Symmetry intro
    - narration_level_3.mp3     Garden Chorus intro
    - narration_level_4.mp3     Still Waters intro
    - narration_breathe.mp3     generic completion line

The game loads all files automatically on startup.
No API key is needed to play - audio gracefully degrades to silence.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Support running with PYTHONPATH=C:\EL for short-path elevenlabs install
sys.path.insert(0, "C:/EL")

import pygame

from game import AudioManager


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # .env loading optional

    pygame.mixer.init()
    sounds_dir = Path(__file__).parent / "assets" / "sounds"
    manager = AudioManager(sounds_dir)

    print("=== Echo Garden Audio Generator ===")
    print("Using ElevenLabs APIs to create immersive garden sounds and narration.\n")

    manager.generate_elevenlabs_placeholders()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
