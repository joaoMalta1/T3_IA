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

# <summary>
# Game AI Example
# </summary>
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
    # 0: Unknown, 1: Safe, 2: Wall, 3: Pit, 4: Teleport (Treat as Pit/Hazard)
    map_state: Dict[Tuple[int, int], str] = {}
    visited: Set[Tuple[int, int]] = set()
    safe_cells: Set[Tuple[int, int]] = set()
    hazards: Set[Tuple[int, int]] = set() # Known pits/teleports/walls
    
    # Inference lists
    breeze_sources: Set[Tuple[int, int]] = set()
    flash_sources: Set[Tuple[int, int]] = set()
    
    current_observations: List[str] = []
    
    # Last action memory for inferring walls
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

    # <summary>
    # Refresh player status
    # </summary>
    def SetStatus(self, x: int, y: int, dir: str, state: str, score: int, energy: int):
        
        self.SetPlayerPosition(x, y)
        self.dir = dir.lower()

        self.state = state
        self.score = score
        self.energy = energy
        
        # Mark current position as visited and safe
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


    # <summary>
    # Get list of observable adjacent positions
    # </summary>
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

    # <summary>
    # Get next forward position
    # </summary>
    def NextPosition(self) -> Position:
        return self.NextPositionAhead(1)
            

    # <summary>
    # Player position
    # </summary>
    def GetPlayerPosition(self):
        return Position(self.player.x, self.player.y)


    # <summary>
    # Set player position
    # </summary>
    def SetPlayerPosition(self, x: int, y: int):
        self.player.x = x
        self.player.y = y
        self.visited.add((x, y))
        self.safe_cells.add((x, y))
    

    # <summary>
    # Observations received
    # </summary>
    def GetObservations(self, o):
        # Handle events specifically
        if "damage" in o:
            self.under_attack = True
            print("EVENT: Taken Damage!")
            return # Don't overwrite visual observations with event data
            
        if "hit" in o:
            self.shot_connected = True
            print("EVENT: Shot Hit!")
            return # Don't overwrite visual observations

        self.current_observations = o
        
        # Immediate processing
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
             
        # If we successfully picked up powerup, remove it from memory
        if "redLight" not in o and (curr_x, curr_y) in self.powerup_locations:
             self.powerup_locations.discard((curr_x, curr_y))
                
        if blocked and self.last_action == "andar":
            # Infer wall
            # The last intended position was a wall
            pass # TODO: Infer wall position based on last dir (Need to store last dir too)
            # Actually, if we just tried to walk and got blocked, the cell in front of us (BEFORE the move?) 
            # Wait, blocked means we didn't move. So the cell in front of us NOW? 
            # Or the cell we TRIED to go to from the PREVIOUS position?
            # Usually blocked update comes after the command.
            # If I am at (0,0), face North, send "andar".
            # If wall at (0,-1), I stay at (0,0) and get "blocked".
            # So the wall is at NextPosition() from where I was?
            # If I stayed only, then NextPosition() from current is the wall.
            wall_pos = self.NextPosition()
            if wall_pos:
                self.hazards.add((wall_pos.x, wall_pos.y))
                self.map_state[(wall_pos.x, wall_pos.y)] = "Wall"
                self.safe_cells.discard((wall_pos.x, wall_pos.y))


    # <summary>
    # No observations received
    # </summary>
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


    # <summary>
    # Get Decision
    # </summary>
    def GetDecision(self) -> str:
        
        # 1. Immediate Reactive Actions
        
        # 1. Immediate Reactive Actions
        
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

        # PRIORITY 0: GOLD (Greedy + Memory)
        # Check if we are standing on gold
        if "blueLight" in self.current_observations:
            print("PRIORITY: Gold found (Current). Collecting.")
            self.last_action = "pegar_ouro"
            return "pegar_ouro"
            
        # Check if we assume chance of gold (weakLight = maybe item?)
        if "weakLight" in self.current_observations:
             print("PRIORITY: Unknown item. Collecting.")
             self.last_action = "pegar_ouro" 
             return "pegar_ouro"

        # Check if we know where gold is (Memory)
        if self.gold_locations:
             # Find nearest gold
             start = (self.player.x, self.player.y)
             nearest = min(self.gold_locations, key=lambda p: abs(p[0]-start[0]) + abs(p[1]-start[1]))
             
             # If we are there but didn't pick it (already handled above by blueLight check)
             # So we must be far. Move towards it.
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
            # We just turned. Now Move.
            print("HUNTER: Strafing (Moving).")
            self.combat_state = "strafe_moving"
            # Check if safe? If not, maybe just turn back? 
            # We assume we tried to turn to a safe spot.
            # TODO: Add safety check here.
            return "andar"
            
        if self.combat_state == "strafe_moving":
            # We moved. Now turn back to original direction (to face enemy)
            print("HUNTER: Strafing (Reacquiring Target).")
            self.combat_state = None # Reset
            
            # Use turn logic to face original_dir
            # Current dir is original_dir + 90 (if we turned right)
            # We want to go back to original_dir.
            # If we turned Right, we are +90. To go back, Turn Left.
            # But wait, we returned "virar_direita" hardcoded above.
            return "virar_esquerda"
            
        if self.under_attack:
            # We took damage but don't see the enemy?
            # They might be behind us or to the side.
            # Strategy: Spin around to find them.
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
        
        # PRIORITY 3: Gold (Secondary/Exploration via SafeFrontier)
        # Note: We already prioritized Known Gold and Current Gold above.
        # This section is mostly redundant for "has_gold" but maybe kept for "has_item" or fallback?
        # Actually removed "has_gold" check here since it's at top.
        
        # 3. Pathfinding / Exploration

        # 3. Pathfinding / Exploration
        # Goal: Find nearest "Safe Frontier"
        # Frontier = Safe cell that has at least one Unknown neighbor
        
        target = self.FindNearestFrontier()
        
        if target:
            # Plan path to target
            next_step = self.GetNextStepTowards(target)
            if next_step:
                self.last_action = next_step
                return next_step
        
        # 3. Fallback: Random Walk (Safe) or Rotate
        return self.RandomSafeMove()

    def HasLineOfFire(self, max_dist=5):
        # Check path to enemy
        print(f"LOS CHECK: Checking {max_dist} steps ahead from {self.player} facing {self.dir}")
        for i in range(1, max_dist): # Check cells strictly BETWEEN player and enemy
            pos = self.NextPositionAhead(i)
            if not pos: break
            
            cell_status = self.map_state.get((pos.x, pos.y), "Unknown")
            print(f"LOS CHECK: Step {i} at {pos} is {cell_status}")
            
            if cell_status == "Wall":
                print(f"LOS: Blocked by wall at {pos}")
                return False
                
        return True

    def GetNeighbors(self, x, y):
        return [(x, y-1), (x+1, y), (x, y+1), (x-1, y)] # N, E, S, W
        
    def IsSafe(self, x, y):
        if (x, y) in self.safe_cells: return True
        if (x, y) in self.hazards: return False
        
        # Check inference
        # If any safe neighbor has NO breeze and NO flash, then (x,y) is safe
        # Logic: Breeze(A) <=> At least one neighbor is Pit.
        # Contrapositive: No Breeze(A) <=> All neighbors are NOT Pit.
        
        # Start optimistic: assume safe unless proven hazardous?
        # Safe Exploration: Assume unsafe unless proven safe.
        
        # Check if known safe:
        if (x,y) in self.safe_cells: return True
        
        # Check if proven safe by neighbors
        # Find neighbors of (x,y) that are visited.
        # If any visited neighbor has NO breeze AND NO flash, then (x,y) is OK to visit.
        neighbors = self.GetNeighbors(x, y)
        for nx, ny in neighbors:
            if (nx, ny) in self.visited:
                # If visited neighbor has NO breeze and NO flash, then (x,y) can't be a pit or teleport
                # (Assuming sensors are perfect and always trigger)
                if (nx, ny) not in self.breeze_sources and (nx, ny) not in self.flash_sources:
                    self.safe_cells.add((x, y))
                    return True
        
        return False

    def FindNearestFrontier(self):
        # BFS to find nearest reachable safe cell that has unknown neighbors
        # Actually we look for a cell C in Safe such that Neighbor(C) is Unknown
        # And we want the path to C (or actually to the unknown neighbor?)
        # We walk to C, then step into Unknown.
        
        # But we need to verify the Unknown is Safe before stepping in?
        # Yes, using IsSafe logic.
        
        start = (self.player.x, self.player.y)
        queue = deque([start])
        visited_bfs = {start}
        
        # If we are already next to a safe unknown, take it.
        
        # Optimization: We want to move to a cell 'target' such that 'target' is SAFE and UNVISITED.
        # The path must consist of VISITED cells (because we know they are safe and we are there).
        
        # Wait, standard Wumpus exploration:
        # Move to a cell that is Safe but Unvisited.
        # Path must go through Visited cells (Safe).
        
        while queue:
            curr = queue.popleft()
            
            # Check if this cell is a "Frontier" = safe and unvisited?
            # Or is it a visited cell that is adjacent to a safe unvisited?
            
            # Condition to be a target: SAFE and NOT VISITED
            if self.IsSafe(curr[0], curr[1]) and curr not in self.visited:
                return curr
            
            # Expand neighbors
            # Valid neighbors for pathfinding must be VISITED (already explored safe zone)
            # OR the *immediate* target (Safe Unvisited).
            
            # So, only expand (add to queue) if the neighbor is VISITED.
            # But we also need to check neighbors of visited to see if they are targets.
            
            # Let's adjust BFS:
            # Graph nodes: All Safe cells (Visited + Known Safe Unvisited).
            # Edges: Adjacency.
            # We want nearest Safe Unvisited.
            
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
        # If stuck, just turn or move randomly to a safe spot if possible
        actions = ["virar_direita", "virar_esquerda"]
        
        # Check if forward is safe
        fwd = self.NextPosition()
        if fwd and self.IsSafe(fwd.x, fwd.y):
             actions.append("andar")
        
        return random.choice(actions)

