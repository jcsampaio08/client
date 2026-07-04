# INF1771 - Desafio dos Drones

## Nomes/Matrícula

 - José Carlos - 2320465
 - Everton Pereira - 2320462

Bot autonomo para o desafio de Inteligencia Artificial da INF1771. O codigo de rede do devkit foi mantido; a politica principal fica em `src/GameAI.py`, a memoria do mapa fica em `src/KnowledgeBase.py` e o planejamento A* fica em `src/PathPlanner.py`.

## Tecnica usada

A decisao combina uma base de conhecimento em memoria, regras de prioridade e busca A* em mapa parcialmente conhecido.

A cada ciclo o bot atualiza o que sabe sobre as celulas observadas e escolhe uma acao nesta ordem:

1. Atacar inimigo visivel na mira quando a energia permite.
2. Fazer tiros de continuacao quando um disparo acabou de acertar.
3. Fugir usando marcha re ou giro seguro quando ha ameaca perto e energia baixa.
4. Coletar item quando uma luz indica item na celula atual.
5. Ir ate powerups/tesouros ja vistos quando existe caminho seguro conhecido.
6. Explorar em linha reta ou com A* ate a fronteira segura mais proxima.
7. Girar ao ouvir passos somente quando nao ha caminho de exploracao.
8. Girar para observar quando nao ha caminho seguro conhecido.

Essa abordagem evita depender do mapa completo. O agente so usa posicao, direcao, energia e sensores recebidos do servidor.

## Base de conhecimento

A base de conhecimento e reiniciada quando uma nova partida comeca e nao e persistida em disco.

Ela foi separada em `src/KnowledgeBase.py` para manter o modelo de memoria isolado da politica de decisao do drone.

O planejamento de caminhos foi separado em `src/PathPlanner.py`. Ele recebe a base de conhecimento, posicao, direcao e historico recente para calcular caminhos ate itens conhecidos ou fronteiras de exploracao.

Para cada coordenada conhecida, o bot pode guardar:

- estado da celula: desconhecida, segura, visitada, bloqueada, risco de morte ou risco de teleporte;
- numero de visitas;
- evidencias positivas e negativas de `breeze` e `flash`;
- item visto por `blueLight`, `redLight`, `weakLight` ou `greenLight`;
- inimigo estimado por `enemy#N`;
- evidencia de inimigo proximo por `steps`.

Sensores tratados:

- `blocked`: marca a celula da frente como parede/obstaculo;
- `breeze`: marca vizinhos ortogonais ainda inseguros como possivel poco;
- ausencia de `breeze`: remove suspeita de poco dos vizinhos da posicao atual;
- `flash`: marca vizinhos ortogonais ainda inseguros como possivel teleporte;
- ausencia de `flash`: remove suspeita de teleporte dos vizinhos da posicao atual;
- `blueLight`, `redLight`, `weakLight`/`weaklight`: registra item na celula atual;
- `greenLight`: registra veneno na celula atual e evita coletar;
- `steps`: registra evidencia de inimigo nas coordenadas a ate 2 passos Manhattan;
- `enemy#N`: registra inimigo na direcao atual a distancia `N`;
- `damage` e `hit`: atualizam contadores e memoria curta de combate.

## Acoes usadas

- `andar`: move para frente quando a celula da frente e aceitavel.
- `andar_re`: move para tras para fugir ou seguir um alvo seguro atras do drone.
- `virar_direita` e `virar_esquerda`: alinham a direcao com o proximo passo ou procuram inimigo quando ha passos.
- `atacar`: dispara quando o sensor de mira indica inimigo em ate 10 passos.
- `pegar_ouro`, `pegar_anel`, `pegar_powerup`: todos chamam o comando de pegar item do servidor.

Quando o status indica um salto grande de posicao durante a partida, o bot assume teletransporte e limpa o plano atual para voltar a explorar a partir da nova coordenada.

O loop do devkit permanece em `0.1s`, mas a espera interna por observacao nova foi reduzida para evitar que o bot fique parado por muitos ciclos quando a rede atrasa.

## Decisao e logs

Cada acao emitida imprime um log no terminal com tempo interno, acao, motivo, posicao, direcao, observacoes, alvo, energia e pontuacao. Exemplo:

```text
[t=42] atacar: inimigo visivel a 3 passo(s), energia=76 | pos=(10, 8) dir=east obs=['enemy#3'] target=None energy=76 score=120
```

## Limitacoes conhecidas

- O bot ainda e conservador: evita celulas com evidencia ativa de poco ou teleporte, entao pode ficar sem deslocamento bom se todos os caminhos conhecidos parecerem perigosos.
- `steps` nao informa direcao; por isso ele e usado como alerta de perigo, nao como alvo preciso.
- A busca A* so planeja sobre celulas visitadas/seguras e fronteiras desconhecidas adjacentes a regioes seguras.
- A decisao de combate ainda nao estima parede entre o drone e o inimigo; ela confia no sensor de mira do servidor.


## Como rodar

Executar `src/Program.py` com Python 3.11.9.
O servidor padrão já está configurado em `src/Bot.py`.
