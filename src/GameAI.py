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

from typing import Dict, List, Optional, Set

from KnowledgeBase import Coord, KnowledgeBase
from Map.Position import Position
from PathPlanner import PathPlanner


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
    COMBAT_EVENTS = {"damage", "hit"}

    def __init__(self) -> None:
        self.player = Position()
        self.state = "ready"
        self.dir = "north"
        self.score = 0
        self.energy = 0

        self.kb = KnowledgeBase()
        self.path_planner = PathPlanner(self.kb)
        self.current_observations: Set[str] = set()
        self.enemy_distance: Optional[int] = None
        self.current_item: Optional[str] = None
        self.current_poison = False
        self.heard_steps = False
        self.damage_count = 0
        self.hit_count = 0
        self.recent_damage = False
        self.last_damage_action: Optional[int] = None
        self.last_hit_action: Optional[int] = None
        self.follow_up_shots = 0
        self.max_follow_up_shots = 4

        self.last_decision = ""
        self.last_reason = ""
        self.last_target: Optional[Coord] = None
        self.awaiting_observation = False
        self.awaiting_ticks = 0
        self.max_awaiting_ticks = 2
        self.action_counter = 0
        self.last_observation_counter = 0
        self.turn_streak = 0
        self.planned_path: List[Coord] = []
        self.recent_positions: List[Coord] = []
        self.max_recent_positions = 8

    def SetStatus(self, x: int, y: int, dir: str, state: str, score: int, energy: int):
        previous_state = self.state.lower()
        next_state = state.lower()
        previous_coord = self._current_coord()

        self.SetPlayerPosition(x, y)
        self.dir = dir.lower()
        self.state = state
        self.score = score
        self.energy = energy

        if previous_state != "game" and next_state == "game":
            self.kb.reset()
            self.planned_path = []
            self.recent_positions = []
            self.awaiting_observation = False
            self.awaiting_ticks = 0
        elif previous_state == "game" and next_state == "game":
            current_coord = self._current_coord()
            if self.path_planner.heuristic(previous_coord, current_coord) > 1:
                self.planned_path = []
                self.recent_positions = []

        self.kb.mark_visited(self._current_coord())
        self._remember_position(self._current_coord())

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
            self.awaiting_ticks = 0
            self.last_observation_counter = self.action_counter
        elif self._is_combat_observation(normalized):
            self.awaiting_observation = False
            self.awaiting_ticks = 0

    def GetObservationsClean(self):
        self.current_observations = set()
        self.enemy_distance = None
        self.current_item = None
        self.current_poison = False
        self.heard_steps = False
        self.recent_damage = False

    def GetDecision(self) -> str:
        if self.awaiting_observation:
            self.awaiting_ticks += 1
            if self.awaiting_ticks < self.max_awaiting_ticks:
                return ""
            print(
                "[t=%s] timeout: nenhuma observacao nova apos %s ciclos; decidindo com a memoria atual" %
                (self.action_counter, self.awaiting_ticks)
            )
            self.awaiting_observation = False
            self.awaiting_ticks = 0

        self.kb.mark_visited(self._current_coord())

        if self._should_attack():
            self.follow_up_shots = 0
            return self._commit(
                "atacar",
                "inimigo visivel a %s passo(s), energia=%s" %
                (self.enemy_distance, self.energy)
            )

        if self._should_follow_up_attack():
            self.follow_up_shots += 1
            return self._commit(
                "atacar",
                "tiro de continuacao apos acerto recente"
            )

        if self._should_escape():
            escape = self._escape_command()
            if escape is not None:
                return self._commit(
                    escape,
                    "ameaca proxima com energia baixa/dano recente; buscando distancia"
                )

        if self._should_collect_item():
            return self._commit(
                self._collect_command(),
                "item %s detectado na celula atual" % self._current_collectible_item()
            )

        item_step = self._next_item_step()
        if item_step is not None:
            command = self._command_to_reach(item_step)
            return self._commit(
                command,
                "indo ate item conhecido em %s" % (
                    self.path_planner.best_item_target(self._current_coord(), self.energy),
                ),
                item_step
            )

        if self._should_continue_forward():
            return self._commit(
                "andar",
                "exploracao em linha reta; frente aceitavel e sem prioridade maior",
                self._coord_ahead()
            )

        next_step = self._next_a_star_step()
        if next_step is None:
            if self._should_scan_for_enemy():
                scan = self._safe_spin()
                return self._commit(
                    scan,
                    "sem caminho de exploracao; passos perto, procurando inimigo"
                )

            return self._commit(
                self._safe_spin(),
                "sem caminho seguro conhecido; girando para observar"
            )

        command = self._command_to_reach(next_step)
        return self._commit(command, "explorando alvo seguro/fronteira %s" % (next_step,), next_step)

    def _process_observation(self, obs: str) -> None:
        if obs == "blocked":
            if self.last_target is not None:
                self.kb.mark_blocked(self.last_target)
                self.planned_path = []
            return

        if obs == "blueLight":
            self.current_item = "treasure"
            self.kb.mark_item(self._current_coord(), self.current_item)
            return

        if obs == "redLight":
            self.current_item = "powerup"
            self.kb.mark_item(self._current_coord(), self.current_item)
            return

        if obs in ("weakLight", "weaklight"):
            self.current_item = "unknown"
            self.kb.mark_item(self._current_coord(), self.current_item)
            return

        if obs == "greenLight":
            self.current_poison = True
            self.kb.mark_item(self._current_coord(), "poison")
            return

        if obs == "steps":
            self.heard_steps = True
            for coord in self._coords_within_manhattan(self._current_coord(), 2):
                self.kb.mark_steps_nearby(coord)
            return

        if obs == "damage":
            self.damage_count += 1
            self.recent_damage = True
            self.last_damage_action = self.action_counter
            return

        if obs == "hit":
            self.hit_count += 1
            self.last_hit_action = self.action_counter
            return

        if obs.startswith("enemy#") or obs.startswith("eneny#"):
            try:
                self.enemy_distance = int(obs.replace("enemy#", "").replace("eneny#", ""))
            except ValueError:
                self.enemy_distance = 1
            self.follow_up_shots = 0
            self._mark_visible_enemy()
            return

        if obs in ("enemy", "eneny"):
            self.enemy_distance = 1
            self.follow_up_shots = 0
            self._mark_visible_enemy()

    def _learn_environment(self) -> None:
        current = self._current_coord()
        self.kb.mark_visited(current)

        has_breeze = "breeze" in self.current_observations
        has_flash = "flash" in self.current_observations

        for coord in self.kb.neighbors(current):
            if self.kb.is_safe_to_cross(coord):
                continue
            if has_breeze:
                self.kb.mark_death_risk(coord)
            else:
                self.kb.mark_no_death_risk(coord)
            if has_flash:
                self.kb.mark_teleport_risk(coord)
            else:
                self.kb.mark_no_teleport_risk(coord)
            if not has_breeze and not has_flash:
                self.kb.mark_safe(coord)

    def _is_environment_observation(self, observations: List[str]) -> bool:
        if len(observations) == 0:
            return True
        return any(
            obs in self.OBSERVATION_EVENTS
            or obs.startswith("enemy#")
            or obs.startswith("eneny#")
            for obs in observations
        )

    def _is_combat_observation(self, observations: List[str]) -> bool:
        return any(obs in self.COMBAT_EVENTS for obs in observations)

    def _should_collect_item(self) -> bool:
        return self._current_collectible_item() is not None

    def _should_attack(self) -> bool:
        if self.enemy_distance is None:
            return False
        if self.energy <= 10:
            return False
        return self.enemy_distance <= 10

    def _should_follow_up_attack(self) -> bool:
        if self.last_decision != "atacar":
            return False
        if self.follow_up_shots >= self.max_follow_up_shots:
            return False
        if self.energy <= 15:
            return False
        return self._recent_hit_memory()

    def _should_scan_for_enemy(self) -> bool:
        if not self.heard_steps:
            return False
        if self.turn_streak >= len(self.DIRECTIONS):
            return False
        if self.energy <= 25:
            return False
        if self._has_usable_planned_step():
            return False
        return self._current_collectible_item() != "powerup"

    def _should_escape(self) -> bool:
        if self.enemy_distance is not None and self.energy > 10:
            return False
        return self.energy <= 25 and (self.heard_steps or self._recent_damage_memory())

    def _recent_damage_memory(self) -> bool:
        if self.recent_damage:
            return True
        if self.last_damage_action is None:
            return False
        return self.action_counter - self.last_damage_action <= 3

    def _recent_hit_memory(self) -> bool:
        if self.last_hit_action is None:
            return False
        return self.action_counter - self.last_hit_action <= 2

    def _escape_command(self) -> Optional[str]:
        behind = self._coord_behind()
        if self.kb.is_safe_to_cross(behind):
            return "andar_re"

        forward = self._coord_ahead()
        if self.kb.is_safe_to_cross(forward) and not self.heard_steps:
            return "andar"

        return self._safe_spin()

    def _has_usable_planned_step(self) -> bool:
        next_step, _ = self.path_planner.next_step_from_existing_path(
            self._current_coord(),
            self.planned_path
        )
        return (
            next_step is not None and
            self.path_planner.is_legal_step_target(next_step)
        )

    def _should_continue_forward(self) -> bool:
        forward = self._coord_ahead()
        if not self.path_planner.is_legal_step_target(forward):
            return False
        if self.kb.is_blocked_or_deadly(forward):
            return False
        if self.turn_streak > 0:
            return False
        if len(self.recent_positions) >= 2 and forward == self.recent_positions[-2]:
            return False
        return True

    def _collect_command(self) -> str:
        item = self._current_collectible_item()
        if item == "powerup":
            return "pegar_powerup"
        if item == "unknown":
            return "pegar_anel"
        return "pegar_ouro"

    def _current_collectible_item(self) -> Optional[str]:
        if self.current_poison:
            return None

        if self.current_item is not None:
            return self.current_item

        item = self.kb.cell(self._current_coord()).item
        if item == "poison":
            return None
        return item

    def _mark_visible_enemy(self) -> None:
        if self.enemy_distance is None:
            return
        enemy_pos = self._coord_ahead(self.enemy_distance)
        if self.kb.in_bounds(enemy_pos):
            self.kb.mark_enemy(enemy_pos, self.enemy_distance, self.action_counter)

    def _next_item_step(self) -> Optional[Coord]:
        next_step, _, path = self.path_planner.next_item_step(
            self._current_coord(),
            self.dir,
            self.energy,
            self.recent_positions,
            self.planned_path
        )
        self.planned_path = path
        return next_step

    def _next_a_star_step(self) -> Optional[Coord]:
        next_step, path = self.path_planner.next_exploration_step(
            self._current_coord(),
            self.dir,
            self.recent_positions,
            self.planned_path
        )
        self.planned_path = path
        return next_step

    def _command_to_reach(self, target: Coord) -> str:
        forward = self._coord_ahead()
        if target == forward:
            return "andar"

        backward = self._coord_behind()
        if target == backward:
            return "andar_re"

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

    def _commit(self, decision: str, reason: str, target: Optional[Coord] = None) -> str:
        self.last_decision = decision
        self.last_reason = reason

        if decision in ("virar_direita", "virar_esquerda"):
            self.turn_streak += 1
        else:
            self.turn_streak = 0

        if decision == "andar":
            self.last_target = self._coord_ahead(1)
        elif decision == "andar_re":
            self.last_target = self._coord_behind()
        else:
            self.last_target = None

        if decision.startswith("pegar_"):
            self.kb.clear_item(self._current_coord())

        if decision:
            self.action_counter += 1
            self.awaiting_observation = True
            self.awaiting_ticks = 0

        print(
            "[t=%s] %s: %s | pos=%s dir=%s obs=%s target=%s energy=%s score=%s" %
            (
                self.action_counter,
                decision,
                reason,
                self._current_coord(),
                self.dir,
                sorted(self.current_observations),
                self.last_target,
                self.energy,
                self.score,
            )
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

    def _coord_ahead(self, steps: int = 1) -> Coord:
        dx, dy = self.DELTAS[self.dir]
        return (self.player.x + dx * steps, self.player.y + dy * steps)

    def _coord_behind(self) -> Coord:
        dx, dy = self.DELTAS[self.dir]
        return (self.player.x - dx, self.player.y - dy)

    def _current_coord(self) -> Coord:
        return (self.player.x, self.player.y)

    def _coords_within_manhattan(self, center: Coord, radius: int) -> List[Coord]:
        coords: List[Coord] = []
        cx, cy = center
        for dx in range(-radius, radius + 1):
            remaining = radius - abs(dx)
            for dy in range(-remaining, remaining + 1):
                coord = (cx + dx, cy + dy)
                if coord != center and self.kb.in_bounds(coord):
                    coords.append(coord)
        return coords

    def _remember_position(self, coord: Coord) -> None:
        if self.recent_positions and self.recent_positions[-1] == coord:
            return

        self.recent_positions.append(coord)
        if len(self.recent_positions) > self.max_recent_positions:
            self.recent_positions.pop(0)
