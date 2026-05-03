"""Validate Echo Garden level data without importing Pygame.

This script parses `build_levels()` directly from `game.py`, so it can run even
before Pygame is installed. It checks that levels are not initially solved and
that each declared solution obeys the same multi-flow rules as the game:

- standard tiles mix incoming colors
- `bridge` tiles let routes cross without mixing
- outputs only count when their final color exactly matches the target

Run:
    python validate_levels.py
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass
from pathlib import Path

UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DIRS = {UP: (0, -1), RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0)}
OPPOSITE = {UP: DOWN, RIGHT: LEFT, DOWN: UP, LEFT: RIGHT}
TILE_CHANNEL_LIBRARY: dict[str, tuple[tuple[int, ...], ...]] = {
    "end": ((UP,),),
    "straight": ((UP, DOWN),),
    "corner": ((UP, RIGHT),),
    "tee": ((UP, RIGHT, DOWN),),
    "cross": ((UP, RIGHT, DOWN, LEFT),),
    "bridge": ((UP, DOWN), (LEFT, RIGHT)),
}


@dataclass(frozen=True)
class ParsedLevel:
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


def rotate_channels(channels: tuple[tuple[int, ...], ...], rotation: int) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple((side + rotation) % 4 for side in channel) for channel in channels)


def channels_for(kind: str, rotation: int) -> tuple[tuple[int, ...], ...]:
    return rotate_channels(TILE_CHANNEL_LIBRARY[kind], rotation)


def load_levels(path: Path) -> list[ParsedLevel]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    build = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "build_levels"
    )
    return_node = next(node for node in ast.walk(build) if isinstance(node, ast.Return))
    if not isinstance(return_node.value, ast.List):
        raise ValueError("build_levels() must return a list literal for validation.")

    levels: list[ParsedLevel] = []
    for item in return_node.value.elts:
        if not isinstance(item, ast.Call):
            continue
        kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in item.keywords if kw.arg}
        levels.append(ParsedLevel(**kwargs))
    return levels


def set_rotation(rotations: tuple[tuple[int, ...], ...], row: int, col: int, value: int) -> tuple[tuple[int, ...], ...]:
    mutable = [list(line) for line in rotations]
    mutable[row][col] = value
    return tuple(tuple(line) for line in mutable)


def candidate_cells(level: ParsedLevel) -> list[tuple[int, int]]:
    """Return cells worth rotating first, sorted by distance from sources/outputs."""

    anchors = list(level.starts) + list(level.sinks)
    cells = [(row, col) for row in range(level.size) for col in range(level.size)]
    return sorted(cells, key=lambda cell: min(abs(cell[0] - a[0]) + abs(cell[1] - a[1]) for a in anchors))


def check_state(
    level: ParsedLevel,
    rotations: tuple[tuple[int, ...], ...],
) -> tuple[bool, int, int, set[tuple[int, int]]]:
    default_source = level.start_colors[0] if level.start_colors else "gold"
    source_colors = level.start_colors or tuple(default_source for _ in level.starts)
    sink_targets = level.sink_targets or tuple((default_source,) for _ in level.sinks)

    channel_lookup: dict[tuple[int, int, int], tuple[int, ...]] = {}
    port_lookup: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    adjacency: dict[tuple[int, int, int], set[tuple[int, int, int]]] = {}

    for row in range(level.size):
        for col in range(level.size):
            for index, channel in enumerate(channels_for(level.tiles[row][col], rotations[row][col])):
                node = (row, col, index)
                channel_lookup[node] = channel
                adjacency[node] = set()
                for side in channel:
                    port_lookup[(row, col, side)] = node

    for node, channel in channel_lookup.items():
        row, col, _ = node
        for side in channel:
            dc, dr = DIRS[side]
            nr, nc = row + dr, col + dc
            if not (0 <= nr < level.size and 0 <= nc < level.size):
                continue
            neighbor = port_lookup.get((nr, nc, OPPOSITE[side]))
            if neighbor is not None:
                adjacency[node].add(neighbor)

    flow_sets: dict[tuple[int, int, int], set[str]] = {node: set() for node in channel_lookup}
    queue: deque[tuple[int, int, int]] = deque()
    for (row, col), color in zip(level.starts, source_colors):
        for index, _ in enumerate(channels_for(level.tiles[row][col], rotations[row][col])):
            node = (row, col, index)
            flow_sets[node].add(color)
            queue.append(node)

    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            previous_size = len(flow_sets[neighbor])
            flow_sets[neighbor].update(flow_sets[node])
            if len(flow_sets[neighbor]) != previous_size:
                queue.append(neighbor)

    visited = {(row, col) for (row, col, _), colors in flow_sets.items() if colors}
    leaks = 0
    for node, channel in channel_lookup.items():
        if not flow_sets[node]:
            continue
        row, col, _ = node
        for side in channel:
            dc, dr = DIRS[side]
            nr, nc = row + dr, col + dc
            neighbor = port_lookup.get((nr, nc, OPPOSITE[side])) if 0 <= nr < level.size and 0 <= nc < level.size else None
            if neighbor is None:
                leaks += 1

    satisfied = 0
    for (row, col), target in zip(level.sinks, sink_targets):
        colors: set[str] = set()
        for index, _ in enumerate(channels_for(level.tiles[row][col], rotations[row][col])):
            colors.update(flow_sets[(row, col, index)])
        if colors and frozenset(colors) == frozenset(target):
            satisfied += 1

    complete = satisfied == len(level.sinks) and leaks == 0
    return complete, len(visited), leaks, visited


def find_solution(level: ParsedLevel, max_states: int = 350_000) -> tuple[bool, int, tuple[tuple[int, ...], ...] | None]:
    """Search rotations when a level does not declare its own known solution."""

    cells = candidate_cells(level)
    base = level.rotations
    checked = 0

    def recurse(index: int, current: tuple[tuple[int, ...], ...]) -> tuple[bool, tuple[tuple[int, ...], ...] | None]:
        nonlocal checked
        if checked >= max_states:
            return False, None
        complete, connected, leaks, _ = check_state(level, current)
        checked += 1
        if complete:
            return True, current

        if index >= len(cells):
            return False, None

        if leaks > 5 and connected > 1:
            return False, None

        row, col = cells[index]
        starting = current[row][col]
        for offset in range(4):
            rotation = (starting + offset) % 4
            candidate = set_rotation(current, row, col, rotation)
            solved, solution = recurse(index + 1, candidate)
            if solved:
                return True, solution
        return False, None

    solved, solution = recurse(0, base)
    return solved, checked, solution


def print_solution(level: ParsedLevel, solution: tuple[tuple[int, ...], ...] | None) -> None:
    if solution is None:
        return
    print("  solution rotations:")
    for row in solution:
        print("   ", " ".join(str(value) for value in row))


def main() -> int:
    levels = load_levels(Path(__file__).with_name("game.py"))
    failures = 0
    for index, level in enumerate(levels, start=1):
        print(f"Level {index}: {level.name} ({level.size}x{level.size}, {level.art_style})")
        if level.start_colors and len(level.start_colors) != len(level.starts):
            print("  WARNING: start_colors length does not match starts")
            failures += 1
        if level.sink_targets and len(level.sink_targets) != len(level.sinks):
            print("  WARNING: sink_targets length does not match sinks")
            failures += 1
        initially_complete, connected, leaks, _ = check_state(level, level.rotations)
        print(f"  initial: complete={initially_complete}, connected={connected}, leaks={leaks}")
        if initially_complete:
            print("  WARNING: level starts already solved")
            failures += 1

        if level.solution_rotations is not None:
            known_complete, known_connected, known_leaks, _ = check_state(level, level.solution_rotations)
            print(f"  known solution: complete={known_complete}, connected={known_connected}, leaks={known_leaks}")
            if not known_complete:
                print("  WARNING: declared solution_rotations are not a valid solution")
                failures += 1
        else:
            solved, checked, solution = find_solution(level)
            print(f"  search: solved={solved}, states_checked={checked}")
            if solved:
                print_solution(level, solution)
            else:
                print("  WARNING: no solution found within the bounded search")
                failures += 1
        print()

    if failures:
        print(f"Validation completed with {failures} warning(s).")
        return 1
    print("Validation passed: all levels have a verified known solution and none start solved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
