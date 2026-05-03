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
MAX_FRAME_DT = 0.05

STATE_TITLE = "title"
STATE_LEVEL_SELECT = "level_select"
STATE_PLAYING = "playing"

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
FLOW_PALETTE: dict[str, tuple[int, int, int]] = {
    "gold": WARM_GOLD,
    "mint": MINT,
    "rose": ROSE,
    "violet": SOFT_PURPLE,
}
TILE_CHANNEL_LIBRARY: dict[str, tuple[tuple[int, ...], ...]] = {
    "end": ((UP,),),
    "straight": ((UP, DOWN),),
    "corner": ((UP, RIGHT),),
    "tee": ((UP, RIGHT, DOWN),),
    "cross": ((UP, RIGHT, DOWN, LEFT),),
    "bridge": ((UP, DOWN), (LEFT, RIGHT)),
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
    start_colors: tuple[str, ...] = ()
    sink_targets: tuple[tuple[str, ...], ...] = ()
    art_style: str = "garden"
    solution_rotations: tuple[tuple[int, ...], ...] | None = None


class AudioManager:
    """Loads optional `.mp3` placeholders and fails quietly if absent.

    Future ElevenLabs files expected in `assets/sounds/`:
    `rotate_organic.mp3`, `connection_chime.mp3`, `output_linked.mp3`,
    `leak_sealed.mp3`, `blocked_tile.mp3`, `success_bloom.mp3`,
    `ambient_garden.mp3`, and `narration_breathe.mp3`.
    """

    def __init__(self, asset_dir: Path) -> None:
        self.asset_dir = asset_dir
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.cooldowns: dict[str, float] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            return

        names = {
            "rotate": "rotate_organic.mp3",
            "connect": "connection_chime.mp3",
            "output": "output_linked.mp3",
            "seal": "leak_sealed.mp3",
            "blocked": "blocked_tile.mp3",
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
                pygame.mixer.music.set_volume(0.45)
                pygame.mixer.music.play(-1)
            except pygame.error:
                pass

        # Per-level narration tracks (narration_level_0.mp3 ... narration_level_9.mp3)
        for idx in range(10):
            path = self.asset_dir / f"narration_level_{idx}.mp3"
            if path.exists():
                try:
                    self.sounds[f"narration_{idx}"] = pygame.mixer.Sound(str(path))
                except pygame.error:
                    pass

    def tick(self, dt: float) -> None:
        if not self.cooldowns:
            return
        expired = [name for name, remaining in self.cooldowns.items() if remaining - dt <= 0]
        for name in expired:
            del self.cooldowns[name]
        for name in list(self.cooldowns):
            self.cooldowns[name] -= dt

    def play(self, name: str, volume: float = 0.55, cooldown: float = 0.0) -> None:
        if not self.enabled or name not in self.sounds:
            return
        if cooldown > 0.0 and self.cooldowns.get(name, 0.0) > 0.0:
            return
        sound = self.sounds[name]
        sound.set_volume(max(0.0, min(1.0, volume)))
        sound.play()
        if cooldown > 0.0:
            self.cooldowns[name] = cooldown

    def set_peacefulness(self, progress: float) -> None:
        if self.enabled and pygame.mixer.music.get_busy():
            # Ambient gently rises from 0.42 -> 0.65 as garden connects
            pygame.mixer.music.set_volume(0.42 + 0.23 * max(0.0, min(1.0, progress)))

    def play_level_narration(self, level_index: int, volume: float = 0.55) -> None:
        """Play per-level narration if available. Missing audio stays silent."""
        key = f"narration_{level_index}"
        if self.enabled and key in self.sounds:
            self.play(key, volume)

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
        self.asset_dir.mkdir(parents=True, exist_ok=True)

        # --- Sound effects via text-to-sound-effects ---
        sfx_prompts: dict[str, str] = {
            "rotate_organic.mp3": "gentle wooden organic tile rotation, soft tactile click, calming nature sound",
            "connection_chime.mp3": "soft resonant crystal chime, warm digital garden tone, peaceful single note",
            "output_linked.mp3": "bright satisfying puzzle solved partial progress chime, glassy bell with gentle upward motion, short and encouraging",
            "leak_sealed.mp3": "soft clean sealing sound, tiny watery click and leaf shimmer, subtle but rewarding, very short",
            "blocked_tile.mp3": "gentle muted wooden knock, soft no-action feedback for a locked puzzle tile, not harsh, very short",
            "success_bloom.mp3": "calming success bloom, airy flower petals, warm sparkle, serene achievement",
            "ambient_garden.mp3": "subtle looping ambient soundscape, peaceful zen digital garden, soft wind through leaves, relaxing pads",
        }
        print("Generating sound effects...")
        for filename, prompt in sfx_prompts.items():
            output_path = self.asset_dir / filename
            print(f"  -> {filename}")
            audio = client.text_to_sound_effects.convert(
                text=prompt,
                duration_seconds=8.0 if filename == "ambient_garden.mp3" else 2.0,
                prompt_influence=0.45,
            )
            with output_path.open("wb") as file:
                for chunk in audio:
                    file.write(chunk)

        # --- Per-level narration via TTS ---
        narration_lines = [level.narration for level in build_levels()]
        print("Generating TTS narration...")
        for idx, text in enumerate(narration_lines):
            output_path = self.asset_dir / f"narration_level_{idx}.mp3"
            print(f"  -> narration_level_{idx}.mp3")
            audio_stream = client.text_to_speech.convert(
                text=text,
                voice_id="EXAVITQu4vr4xnSDxMaL",
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            )
            with output_path.open("wb") as file:
                for chunk in audio_stream:
                    file.write(chunk)

        # Generic fallback narration
        print("  -> narration_breathe.mp3")
        fallback = client.text_to_speech.convert(
            text="Well done. A piece of your attention is restored. The garden grows more whole.",
            voice_id="EXAVITQu4vr4xnSDxMaL",
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        with (self.asset_dir / "narration_breathe.mp3").open("wb") as file:
            for chunk in fallback:
                file.write(chunk)

        print(f"\n+ All Echo Garden audio assets saved to: {self.asset_dir}")


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


def reversed_x(angle_deg: float) -> float:
    return Vec2(1, 0).rotate(angle_deg).x


def rotate_channels(channels: tuple[tuple[int, ...], ...], rotation: int) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple((side + rotation) % 4 for side in channel) for channel in channels)


def mixed_flow_color(colors: Iterable[str]) -> tuple[int, int, int]:
    names = sorted(set(colors))
    if not names:
        return LINE_DIM
    rgb = [FLOW_PALETTE.get(name, TEXT) for name in names]
    blended = tuple(sum(color[idx] for color in rgb) // len(rgb) for idx in range(3))
    if len(names) > 1:
        blended = tuple(min(255, value + 16) for value in blended)
    return blended


def wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    """Wrap a short UI paragraph to fit a target pixel width."""

    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


class Tile:
    """A rotatable neural-root tile."""

    def __init__(self, row: int, col: int, kind: str, rotation: int) -> None:
        self.row = row
        self.col = col
        self.kind = kind
        self.base_channels = TILE_CHANNEL_LIBRARY[kind]
        self.rotation = rotation % 4
        self.visual_angle = self.rotation * 90.0
        self.target_angle = self.visual_angle
        self.connected = False
        self.is_source = False
        self.is_sink = False
        self.source_color: str | None = None
        self.sink_target: frozenset[str] = frozenset()
        self.hover = False
        self.leaking_sides: set[int] = set()
        self.active_channels: list[frozenset[str]] = [frozenset() for _ in self.base_channels]

    @property
    def rotatable(self) -> bool:
        return self.kind != "bridge"

    @property
    def channels(self) -> tuple[tuple[int, ...], ...]:
        return rotate_channels(self.base_channels, self.rotation)

    @property
    def sides(self) -> set[int]:
        open_sides: set[int] = set()
        for channel in self.channels:
            open_sides.update(channel)
        return open_sides

    def rotate_clockwise(self) -> None:
        if not self.rotatable:
            return
        self.rotation = (self.rotation + 1) % 4
        self.target_angle += 90.0

    def rotate_counterclockwise(self) -> None:
        if not self.rotatable:
            return
        self.rotation = (self.rotation - 1) % 4
        self.target_angle -= 90.0

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
        def reversed_x(angle):
            return Vec2(1, 0).rotate(angle).x
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

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, glow_phase: float, hint_highlight: bool = False) -> None:
        shadow = rect.move(0, 6)
        pygame.draw.rect(surface, (6, 22, 24), shadow, border_radius=18)

        base_color = TILE_HOVER if self.hover else TILE_DARK
        if self.connected:
            base_color = (22, 70, 72)
        pygame.draw.rect(surface, base_color, rect, border_radius=16)
        highlight = pygame.Rect(rect.x + 2, rect.y + 2, rect.width - 4, max(10, rect.height // 3))
        pygame.draw.rect(surface, (255, 255, 255, 10), highlight, border_radius=14)

        if hint_highlight:
            pulse = 180 + 75 * abs(reversed_x(glow_phase * 60 + self.row * 20 + self.col * 20))
            pygame.draw.rect(surface, (int(pulse), 120, 20), rect, width=3, border_radius=16)
        else:
            border = (61, 126, 127) if self.connected else (35, 96, 98)
            pygame.draw.rect(surface, border, rect, width=1, border_radius=16)

        center = Vec2(rect.center)
        half = rect.width * 0.5
        path_width = max(5, rect.width // 11)
        visual_vectors = {
            UP: Vec2(0, -rect.width * 0.36),
            RIGHT: Vec2(rect.width * 0.36, 0),
            DOWN: Vec2(0, rect.width * 0.36),
            LEFT: Vec2(-rect.width * 0.36, 0),
        }

        for index, base_channel in enumerate(self.base_channels):
            endpoints = [center + visual_vectors[side].rotate(self.visual_angle) for side in base_channel]
            flow = self.active_channels[index] if index < len(self.active_channels) else frozenset()
            active = mixed_flow_color(flow) if flow else LINE_DIM
            if flow:
                pulse = 0.70 + 0.30 * abs(Vec2(1, 0).rotate(glow_phase * 60 + index * 18).x)
                active = tuple(min(255, int(channel * pulse + 24)) for channel in active)

            if self.kind == "bridge" and len(endpoints) == 2:
                if flow:
                    self.draw_root_line(surface, endpoints[0], endpoints[1], active, path_width + 9, glow_phase)
                self.draw_root_line(surface, endpoints[0], endpoints[1], active, path_width, glow_phase)
                for end in endpoints:
                    pygame.draw.circle(surface, active, end, max(2, path_width // 2))
                continue

            if flow:
                for end in endpoints:
                    self.draw_root_line(surface, center, end, active, path_width + 9, glow_phase)
            for end in endpoints:
                self.draw_root_line(surface, center, end, active, path_width, glow_phase)
                pygame.draw.circle(surface, active, end, max(2, path_width // 2))
            if endpoints:
                pygame.draw.circle(surface, active, center, path_width)

        if self.connected and not (self.is_source or self.is_sink):
            bloom_color = mixed_flow_color(color for channel in self.active_channels for color in channel)
            pygame.draw.circle(surface, bloom_color, center, max(2, path_width // 2))

        for side in self.leaking_sides:
            marker = {UP: Vec2(0, -half + 8), RIGHT: Vec2(half - 8, 0), DOWN: Vec2(0, half - 8), LEFT: Vec2(-half + 8, 0)}[side]
            pygame.draw.circle(surface, LEAK, center + marker, max(3, path_width // 2))

        if self.is_source or self.is_sink:
            color = mixed_flow_color([self.source_color]) if self.is_source else mixed_flow_color(self.sink_target)
            radius = int(rect.width * (0.15 if self.is_source else 0.12))
            aura = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
            pygame.draw.circle(aura, (*color, 45), (radius * 3, radius * 3), radius * 3)
            pygame.draw.circle(aura, (*color, 230), (radius * 3, radius * 3), radius)
            if self.is_sink and len(self.sink_target) > 1:
                for dot_index, name in enumerate(sorted(self.sink_target)):
                    offset = Vec2(radius * 1.8, 0).rotate(dot_index * 360 / len(self.sink_target))
                    dot_pos = Vec2(radius * 3, radius * 3) + offset
                    pygame.draw.circle(aura, (*FLOW_PALETTE[name], 230), dot_pos, max(2, radius // 3))
            surface.blit(aura, center - Vec2(radius * 3, radius * 3), special_flags=pygame.BLEND_PREMULTIPLIED)


class Grid:
    """Grid, mouse-click rotation, and BFS connection checking."""

    def __init__(self, level: Level) -> None:
        self.level = level
        self.size = level.size
        self.connected_count = 0
        self.connected_sinks = 0
        self.leak_count = 0
        self.complete = False
        self.last_new_connection = False
        self.visited: set[tuple[int, int]] = set()
        self.satisfied_sinks: set[tuple[int, int]] = set()
        self.sink_colors: dict[tuple[int, int], frozenset[str]] = {}
        self.tiles: list[list[Tile]] = []
        self._build_tiles()
        self.check_connections()

    def _build_tiles(self) -> None:
        starts = set(self.level.starts)
        sinks = set(self.level.sinks)
        default_source = self.level.start_colors[0] if self.level.start_colors else "gold"
        source_colors = self.level.start_colors or tuple(default_source for _ in self.level.starts)
        sink_targets = self.level.sink_targets or tuple((default_source,) for _ in self.level.sinks)
        source_map = dict(zip(self.level.starts, source_colors))
        sink_map = {pos: frozenset(target) for pos, target in zip(self.level.sinks, sink_targets)}
        for row in range(self.size):
            line: list[Tile] = []
            for col in range(self.size):
                tile = Tile(row, col, self.level.tiles[row][col], self.level.rotations[row][col])
                tile.is_source = (row, col) in starts
                tile.is_sink = (row, col) in sinks
                tile.source_color = source_map.get((row, col))
                tile.sink_target = sink_map.get((row, col), frozenset())
                line.append(tile)
            self.tiles.append(line)

    def iter_tiles(self) -> Iterable[Tile]:
        for row in self.tiles:
            yield from row

    def tile_rect(self, tile: Tile, board_rect: pygame.Rect) -> pygame.Rect:
        gap = max(6, board_rect.width // 90)
        cell = (board_rect.width - gap * (self.size - 1)) // self.size
        return pygame.Rect(board_rect.x + tile.col * (cell + gap), board_rect.y + tile.row * (cell + gap), cell, cell)

    def tile_at_point(self, pos: tuple[int, int], board_rect: pygame.Rect) -> Tile | None:
        for tile in self.iter_tiles():
            if self.tile_rect(tile, board_rect).collidepoint(pos):
                return tile
        return None

    def rotate_tile(self, tile: Tile | None, clockwise: bool = True) -> bool:
        if tile is None or not tile.rotatable:
            return False
        if clockwise:
            tile.rotate_clockwise()
        else:
            tile.rotate_counterclockwise()
        self.check_connections()
        return True

    def handle_click(self, pos: tuple[int, int], board_rect: pygame.Rect, clockwise: bool = True) -> bool:
        if self.rotate_tile(self.tile_at_point(pos, board_rect), clockwise):
            return True
        return False

    def update(self, dt: float, mouse_pos: tuple[int, int], board_rect: pygame.Rect) -> None:
        for tile in self.iter_tiles():
            tile.hover = self.tile_rect(tile, board_rect).collidepoint(mouse_pos)
            tile.update(dt)

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def check_connections(self) -> None:
        previous_count = self.connected_count
        previous_sinks = self.connected_sinks
        for tile in self.iter_tiles():
            tile.connected = False
            tile.leaking_sides.clear()
            tile.active_channels = [frozenset() for _ in tile.base_channels]

        channel_lookup: dict[tuple[int, int, int], tuple[int, ...]] = {}
        port_lookup: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        adjacency: dict[tuple[int, int, int], set[tuple[int, int, int]]] = {}

        for tile in self.iter_tiles():
            for index, channel in enumerate(tile.channels):
                node = (tile.row, tile.col, index)
                channel_lookup[node] = channel
                adjacency[node] = set()
                for side in channel:
                    port_lookup[(tile.row, tile.col, side)] = node

        for node, channel in channel_lookup.items():
            row, col, _ = node
            for side in channel:
                dc, dr = DIRS[side]
                nr, nc = row + dr, col + dc
                if not self.in_bounds(nr, nc):
                    continue
                other = port_lookup.get((nr, nc, OPPOSITE[side]))
                if other is not None:
                    adjacency[node].add(other)

        flow_sets: dict[tuple[int, int, int], set[str]] = {node: set() for node in channel_lookup}
        queue: deque[tuple[int, int, int]] = deque()
        for row, col in self.level.starts:
            tile = self.tiles[row][col]
            if not tile.source_color:
                continue
            for index, _ in enumerate(tile.channels):
                node = (row, col, index)
                flow_sets[node].add(tile.source_color)
                queue.append(node)

        while queue:
            node = queue.popleft()
            for neighbor in adjacency[node]:
                previous_size = len(flow_sets[neighbor])
                flow_sets[neighbor].update(flow_sets[node])
                if len(flow_sets[neighbor]) != previous_size:
                    queue.append(neighbor)

        active_cells: set[tuple[int, int]] = set()
        total_leaks = 0
        for node, colors in flow_sets.items():
            row, col, index = node
            tile = self.tiles[row][col]
            if colors:
                tile.active_channels[index] = frozenset(colors)
                tile.connected = True
                active_cells.add((row, col))

        for node, channel in channel_lookup.items():
            row, col, _ = node
            if not flow_sets[node]:
                continue
            tile = self.tiles[row][col]
            for side in channel:
                dc, dr = DIRS[side]
                nr, nc = row + dr, col + dc
                other = port_lookup.get((nr, nc, OPPOSITE[side])) if self.in_bounds(nr, nc) else None
                if other is None:
                    tile.leaking_sides.add(side)
                    total_leaks += 1

        self.visited = active_cells
        self.connected_count = len(active_cells)
        self.satisfied_sinks = set()
        self.sink_colors = {}
        for row, col in self.level.sinks:
            tile = self.tiles[row][col]
            received = frozenset(color for channel in tile.active_channels for color in channel)
            self.sink_colors[(row, col)] = received
            if received and received == tile.sink_target:
                self.satisfied_sinks.add((row, col))

        self.connected_sinks = len(self.satisfied_sinks)
        self.leak_count = total_leaks
        self.complete = self.connected_sinks == len(self.level.sinks) and total_leaks == 0
        self.last_new_connection = self.connected_count > previous_count or self.connected_sinks > previous_sinks

    @property
    def progress(self) -> float:
        return self.connected_sinks / max(1, len(self.level.sinks))

    def hint_tiles(self) -> set[tuple[int, int]]:
        """Highlight the current problem area rather than a hidden full solution."""

        highlighted: set[tuple[int, int]] = set()
        for tile in self.iter_tiles():
            if tile.connected and tile.leaking_sides:
                highlighted.add((tile.row, tile.col))
                for side in tile.sides:
                    dc, dr = DIRS[side]
                    nr, nc = tile.row + dr, tile.col + dc
                    if self.in_bounds(nr, nc) and not self.tiles[nr][nc].connected:
                        highlighted.add((nr, nc))

        if highlighted:
            return highlighted

        for row, col in self.level.sinks:
            if (row, col) in self.satisfied_sinks:
                continue
            highlighted.add((row, col))
            for dc, dr in DIRS.values():
                nr, nc = row + dr, col + dc
                if self.in_bounds(nr, nc) and self.tiles[nr][nc].connected:
                    highlighted.add((nr, nc))
        return highlighted

    def draw(self, surface: pygame.Surface, board_rect: pygame.Rect, glow_phase: float, hint_mode: bool = False) -> None:
        board_shadow = board_rect.inflate(48, 48).move(0, 10)
        pygame.draw.rect(surface, (6, 20, 24), board_shadow, border_radius=34)
        pygame.draw.rect(surface, (10, 37, 42), board_rect.inflate(32, 32), border_radius=28)
        pygame.draw.rect(surface, (31, 98, 100), board_rect.inflate(32, 32), width=1, border_radius=28)
        self.draw_level_art(surface, board_rect, glow_phase)
        hint_tiles = self.hint_tiles() if hint_mode else set()
        for tile in self.iter_tiles():
            hint = (tile.row, tile.col) in hint_tiles
            tile.draw(surface, self.tile_rect(tile, board_rect), glow_phase, hint)

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
        self.state = STATE_TITLE
        self.font_title = pygame.font.Font(None, 112)
        self.font_big = pygame.font.Font(None, 82)
        self.font = pygame.font.Font(None, 34)
        self.font_small = pygame.font.Font(None, 24)
        self.font_tiny = pygame.font.Font(None, 20)
        self.levels = build_levels()
        self.level_index = 0
        self.grid = Grid(self.levels[self.level_index])
        self.audio = AudioManager(Path(__file__).parent / "assets" / "sounds")
        self.particles: list[Particle] = []
        self.glow_phase = 0.0
        self.move_count = 0
        self.success_announced = False
        self.completed_levels: set[int] = set()
        self.debug_overlay = False
        self.hint_mode = False
        self.show_tutorial = True
        self.feedback_text = ""
        self.feedback_color = MINT
        self.feedback_timer = 0.0
        self.last_sink_progress = self.grid.connected_sinks
        self.last_leak_count = self.grid.leak_count

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, MAX_FRAME_DT)
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
        start_y = height // 2 + 146
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
        self.reset_level(play_narration=True)
        self.state = STATE_PLAYING

    def set_state(self, next_state: str) -> None:
        self.state = next_state

    def show_feedback(self, text: str, color: tuple[int, int, int] = MINT, duration: float = 1.4) -> None:
        self.feedback_text = text
        self.feedback_color = color
        self.feedback_timer = duration

    def current_board_rect(self) -> pygame.Rect:
        return self.board_rect()

    def try_rotate_pointer_tile(self, clockwise: bool) -> bool:
        if self.state != STATE_PLAYING:
            return False
        board = self.current_board_rect()
        tile = self.grid.tile_at_point(pygame.mouse.get_pos(), board)
        if tile is None:
            return False
        if not self.grid.rotate_tile(tile, clockwise):
            self.show_feedback("Bridge tiles are fixed", MUTED_TEXT, duration=0.9)
            self.audio.play("blocked", 0.42, cooldown=0.14)
            return False
        self.show_tutorial = False
        self.move_count += 1
        self.audio.play("rotate", 0.76, cooldown=0.03)
        return True

    def handle_keydown(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            if self.state == STATE_PLAYING:
                self.set_state(STATE_TITLE)
            elif self.state == STATE_LEVEL_SELECT:
                self.set_state(STATE_TITLE)
            else:
                self.running = False
        elif event.key == pygame.K_f:
            self.toggle_fullscreen()
        elif event.key == pygame.K_d:
            self.debug_overlay = not self.debug_overlay
        elif event.key == pygame.K_h:
            self.hint_mode = not self.hint_mode
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == STATE_PLAYING and self.grid.complete:
            self.advance_level()
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == STATE_TITLE:
            self.start_playing()
        elif event.key == pygame.K_r and self.state == STATE_PLAYING:
            self.reset_level()
        elif event.key in (pygame.K_q, pygame.K_LEFT) and self.state == STATE_PLAYING:
            self.try_rotate_pointer_tile(clockwise=False)
        elif event.key in (pygame.K_e, pygame.K_RIGHT) and self.state == STATE_PLAYING:
            self.try_rotate_pointer_tile(clockwise=True)

    def handle_title_click(self, pos: tuple[int, int]) -> None:
        for action, rect in self.title_button_rects().items():
            if not rect.collidepoint(pos):
                continue
            if action == "continue":
                self.start_playing()
            elif action == "levels":
                self.set_state(STATE_LEVEL_SELECT)
            elif action == "quit":
                self.running = False
            break

    def handle_level_select_click(self, pos: tuple[int, int]) -> None:
        for index, rect in enumerate(self.level_card_rects()):
            if rect.collidepoint(pos):
                self.load_level(index)
                break

    def handle_playing_click(self, pos: tuple[int, int], clockwise: bool) -> None:
        board = self.current_board_rect()
        if self.grid.complete:
            if self.complete_overlay_rect().collidepoint(pos):
                self.advance_level()
            return
        tile = self.grid.tile_at_point(pos, board)
        if tile is None:
            return
        if self.grid.rotate_tile(tile, clockwise=clockwise):
            self.show_tutorial = False
            self.move_count += 1
            self.audio.play("rotate", 0.76, cooldown=0.03)
        else:
            self.show_feedback("Bridge tiles are fixed", MUTED_TEXT, duration=0.9)
            self.audio.play("blocked", 0.42, cooldown=0.14)

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                if self.state == STATE_TITLE:
                    if event.button != 1:
                        continue
                    self.handle_title_click(event.pos)
                elif self.state == STATE_LEVEL_SELECT:
                    if event.button != 1:
                        continue
                    self.handle_level_select_click(event.pos)
                elif self.state == STATE_PLAYING:
                    self.handle_playing_click(event.pos, clockwise=event.button == 1)

    def start_playing(self) -> None:
        self.set_state(STATE_PLAYING)
        if self.move_count == 0 and not self.grid.complete:
            self.audio.play_level_narration(self.level_index)

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        self.screen = pygame.display.set_mode(SCREEN_SIZE, flags)

    def reset_level(self, play_narration: bool = False) -> None:
        self.grid = Grid(self.levels[self.level_index])
        self.move_count = 0
        self.success_announced = False
        self.particles.clear()
        self.show_tutorial = self.level_index == 0 and self.level_index not in self.completed_levels
        self.feedback_text = ""
        self.feedback_timer = 0.0
        self.last_sink_progress = self.grid.connected_sinks
        self.last_leak_count = self.grid.leak_count
        if play_narration:
            self.audio.play_level_narration(self.level_index)

    def update(self, dt: float) -> None:
        self.glow_phase += dt
        self.particles = [p for p in self.particles if p.update(dt)]
        self.feedback_timer = max(0.0, self.feedback_timer - dt)
        self.audio.tick(dt)
        if self.state != STATE_PLAYING:
            return

        self.grid.update(dt, pygame.mouse.get_pos(), self.current_board_rect())
        self.audio.set_peacefulness(self.grid.progress)
        if self.grid.connected_sinks > self.last_sink_progress:
            self.show_feedback("Output linked", WARM_GOLD)
            self.audio.play("output", 0.66, cooldown=0.18)
        elif self.grid.leak_count < self.last_leak_count and self.move_count > 0:
            self.show_feedback("Leak sealed", MINT, duration=1.0)
            self.audio.play("seal", 0.52, cooldown=0.16)
        self.last_sink_progress = self.grid.connected_sinks
        self.last_leak_count = self.grid.leak_count
        if self.grid.last_new_connection:
            self.audio.play("connect", 0.80, cooldown=0.08)
            self.grid.last_new_connection = False
        if self.grid.complete and not self.success_announced:
            self.success_announced = True
            self.completed_levels.add(self.level_index)
            self.audio.play("success", 0.92)
            self.show_feedback("Route complete", WARM_GOLD, duration=2.2)
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
        self.reset_level(play_narration=True)

    def draw(self) -> None:
        self.screen.fill(DEEP_TEAL)
        self.draw_background()
        if self.state == STATE_TITLE:
            self.draw_title()
        elif self.state == STATE_LEVEL_SELECT:
            self.draw_level_select()
        else:
            self.draw_game()
        for particle in self.particles:
            particle.draw(self.screen)
        if self.state == STATE_PLAYING:
            self.draw_debug_overlay()
        pygame.display.flip()

    def draw_background(self) -> None:
        width, height = self.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        halos = [
            (Vec2(width * 0.18, height * 0.22), MINT, 220),
            (Vec2(width * 0.82, height * 0.18), SOFT_PURPLE, 200),
            (Vec2(width * 0.75, height * 0.78), WARM_GOLD, 180),
        ]
        for center, color, radius in halos:
            orb = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(orb, (*color, 22), (radius, radius), radius)
            pygame.draw.circle(orb, (*color, 38), (radius, radius), radius // 2)
            self.screen.blit(orb, center - Vec2(radius, radius), special_flags=pygame.BLEND_PREMULTIPLIED)
        for i in range(34):
            x = (i * 149 + int(self.glow_phase * 9)) % (width + 80) - 40
            y = (i * 83) % (height + 80) - 40
            pygame.draw.circle(self.screen, (45, 90, 88), (x, y), 1 + i % 3)
        for i in range(9):
            drift = Vec2(width * 0.14 + i * width * 0.09, height * (0.18 + (i % 3) * 0.18))
            drift += Vec2(0, 12).rotate(self.glow_phase * 18 + i * 37)
            rect = pygame.Rect(0, 0, 54, 18).move(drift.x - 27, drift.y - 9)
            pygame.draw.ellipse(overlay, (*ROSE, 20), rect)
            pygame.draw.ellipse(overlay, (*TEXT, 10), rect.inflate(-10, -8))
        self.screen.blit(overlay, (0, 0))

    def draw_panel(self, rect: pygame.Rect, accent: tuple[int, int, int] = MINT) -> None:
        shadow = rect.move(0, 6)
        pygame.draw.rect(self.screen, (6, 20, 24), shadow, border_radius=20)
        pygame.draw.rect(self.screen, PANEL_TEAL, rect, border_radius=20)
        pygame.draw.rect(self.screen, accent, rect, width=1, border_radius=20)

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
        hint = self.font_small.render("Enter starts. F fullscreen. Esc exits. H highlights the active trouble spot.", True, MUTED_TEXT)
        self.screen.blit(title, title.get_rect(center=(width // 2, height // 2 - 150)))
        subtitle_lines = wrap_text(
            self.font,
            "A root-routing logic puzzle. Match colors, cross cleanly, and seal every route.",
            min(760, width - 110),
        )
        for idx, line in enumerate(subtitle_lines):
            rendered = self.font.render(line, True, MUTED_TEXT)
            self.screen.blit(rendered, rendered.get_rect(center=(width // 2, height // 2 - 54 + idx * 34)))
        self.screen.blit(hint, hint.get_rect(center=(width // 2, height - 36)))

        center = Vec2(width // 2, height // 2 - 244)
        for radius, color in [(82, SOFT_PURPLE), (56, MINT), (28, WARM_GOLD)]:
            pulse = 0.85 + 0.15 * abs(Vec2(1, 0).rotate(self.glow_phase * 40 + radius).x)
            draw_color = tuple(min(255, int(c * pulse)) for c in color)
            pygame.draw.circle(self.screen, draw_color, center, radius, width=2)
        for index in range(8):
            petal = pygame.Rect(0, 0, 74, 26)
            petal.center = center + Vec2(0, -92).rotate(index * 45 + self.glow_phase * 6)
            pygame.draw.ellipse(self.screen, SOFT_PURPLE if index % 2 == 0 else MINT, petal)
            pygame.draw.ellipse(self.screen, TEXT, petal.inflate(-36, -12), 1)

        guide = pygame.Rect(width // 2 - 230, height // 2 + 28, 460, 114)
        self.draw_panel(guide, WARM_GOLD)
        guide_lines = [
            "1. Sources and outputs are color matched.",
            "2. Standard tiles mix. Bridge tiles cross without mixing.",
            "3. Red sparks mark open ends or broken joins.",
        ]
        for idx, line in enumerate(guide_lines):
            color = TEXT if idx == 0 else MUTED_TEXT
            rendered = self.font_small.render(line, True, color)
            self.screen.blit(rendered, (guide.x + 22, guide.y + 18 + idx * 28))

        buttons = self.title_button_rects()
        start_label = "Resume Puzzle" if self.completed_levels or self.level_index else "Start Puzzle"
        self.draw_button(buttons["continue"], start_label, primary=True)
        self.draw_button(buttons["levels"], "Puzzle Select")
        self.draw_button(buttons["quit"], "Quit")

    def draw_level_select(self) -> None:
        width, height = self.screen.get_size()
        title = self.font_big.render("Choose a Puzzle", True, TEXT)
        subtitle = self.font_small.render("Click any card to load it. Esc returns to the title screen.", True, MUTED_TEXT)
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
            status = self.font_small.render("solved" if index in self.completed_levels else "unsolved", True, WARM_GOLD if index in self.completed_levels else MUTED_TEXT)
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
        self.grid.draw(self.screen, board, self.glow_phase, self.hint_mode)
        self.screen.blit(self.font_big.render("Echo Garden", True, TEXT), (38, 26))
        left_panel = pygame.Rect(26, 90, max(210, board.x - 46), 170)
        self.draw_panel(left_panel, WARM_GOLD)
        self.screen.blit(self.font.render(f"{level.name} - {level.size}x{level.size}", True, WARM_GOLD), (left_panel.x + 18, left_panel.y + 16))
        self.screen.blit(self.font_small.render("Goal", True, MINT), (left_panel.x + 18, left_panel.y + 54))
        objective_width = left_panel.width - 36
        for idx, line in enumerate(wrap_text(self.font_small, level.narration, objective_width)):
            self.screen.blit(self.font_small.render(line, True, MUTED_TEXT), (left_panel.x + 18, left_panel.y + 78 + idx * 22))
        controls = self.font_small.render("Click: rotate  Q/E or arrows: rotate  H: hint  R: reset  Esc: title", True, MUTED_TEXT)
        self.screen.blit(controls, (44, self.screen.get_height() - 36))

        progress_panel = pygame.Rect(self.screen.get_width() - 286, 34, 244, 78)
        self.draw_panel(progress_panel, MINT)
        progress_rect = pygame.Rect(progress_panel.x + 18, progress_panel.y + 14, progress_panel.width - 36, 12)
        pygame.draw.rect(self.screen, PANEL_TEAL, progress_rect, border_radius=6)
        fill = progress_rect.copy()
        fill.width = int(progress_rect.width * self.grid.progress)
        pygame.draw.rect(self.screen, MINT, fill, border_radius=6)
        self.screen.blit(self.font_tiny.render("outputs linked", True, MUTED_TEXT), (progress_panel.x + 18, progress_panel.y + 34))
        outputs = self.font_tiny.render(f"{self.grid.connected_sinks}/{len(level.sinks)} connected", True, TEXT)
        self.screen.blit(outputs, (progress_panel.x + 116, progress_panel.y + 34))
        self.screen.blit(self.font_tiny.render(f"rotations {self.move_count}", True, MUTED_TEXT), (progress_panel.x + 18, progress_panel.y + 52))

        legend = pygame.Rect(self.screen.get_width() - 286, 124, 244, 268)
        self.draw_panel(legend, MINT)
        labels = [
            (WARM_GOLD, "Source", "A source launches its color into the network."),
            (SOFT_PURPLE, "Output", "An output only counts if the final color matches."),
            (MINT, "Bridge", "Bridge tiles let two routes cross without mixing."),
            (LEAK, "Leak", "Red sparks mean an open end or a bad connection."),
        ]
        for idx, (color, title, description) in enumerate(labels):
            y = legend.y + 16 + idx * 58
            pygame.draw.circle(self.screen, color, (legend.x + 20, y + 10), 7)
            self.screen.blit(self.font_small.render(title, True, TEXT), (legend.x + 36, y))
            for line_idx, line in enumerate(wrap_text(self.font_tiny, description, legend.width - 54)):
                self.screen.blit(self.font_tiny.render(line, True, MUTED_TEXT), (legend.x + 36, y + 22 + line_idx * 16))

        status_text = "Route sealed" if self.grid.leak_count == 0 else f"Seal {self.grid.leak_count} leak{'s' if self.grid.leak_count != 1 else ''}"
        status_color = MINT if self.grid.leak_count == 0 else LEAK
        self.screen.blit(self.font_small.render(status_text, True, status_color), (legend.x + 18, legend.bottom - 30))

        if self.hint_mode and not self.grid.complete:
            wrong_text = self.font_small.render("Hint mode: highlighted tiles are the next likely fix on the active route.", True, (220, 140, 40))
            self.screen.blit(wrong_text, (progress_rect.x, progress_rect.y - 20))

        if self.feedback_timer > 0.0 and self.feedback_text:
            alpha = min(255, int(255 * min(1.0, self.feedback_timer)))
            banner = pygame.Surface((320, 44), pygame.SRCALPHA)
            pygame.draw.rect(banner, (8, 28, 32, 190), banner.get_rect(), border_radius=14)
            pygame.draw.rect(banner, (*self.feedback_color, alpha), banner.get_rect(), width=1, border_radius=14)
            text = self.font_small.render(self.feedback_text, True, self.feedback_color)
            banner.blit(text, text.get_rect(center=banner.get_rect().center))
            self.screen.blit(banner, banner.get_rect(center=(board.centerx, board.y - 36)))

        if self.show_tutorial and not self.grid.complete:
            tutorial_width = max(360, min(board.width - 28, 430))
            tutorial = pygame.Rect(board.x - 4, board.y - 72, tutorial_width, 88)
            self.draw_panel(tutorial, WARM_GOLD)
            lines = [
                "Tutorial: connect the gold source to the matching gold output.",
                "Red sparks show where the active route is open or mismatched.",
                "Click any tile to begin.",
            ]
            for idx, line in enumerate(lines):
                color = TEXT if idx == 0 else MUTED_TEXT
                self.screen.blit(self.font_small.render(line, True, color), (tutorial.x + 18, tutorial.y + 16 + idx * 22))

        if self.grid.complete:
            panel = self.complete_overlay_rect()
            self.draw_panel(panel, MINT)
            restored = self.font.render("Route complete", True, WARM_GOLD)
            line = self.font_small.render("All required outputs are connected and the network is sealed.", True, TEXT)
            prompt = self.font_small.render("Press Space / Enter or click this panel for the next puzzle", True, MUTED_TEXT)
            self.screen.blit(restored, restored.get_rect(center=(panel.centerx, panel.y + 30)))
            self.screen.blit(line, line.get_rect(center=(panel.centerx, panel.y + 62)))
            self.screen.blit(prompt, prompt.get_rect(center=(panel.centerx, panel.y + 90)))


def build_levels() -> list[Level]:
    """Six handcrafted levels, progressing from clean routing into crossing and color mixing."""

    return [
        Level(
            name="Root Link",
            size=3,
            starts=((2, 0),),
            sinks=((0, 2),),
            tiles=(("corner", "end", "end"), ("corner", "corner", "straight"), ("end", "corner", "corner")),
            rotations=((2, 0, 3), (0, 1, 1), (1, 0, 2)),
            narration="Connect the gold source to the matching output. Every red spark means the route is still broken.",
            start_colors=("gold",),
            sink_targets=(("gold",),),
            art_style="flower",
            solution_rotations=((1, 3, 2), (1, 2, 0), (0, 0, 3)),
        ),
        Level(
            name="Corner Weave",
            size=4,
            starts=((0, 0),),
            sinks=((3, 3),),
            tiles=(("end", "corner", "corner", "end"), ("corner", "corner", "corner", "corner"), ("end", "corner", "corner", "corner"), ("corner", "end", "corner", "end")),
            rotations=((1, 1, 2, 2), (2, 1, 1, 2), (2, 2, 1, 1), (2, 2, 2, 0)),
            narration="Use corners and straights to push one clean gold route from the source to the far output.",
            start_colors=("gold",),
            sink_targets=(("gold",),),
            art_style="vine_mandala",
            solution_rotations=((1, 2, 0, 0), (0, 0, 2, 0), (0, 0, 0, 2), (0, 0, 0, 0)),
        ),
        Level(
            name="Split Canopy",
            size=5,
            starts=((2, 0),),
            sinks=((0, 4), (4, 4)),
            tiles=(("end", "corner", "corner", "straight", "end"), ("corner", "end", "straight", "end", "corner"), ("end", "straight", "tee", "end", "corner"), ("corner", "end", "straight", "end", "corner"), ("end", "corner", "corner", "straight", "end")),
            rotations=((0, 3, 2, 0, 3), (1, 2, 3, 3, 2), (1, 0, 3, 0, 2), (2, 3, 3, 2, 1), (3, 2, 1, 0, 3)),
            narration="Now split one gold source into two matching outputs. Build both branches without leaking either one.",
            start_colors=("gold",),
            sink_targets=(("gold",), ("gold",)),
            art_style="root_symmetry",
            solution_rotations=((2, 1, 1, 1, 3), (3, 0, 0, 1, 0), (1, 1, 2, 2, 0), (0, 1, 0, 0, 3), (1, 0, 0, 1, 3)),
        ),
        Level(
            name="Triple Run",
            size=5,
            starts=((4, 0),),
            sinks=((0, 0), (0, 4), (4, 4)),
            tiles=(("end", "corner", "corner", "straight", "end"), ("straight", "corner", "straight", "corner", "straight"), ("corner", "straight", "cross", "straight", "corner"), ("corner", "end", "straight", "end", "straight"), ("end", "straight", "corner", "corner", "end")),
            rotations=((2, 2, 2, 0, 3), (3, 0, 3, 1, 2), (1, 0, 1, 0, 3), (2, 0, 3, 1, 3), (1, 0, 0, 2, 0)),
            narration="Three outputs are live now. Use the cross junction well, and do not leave loose ends behind.",
            start_colors=("gold",),
            sink_targets=(("gold",), ("gold",), ("gold",)),
            art_style="full_garden",
            solution_rotations=((2, 0, 1, 1, 3), (0, 2, 0, 3, 0), (0, 1, 0, 1, 2), (0, 2, 0, 3, 0), (1, 1, 3, 0, 0)),
        ),
        Level(
            name="Cross Current",
            size=5,
            starts=((2, 0), (0, 2)),
            sinks=((2, 4), (4, 2)),
            tiles=(
                ("corner", "corner", "end", "corner", "corner"),
                ("corner", "corner", "straight", "corner", "corner"),
                ("end", "straight", "bridge", "straight", "end"),
                ("corner", "corner", "straight", "corner", "corner"),
                ("corner", "corner", "end", "corner", "corner"),
            ),
            rotations=((1, 2, 1, 0, 3), (2, 1, 1, 3, 0), (0, 0, 0, 0, 2), (1, 0, 1, 2, 3), (3, 1, 2, 0, 1)),
            narration="Two routes cross here. Use the bridge tile so gold and mint pass through each other without mixing.",
            start_colors=("gold", "mint"),
            sink_targets=(("gold",), ("mint",)),
            art_style="root_symmetry",
            solution_rotations=((0, 0, 2, 0, 0), (0, 0, 0, 0, 0), (1, 1, 0, 1, 3), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)),
        ),
        Level(
            name="Color Fusion",
            size=4,
            starts=((1, 0), (0, 1)),
            sinks=((1, 3),),
            tiles=(
                ("corner", "end", "corner", "corner"),
                ("end", "tee", "straight", "end"),
                ("corner", "corner", "corner", "corner"),
                ("corner", "end", "corner", "corner"),
            ),
            rotations=((1, 0, 2, 3), (2, 0, 0, 2), (0, 1, 2, 3), (3, 1, 0, 2)),
            narration="Standard tiles mix colors. Merge gold and rose, then send the combined flow into the matching output.",
            start_colors=("gold", "rose"),
            sink_targets=(("gold", "rose"),),
            art_style="full_garden",
            solution_rotations=((0, 2, 0, 0), (1, 3, 1, 3), (0, 0, 0, 0), (0, 0, 0, 0)),
        ),
    ]
