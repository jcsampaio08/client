#!/usr/bin/env python
"""GameAI.py: INF1771 GameAI - Decisoes do agente.

ESTRUTURA GERAL (esqueleto):
  - WorldMap: conhecimento do labirinto + inferencia de seguranca + BFS (Map/WorldMap.py)
  - State machine: define o "modo" atual do agente
  - GetObservations/GetObservationsClean: atualizam o WorldMap a cada ciclo
  - GetDecision: decide UMA acao por ciclo, seguindo a ordem de prioridade:

      1) Inimigo alinhado na mira e perto        -> ATACAR
      2) Em cima de item (blue/red/weakLight)    -> PEGAR
      3) Inimigo ouvido perto mas nao alinhado   -> PERSEGUIR (virar/andar)
      4) Energia baixa e powerup conhecido       -> IR ATE POWERUP
      5) Tesouro conhecido nao coletado          -> IR ATE TESOURO
      6) Caso contrario                          -> EXPLORAR (frontier + BFS)

  Os métodos marcados com "# TODO" sao o que falta implementar de fato
  (a parte "pesada"). O fluxo/orquestracao ja esta pronto.
"""

import random
import time
from enum import Enum
from typing import List, Optional, Tuple, Dict

from Map.Position import Position
from Map.WorldMap import WorldMap, Coord


class State(Enum):
    EXPLORE = "explore"
    HUNT_ENEMY = "hunt_enemy"
    SCAN_ENEMY = "scan_enemy"    # ouviu passos, procurando alinhamento pra atirar
    SEEK_ITEM = "seek_item"
    RETREAT = "retreat"          # energia baixa, buscando powerup / evitando combate
    ESCAPE_DANGER = "escape_danger"

ENERGY_FLEE_THRESHOLD = 20      # abaixo disso, foge em vez de trocar tiro
MAX_SCAN_ATTEMPTS = 4           # giros tentando alinhar antes de desistir e reposicionar
ITEM_RESPAWN_COOLDOWN_SEC = 60  # ASSUNCAO: tempo estimado de respawn de itens.
                                 # O enunciado nao especifica o valor exato -
                                 # ajustar apos observar o comportamento real
                                 # do servidor de treino.


class GameAI():

    def __init__(self):
        self.player = Position()
        self.dir = "north"
        self.state_status = "ready"     # estado do SERVIDOR (Ready/Game/Gameover) -> nome != 'state' pra nao colidir com State
        self.score = 0
        self.energy = 100

        # posicao relativa interna (independente da posicao absoluta do servidor)
        self.rel_pos: Coord = (0, 0)

        self.world = WorldMap()
        self.state = State.EXPLORE

        # buffer de observacoes cruas recebidas neste ciclo (posicao atual)
        self._pending_obs: List[str] = []
        self._enemy_distance: Optional[int] = None   # distancia do inimigo na mira, se houver
        self._steps_heard: bool = False               # passos ouvidos (inimigo a ate 2 de manhattan)
        self._scan_attempts: int = 0                  # giros consecutivos tentando alinhar com inimigo
        self._known_items: Dict[Coord, str] = {}       # pos -> "blueLight"|"redLight"|"weakLight", ainda nao pegos
        self._item_cooldown: Dict[Coord, float] = {}    # pos -> timestamp em que foi esvaziada (pegou ou sumiu)
        self._planned_path: List[Coord] = []           # caminho atual sendo seguido passo a passo

        self.action_log: List[str] = []

    # ------------------------------------------------------------ status

    def SetStatus(self, x: int, y: int, dir: str, state: str, score: int, energy: int):
        prev_energy = self.energy
        prev_score = self.score
        prev_state_status = self.state_status

        self.player.x = x
        self.player.y = y
        self.dir = dir.lower()
        self.state_status = state
        self.score = score
        self.energy = energy

        # posicao usada pelo mapa: SEMPRE a confirmada pelo servidor, nunca
        # prevista. Isso evita desincronizacao apos 'blocked' ou teleporte.
        self.rel_pos = (x, y)
        self.world.mark_visited(self.rel_pos)

        self._log_diagnostics(prev_energy, prev_score, prev_state_status)

    def _log_diagnostics(self, prev_energy: int, prev_score: int, prev_state_status: str):
        """Prints explicitos pra facilitar descobrir DEPOIS o que causou o
        fim de uma partida (poço, morte por dano, ou so o timer de 10min)."""
        energy_drop = prev_energy - self.energy
        score_delta = self.score - prev_score

        if energy_drop > 0:
            print(f"!! ENERGIA CAIU: {prev_energy} -> {self.energy} (perdeu {energy_drop}) pos={self.rel_pos}")

        if self.energy <= 0 and prev_energy > 0:
            print(f"!! MORTE POR DANO detectada: energia chegou a 0 em pos={self.rel_pos}, score={self.score}")

        if score_delta <= -900:
            print(f"!! QUEDA EM POCO provavel: score caiu {score_delta} (de {prev_score} para {self.score}) em pos={self.rel_pos}")
        elif score_delta != 0:
            print(f"   score mudou: {prev_score} -> {self.score} (delta={score_delta:+d}) pos={self.rel_pos}")

        if prev_state_status != self.state_status:
            print(f"== ESTADO DO SERVIDOR MUDOU: {prev_state_status} -> {self.state_status} "
                  f"(ultima pos={self.rel_pos}, score={self.score}, energy={self.energy})")

    # ----------------------------------------------------- posicionamento

    def GetPlayerPosition(self) -> Position:
        return Position(self.player.x, self.player.y)

    def NextPosition(self) -> Coord:
        return self.world.next_position(self.rel_pos, self.dir)

    # -------------------------------------------------------- observacoes

    def GetObservationsClean(self):
        self._pending_obs = []
        self._enemy_distance = None
        self._steps_heard = False
        self._refresh_item_memory(None)

    def GetObservations(self, o: List[str]):
        self._pending_obs = list(o)

        item_seen: Optional[str] = None
        for s in o:
            if s.startswith("enemy#"):
                try:
                    self._enemy_distance = int(s.replace("enemy#", ""))
                except ValueError:
                    pass
            elif s == "steps":
                self._steps_heard = True
            elif s == "blocked":
                # a celula A FRENTE (na direcao atual) esta bloqueada
                self.world.mark_wall(self.NextPosition())
            elif s in ("blueLight", "redLight", "weakLight"):
                item_seen = s

        self.world.apply_observations(self.rel_pos, o)
        self._refresh_item_memory(item_seen)

    def _refresh_item_memory(self, item_seen: Optional[str]):
        """Atualiza o conhecimento de item na posicao ATUAL a cada ciclo.
        Isso resolve o respawn: se a celula que julgavamos ter item nao
        acusa mais luz nenhuma (fomos nos que pegamos, ou outro jogador
        pegou), esquecemos - e o cooldown evita ficar voltando la toa antes
        do respawn provavel."""
        pos = self.rel_pos
        if item_seen is not None:
            self._known_items[pos] = item_seen
            self._item_cooldown.pop(pos, None)
        elif pos in self._known_items:
            del self._known_items[pos]
            self._item_cooldown[pos] = time.time()

        # limpa cooldowns expirados (item provavelmente respawnou; se ainda
        # nao respawnou, a proxima visita/observacao vai constatar e nao ha
        # problema em tentar de novo)
        now = time.time()
        expired = [p for p, t in self._item_cooldown.items() if now - t >= ITEM_RESPAWN_COOLDOWN_SEC]
        for p in expired:
            del self._item_cooldown[p]

    # ------------------------------------------------------------ estado

    def _choose_state(self) -> State:
        # TODO: regras de transicao mais refinadas (histerese, prioridade por
        # energia critica, etc.) Por ora, prioridade simples:
        if self._enemy_distance is not None:
            if self.energy <= ENERGY_FLEE_THRESHOLD:
                return State.ESCAPE_DANGER
            return State.HUNT_ENEMY
        if self._steps_heard:
            return State.SCAN_ENEMY
        if self.energy <= 30 and self._known_powerup_available():
            return State.RETREAT
        if self._known_items:
            return State.SEEK_ITEM
        return State.EXPLORE

    def _known_powerup_available(self) -> bool:
        # TODO: distinguir powerups (redLight) de tesouros (blueLight) na
        # lista de itens conhecidos, e checar se ainda nao foram coletados.
        return False

    # --------------------------------------------------------- decisao

    def GetDecision(self) -> str:
        self.state = self._choose_state()

        if self.state == State.HUNT_ENEMY:
            decision = self._decide_hunt_enemy()
        elif self.state == State.SCAN_ENEMY:
            decision = self._decide_scan_enemy()
        elif self.state == State.ESCAPE_DANGER:
            decision = self._decide_escape()
        elif self.state == State.SEEK_ITEM:
            decision = self._decide_seek_item()
        elif self.state == State.RETREAT:
            decision = self._decide_retreat()
        else:
            decision = self._decide_explore()

        self._log(decision)
        return decision

    # ---- handlers por estado (esqueleto - logica principal a implementar)

    def _decide_hunt_enemy(self) -> str:
        # O sensor "enemy#N" so aparece quando ja estamos alinhados com o
        # inimigo na direcao em que olhamos (mira), entao a decisao certa
        # e sempre atirar - nao ha necessidade de "mirar" antes.
        self._scan_attempts = 0
        return "atacar"

    def _decide_scan_enemy(self) -> str:
        # Passos ouvidos (inimigo a ate 2 de distancia manhattan) mas sem
        # alinhamento (sensor da mira nao disparou). Nao sabemos a direcao
        # exata, entao giramos tentando achar o alinhamento. Apos um numero
        # limite de tentativas sem sucesso, desiste e deixa o estado normal
        # (explorar/seek) reposicionar o agente, evitando girar pra sempre
        # caso o inimigo esteja atras de uma esquina que nunca alinha.
        if self._scan_attempts >= MAX_SCAN_ATTEMPTS:
            self._scan_attempts = 0
            return self._decide_explore()

        self._scan_attempts += 1
        return "virar_direita"

    def _decide_escape(self) -> str:
        # Energia critica com inimigo alinhado: recuar em vez de trocar tiro.
        # 'andar_re' desengaja sem precisar virar (o que exporia as costas
        # ao virar 180 na frente do inimigo).
        return "andar_re"

    def _decide_seek_item(self) -> str:
        # Se ja estamos em cima de um item, pegar.
        if self.rel_pos in self._known_items and self._on_item_now():
            return "pegar_ouro"

        target = self._pick_item_target()
        if target is None:
            return self._decide_explore()

        # replaneja se o caminho guardado nao serve mais (posicao mudou
        # inesperadamente, ou o alvo mudou porque um item melhor apareceu)
        if self._planned_path and (
            self._planned_path[0] != self.rel_pos or self._planned_path[-1] != target
        ):
            self._planned_path = []

        if not self._planned_path or len(self._planned_path) < 2:
            path = self.world.bfs_path(self.rel_pos, target, safe_only=True)
            self._planned_path = path if path else []

        if len(self._planned_path) >= 2:
            next_cell = self._planned_path[1]
            decision = self.world.direction_to_step(self.dir, self.rel_pos, next_cell)
            if decision == "andar":
                self._planned_path = self._planned_path[1:]
            return decision

        # item conhecido mas sem caminho seguro ate ele (ilha isolada por
        # perigo) -> nao vale arriscar so por um item, volta a explorar
        return self._decide_explore()

    def _pick_item_target(self) -> Optional[Coord]:
        """Escolhe o item conhecido mais prioritario: tesouro (blueLight) >
        powerup (redLight) > incerto (weakLight); empate por distancia."""
        if not self._known_items:
            return None

        priority = {"blueLight": 0, "redLight": 1, "weakLight": 2}

        def sort_key(item):
            pos, kind = item
            dist = abs(pos[0] - self.rel_pos[0]) + abs(pos[1] - self.rel_pos[1])
            return (priority.get(kind, 3), dist)

        best = min(self._known_items.items(), key=sort_key)
        return best[0]

    def _decide_retreat(self) -> str:
        # TODO: navegar ate o powerup conhecido mais proximo.
        return self._decide_explore()

    def _decide_explore(self) -> str:
        # 'blocked' no ciclo anterior invalida qualquer plano em andamento
        if "blocked" in self._pending_obs:
            self._planned_path = []

        # o caminho planejado deve sempre comecar na posicao atual;
        # se nao bate (ex: fomos teletransportados), descarta e replaneja
        if self._planned_path and self._planned_path[0] != self.rel_pos:
            self._planned_path = []

        if not self._planned_path or len(self._planned_path) < 2:
            path = self.world.nearest_frontier_path(self.rel_pos)
            if path is None:
                # sem fronteira segura alcancavel -> arrisca a celula de
                # menor risco acumulado conhecida
                path = self.world.nearest_risky_frontier_path(self.rel_pos)
            self._planned_path = path if path else []

        if len(self._planned_path) >= 2:
            next_cell = self._planned_path[1]
            decision = self.world.direction_to_step(self.dir, self.rel_pos, next_cell)
            if decision == "andar":
                # consome o passo do plano (a posicao sera confirmada em
                # _apply_local_effect / proximo SetStatus)
                self._planned_path = self._planned_path[1:]
            return decision

        # nao ha absolutamente nenhum lugar para ir (mapa fechado e todo
        # conhecido) -> gira procurando novidade
        return "virar_direita"

    # ------------------------------------------------------------- utils

    def _on_item_now(self) -> bool:
        return any(s in ("blueLight", "redLight", "weakLight") for s in self._pending_obs)

    def _log(self, decision: str):
        msg = f"[{self.state.value}] pos={self.rel_pos} dir={self.dir} energy={self.energy} score={self.score} -> {decision}"
        self.action_log.append(msg)
        print(msg)
