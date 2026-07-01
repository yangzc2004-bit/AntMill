from __future__ import annotations

import random
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any


DIRS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
DIR_ALIASES = {
    "north": "up",
    "south": "down",
    "west": "left",
    "east": "right",
    "u": "up",
    "d": "down",
    "l": "left",
    "r": "right",
}


@dataclass(frozen=True)
class MazeTask:
    task_id: str
    family: str
    width: int
    height: int
    grid: tuple[str, ...]
    start: tuple[int, int]
    goal: tuple[int, int]
    shortest_path: tuple[tuple[int, int], ...]

    def public(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "family": self.family,
            "width": self.width,
            "height": self.height,
            "grid": list(self.grid),
            "start": list(self.start),
            "goal": list(self.goal),
            "shortest_path_length": self.shortest_path_length,
        }

    @property
    def shortest_path_length(self) -> int:
        return max(len(self.shortest_path) - 1, 1)


class MazeEnv:
    """Seeded text maze with local observations and measurable path quality."""

    def __init__(self) -> None:
        self.task_id = ""
        self.task: MazeTask | None = None
        self.pos = (0, 0)
        self.visited: Counter[tuple[int, int]] = Counter()
        self.path: list[tuple[int, int]] = []
        self.actions: list[str] = []
        self.invalid_moves = 0
        self.done = False

    def reset(self, task: dict[str, Any] | MazeTask) -> str:
        maze = task if isinstance(task, MazeTask) else task["maze"]
        if not isinstance(maze, MazeTask):
            raise TypeError("MazeEnv.reset expects a MazeTask or {'maze': MazeTask}.")
        self.task = maze
        self.task_id = maze.task_id
        self.pos = maze.start
        self.visited = Counter([self.pos])
        self.path = [self.pos]
        self.actions = []
        self.invalid_moves = 0
        self.done = False
        return self._obs("Start.")

    def tools_doc(self) -> str:
        return (
            "Use exactly one action per turn: move:up, move:down, move:left, move:right, inspect, submit. "
            "Move actions change position when the direction is open. inspect returns the same local view. "
            "submit only succeeds when you are at the goal."
        )

    def step(self, action: str) -> tuple[str, bool, dict[str, Any]]:
        if self.task is None:
            raise RuntimeError("MazeEnv.step called before reset.")
        clean = _normalize_maze_action(action)
        info: dict[str, Any] = {"normalized_action": clean, "invalid": False, "submitted": False}
        if self.done:
            return self._obs("Already terminal."), True, info
        if clean == "inspect":
            self.actions.append(clean)
            return self._obs("Inspected."), False, info
        if clean == "submit":
            self.actions.append(clean)
            info["submitted"] = True
            self.done = True
            if self.pos == self.task.goal:
                return self._obs("Submitted at the goal. Success."), True, info
            info["invalid"] = True
            self.invalid_moves += 1
            return self._obs("Submitted before reaching the goal. Failure."), True, info
        if clean.startswith("move:"):
            direction = clean.split(":", 1)[1]
            dx, dy = DIRS[direction]
            nx, ny = self.pos[0] + dx, self.pos[1] + dy
            self.actions.append(clean)
            if _is_open(self.task.grid, nx, ny):
                self.pos = (nx, ny)
                self.path.append(self.pos)
                self.visited[self.pos] += 1
                return self._obs(f"Moved {direction}."), False, info
            self.invalid_moves += 1
            info["invalid"] = True
            return self._obs(f"Blocked moving {direction}."), False, info
        self.actions.append(clean or action.strip())
        self.invalid_moves += 1
        info["invalid"] = True
        return self._obs(f"Unknown action {action!r}."), False, info

    def is_success(self) -> bool:
        return bool(self.done and self.task is not None and self.pos == self.task.goal)

    def route_record(self) -> dict[str, Any]:
        if self.task is None:
            return {}
        shortest = self.task.shortest_path_length
        return {
            "task_id": self.task_id,
            "success": self.is_success(),
            "submitted": self.done,
            "steps": len(self.actions),
            "shortest_path_length": shortest,
            "cost_ratio": len(self.actions) / max(shortest, 1),
            "excess_steps": len(self.actions) - shortest,
            "invalid_moves": self.invalid_moves,
            "invalid_move_rate": self.invalid_moves / max(len(self.actions), 1),
            "revisit_max": max(self.visited.values()) if self.visited else 0,
            "looped": detect_position_loop(self.path, goal=self.task.goal),
            "path": [list(p) for p in self.path],
            "actions": list(self.actions),
            "final_position": list(self.pos),
        }

    def _obs(self, event: str) -> str:
        if self.task is None:
            return event
        x, y = self.pos
        gx, gy = self.task.goal
        open_dirs = [name for name, (dx, dy) in DIRS.items() if _is_open(self.task.grid, x + dx, y + dy)]
        wall_dist = {name: _distance_to_wall(self.task.grid, x, y, dx, dy) for name, (dx, dy) in DIRS.items()}
        recent = " -> ".join(f"({px},{py})" for px, py in self.path[-6:])
        return (
            f"{event}\n"
            f"Task: reach the goal, then submit.\n"
            f"Position: ({x},{y}). Goal: ({gx},{gy}). Manhattan distance: {abs(gx - x) + abs(gy - y)}.\n"
            f"Open directions: {', '.join(open_dirs) if open_dirs else 'none'}.\n"
            f"Distance to wall: up={wall_dist['up']}, down={wall_dist['down']}, "
            f"left={wall_dist['left']}, right={wall_dist['right']}.\n"
            f"Visits to this cell: {self.visited[self.pos]}. Recent path: {recent}.\n"
            f"Invalid moves so far: {self.invalid_moves}."
        )


def _is_open(grid: tuple[str, ...] | list[str], x: int, y: int) -> bool:
    return 0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] != "#"


def _distance_to_wall(grid: tuple[str, ...], x: int, y: int, dx: int, dy: int) -> int:
    dist = 0
    nx, ny = x + dx, y + dy
    while _is_open(grid, nx, ny):
        dist += 1
        nx += dx
        ny += dy
    return dist


def _normalize_maze_action(action: str) -> str:
    raw = str(action).strip().lower()
    if raw.startswith("action:"):
        raw = raw.split(":", 1)[1].strip()
    raw = raw.replace(" ", "").strip("`'\".,;")
    if raw in {"inspect", "look", "read"}:
        return "inspect"
    if raw in {"submit", "finish", "done"}:
        return "submit"
    if raw.startswith("move:"):
        direction = raw.split(":", 1)[1]
    elif raw.startswith("move"):
        direction = raw[4:].lstrip(":")
    else:
        direction = raw
    direction = DIR_ALIASES.get(direction, direction)
    if direction in DIRS:
        return f"move:{direction}"
    return raw


def detect_position_loop(
    path: list[tuple[int, int]],
    *,
    goal: tuple[int, int] | None = None,
    min_cycle: int = 2,
    max_cycle: int = 8,
) -> bool:
    if len(path) < min_cycle * 2 + 1:
        return False
    unique = set(path)
    if any(path.count(cell) >= 10 for cell in unique):
        return True
    tail = path[-(max_cycle * 3 + 1):]
    for cycle_len in range(min_cycle, max_cycle + 1):
        if len(tail) < cycle_len * 2 + 1:
            continue
        a = tail[-cycle_len:]
        b = tail[-2 * cycle_len:-cycle_len]
        if a == b:
            if goal is not None:
                prev_best = min(_manhattan(cell, goal) for cell in b)
                last_best = min(_manhattan(cell, goal) for cell in a)
                if last_best < prev_best:
                    continue
            return True
    return False


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def shortest_path(grid: tuple[str, ...], start: tuple[int, int], goal: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    queue: deque[tuple[int, int]] = deque([start])
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while queue:
        cell = queue.popleft()
        if cell == goal:
            break
        for dx, dy in DIRS.values():
            nxt = (cell[0] + dx, cell[1] + dy)
            if nxt not in prev and _is_open(grid, *nxt):
                prev[nxt] = cell
                queue.append(nxt)
    if goal not in prev:
        return ()
    rev = [goal]
    cur = goal
    while prev[cur] is not None:
        cur = prev[cur]  # type: ignore[assignment]
        rev.append(cur)
    return tuple(reversed(rev))


def generate_maze_task(seed: int, *, width: int = 9, height: int = 9, family: str = "trap", split: str = "train") -> MazeTask:
    rng = random.Random(seed)
    grid = [["#" for _ in range(width)] for _ in range(height)]
    start = (1, 1)
    stack = [start]
    grid[start[1]][start[0]] = "."
    while stack:
        x, y = stack[-1]
        neighbors = []
        dirs = list(DIRS.values())
        rng.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = x + dx * 2, y + dy * 2
            if 1 <= nx < width - 1 and 1 <= ny < height - 1 and grid[ny][nx] == "#":
                neighbors.append((dx, dy, nx, ny))
        if not neighbors:
            stack.pop()
            continue
        dx, dy, nx, ny = neighbors[0]
        grid[y + dy][x + dx] = "."
        grid[ny][nx] = "."
        stack.append((nx, ny))

    goal = _farthest_open(tuple("".join(row) for row in grid), start)
    if family in {"trap", "phase_shift"}:
        _add_loops(grid, rng)
    if family == "phase_shift" and split == "heldout":
        _add_crosscuts(grid, rng)

    frozen = tuple("".join(row) for row in grid)
    path = shortest_path(frozen, start, goal)
    if not path:
        # Crosscuts should not disconnect, but keep generation robust.
        return generate_maze_task(seed + 7919, width=width, height=height, family="benign", split=split)
    return MazeTask(
        task_id=f"{split}_{family}_{seed}",
        family=family,
        width=width,
        height=height,
        grid=frozen,
        start=start,
        goal=goal,
        shortest_path=path,
    )


def make_maze_tasks(
    *,
    split: str,
    n: int,
    seed: int,
    width: int = 9,
    height: int = 9,
    family: str = "trap",
) -> list[MazeTask]:
    offset = {"demo": 0, "train": 100_000, "heldout": 200_000}.get(split, 300_000)
    return [
        generate_maze_task(offset + seed * 10_000 + idx, width=width, height=height, family=family, split=split)
        for idx in range(n)
    ]


def maze_static_metrics(task: MazeTask) -> dict[str, Any]:
    open_cells = [(x, y) for y, row in enumerate(task.grid) for x, cell in enumerate(row) if cell != "#"]
    degrees: dict[tuple[int, int], int] = {}
    for cell in open_cells:
        degrees[cell] = sum(1 for dx, dy in DIRS.values() if _is_open(task.grid, cell[0] + dx, cell[1] + dy))
    branch_cells = [cell for cell, degree in degrees.items() if degree >= 3]
    dead_ends = [cell for cell, degree in degrees.items() if degree <= 1]
    shortest = set(task.shortest_path)
    off_path_open = [cell for cell in open_cells if cell not in shortest]
    choice_points_on_shortest = [cell for cell in task.shortest_path if degrees.get(cell, 0) >= 3]
    return {
        "task_id": task.task_id,
        "family": task.family,
        "width": task.width,
        "height": task.height,
        "open_cells": len(open_cells),
        "wall_cells": task.width * task.height - len(open_cells),
        "open_fraction": len(open_cells) / max(task.width * task.height, 1),
        "shortest_path_length": task.shortest_path_length,
        "branch_cells": len(branch_cells),
        "dead_ends": len(dead_ends),
        "off_path_open_cells": len(off_path_open),
        "choice_points_on_shortest": len(choice_points_on_shortest),
        "mean_degree": sum(degrees.values()) / max(len(degrees), 1),
        "max_degree": max(degrees.values(), default=0),
    }


def _farthest_open(grid: tuple[str, ...], start: tuple[int, int]) -> tuple[int, int]:
    queue: deque[tuple[int, int]] = deque([start])
    dist = {start: 0}
    while queue:
        cell = queue.popleft()
        for dx, dy in DIRS.values():
            nxt = (cell[0] + dx, cell[1] + dy)
            if nxt not in dist and _is_open(grid, *nxt):
                dist[nxt] = dist[cell] + 1
                queue.append(nxt)
    return max(dist, key=lambda cell: (dist[cell], cell[0] + cell[1]))


def _add_loops(grid: list[list[str]], rng: random.Random) -> None:
    height = len(grid)
    width = len(grid[0])
    candidates: list[tuple[int, int]] = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if grid[y][x] != "#":
                continue
            open_lr = grid[y][x - 1] == "." and grid[y][x + 1] == "."
            open_ud = grid[y - 1][x] == "." and grid[y + 1][x] == "."
            if open_lr or open_ud:
                candidates.append((x, y))
    rng.shuffle(candidates)
    for x, y in candidates[: max(2, (width * height) // 30)]:
        grid[y][x] = "."


def _add_crosscuts(grid: list[list[str]], rng: random.Random) -> None:
    height = len(grid)
    width = len(grid[0])
    candidates = [(x, y) for y in range(1, height - 1) for x in range(1, width - 1) if grid[y][x] == "#"]
    rng.shuffle(candidates)
    for x, y in candidates[: max(1, (width * height) // 40)]:
        grid[y][x] = "."
