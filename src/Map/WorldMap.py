#!/usr/bin/env python
"""WorldMap.py: Internal map knowledge, safety inference and pathfinding.

O agente NAO recebe o mapa do servidor. Este modulo constroi, incrementalmente,
o conhecimento do labirinto a partir das observacoes recebidas em cada posicao
visitada, e oferece:
  - Inferencia de seguranca (estilo Wumpus World): breeze -> poço provavel nas
    adjacentes; flash -> teletransporte provavel nas adjacentes.
  - BFS para planejar caminho ate uma celula alvo evitando celulas perigosas.
  - Frontier: lista de celulas conhecidas, seguras e ainda nao visitadas, para
    orientar a exploracao.

Coordenadas sao relativas: (0,0) = posicao inicial do agente. Isso funciona
porque so precisamos de posicoes RELATIVAS entre si para navegar; a posicao
absoluta enviada pelo servidor (SetStatus) pode ser usada so como referencia,
nao e obrigatorio remapear para o grid 59x34 absoluto.
"""

from collections import deque
from typing import Optional, Tuple, List, Set, Dict

Coord = Tuple[int, int]

DIRS = ["north", "east", "south", "west"]
DELTA = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
}


class Cell:
    """Conhecimento acumulado sobre uma unica celula do labirinto."""

    def __init__(self):
        self.visited: bool = False
        self.wall: bool = False          # confirmado bloqueado (colisao / "blocked")
        self.breeze: bool = False        # sentiu brisa NESTA celula (poço adjacente)
        self.flash: bool = False         # sentiu flash NESTA celula (teleporte adjacente)
        self.steps: bool = False         # ouviu passos NESTA celula (inimigo adjacente)
        self.item: Optional[str] = None  # "blueLight" | "redLight" | "weakLight" | None
        self.item_taken: bool = False

        # Inferencia (atualizada via WorldMap, nao setada diretamente)
        self.pit_suspect: bool = False
        self.teleport_suspect: bool = False
        self.proven_safe: bool = False   # confirmado seguro (visitado e sobreviveu)


class WorldMap:

    def __init__(self):
        self.cells: Dict[Coord, Cell] = {}
        self.origin_dir_offset = 0  # nao usado por ora; direcao vem do servidor

    # ---------------------------------------------------------------- utils

    def get_cell(self, pos: Coord) -> Cell:
        if pos not in self.cells:
            self.cells[pos] = Cell()
        return self.cells[pos]

    def neighbors(self, pos: Coord) -> List[Coord]:
        x, y = pos
        return [(x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)]

    def next_position(self, pos: Coord, direction: str) -> Coord:
        dx, dy = DELTA[direction]
        return (pos[0] + dx, pos[1] + dy)

    # ------------------------------------------------------- update / sense

    def mark_visited(self, pos: Coord):
        c = self.get_cell(pos)
        c.visited = True
        c.proven_safe = True  # se chegamos aqui vivos, e seguro
        c.pit_suspect = False
        c.teleport_suspect = False

    def mark_wall(self, pos: Coord):
        self.get_cell(pos).wall = True

    def apply_observations(self, pos: Coord, observations: List[str]):
        """Aplica a lista de observacoes recebidas para a posicao atual."""
        c = self.get_cell(pos)

        for obs in observations:
            if obs == "blocked":
                # tratado separadamente por quem chamou (sabe a celula de destino)
                pass
            elif obs == "breeze":
                c.breeze = True
            elif obs == "flash":
                c.flash = True
            elif obs == "steps":
                c.steps = True
            elif obs in ("blueLight", "redLight", "weakLight", "greenLight"):
                c.item = obs
            elif obs == "damage":
                pass
            elif obs == "hit":
                pass
            elif obs.startswith("enemy#"):
                pass  # tratado por quem chamou (precisa da distancia)

        self._update_danger_inference(pos)

    def _update_danger_inference(self, pos: Coord):
        """Propaga breeze/flash desta celula para as adjacentes ainda nao provadas seguras."""
        c = self.get_cell(pos)
        for n in self.neighbors(pos):
            nc = self.get_cell(n)
            if nc.proven_safe or nc.wall:
                continue
            if c.breeze:
                nc.pit_suspect = True
            if c.flash:
                nc.teleport_suspect = True

    def is_safe_to_enter(self, pos: Coord) -> bool:
        c = self.cells.get(pos)
        if c is None:
            return True  # desconhecido: assumido "arriscado mas exploravel", filtrar fora do BFS de seguranca
        if c.wall:
            return False
        if c.proven_safe:
            return True
        return not (c.pit_suspect or c.teleport_suspect)

    def cell_risk(self, pos: Coord) -> int:
        """Custo de risco de ENTRAR nesta celula: 0 (segura/desconhecida),
        1 (suspeita de poço OU teleporte), 2 (suspeita de ambos)."""
        c = self.cells.get(pos)
        if c is None or c.proven_safe:
            return 0
        return int(c.pit_suspect) + int(c.teleport_suspect)

    # ------------------------------------------------------------ frontier

    def frontier(self, from_pos: Coord) -> List[Coord]:
        """Celulas conhecidas (adjacentes a visitadas), seguras, ainda nao visitadas."""
        result: Set[Coord] = set()
        for pos, cell in self.cells.items():
            if not cell.visited:
                continue
            for n in self.neighbors(pos):
                nc = self.cells.get(n)
                if nc is None:
                    # desconhecida mas adjacente a uma segura -> candidata a exploracao
                    result.add(n)
                elif not nc.visited and not nc.wall and self.is_safe_to_enter(n):
                    result.add(n)
        result.discard(from_pos)
        return list(result)

    # -------------------------------------------------------------- search

    def bfs_path(self, start: Coord, goal: Coord, safe_only: bool = True) -> Optional[List[Coord]]:
        """BFS simples. Retorna lista de coordenadas do caminho (incl. goal), ou None."""
        if start == goal:
            return [start]

        visited = {start}
        queue = deque([start])
        parent: Dict[Coord, Coord] = {}

        while queue:
            cur = queue.popleft()
            for n in self.neighbors(cur):
                if n in visited:
                    continue
                cell = self.cells.get(n)
                if cell is not None and cell.wall:
                    continue
                if safe_only and cell is not None and not self.is_safe_to_enter(n):
                    continue
                visited.add(n)
                parent[n] = cur
                if n == goal:
                    # reconstruct
                    path = [n]
                    while path[-1] != start:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(n)

        return None

    def nearest_frontier_path(self, start: Coord) -> Optional[List[Coord]]:
        """Caminho ate a celula de fronteira segura mais proxima (BFS multi-alvo).
        So considera celulas seguras/desconhecidas ao longo do caminho."""
        frontier_set = set(self.frontier(start))
        if not frontier_set:
            return None

        visited = {start}
        queue = deque([start])
        parent: Dict[Coord, Coord] = {}

        while queue:
            cur = queue.popleft()
            if cur in frontier_set:
                path = [cur]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path

            for n in self.neighbors(cur):
                if n in visited:
                    continue
                cell = self.cells.get(n)
                if cell is not None and cell.wall:
                    continue
                if not self.is_safe_to_enter(n):
                    continue
                visited.add(n)
                parent[n] = cur
                queue.append(n)

        return None

    def nearest_risky_frontier_path(self, start: Coord) -> Optional[List[Coord]]:
        """Fallback: quando NAO ha fronteira 100% segura alcancavel, procura a
        celula ainda-nao-visitada mais proxima minimizando o RISCO acumulado
        no caminho (Dijkstra: custo = soma de cell_risk das celulas visitadas
        ao longo do trajeto, desempate por numero de passos).

        So considera parede como intransponivel; tudo o mais e permitido,
        pesado pelo risco. Isso implementa a politica: "quando o mapa
        conhecido acaba, arrisca a celula suspeita de menor risco"."""
        import heapq

        # alvo: qualquer celula nao-parede que ainda nao foi visitada
        counter = 0
        heap = [(0, 0, counter, start)]  # (risco_acumulado, passos, tiebreak, pos)
        best_cost: Dict[Coord, Tuple[int, int]] = {start: (0, 0)}
        parent: Dict[Coord, Coord] = {}

        while heap:
            risk, steps, _, cur = heapq.heappop(heap)

            cur_cell = self.cells.get(cur)
            if cur != start and (cur_cell is None or not cur_cell.visited):
                # achou uma celula nao explorada -> reconstroi caminho
                path = [cur]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path

            for n in self.neighbors(cur):
                ncell = self.cells.get(n)
                if ncell is not None and ncell.wall:
                    continue
                n_risk = risk + self.cell_risk(n)
                n_steps = steps + 1
                if n in best_cost and best_cost[n] <= (n_risk, n_steps):
                    continue
                best_cost[n] = (n_risk, n_steps)
                parent[n] = cur
                counter += 1
                heapq.heappush(heap, (n_risk, n_steps, counter, n))

        return None

    # --------------------------------------------------------- direction helpers

    def direction_to_step(self, cur_dir: str, cur_pos: Coord, target_pos: Coord) -> str:
        """Dado a posicao atual/direcao e o proximo passo do caminho, decide a
        acao unica a enviar: 'virar_direita' | 'virar_esquerda' | 'andar'."""
        dx = target_pos[0] - cur_pos[0]
        dy = target_pos[1] - cur_pos[1]

        wanted_dir = None
        for d, (ddx, ddy) in DELTA.items():
            if (ddx, ddy) == (dx, dy):
                wanted_dir = d
                break

        if wanted_dir is None or wanted_dir == cur_dir:
            return "andar"

        cur_idx = DIRS.index(cur_dir)
        want_idx = DIRS.index(wanted_dir)
        diff = (want_idx - cur_idx) % 4

        if diff == 1:
            return "virar_direita"
        elif diff == 3:
            return "virar_esquerda"
        else:
            # diff == 2 (meia-volta): vira para qualquer lado, resolve em 2 ciclos
            return "virar_direita"
