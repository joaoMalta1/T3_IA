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
        self.last_known_enemy_pos = None
        self.combat_state = None
        self.strafe_dir = None
        self.original_dir = None
        self.gold_locations = set()
        self.powerup_locations = set()
        self.fsm_state = AgentState.EXPLORING
        self.position_history = []  # Track recent positions for anti-stuck


    def SetStatus(self, x: int, y: int, dir: str, state: str, score: int, energy: int):
        
        self.SetPlayerPosition(x, y)
        self.dir = dir.lower()

        self.state = state
        self.score = score
        self.energy = energy

        self.visited.add((x, y))
        self.safe_cells.add((x, y))
        self.map_state[(x, y)] = "Safe"



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
        
        # Determine current state based on conditions
        if self.energy < 50:
            self.fsm_state = AgentState.REFUELING
        elif "blueLight" in self.current_observations or self.gold_locations:
            self.fsm_state = AgentState.COLLECTING_GOLD
        elif any(obs.startswith("enemy#") for obs in self.current_observations):
            self.fsm_state = AgentState.COMBAT
        else:
            self.fsm_state = AgentState.EXPLORING
        
        if old_state != self.fsm_state:
            print(f"FSM: {old_state.value} -> {self.fsm_state.value}")
        
        # ============== STATE-BASED ACTIONS ==============
        # PRIORITY -1: CRITICAL SURVIVAL (REFUELING state)
        if self.energy < 100:
            # Check current cell
            if "redLight" in self.current_observations:
                 print("PRIORITY: Low Energy & PowerUp found. Refueling.")
                 self.last_action = "pegar_powerup"
                 return "pegar_powerup"
                 
            # Check memory for powerups
            if self.powerup_locations:
                 start = (self.player.x, self.player.y)
                 nearest_pup = min(self.powerup_locations, key=lambda p: abs(p[0]-start[0]) + abs(p[1]-start[1]))
                 print(f"PRIORITY: Low Energy. Moving to known PowerUp at {nearest_pup}")
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

            # Check Line of Fire up to enemy distance
            if self.HasLineOfFire(enemy_dist):
                print(f"HUNTER: Enemy detected at dist {enemy_dist} & Clear Shot! Attacking.")
                self.last_action = "atacar"
                return "atacar"
            else:
                print(f"HUNTER: Enemy detected at {enemy_dist} but LOS Blocked! Initiating Strafe.")
                self.combat_state = "strafe_turning"
                self.original_dir = self.dir
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
            self.under_attack = False
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
                        return (nx, ny)
        
        return None

    def GetNextStepTowards(self, target):
        # ============== A* SEARCH ==============
        start = (self.player.x, self.player.y)
        
        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        # Priority queue: (f_score, g_score, position, path)
        open_set = [(manhattan(start, target), 0, start, [])]
        visited_path = {start}
        
        while open_set:
            f, g, curr, path = heapq.heappop(open_set)
            
            if curr == target:
                if not path:
                    return None
                first_move = path[0]
                tx, ty = first_move
                sx, sy = start
                
                curr_dir = self.dir
                target_dir = ""
                
                if ty < sy: target_dir = "north"
                elif tx > sx: target_dir = "east"
                elif ty > sy: target_dir = "south"
                elif tx < sx: target_dir = "west"
                
                if curr_dir == target_dir:
                    return "andar"
                
                dirs = ["north", "east", "south", "west"]
                idx_curr = dirs.index(curr_dir)
                idx_target = dirs.index(target_dir)
                
                diff = (idx_target - idx_curr) % 4
                if diff == 1: return "virar_direita"
                if diff == 3: return "virar_esquerda"
                if diff == 2: return "virar_direita"
            
            for nx, ny in self.GetNeighbors(curr[0], curr[1]):
                if (nx, ny) not in visited_path and self.IsSafe(nx, ny):
                    visited_path.add((nx, ny))
                    new_path = path + [(nx, ny)]
                    new_g = g + 1
                    new_f = new_g + manhattan((nx, ny), target)
                    heapq.heappush(open_set, (new_f, new_g, (nx, ny), new_path))
        
        return None

    def RandomSafeMove(self):
        # Anti vai-e-volta: pegar células recentes do histórico
        recent_positions = set(self.position_history[-5:]) if len(self.position_history) > 0 else set()
        
        fwd = self.NextPosition()
        
        # Prioridade 1: Andar pra frente se for seguro E inexplorado E não recente
        if fwd and self.IsSafe(fwd.x, fwd.y) and (fwd.x, fwd.y) not in self.visited:
            print("FALLBACK: Moving forward to unexplored safe cell.")
            return "andar"
        
        # Prioridade 2: Avaliar todas as direções com pontuação
        dirs = ["north", "east", "south", "west"]
        curr_idx = dirs.index(self.dir)
        
        best_action = None
        best_score = -999
        
        # Checar frente, direita e esquerda
        options = [
            ("andar", 0),           # Frente
            ("virar_direita", 1),   # Direita
            ("virar_esquerda", -1)  # Esquerda
        ]
        
        for action, delta in options:
            if action == "andar":
                check_dir = self.dir
            else:
                new_idx = (curr_idx + delta) % 4
                check_dir = dirs[new_idx]
            
            # Calcular posição resultante
            if check_dir == "north": nx, ny = self.player.x, self.player.y - 1
            elif check_dir == "east": nx, ny = self.player.x + 1, self.player.y
            elif check_dir == "south": nx, ny = self.player.x, self.player.y + 1
            else: nx, ny = self.player.x - 1, self.player.y
            
            # Pular se for parede/hazard
            if (nx, ny) in self.hazards or self.map_state.get((nx, ny)) == "Wall":
                continue
            
            # Calcular score
            score = 0
            if self.IsSafe(nx, ny) and (nx, ny) not in self.visited:
                score = 10  # Melhor: seguro e inexplorado
            elif self.IsSafe(nx, ny):
                score = 5   # Bom: seguro mas visitado
            elif (nx, ny) not in self.hazards:
                score = 2   # OK: desconhecido
            
            # PENALIDADE ANTI VAI-E-VOLTA: -8 se foi visitado recentemente
            if (nx, ny) in recent_positions:
                score -= 8
                print(f"FALLBACK: Penalizing ({nx},{ny}) - visited recently!")
            
            if score > best_score:
                best_score = score
                best_action = action
        
        if best_action:
            if best_action == "andar":
                print(f"FALLBACK: Moving forward (score={best_score}).")
            else:
                print(f"FALLBACK: {best_action} (score={best_score}).")
            return best_action
        
        # Último recurso: virar 180 graus
        print("FALLBACK: All directions blocked. Turning around.")
        return "virar_direita"

