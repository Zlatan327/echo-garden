"""Regenerate Echo Garden audio — puzzle-game optimised design.

Principles applied:
- Rotate: crisp, short, dry wooden click (< 1s) — satisfying, not annoying on repeat
- Connect: bright single marimba/xylophone note — clear rewarding "plink"
- Success: ascending 3-note chime arpeggio + light sparkle — clearly celebratory
- Ambient: peaceful zen garden soundscape — non-intrusive, meditative background
- Narration: Rachel voice — calm, warm, short lines, high stability
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, "C:/EL")

from elevenlabs.client import ElevenLabs


def main() -> None:
    api_key = os.environ["ELEVENLABS_API_KEY"]
    client = ElevenLabs(api_key=api_key)

    sounds_dir = Path(__file__).parent / "assets" / "sounds"
    sounds_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  SOUND EFFECTS  — short, crisp, puzzle-game appropriate              #
    # ------------------------------------------------------------------ #
    sfx: dict[str, tuple[str, float]] = {
        # Rotate: very short dry click — satisfying on every tile tap
        "rotate_organic.mp3": (
            "A single crisp dry wooden click, like placing a wooden game piece "
            "on a board. Short, punchy, clean. No reverb. About half a second.",
            2.0,
        ),
        # Connect: bright upward melodic plink — rewarding feedback
        "connection_chime.mp3": (
            "A single bright clear xylophone note, C major, short and pleasant. "
            "Like a marimba plink. Clean attack, quick fade. Very satisfying ping.",
            2.0,
        ),
        # Success: ascending arpeggio + sparkle — clearly celebratory
        "success_bloom.mp3": (
            "An ascending arpeggio of three bright xylophone notes C-E-G, "
            "followed by a gentle shimmering sparkle sound. Cheerful, rewarding, "
            "puzzle complete feeling. Not too loud, clean and musical.",
            4.0,
        ),
        # Ambient: non-intrusive zen background — helps concentration
        "ambient_garden.mp3": (
            "Soft peaceful background music for a relaxing puzzle game. "
            "Gentle plucked koto strings, soft wind chimes in the distance, "
            "quiet ambient hum. Slow tempo, meditative, non-intrusive. "
            "Lo-fi, warm, calming. No percussion or beats. Loopable.",
            22.0,
        ),
    }

    print("=== Generating SFX (puzzle-game designed) ===")
    for filename, (prompt, duration) in sfx.items():
        out = sounds_dir / filename
        print(f"  -> {filename}  ({duration}s)")
        audio = client.text_to_sound_effects.convert(
            text=prompt,
            duration_seconds=duration,
            prompt_influence=0.55,
        )
        with out.open("wb") as f:
            for chunk in audio:
                f.write(chunk)

    # ------------------------------------------------------------------ #
    #  TTS NARRATION — Rachel, calm + warm, short impactful lines          #
    # ------------------------------------------------------------------ #
    VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — warm, gentle, clear
    MODEL    = "eleven_multilingual_v2"
    FORMAT   = "mp3_44100_128"

    # Shorter, punchier narration lines — easier to hear and remember
    narration: list[tuple[str, str]] = [
        ("narration_level_0.mp3",
         "Breathe. Each petal finds its way home."),
        ("narration_level_1.mp3",
         "Trace the vine. The mandala is waiting."),
        ("narration_level_2.mp3",
         "Balance both sides. Stay patient."),
        ("narration_level_3.mp3",
         "Every connection adds a voice to the chorus."),
        ("narration_level_4.mp3",
         "Let go. The still waters know the way."),
        ("narration_breathe.mp3",
         "Well done. Your attention is restored."),
    ]

    print("\n=== Generating TTS Narration (Rachel, short lines) ===")
    for filename, text in narration:
        out = sounds_dir / filename
        print(f"  -> {filename}  \"{text}\"")
        stream = client.text_to_speech.convert(
            text=text,
            voice_id=VOICE_ID,
            model_id=MODEL,
            output_format=FORMAT,
            voice_settings={
                "stability": 0.80,
                "similarity_boost": 0.85,
                "style": 0.08,
                "use_speaker_boost": False,
            },
        )
        with out.open("wb") as f:
            for chunk in stream:
                f.write(chunk)

    print(f"\n+ Done. All assets in: {sounds_dir}")
    print("\nFiles:")
    for f in sorted(sounds_dir.iterdir()):
        kb = f.stat().st_size / 1024
        print(f"  {f.name:<30} {kb:>6.1f} KB")


if __name__ == "__main__":
    main()
