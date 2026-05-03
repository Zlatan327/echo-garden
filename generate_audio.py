"""Generate Echo Garden audio assets with ElevenLabs.

Usage:
    1. pip install -r requirements.txt
    2. Set ELEVENLABS_API_KEY in your environment (or create a .env file):
           ELEVENLABS_API_KEY=your_key_here
    3. Run: py -3.13 generate_audio.py

Generates in assets/sounds/:
  Sound effects (text-to-sound-effects):
    - rotate_organic.mp3        tile rotation click
    - connection_chime.mp3      route connected chime
    - output_linked.mp3         output satisfied cue
    - leak_sealed.mp3           leak fixed cue
    - blocked_tile.mp3          fixed bridge / no-op cue
    - success_bloom.mp3         level complete bloom
    - ambient_garden.mp3        looping background music

  TTS narration (one file per puzzle, plus a generic completion line):
    - narration_level_<n>.mp3
    - narration_breathe.mp3

The game loads all files automatically on startup.
No API key is needed to play; audio gracefully degrades to silence.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Support running with PYTHONPATH=C:\EL for short-path elevenlabs install
sys.path.insert(0, "C:/EL")

from game import AudioManager, build_levels


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # .env loading optional

    sounds_dir = Path(__file__).parent / "assets" / "sounds"
    manager = AudioManager(sounds_dir)

    print("=== Echo Garden Audio Generator ===")
    print("Using ElevenLabs APIs to create immersive garden sounds and narration.\n")
    print(f"Configured to generate narration for {len(build_levels())} puzzles.\n")

    manager.generate_elevenlabs_placeholders()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
