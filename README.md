# Echo Garden

Echo Garden is a lightweight Pygame puzzle prototype included in this workspace
for development and testing. The game uses Pygame primitives so it can run even
without art or audio assets.

Contents
- `game.py` - core game systems, tiles, rendering and audio manager
- `main.py` - entry point; runs the `Game` class
- `generate_audio.py` - optional helper to generate placeholder audio assets

Quick start (Windows / PowerShell)
1. Open PowerShell and change to the Echo Garden directory:

   cd 'C:\Users\Admin\OneDrive\Dokument\New project\_tmp_echo_garden_review'

2. Create and activate a virtual environment:

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

3. Install the minimal dependency (Pygame):

   pip install pygame

4. Run the game:

   python main.py

The game falls back to simple primitives if assets are missing. Audio files are
optional and placed under `assets/sounds/` if you generate or provide them.

Notes for repository hygiene
- This directory previously contained a local virtual environment and compiled
  files which should not be tracked by Git. A `.gitignore` entry was added to
  prevent committing local venvs and `__pycache__` artifacts.
- If you want Echo Garden to live in its own repository, consider moving this
  folder out and initializing a fresh repo (I can help with that).

Generating optional audio (ElevenLabs)
- `generate_audio.py` contains helpers to produce placeholder `.mp3` assets using
  the ElevenLabs SDK. You must set `ELEVENLABS_API_KEY` and install the SDK to
  use it — the game does not call the generator automatically.

License & credits
- This folder contains prototype code and helper scripts. Add licensing or
  attribution files as needed for redistribution.

If you want me to also stage/commit any remaining uncommitted game source files
under this folder, tell me and I'll list them and commit them on `echo-garden-work`.