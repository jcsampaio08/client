#!/usr/bin/env python

"""PathPlanner.py: A* navigation helpers for the INF1771 drone bot."""

import heapq
from typing import Dict, List, Optional, Set, Tuple

from KnowledgeBase import CellState, Coord, KnowledgeBase


class PathPlanner:
    """Plans safe movement over the bot's partial map memory."""

    DIRECTIONS = ["north", "east", "south", "west"]

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    def next_item_step(
        self,
        current: Coord,
        direction: str,
        energy: int,
        recent_positions: List[Coord],
        planned_path: List[Coord]
    ) -> Tuple[Optional[Coord], Optional[Coord], List[Coord]]:
        target = self.best_item_target(current, energy)
        if target is None:
            return None, None, []

        next_step, remaining_path = self.next_step_from_existing_path(
            current,
            planned_path
        )
        if next_step is not None and remaining_path[-1] == target:
            return next_step, target, remaining_path

        path = self.a_star(current, target, direction, recent_positions)
        if len(path) >= 2:
            return path[1], target, path
        return None, target, []

    def best_item_target(self, current: Coord, energy: int) -> Optional[Coord]:
        candidates: List[Tuple[int, int, Coord]] = []

        for coord, item in self.kb.item_cells.items():
            if item == "poison":
                continue
            if not self.kb.is_safe_to_cross(coord):
                continue

            priority = 0
            if energy <= 60 and item == "powerup":
                priority = -50
            elif item == "powerup":
                priority = -10
            elif item == "treasure":
                priority = -5

            candidates.append((priority + self.heuristic(current, coord), priority, coord))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def next_exploration_step(
        self,
        current: Coord,
        direction: str,
        recent_positions: List[Coord],
        planned_path: List[Coord]
    ) -> Tuple[Optional[Coord], List[Coord]]:
        next_step, remaining_path = self.next_step_from_existing_path(
            current,
            planned_path
        )
        if next_step is not None:
            if (
                self.is_legal_step_target(next_step) and
                not self.is_bad_loop_step(next_step, recent_positions)
            ):
                return next_step, remaining_path

        best_path: List[Coord] = []
        for target in self.frontier_targets():
            path = self.a_star(current, target, direction, recent_positions)
            if len(path) < 2:
                continue
            if (
                self.is_bad_loop_step(path[1], recent_positions) and
                self.has_non_loop_adjacent_option(current, recent_positions)
            ):
                continue
            if (
                not best_path or
                self.path_rank(path, direction, recent_positions) <
                self.path_rank(best_path, direction, recent_positions)
            ):
                best_path = path

        if len(best_path) >= 2:
            return best_path[1], best_path
        return None, best_path

    def next_step_from_existing_path(
        self,
        current: Coord,
        planned_path: List[Coord]
    ) -> Tuple[Optional[Coord], List[Coord]]:
        if len(planned_path) < 2:
            return None, []
        if current not in planned_path:
            return None, []

        current_index = planned_path.index(current)
        if current_index + 1 >= len(planned_path):
            return None, []

        remaining_path = planned_path[current_index:]
        return planned_path[current_index + 1], remaining_path

    def frontier_targets(self) -> List[Coord]:
        targets: Set[Coord] = set()
        known_safe = [
            coord for coord, info in self.kb.cells.items()
            if info.state in (CellState.SAFE, CellState.VISITED)
        ]

        for coord in known_safe:
            for neighbor in self.kb.neighbors(coord):
                if self.kb.is_frontier_target(neighbor):
                    targets.add(neighbor)

        return list(targets)

    def a_star(
        self,
        start: Coord,
        target: Coord,
        direction: str,
        recent_positions: List[Coord]
    ) -> List[Coord]:
        open_heap: List[Tuple[int, int, Coord]] = []
        heapq.heappush(open_heap, (self.heuristic(start, target), 0, start))

        came_from: Dict[Coord, Coord] = {}
        g_score: Dict[Coord, int] = {start: 0}
        closed: Set[Coord] = set()

        while open_heap:
            _, current_cost, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            if current == target:
                return self.reconstruct_path(came_from, current)

            closed.add(current)
            for neighbor in self.kb.neighbors(current):
                if not self.can_a_star_enter(neighbor, target):
                    continue

                tentative = current_cost + self.step_cost(neighbor, recent_positions)
                if tentative >= g_score.get(neighbor, 10**9):
                    continue

                came_from[neighbor] = current
                g_score[neighbor] = tentative
                priority = tentative + self.heuristic(neighbor, target)
                heapq.heappush(open_heap, (priority, tentative, neighbor))

        return []

    def can_a_star_enter(self, coord: Coord, target: Coord) -> bool:
        if coord == target:
            return (
                self.kb.is_frontier_target(coord) or
                self.kb.is_safe_to_cross(coord)
            )
        return self.kb.is_safe_to_cross(coord)

    def is_legal_step_target(self, coord: Coord) -> bool:
        return self.kb.is_safe_to_cross(coord) or self.kb.is_frontier_target(coord)

    def step_cost(self, coord: Coord, recent_positions: List[Coord]) -> int:
        return (
            1 +
            min(self.kb.visit_count(coord), 5) +
            self.recent_position_penalty(coord, recent_positions) +
            self.enemy_pressure_penalty(coord)
        )

    def path_rank(
        self,
        path: List[Coord],
        direction: str,
        recent_positions: List[Coord]
    ) -> Tuple[int, int, int, int, int]:
        return (
            len(path),
            self.turn_cost_to(path[1], path[0], direction) if len(path) > 1 else 0,
            self.recent_position_penalty(path[1], recent_positions) if len(path) > 1 else 0,
            self.enemy_pressure_penalty(path[1]) if len(path) > 1 else 0,
            sum(self.kb.visit_count(coord) for coord in path),
        )

    def enemy_pressure_penalty(self, coord: Coord) -> int:
        return min(self.kb.cell(coord).steps_evidence, 3) * 4

    def recent_position_penalty(self, coord: Coord, recent_positions: List[Coord]) -> int:
        if coord not in recent_positions:
            return 0
        age = len(recent_positions) - recent_positions.index(coord)
        return age * 10

    def is_bad_loop_step(self, coord: Coord, recent_positions: List[Coord]) -> bool:
        if len(recent_positions) < 2:
            return False
        return coord == recent_positions[-2]

    def has_non_loop_adjacent_option(
        self,
        current: Coord,
        recent_positions: List[Coord]
    ) -> bool:
        for coord in self.kb.neighbors(current):
            if self.is_bad_loop_step(coord, recent_positions):
                continue
            if self.is_legal_step_target(coord):
                return True
        return False

    def heuristic(self, a: Coord, b: Coord) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def turn_cost_to(self, target: Coord, current: Coord, direction: str) -> int:
        desired_dir = self.direction_to(target, current)
        if desired_dir is None:
            return 99

        current_idx = self.DIRECTIONS.index(direction)
        target_idx = self.DIRECTIONS.index(desired_dir)
        diff = abs(target_idx - current_idx)
        return min(diff, len(self.DIRECTIONS) - diff)

    def direction_to(self, target: Coord, current: Coord) -> Optional[str]:
        dx = target[0] - current[0]
        dy = target[1] - current[1]
        deltas: Dict[str, Coord] = {
            "north": (0, -1),
            "east": (1, 0),
            "south": (0, 1),
            "west": (-1, 0),
        }
        for direction, delta in deltas.items():
            if delta == (dx, dy):
                return direction
        return None

    def reconstruct_path(self, came_from: Dict[Coord, Coord], current: Coord) -> List[Coord]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
