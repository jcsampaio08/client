# INF1771 - Desafio dos Drones

## Nomes/Matrícula

 - José Carlos - 2320465
 - Everton Pereira - 2320462

A politica principal fica em `src/GameAI.py`, a memória do mapa fica em `src/KnowledgeBase.py` e o algoritmo A* fica em `src/PathPlanner.py`.

## Técnica utilizada

A decisão combina uma base de conhecimento em memória, regras de prioridade e busca A* em mapa parcialmente conhecido.

A cada ciclo o drone atualiza o que sabe sobre as células observadas e escolhe uma ação nesta ordem:

1. Atacar inimigo visível na mira quando a energia permite.
2. Fazer tiros de continuação quando um disparo acabou de acertar.
3. Fugir usando marcha ré ou giro seguro quando ha ameaça perto e energia baixa.
4. Coletar item quando uma luz indica item na celula atual.
5. Ir ate powerups/tesouros ja vistos quando existe caminho seguro conhecido.
6. Explorar em linha reta ou com A* até a fronteira segura mais proxima.
7. Girar ao ouvir passos somente quando não ha caminho de exploração.
8. Girar para observar quando não ha caminho seguro conhecido.

O drone só usa posição, direção, energia e sensores recebidos do servidor.

## Base de conhecimento

A base de conhecimento é reiniciada quando uma nova partida começa e não e persistida em disco.

Ela foi separada em `src/KnowledgeBase.py` para manter o modelo de memória isolado da politica de decisão do drone.

O planejamento de caminhos foi separado em `src/PathPlanner.py`. Ele recebe a base de conhecimento, posição, direção e histórico recente para calcular caminhos até itens conhecidos ou fronteiras de exploração.

Para cada coordenada conhecida, o drone pode guardar:

- estado da célula: desconhecida, segura, visitada, bloqueada, risco de morte ou risco de teleporte;
- número de visitas;
- evidências positivas e negativas de `breeze` e `flash`;
- item visto por `blueLight`, `redLight`, `weakLight` ou `greenLight`;
- inimigo estimado por `enemy#N`;
- evidência de inimigo próximo por `steps`.

Sensores tratados:

- `blocked`: marca a célula da frente como parede/obstáculo;
- `breeze`: marca vizinhos ortogonais ainda inseguros como possível poço;
- ausência de `breeze`: remove suspeita de poço dos vizinhos da posição atual;
- `flash`: marca vizinhos ortogonais ainda inseguros como possível teleporte;
- ausência de `flash`: remove suspeita de teleporte dos vizinhos da posição atual;
- `blueLight`, `redLight`, `weakLight`/`weaklight`: registra item na célula atual;
- `greenLight`: registra veneno na célula atual e evita coletar;
- `steps`: registra evidência de inimigo nas coordenadas a até 2 passos Manhattan;
- `enemy#N`: registra inimigo na direção atual a distância `N`;
- `damage` e `hit`: atualizam contadores e memória curta de combate.

## Ações usadas

- `andar`: move para frente quando a célula da frente e aceitável.
- `andar_re`: move para trás para fugir ou seguir um alvo seguro atrás do drone.
- `virar_direita` e `virar_esquerda`: alinham a direção com o proximo passo ou procuram inimigo quando ha passos.
- `atacar`: dispara quando o sensor de mira indica inimigo em ate 10 passos.
- `pegar_ouro`, `pegar_anel`, `pegar_powerup`: todos chamam o comando de pegar item do servidor.

Quando o status indica um salto grande de posição durante a partida, o drone assume teletransporte e limpa o plano atual para voltar a explorar a partir da nova coordenada.

O loop do devkit permanece em `0.1s`, mas a espera interna por observação nova foi reduzida para evitar que o drone fique parado por muitos ciclos quando a rede atrasa.

## Decisão e logs

Cada ação emitida imprime um log no terminal com tempo interno, ação, motivo, posição, direção, observações, alvo, energia e pontuação. Exemplo:

```text
[t=42] atacar: inimigo visivel a 3 passo(s), energia=76 | pos=(10, 8) dir=east obs=['enemy#3'] target=None energy=76 score=120
```

## Limitações conhecidas

- O drone ainda é conservador: evita células com evidência ativa de poço ou teleporte, entao pode ficar sem deslocamento bom se todos os caminhos conhecidos parecerem perigosos.
- `steps` não informa direção; por isso ele é usado como alerta de perigo, não como alvo preciso.
- A busca A* só planeja sobre células visitadas/seguras e fronteiras desconhecidas adjacentes a regiões seguras.
- A decisão de combate ainda não estima parede entre o drone e o inimigo; ela confia no sensor de mira do servidor.


## Como rodar

Executar `src/Program.py` com Python 3.11.9.
O servidor padrão já está configurado em `src/Bot.py`.
