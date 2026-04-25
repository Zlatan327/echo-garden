"""
Pipe Puzzle  —  Echo Garden

Classic pipe-rotation puzzle. Rotate every tile so ALL pipes on the
grid form one sealed network with no open ends.

Controls:
  Click            rotate tile clockwise
  Right-click      rotate tile counter-clockwise
  R                reset level
  S                reveal solution (animates tiles into place)
  N / Enter        next level (after solving)
  F                toggle fullscreen
  Esc              title / quit
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from random import choice, uniform
from typing import Iterable

import pygame

# ── Window ────────────────────────────────────────────────────────────────────
SW, SH = 1080, 720
FPS    = 60
Vec2   = pygame.math.Vector2

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = (  8,  12,  20)       # near-black
PANEL       = ( 13,  19,  36)
BOARD_BG    = ( 10,  15,  28)
CELL_OFF    = ( 16,  24,  44)       # idle tile fill
CELL_HOV    = ( 26,  40,  72)       # hovered tile fill
CELL_ON     = ( 12,  36,  56)       # connected tile fill
PIPE_OFF    = ( 40,  62, 108)       # unconnected pipe segments
BORDER_OFF  = ( 24,  38,  72)
BORDER_HOV  = ( 60, 200, 160)
PIPE_LEAK   = (220,  50,  70)       # open-end / mismatch indicator
TEXT        = (215, 228, 248)
TEXTD       = ( 80, 110, 152)
SUCCESS_COL = (  0, 245, 152)

# Per-level pipe colours (connected state)
LEVEL_COLS = [
    (  0, 210, 168),   # 1 mint
    (  0, 160, 255),   # 2 neon-blue
    (255, 140,   0),   # 3 orange
    (180,  80, 255),   # 4 violet
    (255,  70, 140),   # 5 hot-pink
]

# ── Tile definitions ──────────────────────────────────────────────────────────
UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
# (col_delta, row_delta) — matches the grid address arithmetic
DMAP = {UP: (0, -1), RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0)}
OPP  = {UP: DOWN, RIGHT: LEFT, DOWN: UP, LEFT: RIGHT}

# Base openings for each type (rotation=0, opening in UP direction)
TLIB: dict[str, set[int]] = {
    "end":      {UP},
    "straight": {UP, DOWN},
    "corner":   {UP, RIGHT},
    "tee":      {UP, RIGHT, DOWN},
    "cross":    {UP, RIGHT, DOWN, LEFT},
}


# ── Level ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Level:
    name:     str
    size:     int
    tiles:    tuple[tuple[str, ...], ...]
    start_rotations: tuple[tuple[int, ...], ...]     # scrambled start state
    solution_rotations: tuple[tuple[int, ...], ...]  # solved state
    theme:    int = 0                                # index into LEVEL_COLS


# ── Tiny synthesised audio ────────────────────────────────────────────────────
def _tone(freq: float, ms: int, vol: float = 0.30,
          wave: str = "sine", decay: int = 70) -> pygame.mixer.Sound:
    sr  = 44_100
    n   = int(sr * ms / 1000)
    buf = bytearray(n * 4)
    for i in range(n):
        t   = i / sr
        raw = math.sin(2 * math.pi * freq * t) if wave == "sine" else (
              2 * abs(2 * (t * freq - math.floor(t * freq + 0.5))) - 1)
        dcy = int(sr * decay / 1000)
        env = (n - i) / max(1, dcy) if i > n - dcy else 1.0
        v   = max(-32768, min(32767, int(raw * env * vol * 32767)))
        lo, hi = v & 0xFF, (v >> 8) & 0xFF
        b = i * 4
        buf[b], buf[b+1], buf[b+2], buf[b+3] = lo, hi, lo, hi
    return pygame.mixer.Sound(buffer=bytes(buf))


class Audio:
    def __init__(self, asset_dir: Path) -> None:
        self.ok = False
        self.s: dict[str, pygame.mixer.Sound] = {}
        try:
            pygame.mixer.init(44_100, -16, 2, 512)
            self.ok = True
        except pygame.error:
            return
        # MP3 assets (optional)
        for k, fn in [("rotate", "rotate_organic.mp3"),
                      ("connect", "connection_chime.mp3"),
                      ("win", "success_bloom.mp3")]:
            p = asset_dir / fn
            if p.exists():
                try:
                    self.s[k] = pygame.mixer.Sound(str(p))
                except Exception:
                    pass
        # Synth fallbacks
        for k, args in [
            ("rotate",  dict(freq=400, ms=50,  vol=0.22, wave="sine")),
            ("connect", dict(freq=600, ms=90,  vol=0.28, wave="sine")),
            ("bad",     dict(freq=180, ms=70,  vol=0.18, wave="tri")),
            ("win",     dict(freq=528, ms=380, vol=0.36, wave="sine", decay=180)),
        ]:
            if k not in self.s:
                try:
                    self.s[k] = _tone(**args)
                except Exception:
                    pass
        music = asset_dir / "ambient_garden.mp3"
        if music.exists():
            try:
                pygame.mixer.music.load(str(music))
                pygame.mixer.music.set_volume(0.18)
                pygame.mixer.music.play(-1)
            except Exception:
                pass

    def play(self, name: str, vol: float = 0.5) -> None:
        if self.ok and name in self.s:
            s = self.s[name]
            s.stop()   # prevent overlapping / stacking
            s.set_volume(max(0., min(1., vol)))
            s.play()


# ── Particles ──────────────────────────────────────────────────────────────────
class Particle:
    def __init__(self, pos: Vec2, col: tuple) -> None:
        self.pos  = Vec2(pos)
        self.vel  = Vec2(uniform(-1.2, 1.2), uniform(-1.8, 0.4)) * uniform(55, 145)
        self.col  = col
        self.life = uniform(0.5, 1.7)
        self.ml   = self.life
        self.r    = uniform(3, 8)

    def update(self, dt: float) -> bool:
        self.life -= dt
        self.vel  *= 0.96
        self.pos  += self.vel * dt
        return self.life > 0

    def draw(self, surf: pygame.Surface) -> None:
        a = int(200 * max(0, self.life / self.ml))
        r = max(1, int(self.r * (self.life / self.ml)))
        s = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.col[:3], a), (r*2, r*2), r)
        surf.blit(s, (int(self.pos.x) - r*2, int(self.pos.y) - r*2))


# ── Pipe-arm drawing ──────────────────────────────────────────────────────────
def _rot_vec(bx: float, by: float, deg: float) -> tuple[float, float]:
    """Rotate base vector by deg degrees clockwise (screen-space)."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return bx * ca - by * sa, bx * sa + by * ca


def _draw_arm(surf: pygame.Surface,
              cx: float, cy: float,
              rdx: float, rdy: float,
              length: float, pw: float,
              col: tuple) -> None:
    """Draw a filled rectangular pipe arm from center outward."""
    ex, ey = cx + rdx * length, cy + rdy * length
    px, py = -rdy, rdx          # perpendicular unit vector
    h = pw * 0.5
    pts = [(int(cx + px*h), int(cy + py*h)),
           (int(cx - px*h), int(cy - py*h)),
           (int(ex - px*h), int(ey - py*h)),
           (int(ex + px*h), int(ey + py*h))]
    pygame.draw.polygon(surf, col, pts)


# ── Tile ──────────────────────────────────────────────────────────────────────
class Tile:
    def __init__(self, row: int, col: int, kind: str, rotation: int) -> None:
        self.row       = row
        self.col       = col
        self.kind      = kind
        self.base      = TLIB[kind]
        self.rotation  = rotation % 4
        self.vis_angle = float(self.rotation * 90)
        self.tgt_angle = self.vis_angle
        self.connected = False
        self.hover     = False
        self.leaking:  set[int] = set()

    @property
    def sides(self) -> set[int]:
        return {(s + self.rotation) % 4 for s in self.base}

    def rotate_cw(self) -> None:
        self.rotation = (self.rotation + 1) % 4
        self.tgt_angle += 90.0

    def rotate_ccw(self) -> None:
        self.rotation = (self.rotation - 1) % 4
        self.tgt_angle -= 90.0

    def update(self, dt: float) -> None:
        d = self.tgt_angle - self.vis_angle
        self.vis_angle = (self.tgt_angle if abs(d) < 0.3
                          else self.vis_angle + d * min(1., dt * 18.))

    def draw(self, surf: pygame.Surface, rect: pygame.Rect,
             gap: int, glow: float,
             pipe_col: tuple, hint: bool = False) -> None:
        cell = rect.width
        cx, cy = float(rect.centerx), float(rect.centery)

        # ── Cell fill ──────────────────────────────────────────────
        if self.connected:
            fill = CELL_ON
        elif self.hover:
            fill = CELL_HOV
        else:
            fill = CELL_OFF
        pygame.draw.rect(surf, fill, rect, border_radius=8)

        # ── Border ─────────────────────────────────────────────────
        lk = bool(self.leaking)
        if lk:
            pulse = 0.6 + 0.4 * math.sin(glow * 7)
            bc = tuple(int(PIPE_LEAK[i]*pulse + BORDER_OFF[i]*(1-pulse)) for i in range(3))
            bw = 3
        elif hint:
            bc = (255, 150, 28)
            bw = 3
        elif self.hover:
            bc, bw = BORDER_HOV, 2
        elif self.connected:
            t = 0.55 + 0.45 * math.sin(glow * 2)
            bc = tuple(int(pipe_col[i]*t + BORDER_OFF[i]*(1-t)) for i in range(3))
            bw = 1
        else:
            bc, bw = BORDER_OFF, 1
        pygame.draw.rect(surf, bc, rect, width=bw, border_radius=8)

        # ── Pipe geometry ──────────────────────────────────────────
        pw     = max(8, cell // 7)
        # Arms extend to just past tile edge → seamless join with neighbour
        reach  = cell // 2 + max(2, gap // 2)
        col    = pipe_col if self.connected else PIPE_OFF

        # Glow pass (thicker arm, lighter colour)
        if self.connected:
            glow_t = 0.7 + 0.3 * math.sin(glow * 3.5)
            gcol = tuple(min(255, int(c * glow_t + 30)) for c in pipe_col)
            for bs in self.base:
                rdx, rdy = _rot_vec(*{UP:(0.,-1.), RIGHT:(1.,0.),
                                       DOWN:(0.,1.), LEFT:(-1.,0.)}[bs],
                                    self.vis_angle)
                _draw_arm(surf, cx, cy, rdx, rdy, reach, pw + 6, gcol)

        # Main arms
        for bs in self.base:
            bvec = {UP:(0.,-1.), RIGHT:(1.,0.),
                    DOWN:(0.,1.), LEFT:(-1.,0.)}[bs]
            rdx, rdy = _rot_vec(*bvec, self.vis_angle)
            actual   = (bs + round(self.vis_angle / 90)) % 4
            _draw_arm(surf, cx, cy, rdx, rdy, reach, pw, col)
            # Tip cap
            ex, ey = int(cx + rdx*reach), int(cy + rdy*reach)
            is_lk  = actual in self.leaking
            cap    = PIPE_LEAK if is_lk else col
            pygame.draw.circle(surf, cap, (ex, ey), int(pw * 0.55) + (3 if is_lk else 0))

        # ── Central hub ────────────────────────────────────────────
        hr = max(5, int(pw * 0.7))
        if self.connected:
            pygame.draw.circle(surf, gcol, (int(cx), int(cy)), hr + 2)
        pygame.draw.circle(surf, col, (int(cx), int(cy)), hr)


# ── Grid ──────────────────────────────────────────────────────────────────────
class Grid:
    def __init__(self, level: Level) -> None:
        self.level = level
        self.size  = level.size
        self.tiles: list[list[Tile]] = []
        self.connected_count = 0
        self.complete        = False
        self.new_conn        = False
        self._build()
        self.check()

    def _build(self) -> None:
        for r in range(self.size):
            row: list[Tile] = []
            for c in range(self.size):
                row.append(Tile(r, c,
                                self.level.tiles[r][c],
                                self.level.start_rotations[r][c]))
            self.tiles.append(row)

    def iter(self) -> Iterable[Tile]:
        for row in self.tiles:
            yield from row

    def _gap(self, board: pygame.Rect) -> int:
        return max(4, board.width // 90)

    def _cell(self, board: pygame.Rect) -> int:
        return (board.width - self._gap(board) * (self.size - 1)) // self.size

    def tile_rect(self, t: Tile, board: pygame.Rect) -> pygame.Rect:
        g = self._gap(board)
        c = self._cell(board)
        return pygame.Rect(board.x + t.col*(c+g), board.y + t.row*(c+g), c, c)

    def click(self, pos: tuple, board: pygame.Rect, ccw: bool = False) -> Tile | None:
        for t in self.iter():
            if self.tile_rect(t, board).collidepoint(pos):
                t.rotate_ccw() if ccw else t.rotate_cw()
                self.check()
                return t
        return None

    def update(self, dt: float, mouse: tuple, board: pygame.Rect) -> None:
        for t in self.iter():
            t.hover = self.tile_rect(t, board).collidepoint(mouse)
            t.update(dt)

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.size and 0 <= c < self.size

    def check(self) -> None:
        prev = self.connected_count
        for t in self.iter():
            t.connected = False
            t.leaking.clear()

        # BFS from (0,0)
        visited = {(0, 0)}
        queue   = deque([(0, 0)])
        leaks   = False
        while queue:
            r, c = queue.popleft()
            t    = self.tiles[r][c]
            t.connected = True
            for side in t.sides:
                dc, dr = DMAP[side]
                nr, nc = r + dr, c + dc
                if not self.in_bounds(nr, nc):
                    t.leaking.add(side); leaks = True; continue
                nb = self.tiles[nr][nc]
                if OPP[side] not in nb.sides:
                    t.leaking.add(side); leaks = True; continue
                if (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc))

        self.connected_count = len(visited)
        self.complete = (self.connected_count == self.size * self.size) and not leaks
        self.new_conn = self.connected_count > prev

    @property
    def progress(self) -> float:
        return self.connected_count / max(1, self.size * self.size)

    def reveal_solution(self) -> None:
        sol = self.level.solution_rotations
        for t in self.iter():
            target = sol[t.row][t.col]
            diff   = (target - t.rotation) % 4
            t.rotation  = target
            t.tgt_angle += diff * 90.0
        self.check()

    def draw(self, surf: pygame.Surface, board: pygame.Rect,
             glow: float, pipe_col: tuple,
             hint: bool = False) -> None:
        gap  = self._gap(board)
        well = board.inflate(gap*2+4, gap*2+4)
        pygame.draw.rect(surf, BOARD_BG, well, border_radius=14)
        pygame.draw.rect(surf, BORDER_OFF, well, width=2, border_radius=14)

        sol = self.level.solution_rotations
        for t in self.iter():
            show_hint = hint and t.rotation != sol[t.row][t.col]
            t.draw(surf, self.tile_rect(t, board), gap, glow, pipe_col, show_hint)


# ── Game ──────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self) -> None:
        self.screen = pygame.display.set_mode((SW, SH), pygame.RESIZABLE)
        pygame.display.set_caption("Pipe Puzzle — Echo Garden")
        self.clock  = pygame.time.Clock()
        self.running = True
        self.fs     = False
        self.state  = "title"
        self._init_fonts()
        self.levels = build_levels()
        self.li     = 0
        self.grid   = Grid(self.levels[self.li])
        self.audio  = Audio(Path(__file__).parent / "assets" / "sounds")
        self.parts: list[Particle] = []
        self.glow   = 0.0
        self.moves  = 0
        self.won    = False
        self.sol_shown = False
        self.hint   = False
        self.done:  set[int] = set()
        self._next_btn: pygame.Rect | None = None
        self._pending_conn = False   # defer connect sound until anim settles

    def _init_fonts(self) -> None:
        try:
            self.ft = pygame.font.SysFont("Segoe UI", 64, bold=True)
            self.fb = pygame.font.SysFont("Segoe UI", 40, bold=True)
            self.fm = pygame.font.SysFont("Segoe UI", 26)
            self.fs_ = pygame.font.SysFont("Segoe UI", 20)
            self.fx = pygame.font.SysFont("Segoe UI", 15)
        except Exception:
            self.ft = pygame.font.Font(None, 72)
            self.fb = pygame.font.Font(None, 50)
            self.fm = pygame.font.Font(None, 32)
            self.fs_ = pygame.font.Font(None, 26)
            self.fx = pygame.font.Font(None, 20)

    # ── Layout ───────────────────────────────────────────────────────────────
    def board_rect(self) -> pygame.Rect:
        w, h = self.screen.get_size()
        pad  = 110           # top/bottom padding for header+footer
        side = min(w - 240, h - pad * 2)
        return pygame.Rect((w - side) // 2, pad, side, side)

    def _pipe_col(self) -> tuple:
        return LEVEL_COLS[self.li % len(LEVEL_COLS)]

    # ── Main loop ────────────────────────────────────────────────────────────
    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self._events()
            self._update(dt)
            self._draw()

    # ── Events ───────────────────────────────────────────────────────────────
    def _events(self) -> None:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False

            elif e.type == pygame.KEYDOWN:
                k = e.key
                if k == pygame.K_ESCAPE:
                    if self.state in ("playing", "levels"):
                        self.state = "title"
                    else:
                        self.running = False
                elif k == pygame.K_f:
                    self.fs = not self.fs
                    self.screen = pygame.display.set_mode(
                        (SW, SH), pygame.FULLSCREEN if self.fs else pygame.RESIZABLE)
                elif k == pygame.K_r and self.state == "playing":
                    self._reset()
                elif k == pygame.K_h and self.state == "playing":
                    self.hint = not self.hint
                elif k == pygame.K_s and self.state == "playing":
                    self._show_sol()
                elif k in (pygame.K_n, pygame.K_RETURN) and self.won:
                    self._next()

            elif e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    self._lclick(e.pos)
                elif e.button == 3:
                    self._rclick(e.pos)

    def _lclick(self, pos: tuple) -> None:
        if self.state == "title":
            self._title_click(pos)
        elif self.state == "levels":
            self._lvl_click(pos)
        elif self.state == "playing":
            if self._next_btn and self._next_btn.collidepoint(pos) and self.won:
                self._next(); return
            for act, rect in self._footer_btns().items():
                if rect.collidepoint(pos):
                    {"reset": self._reset,
                     "hint":  lambda: setattr(self, "hint", not self.hint),
                     "solve": self._show_sol,
                     "menu":  lambda: setattr(self, "state", "levels")}[act]()
                    return
            if not self.won:
                t = self.grid.click(pos, self.board_rect())
                if t:
                    self.moves += 1
                    self.audio.play("rotate", 0.38)

    def _rclick(self, pos: tuple) -> None:
        if self.state == "playing" and not self.won:
            t = self.grid.click(pos, self.board_rect(), ccw=True)
            if t:
                self.moves += 1
                self.audio.play("rotate", 0.38)

    def _title_click(self, pos: tuple) -> None:
        for act, r in self._title_btns().items():
            if r.collidepoint(pos):
                {"play":   lambda: self._go_play(),
                 "levels": lambda: setattr(self, "state", "levels"),
                 "quit":   lambda: setattr(self, "running", False)}[act]()
                break

    def _lvl_click(self, pos: tuple) -> None:
        if self._back_rect().collidepoint(pos):
            self.state = "title"; return
        for i, r in enumerate(self._card_rects()):
            if r.collidepoint(pos):
                self.li = i; self._reset(); self.state = "playing"; return

    # ── State helpers ─────────────────────────────────────────────────────────
    def _go_play(self) -> None:
        self.state = "playing"

    def _reset(self) -> None:
        self.grid      = Grid(self.levels[self.li])
        self.won       = False
        self.sol_shown = False
        self.moves     = 0
        self.hint      = False
        self.parts.clear()
        self._next_btn = None

    def _next(self) -> None:
        self.done.add(self.li)
        self.li = (self.li + 1) % len(self.levels)
        self._reset()

    def _show_sol(self) -> None:
        self.sol_shown = True
        self.grid.reveal_solution()

    # ── Update ───────────────────────────────────────────────────────────────
    def _update(self, dt: float) -> None:
        self.glow  += dt
        self.parts  = [p for p in self.parts if p.update(dt)]
        if self.state != "playing":
            return
        self.grid.update(dt, pygame.mouse.get_pos(), self.board_rect())
        # Defer the connect chime until tile rotation animation is settled
        if self.grid.new_conn:
            self._pending_conn = True
            self.grid.new_conn = False
        if self._pending_conn and self._anim_settled():
            self.audio.play("connect", 0.45)
            self._pending_conn = False
        if self.grid.complete and not self.won:
            self.won = True
            self._pending_conn = False
            if not self.sol_shown:
                self.done.add(self.li)
                self.audio.play("win", 0.60)
                self._bloom()

    def _anim_settled(self) -> bool:
        """True when every tile has finished its rotation animation."""
        return all(abs(t.tgt_angle - t.vis_angle) < 0.8 for t in self.grid.iter())

    def _bloom(self) -> None:
        b   = self.board_rect()
        col = self._pipe_col()
        extras = [SUCCESS_COL, (255,255,255), (255, 220, 80)]
        for _ in range(120):
            c = choice([col, *extras])
            self.parts.append(
                Particle(Vec2(uniform(b.left, b.right), uniform(b.top, b.bottom)), c))

    # ── Draw ─────────────────────────────────────────────────────────────────
    def _draw(self) -> None:
        self.screen.fill(BG)
        self._dots()
        if self.state == "title":
            self._draw_title()
        elif self.state == "levels":
            self._draw_lvlsel()
        else:
            self._draw_game()
        for p in self.parts:
            p.draw(self.screen)
        pygame.display.flip()

    def _dots(self) -> None:
        w, h = self.screen.get_size()
        for x in range(0, w+44, 44):
            for y in range(0, h+44, 44):
                pygame.draw.circle(self.screen, (20, 30, 54), (x, y), 1)

    def _lbl(self, text: str, font: pygame.font.Font,
              col: tuple, cx: int, cy: int) -> None:
        s = font.render(text, True, col)
        self.screen.blit(s, s.get_rect(center=(cx, cy)))

    def _btn(self, rect: pygame.Rect, label: str, primary: bool = False) -> None:
        hov = rect.collidepoint(pygame.mouse.get_pos())
        col = self._pipe_col()
        if primary:
            bg = tuple(int(c * (0.5 + 0.15*hov)) for c in col)
            bc = col
            tc = (255, 255, 255)
        else:
            bg = (28, 44, 76) if hov else PANEL
            bc = BORDER_HOV if hov else BORDER_OFF
            tc = TEXT
        pygame.draw.rect(self.screen, bg,  rect, border_radius=10)
        pygame.draw.rect(self.screen, bc,  rect, width=2, border_radius=10)
        s = self.fs_.render(label, True, tc)
        self.screen.blit(s, s.get_rect(center=rect.center))

    # ── Title screen ──────────────────────────────────────────────────────────
    def _title_btns(self) -> dict[str, pygame.Rect]:
        w, h = self.screen.get_size()
        bw, bh, cx = min(280, w-80), 54, w // 2
        sy = h // 2 + 28
        return {"play":   pygame.Rect(cx-bw//2, sy,      bw, bh),
                "levels": pygame.Rect(cx-bw//2, sy+72,   bw, bh),
                "quit":   pygame.Rect(cx-bw//2, sy+144,  bw, bh)}

    def _draw_title(self) -> None:
        w, h = self.screen.get_size()
        cx   = w // 2
        col  = self._pipe_col()
        for r, c, lw in [(72,col,2),(50,(255,195,48),2),(28,(165,92,255),3)]:
            p = 0.82 + 0.18 * math.sin(self.glow * 2 + r * 0.04)
            pygame.draw.circle(self.screen, tuple(min(255,int(ch*p)) for ch in c),
                               (cx, h//2 - 190), r, lw)
        self._lbl("Pipe Puzzle",    self.ft,  TEXT, cx, h//2 - 110)
        self._lbl("Echo Garden",    self.fb,  col,  cx, h//2 - 56)
        self._lbl("Rotate tiles so every pipe connects — no open ends allowed",
                   self.fs_, TEXTD, cx, h//2 - 12)
        for lbl, rect in [
            ("▶  Play",         self._title_btns()["play"]),
            ("⊞  All Levels",   self._title_btns()["levels"]),
            ("✕  Quit",         self._title_btns()["quit"]),
        ]:
            self._btn(rect, lbl, primary=lbl.startswith("▶"))
        self._lbl("Left-click: rotate CW   Right-click: rotate CCW   R: reset   S: solution   H: hint",
                   self.fx, TEXTD, cx, h - 24)

    # ── Level select ──────────────────────────────────────────────────────────
    def _back_rect(self) -> pygame.Rect:
        w, _ = self.screen.get_size()
        return pygame.Rect(w//2 - 80, 96, 160, 40)

    def _card_rects(self) -> list[pygame.Rect]:
        w, h = self.screen.get_size()
        cols, gutter = 3, 20
        cw = min(300, (w - 100 - gutter*(cols-1)) // cols)
        ch = 104
        sx = w//2 - (cols*cw + (cols-1)*gutter)//2
        return [pygame.Rect(sx + (i%cols)*(cw+gutter),
                            156 + (i//cols)*(ch+gutter), cw, ch)
                for i in range(len(self.levels))]

    def _draw_lvlsel(self) -> None:
        w, _ = self.screen.get_size()
        self._lbl("Choose a Level", self.fb, TEXT, w//2, 60)
        self._btn(self._back_rect(), "← Back")
        mouse = pygame.mouse.get_pos()
        for i, rect in enumerate(self._card_rects()):
            done = i in self.done
            hov  = rect.collidepoint(mouse)
            col  = LEVEL_COLS[i % len(LEVEL_COLS)]
            bg   = (24, 38, 64) if hov else PANEL
            bc   = col if done else (BORDER_HOV if hov else BORDER_OFF)
            pygame.draw.rect(self.screen, bg, rect, border_radius=12)
            pygame.draw.rect(self.screen, bc, rect, width=2, border_radius=12)
            # Colour swatch
            pygame.draw.circle(self.screen, col, (rect.x + 24, rect.centery), 10)
            nm = self.fm.render(self.levels[i].name, True, TEXT)
            self.screen.blit(nm, (rect.x + 44, rect.y + 18))
            sz = self.fx.render(f"{self.levels[i].size}×{self.levels[i].size} grid", True, TEXTD)
            self.screen.blit(sz, (rect.x + 44, rect.y + 52))
            if done:
                ok = self.fx.render("✓ solved", True, col)
                self.screen.blit(ok, (rect.x + 44, rect.y + 72))

    # ── Gameplay ──────────────────────────────────────────────────────────────
    def _footer_btns(self) -> dict[str, pygame.Rect]:
        w, h = self.screen.get_size()
        labels = ["reset", "hint", "solve", "menu"]
        bw, bh = 128, 42
        total  = len(labels) * bw + (len(labels)-1) * 14
        sx     = (w - total) // 2
        fy     = h - 62
        return {k: pygame.Rect(sx + i*(bw+14), fy, bw, bh)
                for i, k in enumerate(labels)}

    def _draw_game(self) -> None:
        w, h   = self.screen.get_size()
        board  = self.board_rect()
        col    = self._pipe_col()
        level  = self.levels[self.li]

        # ── Header bar ────────────────────────────────────────────────────────
        pygame.draw.rect(self.screen, PANEL, (0, 0, w, 64))
        pygame.draw.line(self.screen, BORDER_OFF, (0, 64), (w, 64))

        # Level progress dots
        dot_x = 32
        for i in range(len(self.levels)):
            c  = LEVEL_COLS[i % len(LEVEL_COLS)]
            fc = c if i in self.done else (BORDER_OFF if i != self.li else col)
            pygame.draw.circle(self.screen, fc, (dot_x + i*28, 32), 9)
            if i == self.li:
                pygame.draw.circle(self.screen, col, (dot_x + i*28, 32), 12, 2)

        self._lbl(level.name, self.fb, col, w//2, 32)

        # Progress fraction + connections
        frac = self.grid.progress
        bar  = pygame.Rect(w - 220, 22, 190, 12)
        pygame.draw.rect(self.screen, BOARD_BG, bar, border_radius=6)
        filled           = bar.copy()
        filled.width     = int(bar.width * frac)
        if filled.width > 0:
            pygame.draw.rect(self.screen, col, filled, border_radius=6)
        pygame.draw.rect(self.screen, BORDER_OFF, bar, width=1, border_radius=6)
        pct = self.fs_.render(f"{int(frac*100)}%  {self.grid.connected_count}/{self.grid.size**2} tiles",
                               True, TEXTD)
        self.screen.blit(pct, (bar.x, bar.y + 18))

        moves_s = self.fs_.render(f"Moves: {self.moves}", True, TEXTD)
        self.screen.blit(moves_s, (w - 100, 44))

        # ── Footer bar ────────────────────────────────────────────────────────
        pygame.draw.rect(self.screen, PANEL, (0, h-72, w, 72))
        pygame.draw.line(self.screen, BORDER_OFF, (0, h-72), (w, h-72))
        labels = {"reset": "↺ Reset", "hint": ("✦ Hint ON" if self.hint else "◇ Hint"),
                  "solve": "⚑ Solve", "menu": "⊞ Levels"}
        for act, rect in self._footer_btns().items():
            self._btn(rect, labels[act],
                      primary=(act == "solve" and not self.sol_shown))

        # ── Board ─────────────────────────────────────────────────────────────
        self.grid.draw(self.screen, board, self.glow, col, self.hint)

        # ── Win / solution banner ──────────────────────────────────────────────
        if self.won or (self.sol_shown and self.grid.complete):
            self._draw_banner(board, col)

    def _draw_banner(self, board: pygame.Rect, col: tuple) -> None:
        w, h = self.screen.get_size()
        bw, bh = 400, 112
        bx = board.centerx - bw//2
        by = board.bottom + 14
        if by + bh > h - 76:
            by = board.top - bh - 14

        banner = pygame.Rect(bx, by, bw, bh)
        p = math.sin(self.glow * 4) * 0.5 + 0.5

        if self.sol_shown and not (self.won and not self.sol_shown):
            title  = "Solution revealed"
            subtitle = "Press  R  to try again  or  N  for next"
            hcol   = (165, 92, 255)
            bcol   = tuple(int(hcol[i]*p + BORDER_OFF[i]*(1-p)) for i in range(3))
        else:
            title  = "✓  All pipes connected!"
            subtitle = f"Solved in {self.moves} move{'s' if self.moves!=1 else ''} — press N or click below"
            hcol   = SUCCESS_COL
            bcol   = tuple(int(col[i]*p + BORDER_OFF[i]*(1-p)) for i in range(3))

        pygame.draw.rect(self.screen, (10, 18, 36), banner, border_radius=16)
        pygame.draw.rect(self.screen, bcol, banner, width=2, border_radius=16)
        self._lbl(title,    self.fb,  hcol, banner.centerx, banner.y + 28)
        self._lbl(subtitle, self.fx,  TEXTD, banner.centerx, banner.y + 62)

        nr = pygame.Rect(banner.centerx - 110, banner.y + 78, 220, 36)
        self._btn(nr, "Next Level  →", primary=True)
        self._next_btn = nr


# ── Level definitions ─────────────────────────────────────────────────────────
def build_levels() -> list[Level]:
    """
    Five levels, each with a structurally distinct Hamiltonian path.
    Win condition: every tile lit (all connected, zero open ends).

    Encoding: rotation = clockwise quarter-turns from canonical UP orientation.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # Level 1  3×3  "C-Turn"
    # Path: (0,0)→R(0,1)→R(0,2)→D(1,2)→D(2,2)→L(2,1)→L(2,0)→U(1,0)→R(1,1)
    # Shape: outer-right C with the one inner cell at end.
    # ─────────────────────────────────────────────────────────────────────────
    L1_tiles = (
        ("end",    "straight", "corner"),
        ("corner", "end",      "straight"),
        ("corner", "straight", "corner"),
    )
    L1_sol   = ((1, 1, 2), (1, 3, 0), (0, 1, 3))
    L1_start = ((3, 2, 0), (0, 1, 2), (1, 3, 1))

    # ─────────────────────────────────────────────────────────────────────────
    # Level 2  4×4  "Inward Spiral"
    # Path spirals CW from top-left inward:
    #   (0,0)→(0,1)→(0,2)→(0,3)→(1,3)→(2,3)→(3,3)→(3,2)→(3,1)→(3,0)→
    #   (2,0)→(1,0)→(1,1)→(1,2)→(2,2)→(2,1)
    # ─────────────────────────────────────────────────────────────────────────
    L2_tiles = (
        ("end",      "straight", "straight", "corner"),
        ("corner",   "straight", "corner",   "straight"),
        ("straight", "end",      "corner",   "straight"),
        ("corner",   "straight", "straight", "corner"),
    )
    L2_sol   = ((1, 1, 1, 2), (1, 1, 2, 0), (0, 1, 3, 0), (0, 1, 1, 3))
    L2_start = ((3, 2, 0, 0), (2, 0, 0, 1), (3, 3, 0, 2), (1, 3, 0, 0))

    # ─────────────────────────────────────────────────────────────────────────
    # Level 3  5×5  "Column Serpentine"
    # Path snakes column-by-column (↓ col 0, → turn, ↑ col 1, → turn, …)
    # Completely different visual than row-serpentine.
    #   (0,0)↓…↓(4,0)→(4,1)↑…↑(0,1)→(0,2)↓…↓(4,2)→(4,3)↑…↑(0,3)→(0,4)↓…↓(4,4)
    # ─────────────────────────────────────────────────────────────────────────
    L3_tiles = (
        ("end",      "corner",   "corner",   "corner",   "corner"),
        ("straight", "straight", "straight", "straight", "straight"),
        ("straight", "straight", "straight", "straight", "straight"),
        ("straight", "straight", "straight", "straight", "straight"),
        ("corner",   "corner",   "corner",   "corner",   "end"),
    )
    L3_sol   = (
        (2, 1, 2, 1, 2),
        (0, 0, 0, 0, 0),
        (0, 0, 0, 0, 0),
        (0, 0, 0, 0, 0),
        (0, 3, 0, 3, 0),
    )
    L3_start = (
        (3, 3, 1, 3, 3),
        (2, 1, 3, 2, 1),
        (3, 2, 1, 3, 2),
        (1, 3, 2, 1, 3),
        (2, 0, 2, 0, 2),
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Level 4  5×5  "Outward Spiral"
    # Path: outer ring CW → second ring CW → ends at centre (2,2).
    #   (0,0)→(0,1)→(0,2)→(0,3)→(0,4)→(1,4)→(2,4)→(3,4)→(4,4)→(4,3)→(4,2)→
    #   (4,1)→(4,0)→(3,0)→(2,0)→(1,0)→(1,1)→(1,2)→(1,3)→(2,3)→(3,3)→
    #   (3,2)→(3,1)→(2,1)→(2,2)
    # ─────────────────────────────────────────────────────────────────────────
    L4_tiles = (
        ("end",      "straight", "straight", "straight", "corner"),
        ("corner",   "straight", "straight", "corner",   "straight"),
        ("straight", "corner",   "end",      "straight", "straight"),
        ("straight", "corner",   "straight", "corner",   "straight"),
        ("corner",   "straight", "straight", "straight", "corner"),
    )
    L4_sol   = (
        (1, 1, 1, 1, 2),
        (1, 1, 1, 2, 0),
        (0, 1, 3, 0, 0),
        (0, 0, 1, 3, 0),
        (0, 1, 1, 1, 3),
    )
    L4_start = (
        (3, 0, 3, 0, 0),
        (0, 0, 3, 0, 2),
        (2, 3, 2, 2, 2),
        (3, 2, 0, 2, 2),
        (2, 0, 0, 3, 2),
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Level 5  5×5  "Winding Zigzag"
    # Path weaves column-by-column in pairs, then sweeps the bottom row.
    #   (0,0)↓(1,0)↓(2,0)→(2,1)↑(1,1)↑(0,1)→(0,2)↓(1,2)↓(2,2)→(2,3)↑(1,3)↑(0,3)→
    #   (0,4)↓(1,4)↓(2,4)↓(3,4)↓(4,4)←(4,3)←(4,2)←(4,1)←(4,0)↑(3,0)→(3,1)→(3,2)→(3,3)
    # ─────────────────────────────────────────────────────────────────────────
    L5_tiles = (
        ("end",      "corner",   "corner",   "corner",   "corner"),
        ("straight", "straight", "straight", "straight", "straight"),
        ("corner",   "corner",   "corner",   "corner",   "straight"),
        ("corner",   "straight", "straight", "end",      "straight"),
        ("corner",   "straight", "straight", "straight", "corner"),
    )
    L5_sol   = (
        (2, 1, 2, 1, 2),
        (0, 0, 0, 0, 0),
        (0, 3, 0, 3, 0),
        (1, 1, 1, 3, 0),
        (0, 1, 1, 1, 3),
    )
    L5_start = (
        (3, 0, 0, 2, 1),
        (2, 1, 3, 2, 1),
        (3, 1, 1, 2, 2),
        (3, 0, 3, 0, 3),
        (1, 3, 2, 0, 1),
    )

    return [
        Level("C-Turn",         3, L1_tiles, L1_start, L1_sol, theme=0),
        Level("Inward Spiral",  4, L2_tiles, L2_start, L2_sol, theme=1),
        Level("Column Snake",   5, L3_tiles, L3_start, L3_sol, theme=2),
        Level("Outward Spiral", 5, L4_tiles, L4_start, L4_sol, theme=3),
        Level("Winding Zigzag", 5, L5_tiles, L5_start, L5_sol, theme=4),
    ]
