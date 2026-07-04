#!/usr/bin/env python

"""KnowledgeBase.py: memory model for the INF1771 drone bot."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


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
    no_breeze_evidence: int = 0
    no_flash_evidence: int = 0
    item: Optional[str] = None
    enemy_distance: Optional[int] = None
    enemy_last_seen_turn: Optional[int] = None
    steps_evidence: int = 0


class KnowledgeBase:
    """Graph-like memory for the hidden 59x34 board."""

    WIDTH = 59
    HEIGHT = 34

    def __init__(self) -> None:
        self.cells: Dict[Coord, CellInfo] = {}
        self.item_cells: Dict[Coord, str] = {}
        self.enemy_cells: Dict[Coord, Tuple[int, int]] = {}

    def reset(self) -> None:
        self.cells.clear()
        self.item_cells.clear()
        self.enemy_cells.clear()

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

    def mark_no_death_risk(self, coord: Coord) -> None:
        info = self.cell(coord)
        info.no_breeze_evidence += 1
        if info.state == CellState.DEATH_RISK:
            if info.flash_evidence > info.no_flash_evidence:
                info.state = CellState.TELEPORT_RISK
            else:
                info.state = CellState.SAFE

    def mark_no_teleport_risk(self, coord: Coord) -> None:
        info = self.cell(coord)
        info.no_flash_evidence += 1
        if info.state == CellState.TELEPORT_RISK:
            if info.breeze_evidence > info.no_breeze_evidence:
                info.state = CellState.DEATH_RISK
            else:
                info.state = CellState.SAFE

    def mark_item(self, coord: Coord, item: str) -> None:
        info = self.cell(coord)
        info.item = item
        self.item_cells[coord] = item

    def clear_item(self, coord: Coord) -> None:
        info = self.cell(coord)
        info.item = None
        self.item_cells.pop(coord, None)

    def mark_enemy(self, coord: Coord, distance: int, turn: int) -> None:
        info = self.cell(coord)
        info.enemy_distance = distance
        info.enemy_last_seen_turn = turn
        self.enemy_cells[coord] = (distance, turn)

    def mark_steps_nearby(self, coord: Coord) -> None:
        self.cell(coord).steps_evidence += 1

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
