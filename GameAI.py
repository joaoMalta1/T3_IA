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
        self.last_known_enemy_pos = None
        self.combat_state = None # None, "strafe_turning", "strafe_moving", "reacquiring"
        self.strafe_dir = None   # "left" or "right" relative to enemy
        self.original_dir = None # "north", etc.
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


    # <summary>
    # Get Decision
    # </summary>
    def GetDecision(self) -> str:
        
        # 1. Immediate Reactive Actions
        
        # HUNTER LOGIC
        # Priority 0: Combat
        enemy_visible = False
        enemy_dist = 999
        
        for obs in self.current_observations:
            if obs.startswith("enemy#"):
                enemy_visible = True
                try:
                    # Enemy obs format: enemy#distance
                    # But the string is usually just "enemy#n"? No, usually "enemy#1" etc?
                    # Let's assume just existence for now, or parse if needed.
                    pass
                except:
                    pass
                break
        
        if enemy_visible:
            # Check Line of Fire
            if self.HasLineOfFire():
                print("HUNTER: Enemy detected & Clear Shot! Attacking.")
                self.last_action = "atacar"
                return "atacar"
            else:
                print("HUNTER: Enemy detected but LOS Blocked! Initiating Strafe.")
                self.combat_state = "strafe_turning"
                self.original_dir = self.dir
                # Decide turning direction (random or based on safety)
                # Try Right first
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
            
        if self.shot_connected:
             print("HUNTER: Shot connected! Keeping pressure/search.")
             self.shot_connected = False
             # If we hit, they might still be there, but maybe not visible if they moved or we turned?
             # If visible, we already attacked above.
             # If not visible, maybe move forward to chase or turn?
             # Let's just continue standard logic, maybe we'll see them again.
        
        # Priority 1: PowerUps (Sustain the hunt)
        has_powerup = "redLight" in self.current_observations
        if has_powerup and self.energy < 100:
             print("HUNTER: PowerUp found. Refueling.")
             self.last_action = "pegar_powerup"
             return "pegar_powerup"

        # Priority 2: Gold (Secondary)
        has_gold = "blueLight" in self.current_observations
        if has_gold:
            print("HUNTER: Gold found. Collecting.")
            self.last_action = "pegar_ouro"
            return "pegar_ouro"
        
        has_item = "weakLight" in self.current_observations
        if has_item:
             print("HUNTER: Unknown item. Collecting.")
             self.last_action = "pegar_ouro" 
             return "pegar_ouro"

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

    def HasLineOfFire(self):
        # Check up to 5 steps ahead for walls
        # If we see a wall, return False
        # If we don't, return True (optimistic)
        for i in range(1, 6):
            pos = self.NextPositionAhead(i)
            if not pos: break
            if (pos.x, pos.y) in self.hazards:
                # If it's a hazard (pit/wall), we can't shoot through it?
                # Actually pits we can shoot over? 
                # Map spec: Wall=2. Pit=3.
                # Usually walls block shots. Pits might not.
                # Let's assume Wall blocks.
                if self.map_state.get((pos.x, pos.y)) == "Wall":
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
        # A* or BFS to find first step
        start = (self.player.x, self.player.y)
        # Reconstruct path
        queue = deque([(start, [])])
        visited_path = {start}
        
        while queue:
            curr, path = queue.popleft()
            if curr == target:
                if not path: return None 
                first_move = path[0]
                
                # Determine action based on first_move coord
                tx, ty = first_move
                sx, sy = start
                
                # Turn logic
                # We need to face the direction first
                curr_dir = self.dir
                target_dir = ""
                
                if ty < sy: target_dir = "north"
                elif tx > sx: target_dir = "east"
                elif ty > sy: target_dir = "south"
                elif tx < sx: target_dir = "west"
                
                if curr_dir == target_dir:
                    return "andar"
                
                # Better turn logic
                dirs = ["north", "east", "south", "west"]
                idx_curr = dirs.index(curr_dir)
                idx_target = dirs.index(target_dir)
                
                diff = (idx_target - idx_curr) % 4
                if diff == 1: return "virar_direita"
                if diff == 3: return "virar_esquerda"
                if diff == 2: return "virar_direita" # 180 turn
                
            
            # Neighbors
            for nx, ny in self.GetNeighbors(curr[0], curr[1]):
                if (nx, ny) not in visited_path:
                    # Can only traverse visited cells to reach the frontier
                    # EXCEPT the last step which is the target (Safe Unvisited)
                    if (nx, ny) in self.visited or (nx, ny) == target:
                         visited_path.add((nx, ny))
                         new_path = list(path)
                         new_path.append((nx, ny))
                         queue.append(((nx, ny), new_path))
                         
        return None

    def RandomSafeMove(self):
        # If stuck, just turn or move randomly to a safe spot if possible
        actions = ["virar_direita", "virar_esquerda"]
        
        # Check if forward is safe
        fwd = self.NextPosition()
        if fwd and self.IsSafe(fwd.x, fwd.y):
             actions.append("andar")
        
        return random.choice(actions)

