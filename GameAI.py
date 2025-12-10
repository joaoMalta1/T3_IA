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
from typing import List, Dict, Set, Tuple, Optional
from collections import deque
import heapq

# ============== FINITE STATE MACHINE ==============
class AgentState(Enum):
    EXPLORING = "exploring"
    COLLECTING_GOLD = "collecting_gold"
    REFUELING = "refueling"
    COMBAT = "combat"
    RETREATING = "retreating"


class GameAI():

    # Energy thresholds
    CRITICAL_ENERGY = 20  # Emergency - must find powerup
    LOW_ENERGY = 30        # Tactical - avoid combat, seek powerup
    
    # Scoring and strategic state
    my_name = "LEIAM WORM (WILDBOW) PLS"  # Bot name from Bot.py
    my_score = 0
    my_rank = 0
    enemy_scores = {}  # {name: score}
    total_players = 0
    game_time = 0  # seconds
    game_status = "Ready"  # Ready, Game, GameOver
    
    # Enemy tracking for prediction
    enemy_last_positions = {}  # {enemy_id: (x, y, timestamp)}
    enemy_velocity = {}        # {enemy_id: (dx, dy)}
    
    player = Position()
    state = "ready"
    dir = "north"
    score = 0
    energy = 0

    # Map State
    map_state: Dict[Tuple[int, int], str] = {}
    visited: Set[Tuple[int, int]] = set()
    safe_cells: Set[Tuple[int, int]] = set()
    hazards: Set[Tuple[int, int]] = set() # Known pits/teleports/walls
    

    breeze_sources: Set[Tuple[int, int]] = set()
    flash_sources: Set[Tuple[int, int]] = set()
    
    current_observations: List[str] = []
    

    last_action = ""
    last_pos = (0, 0)
    
    def __init__(self):
        self.map_state = {}
        self.visited = set()
        self.safe_cells = set()
        self.hazards = set()
        self.breeze_sources = set()
        self.flash_sources = set()
        self.current_observations = []
        self.under_attack = False
        self.shot_connected = False
        self.enemy_nearby = False  # True when "steps" detected
        self.last_known_enemy_pos = None
        self.combat_state = None # None, "strafe_turning", "strafe_moving", "reacquiring"
        self.strafe_dir = None   # "left" or "right" relative to enemy
        self.original_dir = None # "north", etc.
        self.gold_locations = set() # Memory for known gold
        self.powerup_locations = set() # Memory for known powerups
        # Pre-mark 0,0 (or start) as safe once we get first status? 
        # Actually SetStatus calls SetPlayerPosition.

    def SetStatus(self, x: int, y: int, dir: str, state: str, score: int, energy: int):
        
        self.SetPlayerPosition(x, y)
        self.dir = dir.lower()

        self.state = state
        self.score = score
        self.energy = energy

        self.visited.add((x, y))
        self.safe_cells.add((x, y))
        self.map_state[(x, y)] = "Safe"

    # <summary>
    # Update game state from scoreboard
    # </summary>
    def UpdateGameState(self, scoreboard_data, game_time, game_status):
        """
        Atualiza estado do jogo baseado em scoreboard
        scoreboard_data: list of ScoreBoard objects
        """
        self.game_time = game_time
        self.game_status = game_status
        
        self.enemy_scores = {}
        for entry in scoreboard_data:
            if entry.name == self.my_name:
                self.my_score = entry.score
            else:
                self.enemy_scores[entry.name] = entry.score
        
        # Calculate rank
        all_scores = [self.my_score] + list(self.enemy_scores.values())
        all_scores_sorted = sorted(all_scores, reverse=True)
        self.my_rank = all_scores_sorted.index(self.my_score) + 1 if self.my_score in all_scores_sorted else 0
        self.total_players = len(all_scores)
        
        print(f"SCOREBOARD: Rank {self.my_rank}/{self.total_players}, Score: {self.my_score}, Time: {game_time}s")
    
    # <summary>
    # Get strategic mode based on ranking and time
    # </summary>
    def GetStrategicMode(self):
        """
        Determina modo estratégico baseado em ranking e tempo
        Returns: "DEFENSIVE", "BALANCED", "AGGRESSIVE"
        """
        if self.game_status != "Game":
            return "BALANCED"
        
        if not self.enemy_scores:
            return "BALANCED"  # Sem info, joga normal
        
        time_remaining = 600 - self.game_time  # 10min = 600s
        rank_percentile = self.my_rank / self.total_players if self.total_players > 0 else 0.5
        
        # DEFENSIVE: Proteger lead quando ganhando perto do fim
        if self.my_rank == 1 and time_remaining < 120:  # 1st place, < 2min
            return "DEFENSIVE"
        
        # AGGRESSIVE: Precisa arriscar quando perdendo
        elif rank_percentile > 0.7:  # Bottom 30%
            return "AGGRESSIVE"
        
        # BALANCED: Meio da tabela ou início de jogo
        else:
            return "BALANCED"



    def GetCurrentObservableAdjacentPositions(self) -> List[Position]:
        return self.GetObservableAdjacentPositions(self.player)
        
    def GetObservableAdjacentPositions(self, pos):
        ret = []
        ret.append(Position(pos.x - 1, pos.y))
        ret.append(Position(pos.x + 1, pos.y))
        ret.append(Position(pos.x, pos.y - 1))
        ret.append(Position(pos.x, pos.y + 1))
        return ret



    def GetAllAdjacentPositions(self):
        ret = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue
                ret.append(Position(self.player.x + dx, self.player.y + dy))
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


    def NextPosition(self) -> Position:
        return self.NextPositionAhead(1)
            


    def GetPlayerPosition(self):
        return Position(self.player.x, self.player.y)



    def SetPlayerPosition(self, x: int, y: int):
        self.player.x = x
        self.player.y = y
        self.visited.add((x, y))
        self.safe_cells.add((x, y))
    


    def GetObservations(self, o):
        if "damage" in o:
            self.under_attack = True
            print("EVENT: Taken Damage!")
            return
            
        if "hit" in o:
            self.shot_connected = True
            print("EVENT: Shot Hit!")
            return

        self.current_observations = o

        curr_x, curr_y = self.player.x, self.player.y
        self.safe_cells.add((curr_x, curr_y))
        self.map_state[(curr_x, curr_y)] = "Safe"
        
        blocked = False
        
        for s in o:
            if s == "blocked":
                blocked = True
            elif s == "breeze":
                self.breeze_sources.add((curr_x, curr_y))
            elif s == "flash":
                self.flash_sources.add((curr_x, curr_y))
            elif s == "blueLight":
                self.gold_locations.add((curr_x, curr_y))
            elif s == "redLight":
                self.powerup_locations.add((curr_x, curr_y))
            elif s == "steps":
                self.enemy_nearby = True
                print("ALERT: Enemy nearby (steps detected)! Hunting mode activated.")
        
        # If we successfully picked up gold, remove it from memory
        if "blueLight" not in o and (curr_x, curr_y) in self.gold_locations:
             self.gold_locations.discard((curr_x, curr_y))

        if "redLight" not in o and (curr_x, curr_y) in self.powerup_locations:
             self.powerup_locations.discard((curr_x, curr_y))
                
        if blocked and self.last_action == "andar":
            wall_pos = self.NextPosition()
            if wall_pos:
                self.hazards.add((wall_pos.x, wall_pos.y))
                self.map_state[(wall_pos.x, wall_pos.y)] = "Wall"
                self.safe_cells.discard((wall_pos.x, wall_pos.y))



    def GetObservationsClean(self):
        self.current_observations = []
        self.enemy_nearby = False  # Reset flag
    
    # <summary>
    # Track enemy position for prediction
    # </summary>
    def UpdateEnemyTracking(self, enemy_obs):
        """
        Atualiza tracking de inimigos baseado em observação
        enemy_obs: string like "enemy#3" (distance)
        """
        try:
            parts = enemy_obs.split('#')
            if len(parts) > 1:
                distance = int(parts[1])
                
                # Inferir posição aproximada (inimigo está na nossa direção)
                enemy_x, enemy_y = self.player.x, self.player.y
                
                if self.dir == "north":
                    enemy_y -= distance
                elif self.dir == "east":
                    enemy_x += distance
                elif self.dir == "south":
                    enemy_y += distance
                elif self.dir == "west":
                    enemy_x -= distance
                
                # Salvar última posição conhecida
                enemy_id = f"enemy_{self.dir}_{distance}"  # ID aproximado
                current_time = self.game_time
                
                if enemy_id in self.enemy_last_positions:
                    old_x, old_y, old_time = self.enemy_last_positions[enemy_id]
                    dt = current_time - old_time
                    if dt > 0:
                        dx = (enemy_x - old_x) / dt
                        dy = (enemy_y - old_y) / dt
                        self.enemy_velocity[enemy_id] = (dx, dy)
                
                self.enemy_last_positions[enemy_id] = (enemy_x, enemy_y, current_time)
                
        except Exception as e:
            print(f"Error tracking enemy: {e}")
    
    # <summary>
    # Predict if should shoot based on enemy movement
    # </summary>
    def PredictEnemyInterception(self, enemy_dist):
        """
        Prevê se deve atirar agora ou esperar baseado em movimento inimigo
        Returns: True se deve atirar, False se deve esperar
        """
        # Se temos tracking de velocidade para inimigo atual
        enemy_id = f"enemy_{self.dir}_{enemy_dist}"
        
        if enemy_id not in self.enemy_velocity:
            return True  # Sem dados, atira normal
        
        dx, dy = self.enemy_velocity[enemy_id]
        
        # Se inimigo está se movendo perpendicular (lateral), dificulta acerto
        # Se está se aproximando/afastando na nossa direção, é mais fácil
        
        if self.dir in ["north", "south"]:
            lateral_speed = abs(dx)
        else:  # east, west
            lateral_speed = abs(dy)
        
        # Se movimento lateral é significativo, considerar não atirar
        if lateral_speed > 0.5:  # Movendo rápido lateral
            return enemy_dist <= 3  # Só atira se muito perto
        
        return True  # Atira normalmente



    def GetDecision(self) -> str:
        # ============== ANTI-STUCK: Track position history ==============
        curr_pos = (self.player.x, self.player.y)
        self.position_history.append(curr_pos)
        if len(self.position_history) > 10:
            self.position_history.pop(0)
        
        # Check if stuck in straight line (same row OR column for 4+ moves)
        if len(self.position_history) >= 4 and not self.gold_locations:
            last_4 = self.position_history[-4:]
            all_same_x = all(p[0] == last_4[0][0] for p in last_4)
            all_same_y = all(p[1] == last_4[0][1] for p in last_4)
            
            if all_same_x or all_same_y:
                print("ANTI-STUCK: Detected straight-line pattern! Forcing turn.")
                self.position_history.clear()
                return "virar_direita"
        
        # ============== FSM STATE TRANSITIONS ==============
        old_state = self.fsm_state
        
        # PRIORITY -2: CRITICAL SURVIVAL (Energy Critical < 20)
        # ABSOLUTE PRIORITY: Must find powerup immediately, ignore everything
        if self.energy < self.CRITICAL_ENERGY:
            # Check current cell
            if "redLight" in self.current_observations:
                print(f"CRITICAL: Energy at {self.energy}! Grabbing powerup NOW!")
                self.last_action = "pegar_powerup"
                return "pegar_powerup"
            
            # Search for known powerups with HIGHEST priority
            if self.powerup_locations:
                start = (self.player.x, self.player.y)
                nearest_pup = min(self.powerup_locations, key=lambda p: abs(p[0]-start[0]) + abs(p[1]-start[1]))
                print(f"CRITICAL: Energy at {self.energy}! Fleeing to PowerUp at {nearest_pup}")
                next_step = self.GetNextStepTowards(nearest_pup)
                if next_step:
                    self.last_action = next_step
                    return next_step
            
            print(f"CRITICAL: Energy at {self.energy}! No powerups known. Exploring for survival.")
            # Will continue to exploration below to find powerups
        
        # PRIORITY -1: LOW ENERGY (Proactive refueling when < 100)
        elif self.energy < 100:
            # Check current cell
            if "redLight" in self.current_observations:
                 print(f"PRIORITY: Low Energy ({self.energy}) & PowerUp found. Refueling.")
                 self.last_action = "pegar_powerup"
                 return "pegar_powerup"
                 
            # Check memory for powerups
            if self.powerup_locations:
                 start = (self.player.x, self.player.y)
                 nearest_pup = min(self.powerup_locations, key=lambda p: abs(p[0]-start[0]) + abs(p[1]-start[1]))
                 print(f"PRIORITY: Low Energy ({self.energy}). Moving to known PowerUp at {nearest_pup}")
                 next_step = self.GetNextStepTowards(nearest_pup)
                 if next_step:
                     self.last_action = next_step
                     return next_step

        # PRIORITY 0: GOLD
        if "blueLight" in self.current_observations:
            print("PRIORITY: Gold found (Current). Collecting.")
            self.last_action = "pegar_ouro"
            return "pegar_ouro"
            

        if "weakLight" in self.current_observations:
             print("PRIORITY: Unknown item. Collecting.")
             self.last_action = "pegar_ouro" 
             return "pegar_ouro"


        if self.gold_locations:
             start = (self.player.x, self.player.y)
             nearest = min(self.gold_locations, key=lambda p: abs(p[0]-start[0]) + abs(p[1]-start[1]))
             
             # If we are AT the gold location but don't see blueLight, it's gone!
             if nearest == start:
                 print(f"PRIORITY: Arrived at gold location {nearest} but no gold found. Removing from memory.")
                 self.gold_locations.discard(nearest)
             else:
                 print(f"PRIORITY: Moving to known gold at {nearest}")
                 next_step = self.GetNextStepTowards(nearest)
                 if next_step:
                     self.last_action = next_step
                     return next_step
                 
        # PRIORITY 1: HUNTER / COMBAT
        enemy_visible = False
        enemy_dist = 999
        
        for obs in self.current_observations:
            if obs.startswith("enemy#"):
                enemy_visible = True
                self.UpdateEnemyTracking(obs)  # Track enemy movement
                try:
                    # Enemy obs format: enemy#distance
                    # But the string is usually just "enemy#n"? No, usually "enemy#1" etc?
                    # Let's assume just existence for now, or parse if needed.
                    pass
                except:
                    pass
                break
        
        if enemy_visible:
            # Parse distance if available (e.g., enemy#2)
            try:
                parts = obs.split('#')
                if len(parts) > 1:
                    enemy_dist = int(parts[1])
                else:
                    enemy_dist = 5 # Default max range
            except:
                enemy_dist = 5
        
            # TACTICAL RETREAT: Flee if low energy and enemy visible
            # OR if DEFENSIVE mode (protecting lead)
            strategic_mode = self.GetStrategicMode()
            
            if self.energy < self.LOW_ENERGY or strategic_mode == "DEFENSIVE":
                if strategic_mode == "DEFENSIVE":
                    print(f"STRATEGIC RETREAT: Protecting lead (Rank {self.my_rank}/{self.total_players}). Avoiding combat.")
                else:
                    print(f"TACTICAL RETREAT: Energy low ({self.energy}) & enemy detected at {enemy_dist}! Fleeing.")
                
                import random
                if random.choice([True, False]):
                    return "virar_direita"
                else:
                    return "virar_esquerda"

            # Check Line of Fire up to enemy distance
            if self.HasLineOfFire(enemy_dist):
                # Check if shot is likely to hit based on enemy movement
                should_shoot = self.PredictEnemyInterception(enemy_dist)
                
                if should_shoot:
                    print(f"HUNTER: Enemy detected at dist {enemy_dist} & Clear Shot! Attacking.")
                    self.last_action = "atacar"
                    return "atacar"
                else:
                    print(f"HUNTER: Enemy at {enemy_dist} moving laterally. Repositioning for better shot.")
                    # Move closer instead of shooting
                    return "andar"
            else:
                print(f"HUNTER: Enemy detected at {enemy_dist} but LOS Blocked! Initiating Strafe.")
                self.combat_state = "strafe_turning"
                self.original_dir = self.dir
                
                # Check if strafe direction is safe before committing
                # Try both directions and pick safe one
                # For now, simple: just turn right
                return "virar_direita"

        # Handle Combat States (Strafing sequence)
        if self.combat_state == "strafe_turning":
            print("HUNTER: Strafing (Moving).")
            self.combat_state = "strafe_moving"
            return "andar"
            
        if self.combat_state == "strafe_moving":
            print("HUNTER: Strafing (Reacquiring Target).")
            self.combat_state = None
            return "virar_esquerda"
            
        if self.under_attack:
            print("HUNTER: Under attack! Spinning to find target.")
            self.under_attack = False # Reset flag after reacting
            return "virar_direita" # Spin to find
        
        # HUNTER: Active hunting when steps detected
        if self.enemy_nearby and not enemy_visible:
            strategic_mode = self.GetStrategicMode()
            
            # If AGGRESSIVE mode, hunt more aggressively
            if strategic_mode == "AGGRESSIVE":
                print(f"HUNTER (AGGRESSIVE): Steps detected! Actively hunting to catch up on score.")
            else:
                print("HUNTER: Steps detected! Enemy is close but not in sight. Scanning area.")
            
            # Enemy is adjacent but not in front of us
            # Spin to find them
            self.enemy_nearby = False  # Reset to avoid infinite spin
            return "virar_direita"
            
        if self.shot_connected:
             print("HUNTER: Shot connected! Keeping pressure/search.")
             self.shot_connected = False
        
        # EXPLORATION
        
        target = self.FindNearestFrontier()
        
        if target:

            next_step = self.GetNextStepTowards(target)
            if next_step:
                self.last_action = next_step
                return next_step
        
        # FALLBACK
        return self.RandomSafeMove()

    def HasLineOfFire(self, max_dist=5):
        print(f"LOS CHECK: Checking {max_dist} steps ahead from {self.player} facing {self.dir}")
        for i in range(1, max_dist):
            pos = self.NextPositionAhead(i)
            if not pos: break
            
            cell_status = self.map_state.get((pos.x, pos.y), "Unknown")
            print(f"LOS CHECK: Step {i} at {pos} is {cell_status}")
            
            if cell_status == "Wall":
                print(f"LOS: Blocked by wall at {pos}")
                return False
                
        return True

    def GetNeighbors(self, x, y):
        return [(x, y-1), (x+1, y), (x, y+1), (x-1, y)]
        
    def IsSafe(self, x, y):
        if x < 0 or y < 0: return False
        
        if (x, y) in self.safe_cells: return True
        if (x, y) in self.hazards: return False
        

        

        neighbors = self.GetNeighbors(x, y)
        for nx, ny in neighbors:
            if (nx, ny) in self.visited:
                if (nx, ny) not in self.breeze_sources and (nx, ny) not in self.flash_sources:
                    self.safe_cells.add((x, y))
                    return True
        
        return False

    def FindNearestFrontier(self):
        start = (self.player.x, self.player.y)
        queue = deque([start])
        visited_bfs = {start}

        while queue:
            curr = queue.popleft()
            if self.IsSafe(curr[0], curr[1]) and curr not in self.visited:
                return curr

            
            for nx, ny in self.GetNeighbors(curr[0], curr[1]):
                if (nx, ny) not in visited_bfs:
                    if (nx, ny) in self.visited:
                        visited_bfs.add((nx, ny))
                        queue.append((nx, ny))
                    elif self.IsSafe(nx, ny):
                        # Found a safe unvisited! This is our target.
            # We don't add to queue because we stop here.
                        return (nx, ny)
        
        return None

    def GetNextStepTowards(self, target):
        # A* pathfinding with Manhattan distance heuristic
        start = (self.player.x, self.player.y)
        
        if start == target:
            return None
        
        # Manhattan distance heuristic
        def heuristic(pos):
            return abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        
        # Priority queue: (f_score, counter, current_pos, path)
        # f_score = g_score + h_score
        # g_score = actual cost from start
        # h_score = heuristic estimated cost to target
        counter = 0  # Tie-breaker for equal f_scores
        pq = [(heuristic(start), counter, start, [])]
        visited_astar = {start}
        g_scores = {start: 0}
        
        while pq:
            f_score, _, curr, path = heapq.heappop(pq)
            
            # Found target
            if curr == target:
                if not path:
                    return None
                    
                first_move = path[0]
                
                # Determine action based on first_move coordinate
                tx, ty = first_move
                sx, sy = start
                
                # Determine target direction
                curr_dir = self.dir
                target_dir = ""
                
                if ty < sy: target_dir = "north"
                elif tx > sx: target_dir = "east"
                elif ty > sy: target_dir = "south"
                elif tx < sx: target_dir = "west"
                
                if curr_dir == target_dir:
                    return "andar"
                
                # Turn logic (shortest turn)
                dirs = ["north", "east", "south", "west"]
                idx_curr = dirs.index(curr_dir)
                idx_target = dirs.index(target_dir)
                
                diff = (idx_target - idx_curr) % 4
                if diff == 1: return "virar_direita"
                if diff == 3: return "virar_esquerda"
                if diff == 2: return "virar_direita"  # 180 turn (arbitrary choice)
            
            # Expand neighbors
            curr_g = g_scores[curr]
            for nx, ny in self.GetNeighbors(curr[0], curr[1]):
                # Can only traverse visited cells OR the target itself
                if (nx, ny) not in self.visited and (nx, ny) != target:
                    continue
                    
                new_g = curr_g + 1  # Cost to neighbor is always 1
                
                # If we found a better path to this neighbor, update it
                if (nx, ny) not in g_scores or new_g < g_scores[(nx, ny)]:
                    g_scores[(nx, ny)] = new_g
                    f_score = new_g + heuristic((nx, ny))
                    
                    new_path = list(path)
                    new_path.append((nx, ny))
                    
                    counter += 1
                    heapq.heappush(pq, (f_score, counter, (nx, ny), new_path))
                    visited_astar.add((nx, ny))
        
        return None

    def RandomSafeMove(self):
        fwd = self.NextPosition()
        

        if fwd and self.IsSafe(fwd.x, fwd.y) and (fwd.x, fwd.y) not in self.visited:
            print("FALLBACK: Moving forward to unexplored safe cell.")
            return "andar"
        

        if fwd and self.IsSafe(fwd.x, fwd.y):
            print("FALLBACK: Moving forward.")
            return "andar"
        

        for turn_action in ["virar_direita", "virar_esquerda"]:

            dirs = ["north", "east", "south", "west"]
            idx = dirs.index(self.dir)
            if turn_action == "virar_direita": idx = (idx + 1) % 4
            else: idx = (idx - 1) % 4
            new_dir = dirs[idx]

            if new_dir == "north": nx, ny = self.player.x, self.player.y - 1
            elif new_dir == "east": nx, ny = self.player.x + 1, self.player.y
            elif new_dir == "south": nx, ny = self.player.x, self.player.y + 1
            else: nx, ny = self.player.x - 1, self.player.y
            
            if self.IsSafe(nx, ny) and (nx, ny) not in self.visited:
                print(f"FALLBACK: Turning {turn_action} towards unexplored ({nx},{ny}).")
                return turn_action
        

        print("FALLBACK: Turning right to continue search.")
        return "virar_direita"

