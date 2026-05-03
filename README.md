# Echo Garden

Echo Garden is a Pygame routing puzzle about connecting color-matched sources
and outputs, managing leaks, and solving later boards that introduce bridges
and color mixing. The game is intentionally asset-light: it renders with
Pygame primitives and still runs cleanly without generated audio files.

## Files

- `main.py` - entry point that boots Pygame and runs the main game loop
- `game.py` - gameplay, rendering, level data, and optional audio tooling
- `validate_levels.py` - headless level validator that checks every declared solution
- `generate_audio.py` - optional ElevenLabs helper for narration and sound effects
- `regen_audio.py` - alternative ElevenLabs regeneration script with tuned prompts

## Quick start

```powershell
cd 'C:\Users\Admin\OneDrive\Dokument\New project\_tmp_echo_garden_review'
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python validate_levels.py
python main.py
```

## Controls

- Left click rotates clockwise
- Right click rotates counter-clockwise
- `Q` / `E` or left / right arrows rotate the tile under the cursor
- `H` toggles hint mode
- `R` resets the current puzzle
- `F` toggles fullscreen
- `Esc` returns to the title screen or quits from the title screen

## Audio
Audio is optional. If you want generated voice lines and sound effects, set
`ELEVENLABS_API_KEY` and run:

```powershell
python generate_audio.py
```

The generator writes files under `assets/sounds/`. The game will load
`narration_level_<n>.mp3` files automatically when a level starts. Optional
effect hooks also support separate cues for linked outputs, sealed leaks,
blocked fixed tiles, route connections, and final completion.
