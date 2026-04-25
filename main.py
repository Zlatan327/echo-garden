"""Echo Garden entry point.

Run this file to start the game:

    python main.py
"""

from __future__ import annotations

import sys

import pygame

from game import Game


def main() -> int:
    """Initialize Pygame, run Echo Garden, and return a process exit code."""
    pygame.init()

    try:
        game = Game()
        game.run()
    finally:
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
