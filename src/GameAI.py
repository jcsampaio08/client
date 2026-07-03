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

import random
from Map.Position import Position
from enum import Enum
from typing import List, Dict

# <summary>
# Game AI Example
# </summary>
class GameAI():

    player = Position()
    state = "ready"
    dir = "north"
    score = 0
    energy = 0

    # <summary>
    # Refresh player status
    # </summary>
    # <param name="x">player position x</param>
    # <param name="y">player position y</param>
    # <param name="dir">player direction</param>
    # <param name="state">player state</param>
    # <param name="score">player score</param>
    # <param name="energy">player energy</param>
    def SetStatus(self, x: int, y: int, dir: str, state: str, score: int, energy: int):
        
        self.SetPlayerPosition(x, y)
        self.dir = dir.lower()

        self.state = state
        self.score = score
        self.energy = energy


    # <summary>
    # Get list of observable adjacent positions
    # </summary>
    # <returns>List of observable adjacent positions</returns>
    def GetCurrentObservableAdjacentPositions(self) -> List[Position]:
        return self.GetObservableAdjacentPositions(self.player)
        
    def GetObservableAdjacentPositions(self, pos):
        ret = []

        ret.append(Position(pos.x - 1, pos.y))
        ret.append(Position(pos.x + 1, pos.y))
        ret.append(Position(pos.x, pos.y - 1))
        ret.append(Position(pos.x, pos.y + 1))

        return ret


    # <summary>
    # Get list of all adjacent positions (including diagonal)
    # </summary>
    # <returns>List of all adjacent positions (including diagonal)</returns>
    def GetAllAdjacentPositions(self):
    
        ret = []

        ret.append(Position(self.player.x - 1, self.player.y - 1))
        ret.append(Position(self.player.x, self.player.y - 1))
        ret.append(Position(self.player.x + 1, self.player.y - 1))

        ret.append(Position(self.player.x - 1, self.player.y))
        ret.append(Position(self.player.x + 1, self.player.y))

        ret.append(Position(self.player.x - 1, self.player.y + 1))
        ret.append(Position(self.player.x, self.player.y + 1))
        ret.append(Position(self.player.x + 1, self.player.y + 1))

        return ret

    def NextPositionAhead(self, steps):
        ret = None
        if self.dir == "north":
            ret = Position(self.player.x, self.player.y - steps)
        elif self.dir == "east":
            ret = Position(self.player.x + steps, self.player.y)
        elif self.dir == "south":
            ret = Position(self.player.x, self.player.y + steps)
        elif self.dir == "west":
            ret = Position(self.player.x - steps, self.player.y)
        return ret

    # <summary>
    # Get next forward position
    # </summary>
    # <returns>next forward position</returns>
    def NextPosition(self) -> Position:
        return self.NextPositionAhead(1)
        
    def NextPosition(self):
    
        ret = None
        
        if self.dir == "north":
            ret = Position(self.player.x, self.player.y - 1)
                
        elif self.dir == "east":
                ret = Position(self.player.x + 1, self.player.y)
                
        elif self.dir == "south":
                ret = Position(self.player.x, self.player.y + 1)
                
        elif self.dir == "west":
                ret = Position(self.player.x - 1, self.player.y)

        return ret
    

    # <summary>
    # Player position
    # </summary>
    # <returns>player position</returns>
    def GetPlayerPosition(self):
        return Position(self.player.x, self.player.y)


    # <summary>
    # Set player position
    # </summary>
    # <param name="x">x position</param>
    # <param name="y">y position</param>
    def SetPlayerPosition(self, x: int, y: int):
        self.player.x = x
        self.player.y = y
    

    # <summary>
    # Observations received
    # </summary>
    # <param name="o">list of observations</param>
    def GetObservations(self, o):
    
        # IMPLEMENTAR
        # como sua solucao vai tratar as observacoes?
        # como seu bot vai memorizar os lugares por onde passou?
        # aqui, recebe-se as observacoes dos sensores para as
        # coordenadas atuais do player
        for s in o:
        
            if s == "blocked":
                pass
            
            elif s == "steps":
                pass
            
            elif s == "breeze":
                pass

            elif s == "flash":
                pass

            elif s == "blueLight":
                pass

            elif s == "redLight":
                pass

            elif s == "greenLight":
                pass

            elif s == "weakLight":
                pass

            elif s == "damage":
                pass

            elif s == "hit":
                pass
            
            elif s.startswith("enemy#"):
                try:
                    steps = int(s.replace("enemy#", ""))
                except:
                    pass


    # <summary>
    # No observations received
    # </summary>
    def GetObservationsClean(self):
    
        # IMPLEMENTAR
        # como "apagar/esquecer" as observacoes?
        # devemos apagar as atuais para poder receber novas
        # se nao apagarmos, as novas se misturam com as anteriores
        pass
    

    # <summary>
    # Get Decision
    # </summary>
    # <returns>command string to new decision</returns>
    def GetDecision(self) -> str:

        # IMPLEMENTAR
        # Qual a decisão do seu bot?

        # A cada ciclo, o bot segue os passos:
        # 1- Solicita observações
        # 2- Ao receber observações:
        # 2.1 - chama "GetObservationsClean()" para apagar as anteriores
        # 2.2 - chama "GetObservations(_)" passando as novas observacoes
        # 3- chama "GetDecision()" para perguntar o que deve fazer agora
        # 4- envia decisão ao servidor
        # 5- após ação enviada, reinicia voltando ao passo 1
        
        # Exemplo de decisão aleatória:
        n = random.randint(0,7)

        if n == 0:
            return "virar_direita"
        elif n == 1:
            return "virar_esquerda"
        elif n == 2:
            return "andar"
        elif n == 3:
            return "atacar"
        elif n == 4:
            return "pegar_ouro"
        elif n == 5:
            return "pegar_anel"
        elif n == 6:
            return "pegar_powerup"
        elif n == 7:
            return "andar_re"

        return ""

