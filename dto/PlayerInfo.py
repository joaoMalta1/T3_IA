
class PlayerInfo:
    def __init__(self, id, name, x, y, state, score, color):
        self.id = id
        self.name = name
        self.x = x
        self.y = y
        self.state = state
        self.score = score
        self.color = color

class ScoreBoard:
    def __init__(self, name, connected, energy, score, color):
        self.name = name
        self.connected = connected
        self.energy = energy
        self.score = score
        self.color = color
