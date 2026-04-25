"""Generate Echo Garden audio placeholders with ElevenLabs.

Usage:
    1. Install dependencies: pip install -r requirements.txt
    2. Set ELEVENLABS_API_KEY in your environment.
    3. Run: python generate_audio.py

The game itself never requires your API key. This script only creates local mp3
files in assets/sounds/ for Pygame to load later.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from game import AudioManager


def main() -> int:
    pygame.mixer.init()
    sounds_dir = Path(__file__).parent / "assets" / "sounds"
    manager = AudioManager(sounds_dir)
    manager.generate_elevenlabs_placeholders()
    print(f"Generated Echo Garden audio assets in: {sounds_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
