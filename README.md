# T3_IA - Bot Inteligente para Jogo de Combate

- **João Ricardo Malta**
- **João Pedro Biscaia**


## Logica 

O bot é composto por dois módulos principais:

1. **`Bot.py`**: Gerencia a comunicação com o servidor do jogo via TCP/IP, processa comandos recebidos e envia decisões.
2. **`GameAI.py`**: Contém toda a inteligência artificial do bot, incluindo tomada de decisões, mapeamento do ambiente e estratégias de combate.

### Fluxo de Execução

```
Servidor do Jogo
      ↓
   Bot.py (Comunicação)
      ↓
   GameAI.py (Decisão)
      ↓
   Ação Executada
```

---

## Algoritmos Implementados

### 1. **Máquina de Estados Finitos (FSM)**

O bot utiliza uma FSM implícita para gerenciar diferentes estados comportamentais:

- **EXPLORING**: Exploração do mapa em busca de recursos
- **COLLECTING_GOLD**: Coleta de ouro quando detectado
- **REFUELING**: Busca por powerups quando energia está baixa
- **COMBAT**: Engajamento com inimigos
- **RETREATING**: Recuo tático quando em desvantagem

### 2. **Busca A* (A-Star)**

Implementado no método `GetNextStepTowards()`, o algoritmo A* é utilizado para:
- Calcular o caminho mais curto até objetivos (ouro, powerups, fronteiras)
- Utiliza distância de Manhattan como heurística
- Considera apenas células visitadas e seguras no pathfinding

```python
def heuristic(pos):
    return abs(pos[0] - target[0]) + abs(pos[1] - target[1])
```

### 3. **Busca em Largura (BFS)**

Implementado no método `FindNearestFrontier()`, o BFS é usado para:
- Encontrar a célula inexplorada mais próxima
- Expandir a exploração do mapa de forma sistemática
- Priorizar áreas seguras e adjacentes

### 4. **Sistema de Mapeamento Inteligente**

O bot mantém um mapa mental do ambiente com:
- **Células visitadas**: Rastreamento de posições já exploradas
- **Células seguras**: Áreas confirmadas como livres de perigos
- **Hazards**: Paredes, buracos e teleportes identificados
- **Recursos**: Localização de ouro (`blueLight`) e powerups (`redLight`)

### 5. **Sistema de Rastreamento de Inimigos**

Implementa predição de movimento inimigo:
- **Tracking de posição**: Armazena últimas posições conhecidas de inimigos
- **Cálculo de velocidade**: Determina direção e velocidade do movimento inimigo
- **Predição de interceptação**: Decide quando atirar baseado no movimento lateral do inimigo

```python
def PredictEnemyInterception(self, enemy_dist):
    # Analisa movimento lateral do inimigo
    # Decide se deve atirar ou reposicionar
```

### 6. **Sistema de Prioridades Dinâmicas**

O bot toma decisões baseado em uma hierarquia de prioridades:

1. **CRÍTICO**: Energia < 20 → Busca emergencial por powerup
2. **ALTA**: Energia < 100 → Busca proativa por powerup
3. **MÉDIA**: Ouro detectado → Coleta imediata
4. **COMBATE**: Inimigo visível → Engajamento ou recuo tático
5. **EXPLORAÇÃO**: Busca por fronteiras inexploradas

### 7. **Sistema de Estratégia Adaptativa**

Implementado no método `GetStrategicMode()`, o bot adapta sua estratégia baseado em:

- **DEFENSIVE**: Quando está em 1º lugar e faltam < 2 minutos
  - Evita combate desnecessário
  - Foca em preservar vantagem
  
- **AGGRESSIVE**: Quando está nos últimos 30% do ranking
  - Busca combate ativamente
  - Toma mais riscos para recuperar pontos
  
- **BALANCED**: Situações normais
  - Equilíbrio entre exploração, coleta e combate

### 8. **Anti-Stuck System**

Sistema de detecção e correção de loops:
- Detecta padrões de movimento repetitivo
- Identifica quando o bot está preso em linha reta
- Força mudanças de direção para escapar de situações de deadlock

```python
if all_same_x or all_same_y:
    print("ANTI-STUCK: Detected straight-line pattern! Forcing turn.")
    return "virar_direita"
```

### 9. **Line of Sight (LOS) Check**

Verifica se há linha de visão clara para atirar:
- Analisa células à frente até a distância do inimigo
- Detecta obstáculos (paredes) que bloqueiam o tiro
- Decide entre atirar, mover-se ou fazer strafe

### 10. **Sistema de Strafe Tático**

Quando o inimigo está visível mas sem linha de tiro clara:
1. Vira para o lado (strafe_turning)
2. Move-se lateralmente (strafe_moving)
3. Vira de volta para reacquirir o alvo


## Estrutura usadas

```python
# Mapeamento do ambiente
map_state: Dict[Tuple[int, int], str]  # Estado de cada célula
visited: Set[Tuple[int, int]]          # Células visitadas
safe_cells: Set[Tuple[int, int]]       # Células seguras
hazards: Set[Tuple[int, int]]          # Perigos conhecidos

# Rastreamento de recursos
gold_locations: Set[Tuple[int, int]]     # Localizações de ouro
powerup_locations: Set[Tuple[int, int]]  # Localizações de powerups

# Tracking de inimigos
enemy_last_positions: Dict[str, Tuple[int, int, int]]  # ID -> (x, y, time)
enemy_velocity: Dict[str, Tuple[float, float]]         # ID -> (dx, dy)

# Estado estratégico
my_rank: int              # Posição no ranking
my_score: int             # Pontuação atual
enemy_scores: Dict        # Pontuações dos adversários
game_time: int            # Tempo de jogo em segundos
```

