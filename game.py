"""Core systems for Echo Garden.

Everything renders with Pygame primitives for now, so the project is runnable
without art/audio assets. The `assets/` folder is ready for later images,
ElevenLabs text-to-sound-effects exports, narration, and music.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import os
from random import choice, random, uniform
from typing import Iterable

import pygame

Vec2 = pygame.math.Vector2
SCREEN_SIZE = (960, 720)
FPS = 60

DEEP_TEAL = (8, 28, 32)
PANEL_TEAL = (13, 48, 54)
SOFT_PURPLE = (166, 144, 214)
WARM_GOLD = (245, 203, 116)
MINT = (117, 224, 190)
ROSE = (230, 143, 169)
TEXT = (224, 235, 229)
MUTED_TEXT = (142, 166, 162)
TILE_DARK = (19, 58, 63)
TILE_HOVER = (26, 75, 82)
LINE_DIM = (79, 108, 111)
LINE_GLOW = (119, 239, 210)
LEAK = (235, 115, 132)

UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DIRS = {UP: (0, -1), RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0)}
OPPOSITE = {UP: DOWN, RIGHT: LEFT, DOWN: UP, LEFT: RIGHT}
TILE_LIBRARY: dict[str, set[int]] = {
    "end": {UP},
    "straight": {UP, DOWN},
    "corner": {UP, RIGHT},
    "tee": {UP, RIGHT, DOWN},
    "cross": {UP, RIGHT, DOWN, LEFT},
}


@dataclass(frozen=True)
class Level:
    """Immutable level description."""

    name: str
    size: int
    tiles: tuple[tuple[str, ...], ...]
    starts: tuple[tuple[int, int], ...]
    sinks: tuple[tuple[int, int], ...]
    rotations: tuple[tuple[int, ...], ...]
    narration: str
    art_style: str = "garden"
    solution_rotations: tuple[tuple[int, ...], ...] | None = None


class AudioManager:
    """Loads optional `.mp3` placeholders and fails quietly if absent.

    Future ElevenLabs files expected in `assets/sounds/`:
    `rotate_organic.mp3`, `connection_chime.mp3`, `success_bloom.mp3`,
    `ambient_garden.mp3`, and `narration_breathe.mp3`.
    """

    def __init__(self, asset_dir: Path) -> None:
        self.asset_dir = asset_dir
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            return

        names = {
            "rotate": "rotate_organic.mp3",
            "connect": "connection_chime.mp3",
            "success": "success_bloom.mp3",
            "narration": "narration_breathe.mp3",
        }
        for key, filename in names.items():
            path = self.asset_dir / filename
            if path.exists():
                try:
                    self.sounds[key] = pygame.mixer.Sound(str(path))
                except pygame.error:
                    pass

        music = self.asset_dir / "ambient_garden.mp3"
        if music.exists():
            try:
                pygame.mixer.music.load(str(music))
                pygame.mixer.music.set_volume(0.25)
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass

    def play(self, name: str, volume: float = 0.55) -> None:
        if not self.enabled or name not in self.sounds:
            return
        sound = self.sounds[name]
        sound.set_volume(max(0.0, min(1.0, volume)))
        sound.play()

    def set_peacefulness(self, progress: float) -> None:
        if self.enabled and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(0.16 + 0.18 * max(0.0, min(1.0, progress)))

    def generate_elevenlabs_placeholders(self) -> None:
        """Optional helper for later ElevenLabs SDK sound generation.

        This is intentionally not called by the game loop. After you install the
        ElevenLabs SDK and set ELEVENLABS_API_KEY, you can call this method from
        a small script to create real `.mp3` assets in `assets/sounds/`.
        """

        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError("Set ELEVENLABS_API_KEY before generating audio assets.")

        try:
            from elevenlabs.client import ElevenLabs
        except ImportError as exc:
            raise RuntimeError("Install the ElevenLabs SDK first: pip install elevenlabs") from exc

        client = ElevenLabs(api_key=api_key)
        prompts = {
            "rotate_organic.mp3": "gentle wooden organic tile rotation, soft tactile click, calming",
            "connection_chime.mp3": "soft resonant chime, warm digital garden tone, peaceful",
            "success_bloom.mp3": "calming success bloom, airy petals, warm sparkle, serene",
            "ambient_garden.mp3": "subtle looping ambient music, peaceful digital garden, soft pads",
            "narration_breathe.mp3": "calm warm voice saying: Well done. A piece of your attention is restored.",
        }
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        for filename, prompt in prompts.items():
            output_path = self.asset_dir / filename
            audio = client.text_to_sound_effects.convert(text=prompt, duration_seconds=4.0, prompt_influence=0.45)
            with output_path.open("wb") as file:
                for chunk in audio:
                    file.write(chunk)


class Particle:
    """Tiny success bloom particle: spark, leaf, or petal."""

    def __init__(self, pos: Vec2, color: tuple[int, int, int], shape: str = "spark") -> None:
        self.pos = Vec2(pos)
        self.vel = Vec2(uniform(-1.0, 1.0), uniform(-1.35, 0.65)) * uniform(40, 125)
        self.color = color
        self.shape = shape
        self.life = uniform(0.7, 1.75)
        self.max_life = self.life
        self.radius = uniform(2.0, 6.0)
        self.angle = uniform(0, 360)
        self.spin = uniform(-95, 95)

    def update(self, dt: float) -> bool:
        self.life -= dt
        self.vel *= 0.982
        self.pos += self.vel * dt
        self.angle += self.spin * dt
        return self.life > 0

    def draw(self, surface: pygame.Surface) -> None:
        alpha = int(215 * max(0.0, self.life / self.max_life))
        radius = max(1, int(self.radius * (1.8 - self.life / self.max_life)))
        layer = pygame.Surface((radius * 10, radius * 10), pygame.SRCALPHA)
        center = Vec2(radius * 5, radius * 5)

        if self.shape == "leaf":
            rect = pygame.Rect(0, 0, radius * 5, radius * 2).move(center.x - radius * 2.5, center.y - radius)
            pygame.draw.ellipse(layer, (*self.color, alpha), rect)
            pygame.draw.line(layer, (220, 245, 218, alpha), center - Vec2(radius * 2, 0), center + Vec2(radius * 2, 0), 1)
        elif self.shape == "petal":
            for offset in (-18, 18):
                petal = pygame.Rect(0, 0, radius * 3, radius * 5).move(center.x - radius * 1.5, center.y - radius * 2.5)
                rotated_center = center + Vec2(0, -radius).rotate(offset)
                petal.center = rotated_center
                pygame.draw.ellipse(layer, (*self.color, alpha), petal)
            pygame.draw.circle(layer, (*WARM_GOLD, alpha), center, max(1, radius // 2))
        else:
            pygame.draw.circle(layer, (*self.color, alpha), center, radius)
            pygame.draw.circle(layer, (*self.color, max(0, alpha // 3)), center, radius * 3, width=1)

        rotated = pygame.transform.rotozoom(layer, self.angle, 1.0)
        surface.blit(rotated, rotated.get_rect(center=self.pos), special_flags=pygame.BLEND_PREMULTIPLIED)


class Tile:
    """A rotatable neural-root tile."""

    def __init__(self, row: int, col: int, kind: str, rotation: int) -> None:
        self.row = row
        self.col = col
        self.kind = kind
        self.base_sides = TILE_LIBRARY[kind]
        self.rotation = rotation % 4
        self.visual_angle = self.rotation * 90.0
        self.target_angle = self.visual_angle
        self.connected = False
        self.is_source = False
        self.is_sink = False
        self.hover = False
        self.leaking_sides: set[int] = set()

    @property
    def sides(self) -> set[int]:
        return {(side + self.rotation) % 4 for side in self.base_sides}

    def rotate_clockwise(self) -> None:
        self.rotation = (self.rotation + 1) % 4
        self.target_angle += 90.0

    def update(self, dt: float) -> None:
        delta = self.target_angle - self.visual_angle
        self.visual_angle = self.target_angle if abs(delta) < 0.1 else self.visual_angle + delta * min(1.0, dt * 13.0)

    def draw_root_line(
        self,
        surface: pygame.Surface,
        start: Vec2,
        end: Vec2,
        color: tuple[int, int, int],
        width: int,
        glow_phase: float,
    ) -> None:
        """Draw a slightly organic curved focus-root segment."""

        direction = end - start
        if direction.length_squared() == 0:
            return
        normal = Vec2(-direction.y, direction.x).normalize()
        sway = normal * (2.2 * abs(Vec2(1, 0).rotate(glow_phase * 50 + self.row * 23 + self.col * 17).x))
        points: list[Vec2] = []
        for i in range(9):
            t = i / 8
            curve = sway * (1 - abs(0.5 - t) * 2)
            points.append(start.lerp(end, t) + curve)
        pygame.draw.lines(surface, color, False, points, width)
        if width > 3:
            pygame.draw.lines(surface, tuple(max(0, c - 50) for c in color), False, points, max(1, width // 3))

    def draw_bud(self, surface: pygame.Surface, center: Vec2, radius: int, glow_phase: float) -> None:
        """Draw a tiny original bud/flower accent for restored pathways."""

        bloom = 0.75 + 0.25 * abs(Vec2(1, 0).rotate(glow_phase * 70 + self.row * 31).x)
        petal_color = tuple(min(255, int(c * bloom + 20)) for c in SOFT_PURPLE)
        for i in range(4):
            pos = center + Vec2(0, -radius).rotate(i * 90 + glow_phase * 12)
            pygame.draw.circle(surface, petal_color, pos, max(2, radius // 2))
        pygame.draw.circle(surface, WARM_GOLD, center, max(2, radius // 3))

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, glow_phase: float) -> None:
        base_color = TILE_HOVER if self.hover else TILE_DARK
        if self.connected:
            base_color = (22, 70, 72)
        pygame.draw.rect(surface, base_color, rect, border_radius=16)
        pygame.draw.rect(surface, (35, 96, 98), rect, width=1, border_radius=16)

        center = Vec2(rect.center)
        half = rect.width * 0.5
        path_width = max(5, rect.width // 11)
        endpoints: list[Vec2] = []
        for base_side in self.base_sides:
            local = {
                UP: Vec2(0, -rect.width * 0.36),
                RIGHT: Vec2(rect.width * 0.36, 0),
                DOWN: Vec2(0, rect.width * 0.36),
                LEFT: Vec2(-rect.width * 0.36, 0),
            }[base_side].rotate(self.visual_angle)
            endpoints.append(center + local)

        active = LINE_GLOW if self.connected else LINE_DIM
        if self.connected:
            pulse = 0.70 + 0.30 * abs(Vec2(1, 0).rotate(glow_phase * 60).x)
            active = tuple(min(255, int(channel * pulse + 32)) for channel in LINE_GLOW)
            for end in endpoints:
                self.draw_root_line(surface, center, end, active, path_width + 9, glow_phase)

        for end in endpoints:
            self.draw_root_line(surface, center, end, active, path_width, glow_phase)
            pygame.draw.circle(surface, active, end, max(2, path_width // 2))
        pygame.draw.circle(surface, active, center, path_width)

        if self.connected and not (self.is_source or self.is_sink):
            self.draw_bud(surface, center + Vec2(rect.width * 0.18, -rect.width * 0.18), max(4, rect.width // 13), glow_phase)

        for side in self.leaking_sides:
            marker = {UP: Vec2(0, -half + 8), RIGHT: Vec2(half - 8, 0), DOWN: Vec2(0, half - 8), LEFT: Vec2(-half + 8, 0)}[side]
            pygame.draw.circle(surface, LEAK, center + marker, max(3, path_width // 2))

        if self.is_source or self.is_sink:
            color = WARM_GOLD if self.is_source else SOFT_PURPLE
            radius = int(rect.width * (0.15 if self.is_source else 0.12))
            aura = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
            pygame.draw.circle(aura, (*color, 45), (radius * 3, radius * 3), radius * 3)
            pygame.draw.circle(aura, (*color, 230), (radius * 3, radius * 3), radius)
            surface.blit(aura, center - Vec2(radius * 3, radius * 3), special_flags=pygame.BLEND_PREMULTIPLIED)


class Grid:
    """Grid, mouse-click rotation, and BFS connection checking."""

    def __init__(self, level: Level) -> None:
        self.level = level
        self.size = level.size
        self.connected_count = 0
        self.complete = False
        self.last_new_connection = False
        self.tiles: list[list[Tile]] = []
        self._build_tiles()
        self.check_connections()

    def _build_tiles(self) -> None:
        starts = set(self.level.starts)
        sinks = set(self.level.sinks)
        for row in range(self.size):
            line: list[Tile] = []
            for col in range(self.size):
                tile = Tile(row, col, self.level.tiles[row][col], self.level.rotations[row][col])
                tile.is_source = (row, col) in starts
                tile.is_sink = (row, col) in sinks
                line.append(tile)
            self.tiles.append(line)

    def iter_tiles(self) -> Iterable[Tile]:
        for row in self.tiles:
            yield from row

    def tile_rect(self, tile: Tile, board_rect: pygame.Rect) -> pygame.Rect:
        gap = max(6, board_rect.width // 90)
        cell = (board_rect.width - gap * (self.size - 1)) // self.size
        return pygame.Rect(board_rect.x + tile.col * (cell + gap), board_rect.y + tile.row * (cell + gap), cell, cell)

    def handle_click(self, pos: tuple[int, int], board_rect: pygame.Rect) -> bool:
        for tile in self.iter_tiles():
            if self.tile_rect(tile, board_rect).collidepoint(pos):
                tile.rotate_clockwise()
                self.check_connections()
                return True
        return False

    def update(self, dt: float, mouse_pos: tuple[int, int], board_rect: pygame.Rect) -> None:
        for tile in self.iter_tiles():
            tile.hover = self.tile_rect(tile, board_rect).collidepoint(mouse_pos)
            tile.update(dt)

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def check_connections(self) -> None:
        previous = self.connected_count
        for tile in self.iter_tiles():
            tile.connected = False
            tile.leaking_sides.clear()

        visited = set(self.level.starts)
        queue = deque(self.level.starts)
        leaks = False
        while queue:
            row, col = queue.popleft()
            tile = self.tiles[row][col]
            tile.connected = True
            for side in tile.sides:
                dc, dr = DIRS[side]
                nr, nc = row + dr, col + dc
                if not self.in_bounds(nr, nc):
                    tile.leaking_sides.add(side)
                    leaks = True
                    continue
                neighbor = self.tiles[nr][nc]
                if OPPOSITE[side] not in neighbor.sides:
                    tile.leaking_sides.add(side)
                    leaks = True
                    continue
                if (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc))

        self.connected_count = len(visited)
        self.complete = all(sink in visited for sink in self.level.sinks) and not leaks
        self.last_new_connection = self.connected_count > previous

    @property
    def progress(self) -> float:
        return self.connected_count / max(1, self.size * self.size)

    def draw(self, surface: pygame.Surface, board_rect: pygame.Rect, glow_phase: float) -> None:
        pygame.draw.rect(surface, (10, 37, 42), board_rect.inflate(32, 32), border_radius=28)
        self.draw_level_art(surface, board_rect, glow_phase)
        for tile in self.iter_tiles():
            tile.draw(surface, self.tile_rect(tile, board_rect), glow_phase)

    def draw_level_art(self, surface: pygame.Surface, board_rect: pygame.Rect, glow_phase: float) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        center = Vec2(board_rect.center)
        pulse = 0.5 + 0.5 * abs(Vec2(1, 0).rotate(glow_phase * 35).x)
        if self.level.art_style == "flower":
            for i in range(8):
                petal = center + Vec2(0, -board_rect.width * 0.34).rotate(i * 45 + glow_phase * 5)
                pygame.draw.ellipse(overlay, (*SOFT_PURPLE, 28), pygame.Rect(0, 0, 86, 42).move(petal.x - 43, petal.y - 21))
            pygame.draw.circle(overlay, (*WARM_GOLD, 38 + int(20 * pulse)), center, int(board_rect.width * 0.18))
        elif self.level.art_style == "vine_mandala":
            for i in range(5):
                pygame.draw.circle(overlay, (*MINT, 18), center, int(board_rect.width * (0.16 + i * 0.07)), width=2)
            for i in range(12):
                end = center + Vec2(board_rect.width * 0.38, 0).rotate(i * 30 + glow_phase * 3)
                pygame.draw.line(overlay, (*MINT, 24), center, end, 2)
                pygame.draw.ellipse(overlay, (*ROSE, 30), pygame.Rect(0, 0, 34, 16).move(end.x - 17, end.y - 8))
        elif self.level.art_style == "root_symmetry":
            for i in range(9):
                left = center + Vec2(-board_rect.width * 0.43, -board_rect.height * 0.34 + i * board_rect.height * 0.085)
                right = center + Vec2(board_rect.width * 0.43, -board_rect.height * 0.34 + i * board_rect.height * 0.085)
                pygame.draw.line(overlay, (*MINT, 22), left, center, 1)
                pygame.draw.line(overlay, (*MINT, 22), center, right, 1)
                pygame.draw.circle(overlay, (*SOFT_PURPLE, 16), left, 10 + i % 3)
                pygame.draw.circle(overlay, (*SOFT_PURPLE, 16), right, 10 + i % 3)
        elif self.level.art_style == "full_garden":
            for i in range(18):
                angle = i * 20 + glow_phase * 2
                pos = center + Vec2(board_rect.width * (0.18 + (i % 4) * 0.06), 0).rotate(angle)
                pygame.draw.circle(overlay, (*MINT, 18), pos, 18 + i % 5, width=2)
                pygame.draw.circle(overlay, (*WARM_GOLD, 14), pos, 4 + i % 3)
            pygame.draw.circle(overlay, (*SOFT_PURPLE, 22), center, int(board_rect.width * 0.42), width=2)
        else:
            for i in range(10):
                start = center + Vec2(-board_rect.width * 0.42, -board_rect.height * 0.3 + i * board_rect.height * 0.07)
                end = center + Vec2(board_rect.width * 0.42, board_rect.height * 0.3 - i * board_rect.height * 0.04)
                pygame.draw.line(overlay, (*MINT, 18), start, end, 1)
        surface.blit(overlay, (0, 0))

class Game:
    """Main Echo Garden state machine."""

    def __init__(self) -> None:
        self.screen = pygame.display.set_mode(SCREEN_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption("Echo Garden")
        self.clock = pygame.time.Clock()
        self.running = True
        self.fullscreen = False
        self.state = "title"
        self.font_title = pygame.font.Font(None, 112)
        self.font_big = pygame.font.Font(None, 82)
        self.font = pygame.font.Font(None, 34)
        self.font_small = pygame.font.Font(None, 24)
        self.levels = build_levels()
        self.level_index = 0
        self.grid = Grid(self.levels[self.level_index])
        self.audio = AudioManager(Path(__file__).parent / "assets" / "sounds")
        self.particles: list[Particle] = []
        self.glow_phase = 0.0
        self.distraction = 0.0
        self.click_times: list[float] = []
        self.success_announced = False
        self.completed_levels: set[int] = set()
        self.debug_overlay = False

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()

    def board_rect(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        side = int(min(width * 0.58, height * 0.66))
        return pygame.Rect(width // 2 - side // 2, height // 2 - side // 2 + 44, side, side)

    def complete_overlay_rect(self) -> pygame.Rect:
        board = self.board_rect()
        width, height = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(500, width - 48), 116)
        preferred_y = board.bottom + 18
        safe_y = min(preferred_y, height - panel.height - 52)
        panel.centerx = width // 2
        panel.y = max(150, safe_y)
        return panel

    def title_button_rects(self) -> dict[str, pygame.Rect]:
        width, height = self.screen.get_size()
        button_w = min(330, width - 80)
        start_y = height // 2 + 74
        return {
            "continue": pygame.Rect(width // 2 - button_w // 2, start_y, button_w, 48),
            "levels": pygame.Rect(width // 2 - button_w // 2, start_y + 62, button_w, 48),
            "quit": pygame.Rect(width // 2 - button_w // 2, start_y + 124, button_w, 48),
        }

    def level_card_rects(self) -> list[pygame.Rect]:
        width, height = self.screen.get_size()
        card_w = min(360, (width - 120) // 2)
        card_h = 118
        total_w = card_w * 2 + 24
        start_x = width // 2 - total_w // 2
        start_y = max(170, height // 2 - 118)
        return [
            pygame.Rect(start_x + (i % 2) * (card_w + 24), start_y + (i // 2) * (card_h + 24), card_w, card_h)
            for i in range(len(self.levels))
        ]

    def load_level(self, index: int) -> None:
        self.level_index = max(0, min(index, len(self.levels) - 1))
        self.reset_level()
        self.state = "playing"
        self.audio.play("narration", 0.35)

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.state == "playing":
                        self.state = "title"
                    elif self.state == "level_select":
                        self.state = "title"
                    else:
                        self.running = False
                elif event.key == pygame.K_f:
                    self.toggle_fullscreen()
                elif event.key == pygame.K_d:
                    self.debug_overlay = not self.debug_overlay
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == "title":
                    self.start_playing()
                elif event.key == pygame.K_r and self.state == "playing":
                    self.reset_level()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.state == "title":
                    for action, rect in self.title_button_rects().items():
                        if rect.collidepoint(event.pos):
                            if action == "continue":
                                self.start_playing()
                            elif action == "levels":
                                self.state = "level_select"
                            elif action == "quit":
                                self.running = False
                            break
                elif self.state == "level_select":
                    for index, rect in enumerate(self.level_card_rects()):
                        if rect.collidepoint(event.pos):
                            self.load_level(index)
                            break
                elif self.state == "playing" and self.grid.complete:
                    if self.complete_overlay_rect().collidepoint(event.pos):
                        self.advance_level()
                elif self.state == "playing" and self.grid.handle_click(event.pos, self.board_rect()):
                    self.record_click_rhythm()
                    self.audio.play("rotate", 0.42 + self.distraction * 0.12)

    def start_playing(self) -> None:
        self.state = "playing"
        self.audio.play("narration", 0.45)

    def record_click_rhythm(self) -> None:
        now = pygame.time.get_ticks() / 1000.0
        self.click_times = [t for t in self.click_times if now - t < 1.0]
        self.click_times.append(now)
        if len(self.click_times) >= 4:
            self.distraction = min(1.0, self.distraction + 0.28)

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        self.screen = pygame.display.set_mode(SCREEN_SIZE, flags)

    def reset_level(self) -> None:
        self.grid = Grid(self.levels[self.level_index])
        self.success_announced = False
        self.particles.clear()

    def update(self, dt: float) -> None:
        self.glow_phase += dt
        self.distraction = max(0.0, self.distraction - dt * 0.26)
        self.particles = [p for p in self.particles if p.update(dt)]
        if self.state != "playing":
            return

        self.grid.update(dt, pygame.mouse.get_pos(), self.board_rect())
        self.audio.set_peacefulness(self.grid.progress)
        if self.grid.last_new_connection:
            self.audio.play("connect", 0.38)
            self.grid.last_new_connection = False
        if self.grid.complete and not self.success_announced:
            self.success_announced = True
            self.completed_levels.add(self.level_index)
            self.audio.play("success", 0.65)
            self.spawn_bloom(90)
        if self.grid.complete and len(self.particles) < 18 and random() < dt * 4:
            self.spawn_bloom(2)

    def spawn_bloom(self, count: int) -> None:
        rect = self.board_rect()
        for _ in range(count):
            pos = Vec2(uniform(rect.left, rect.right), uniform(rect.top, rect.bottom))
            self.particles.append(Particle(pos, choice([MINT, WARM_GOLD, SOFT_PURPLE, ROSE]), choice(["spark", "leaf", "petal"])))

    def advance_level(self) -> None:
        self.completed_levels.add(self.level_index)
        self.level_index = (self.level_index + 1) % len(self.levels)
        self.reset_level()

    def draw(self) -> None:
        self.screen.fill(DEEP_TEAL)
        self.draw_background()
        if self.state == "title":
            self.draw_title()
        elif self.state == "level_select":
            self.draw_level_select()
        else:
            self.draw_game()
        for particle in self.particles:
            particle.draw(self.screen)
        if self.distraction > 0.02:
            self.draw_distraction_noise()
        if self.state == "playing":
            self.draw_debug_overlay()
        pygame.display.flip()

    def draw_background(self) -> None:
        width, height = self.screen.get_size()
        for i in range(34):
            x = (i * 149 + int(self.glow_phase * 9)) % (width + 80) - 40
            y = (i * 83) % (height + 80) - 40
            pygame.draw.circle(self.screen, (45, 90, 88), (x, y), 1 + i % 3)

    def draw_button(self, rect: pygame.Rect, label: str, primary: bool = False) -> None:
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        color = (24, 76, 80) if hovered else (17, 58, 63)
        border = WARM_GOLD if primary else MINT
        pygame.draw.rect(self.screen, color, rect, border_radius=16)
        pygame.draw.rect(self.screen, border, rect, width=1, border_radius=16)
        text = self.font.render(label, True, TEXT if not primary else WARM_GOLD)
        self.screen.blit(text, text.get_rect(center=rect.center))

    def draw_title(self) -> None:
        width, height = self.screen.get_size()
        title = self.font_title.render("Echo Garden", True, TEXT)
        subtitle = self.font.render("A mindful puzzle of neural roots and focus pathways", True, MUTED_TEXT)
        hint = self.font_small.render("F: fullscreen   D: debug overlay   Esc: quit", True, MUTED_TEXT)
        self.screen.blit(title, title.get_rect(center=(width // 2, height // 2 - 138)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(width // 2, height // 2 - 48)))
        self.screen.blit(hint, hint.get_rect(center=(width // 2, height - 36)))

        center = Vec2(width // 2, height // 2 - 220)
        for radius, color in [(62, SOFT_PURPLE), (42, MINT), (22, WARM_GOLD)]:
            pygame.draw.circle(self.screen, color, center, radius, width=2)

        buttons = self.title_button_rects()
        self.draw_button(buttons["continue"], "Continue Garden", primary=True)
        self.draw_button(buttons["levels"], "Level Select")
        self.draw_button(buttons["quit"], "Quit")

    def draw_level_select(self) -> None:
        width, height = self.screen.get_size()
        title = self.font_big.render("Choose a Garden", True, TEXT)
        subtitle = self.font_small.render("Click any level card. Esc returns to the title screen.", True, MUTED_TEXT)
        self.screen.blit(title, title.get_rect(center=(width // 2, 82)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(width // 2, 126)))

        for index, rect in enumerate(self.level_card_rects()):
            level = self.levels[index]
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            fill = (24, 76, 80) if hovered else (16, 55, 60)
            pygame.draw.rect(self.screen, fill, rect, border_radius=18)
            pygame.draw.rect(self.screen, WARM_GOLD if index in self.completed_levels else MINT, rect, width=1, border_radius=18)
            number = self.font.render(f"{index + 1}", True, WARM_GOLD)
            name = self.font.render(level.name, True, TEXT)
            size = self.font_small.render(f"{level.size}x{level.size} - {level.art_style.replace('_', ' ')}", True, MUTED_TEXT)
            status = self.font_small.render("restored" if index in self.completed_levels else "unrestored", True, WARM_GOLD if index in self.completed_levels else MUTED_TEXT)
            self.screen.blit(number, (rect.x + 20, rect.y + 18))
            self.screen.blit(name, (rect.x + 70, rect.y + 20))
            self.screen.blit(size, (rect.x + 70, rect.y + 55))
            self.screen.blit(status, (rect.x + 70, rect.y + 82))

    def draw_debug_overlay(self) -> None:
        if not self.debug_overlay:
            return
        leaks = sum(len(tile.leaking_sides) for tile in self.grid.iter_tiles())
        lines = [
            "DEBUG",
            f"state: {self.state}",
            f"level: {self.level_index + 1}/{len(self.levels)}",
            f"connected: {self.grid.connected_count}",
            f"leaks: {leaks}",
            f"complete: {self.grid.complete}",
        ]
        panel = pygame.Rect(18, 170, 190, 24 + len(lines) * 22)
        pygame.draw.rect(self.screen, (5, 20, 24), panel, border_radius=12)
        pygame.draw.rect(self.screen, MINT, panel, width=1, border_radius=12)
        for i, line in enumerate(lines):
            rendered = self.font_small.render(line, True, TEXT)
            self.screen.blit(rendered, (panel.x + 12, panel.y + 12 + i * 22))

    def draw_game(self) -> None:
        level = self.levels[self.level_index]
        board = self.board_rect()
        self.grid.draw(self.screen, board, self.glow_phase)
        self.screen.blit(self.font_big.render("Echo Garden", True, TEXT), (38, 26))
        self.screen.blit(self.font.render(f"{level.name} - {level.size}x{level.size}", True, WARM_GOLD), (44, 100))
        self.screen.blit(self.font_small.render(level.narration, True, MUTED_TEXT), (44, 134))
        controls = self.font_small.render("Click tiles to rotate. R: reset  F: fullscreen  D: debug  Esc: title", True, MUTED_TEXT)
        self.screen.blit(controls, (44, self.screen.get_height() - 36))

        progress_rect = pygame.Rect(self.screen.get_width() - 266, 42, 204, 12)
        pygame.draw.rect(self.screen, PANEL_TEAL, progress_rect, border_radius=6)
        fill = progress_rect.copy()
        fill.width = int(progress_rect.width * self.grid.progress)
        pygame.draw.rect(self.screen, MINT, fill, border_radius=6)
        self.screen.blit(self.font_small.render("garden coherence", True, MUTED_TEXT), (progress_rect.x, progress_rect.y + 18))

        if self.grid.complete:
            panel = self.complete_overlay_rect()
            pygame.draw.rect(self.screen, (15, 50, 55), panel, border_radius=22)
            pygame.draw.rect(self.screen, MINT, panel, width=1, border_radius=22)
            restored = self.font.render("Attention restored", True, WARM_GOLD)
            line = self.font_small.render("Well done. A piece of your attention is restored.", True, TEXT)
            prompt = self.font_small.render("Click this bloom panel to enter the next garden", True, MUTED_TEXT)
            self.screen.blit(restored, restored.get_rect(center=(panel.centerx, panel.y + 30)))
            self.screen.blit(line, line.get_rect(center=(panel.centerx, panel.y + 62)))
            self.screen.blit(prompt, prompt.get_rect(center=(panel.centerx, panel.y + 90)))

    def draw_distraction_noise(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        width, height = self.screen.get_size()
        for _ in range(int(28 * self.distraction)):
            x, y = int(uniform(0, width)), int(uniform(0, height))
            pygame.draw.line(overlay, (154, 115, 180, 35), (x, y), (x + int(uniform(5, 22)), y), 1)
        self.screen.blit(overlay, (0, 0))


def build_levels() -> list[Level]:
    """Four compact handcrafted levels, progressing 3x3 to 5x5."""

    return [
        Level(
            name="Petal Circuit",
            size=3,
            starts=((1, 1),),
            sinks=((0, 1), (1, 0), (1, 2), (2, 1)),
            tiles=(("corner", "end", "corner"), ("end", "cross", "end"), ("corner", "end", "corner")),
            rotations=((1, 1, 2), (0, 0, 2), (0, 3, 3)),
            narration="Breathe... each petal returns to the center.",
            art_style="flower",
            solution_rotations=((1, 2, 2), (1, 0, 3), (0, 0, 3)),
        ),
        Level(
            name="Vine Mandala",
            size=4,
            starts=((0, 0),),
            sinks=((3, 3),),
            tiles=(("end", "corner", "corner", "end"), ("corner", "corner", "corner", "corner"), ("end", "corner", "corner", "corner"), ("corner", "end", "corner", "end")),
            rotations=((2, 3, 1, 2), (1, 1, 3, 2), (0, 2, 1, 1), (3, 0, 2, 1)),
            narration="Trace the vine as it curls into a quiet mandala.",
            art_style="vine_mandala",
            solution_rotations=((1, 2, 0, 0), (0, 0, 2, 0), (0, 0, 0, 2), (0, 0, 0, 0)),
        ),
        Level(
            name="Root Symmetry",
            size=5,
            starts=((2, 0),),
            sinks=((0, 4), (4, 4)),
            tiles=(("end", "corner", "corner", "straight", "end"), ("corner", "end", "straight", "end", "corner"), ("end", "straight", "tee", "end", "corner"), ("corner", "end", "straight", "end", "corner"), ("end", "corner", "corner", "straight", "end")),
            rotations=((2, 1, 2, 0, 2), (3, 0, 1, 1, 0), (0, 0, 0, 2, 1), (0, 1, 1, 0, 3), (1, 2, 3, 0, 2)),
            narration="Balance both sides of the root system with patient attention.",
            art_style="root_symmetry",
            solution_rotations=((2, 1, 1, 1, 3), (3, 0, 0, 1, 0), (1, 1, 2, 2, 0), (0, 1, 0, 0, 3), (1, 0, 0, 1, 3)),
        ),
        Level(
            name="Garden Chorus",
            size=5,
            starts=((4, 0),),
            sinks=((0, 0), (0, 4), (4, 4)),
            tiles=(("end", "corner", "corner", "straight", "end"), ("straight", "corner", "straight", "corner", "straight"), ("corner", "straight", "cross", "straight", "corner"), ("corner", "end", "straight", "end", "straight"), ("end", "straight", "corner", "corner", "end")),
            rotations=((2, 0, 2, 0, 1), (1, 2, 1, 3, 0), (1, 0, 0, 0, 1), (0, 2, 1, 2, 1), (0, 0, 0, 3, 2)),
            narration="Every restored pathway adds a quiet voice to the garden chorus.",
            art_style="full_garden",
            solution_rotations=((2, 0, 1, 1, 3), (0, 2, 0, 3, 0), (0, 1, 0, 1, 2), (0, 2, 0, 3, 0), (1, 1, 3, 0, 0)),
        ),
    ]
