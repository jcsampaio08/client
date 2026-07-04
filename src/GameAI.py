#!/usr/bin/env python

"""GameAI.py: INF1771 GameAI File - Where Decisions are made."""
#############################################################
#Copyright 2020 Augusto Baffa
#
#Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#############################################################
__author__      = "Augusto Baffa"
__copyright__   = "Copyright 2020, Rio de janeiro, Brazil"
__license__ = "GPL"
__version__ = "1.0.0"
__email__ = "abaffa@inf.puc-rio.br"
#############################################################

from dataclasses import dataclass
from enum import Enum
import heapq
from typing import Dict, List, Optional, Set, Tuple

from Map.Position import Position


Coord = Tuple[int, int]


class CellState(Enum):
    """Knowledge states used by the path planner."""

    UNKNOWN = "unknown"
    SAFE = "safe"
    VISITED = "visited"
    BLOCKED = "blocked"
    DEATH_RISK = "death_risk"
    TELEPORT_RISK = "teleport_risk"


@dataclass
class CellInfo:
    """Memory stored for each known map coordinate."""

    state: CellState = CellState.UNKNOWN
    visits: int = 0
    breeze_evidence: int = 0
    flash_evidence: int = 0


class KnowledgeBase:
    """Graph-like memory for the hidden 59x34 board."""

    WIDTH = 59
    HEIGHT = 34

    def __init__(self) -> None:
        self.cells: Dict[Coord, CellInfo] = {}

    def reset(self) -> None:
        self.cells.clear()

    def cell(self, coord: Coord) -> CellInfo:
        if coord not in self.cells:
            self.cells[coord] = CellInfo()
        return self.cells[coord]

    def in_bounds(self, coord: Coord) -> bool:
        x, y = coord
        return 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT

    def neighbors(self, coord: Coord) -> List[Coord]:
        x, y = coord
        candidates = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
        return [pos for pos in candidates if self.in_bounds(pos)]

    def mark_visited(self, coord: Coord) -> None:
        info = self.cell(coord)
        info.state = CellState.VISITED
        info.visits += 1

    def mark_safe(self, coord: Coord) -> None:
        info = self.cell(coord)
        if info.state not in (CellState.VISITED, CellState.BLOCKED):
            info.state = CellState.SAFE

    def mark_blocked(self, coord: Coord) -> None:
        info = self.cell(coord)
        info.state = CellState.BLOCKED

    def mark_death_risk(self, coord: Coord) -> None:
        info = self.cell(coord)
        if info.state in (CellState.UNKNOWN, CellState.TELEPORT_RISK):
            info.state = CellState.DEATH_RISK
        info.breeze_evidence += 1

    def mark_teleport_risk(self, coord: Coord) -> None:
        info = self.cell(coord)
        if info.state == CellState.UNKNOWN:
            info.state = CellState.TELEPORT_RISK
        info.flash_evidence += 1

    def is_safe_to_cross(self, coord: Coord) -> bool:
        return self.cell(coord).state in (CellState.SAFE, CellState.VISITED)

    def is_frontier_target(self, coord: Coord) -> bool:
        return self.cell(coord).state == CellState.UNKNOWN

    def is_blocked_or_deadly(self, coord: Coord) -> bool:
        return self.cell(coord).state in (
            CellState.BLOCKED,
            CellState.DEATH_RISK,
            CellState.TELEPORT_RISK,
        )

    def visit_count(self, coord: Coord) -> int:
        return self.cell(coord).visits


class GameAI():
    """Decision module for the drone challenge.

    The policy is hybrid:
    - Opportunistic combat when an enemy is directly visible.
    - Item collection on the current tile.
    - A* exploration toward the closest safe frontier.
    - Strong risk aversion around breeze/flash evidence.
    - A network semaphore that prevents issuing a second action before the
      observation cycle for the previous action has been processed.
    """

    DIRECTIONS = ["north", "east", "south", "west"]
    DELTAS: Dict[str, Coord] = {
        "north": (0, -1),
        "east": (1, 0),
        "south": (0, 1),
        "west": (-1, 0),
    }
    OBSERVATION_EVENTS = {
        "blocked",
        "steps",
        "breeze",
        "flash",
        "blueLight",
        "redLight",
        "greenLight",
        "weakLight",
        "weaklight",
        "enemy",
        "eneny",
    }

    def __init__(self) -> None:
        self.player = Position()
        self.state = "ready"
        self.dir = "north"
        self.score = 0
        self.energy = 0

        self.kb = KnowledgeBase()
        self.current_observations: Set[str] = set()
        self.enemy_distance: Optional[int] = None
        self.current_item: Optional[str] = None
        self.current_poison = False

        self.last_decision = ""
        self.last_target: Optional[Coord] = None
        self.awaiting_observation = False
        self.action_counter = 0
        self.last_observation_counter = 0
        self.turn_streak = 0
        self.planned_path: List[Coord] = []

    def SetStatus(self, x: int, y: int, dir: str, state: str, score: int, energy: int):
        previous_state = self.state.lower()
        next_state = state.lower()

        self.SetPlayerPosition(x, y)
        self.dir = dir.lower()
        self.state = state
        self.score = score
        self.energy = energy

        if previous_state != "game" and next_state == "game":
            self.kb.reset()
            self.planned_path = []
            self.awaiting_observation = False

        self.kb.mark_visited(self._current_coord())

    def GetCurrentObservableAdjacentPositions(self) -> List[Position]:
        return self.GetObservableAdjacentPositions(self.player)

    def GetObservableAdjacentPositions(self, pos) -> List[Position]:
        return [
            Position(pos.x - 1, pos.y),
            Position(pos.x + 1, pos.y),
            Position(pos.x, pos.y - 1),
            Position(pos.x, pos.y + 1),
        ]

    def GetAllAdjacentPositions(self) -> List[Position]:
        return [
            Position(self.player.x - 1, self.player.y - 1),
            Position(self.player.x, self.player.y - 1),
            Position(self.player.x + 1, self.player.y - 1),
            Position(self.player.x - 1, self.player.y),
            Position(self.player.x + 1, self.player.y),
            Position(self.player.x - 1, self.player.y + 1),
            Position(self.player.x, self.player.y + 1),
            Position(self.player.x + 1, self.player.y + 1),
        ]

    def NextPositionAhead(self, steps):
        dx, dy = self.DELTAS[self.dir]
        return Position(self.player.x + dx * steps, self.player.y + dy * steps)

    def NextPosition(self) -> Position:
        return self.NextPositionAhead(1)

    def GetPlayerPosition(self):
        return Position(self.player.x, self.player.y)

    def SetPlayerPosition(self, x: int, y: int):
        self.player.x = x
        self.player.y = y

    def GetObservations(self, observations):
        self.GetObservationsClean()
        normalized = [obs.strip() for obs in observations if obs.strip()]

        for obs in normalized:
            self.current_observations.add(obs)
            self._process_observation(obs)

        if self._is_environment_observation(normalized):
            self._learn_environment()
            self.awaiting_observation = False
            self.last_observation_counter = self.action_counter

    def GetObservationsClean(self):
        self.current_observations = set()
        self.enemy_distance = None
        self.current_item = None
        self.current_poison = False

    def GetDecision(self) -> str:
        if self.awaiting_observation:
            return ""

        self.kb.mark_visited(self._current_coord())

        if self._should_collect_item():
            return self._commit("pegar_ouro")

        if self._should_attack():
            return self._commit("atacar")

        next_step = self._next_a_star_step()
        if next_step is None:
            return self._commit(self._safe_spin())

        return self._commit(self._command_to_reach(next_step), next_step)

    def _process_observation(self, obs: str) -> None:
        if obs == "blocked":
            if self.last_target is not None:
                self.kb.mark_blocked(self.last_target)
                self.planned_path = []
            return

        if obs == "blueLight":
            self.current_item = "treasure"
            return

        if obs == "redLight":
            self.current_item = "powerup"
            return

        if obs in ("weakLight", "weaklight"):
            self.current_item = "unknown"
            return

        if obs == "greenLight":
            self.current_poison = True
            return

        if obs.startswith("enemy#") or obs.startswith("eneny#"):
            try:
                self.enemy_distance = int(obs.replace("enemy#", "").replace("eneny#", ""))
            except ValueError:
                self.enemy_distance = 1
            return

        if obs in ("enemy", "eneny"):
            self.enemy_distance = 1

    def _learn_environment(self) -> None:
        current = self._current_coord()
        self.kb.mark_visited(current)

        has_breeze = "breeze" in self.current_observations
        has_flash = "flash" in self.current_observations

        if not has_breeze and not has_flash:
            for coord in self.kb.neighbors(current):
                self.kb.mark_safe(coord)
            return

        for coord in self.kb.neighbors(current):
            if self.kb.is_safe_to_cross(coord):
                continue
            if has_breeze:
                self.kb.mark_death_risk(coord)
            if has_flash:
                self.kb.mark_teleport_risk(coord)

    def _is_environment_observation(self, observations: List[str]) -> bool:
        if len(observations) == 0:
            return True
        return any(
            obs in self.OBSERVATION_EVENTS
            or obs.startswith("enemy#")
            or obs.startswith("eneny#")
            for obs in observations
        )

    def _should_collect_item(self) -> bool:
        return self.current_item is not None and not self.current_poison

    def _should_attack(self) -> bool:
        return self.enemy_distance is not None and self.energy > 15

    def _next_a_star_step(self) -> Optional[Coord]:
        current = self._current_coord()
        if len(self.planned_path) >= 2 and self.planned_path[0] == current:
            next_step = self.planned_path[1]
            if self._is_legal_step_target(next_step):
                return next_step

        best_path: List[Coord] = []
        for target in self._frontier_targets():
            path = self._a_star(current, target)
            if len(path) < 2:
                continue
            if not best_path or self._path_rank(path) < self._path_rank(best_path):
                best_path = path

        self.planned_path = best_path
        if len(best_path) >= 2:
            return best_path[1]
        return None

    def _frontier_targets(self) -> List[Coord]:
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

    def _a_star(self, start: Coord, target: Coord) -> List[Coord]:
        open_heap: List[Tuple[int, int, Coord]] = []
        heapq.heappush(open_heap, (self._heuristic(start, target), 0, start))

        came_from: Dict[Coord, Coord] = {}
        g_score: Dict[Coord, int] = {start: 0}
        closed: Set[Coord] = set()

        while open_heap:
            _, current_cost, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            if current == target:
                return self._reconstruct_path(came_from, current)

            closed.add(current)
            for neighbor in self.kb.neighbors(current):
                if not self._can_a_star_enter(neighbor, target):
                    continue

                tentative = current_cost + self._step_cost(neighbor)
                if tentative >= g_score.get(neighbor, 10**9):
                    continue

                came_from[neighbor] = current
                g_score[neighbor] = tentative
                priority = tentative + self._heuristic(neighbor, target)
                heapq.heappush(open_heap, (priority, tentative, neighbor))

        return []

    def _can_a_star_enter(self, coord: Coord, target: Coord) -> bool:
        if coord == target:
            return self.kb.is_frontier_target(coord)
        return self.kb.is_safe_to_cross(coord)

    def _is_legal_step_target(self, coord: Coord) -> bool:
        return self.kb.is_safe_to_cross(coord) or self.kb.is_frontier_target(coord)

    def _step_cost(self, coord: Coord) -> int:
        return 1 + min(self.kb.visit_count(coord), 5)

    def _path_rank(self, path: List[Coord]) -> Tuple[int, int, int]:
        return (
            len(path),
            self._turn_cost_to(path[1]) if len(path) > 1 else 0,
            sum(self.kb.visit_count(coord) for coord in path),
        )

    def _heuristic(self, a: Coord, b: Coord) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _turn_cost_to(self, target: Coord) -> int:
        desired_dir = self._direction_to(target)
        if desired_dir is None:
            return 99

        current_idx = self.DIRECTIONS.index(self.dir)
        target_idx = self.DIRECTIONS.index(desired_dir)
        diff = abs(target_idx - current_idx)
        return min(diff, len(self.DIRECTIONS) - diff)

    def _reconstruct_path(self, came_from: Dict[Coord, Coord], current: Coord) -> List[Coord]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    def _command_to_reach(self, target: Coord) -> str:
        forward = self._coord_ahead()
        if target == forward:
            return "andar"

        desired_dir = self._direction_to(target)
        if desired_dir is None:
            return self._safe_spin()

        current_idx = self.DIRECTIONS.index(self.dir)
        target_idx = self.DIRECTIONS.index(desired_dir)
        diff = (target_idx - current_idx) % len(self.DIRECTIONS)

        if diff == 1:
            return "virar_direita"
        if diff == 3:
            return "virar_esquerda"
        return "virar_direita"

    def _safe_spin(self) -> str:
        return "virar_direita"

    def _commit(self, decision: str, target: Optional[Coord] = None) -> str:
        self.last_decision = decision

        if decision in ("virar_direita", "virar_esquerda"):
            self.turn_streak += 1
        else:
            self.turn_streak = 0

        if decision == "andar":
            self.last_target = self._coord_ahead()
        else:
            self.last_target = None

        if decision:
            self.action_counter += 1
            self.awaiting_observation = True

        print(
            "AI:",
            decision,
            "pos=", self._current_coord(),
            "dir=", self.dir,
            "obs=", sorted(self.current_observations),
            "target=", self.last_target,
            "awaiting=", self.awaiting_observation,
            "energy=", self.energy,
            "score=", self.score
        )
        return decision

    def _direction_to(self, target: Coord) -> Optional[str]:
        current = self._current_coord()
        dx = target[0] - current[0]
        dy = target[1] - current[1]
        for direction, delta in self.DELTAS.items():
            if delta == (dx, dy):
                return direction
        return None

    def _coord_ahead(self) -> Coord:
        dx, dy = self.DELTAS[self.dir]
        return (self.player.x + dx, self.player.y + dy)

    def _current_coord(self) -> Coord:
        return (self.player.x, self.player.y)
