
import unittest
from GameAI import GameAI
from Map.Position import Position

class TestGameAI(unittest.TestCase):
    def setUp(self):
        self.ai = GameAI()
        # Initialize basic state
        self.ai.SetStatus(0, 0, "north", "game", 0, 100)

    def test_initial_decision(self):
        # Should probably explore or rotate
        cmd = self.ai.GetDecision()
        self.assertIn(cmd, ["virar_direita", "virar_esquerda", "andar", "atacar", "pegar_ouro", "pegar_anel", "pegar_powerup", "andar_re"])

    def test_collect_gold(self):
        # Simulate seeing blueLight (treasure)
        self.ai.GetObservationsClean()
        self.ai.GetObservations(["blueLight"])
        cmd = self.ai.GetDecision()
        self.assertIn(cmd, ["pegar_ouro", "pegar_anel", "pegar_powerup"]) 
        # Actually standard response for blueLight is usually pegar_ouro/anel. 
        # The bot should try to pick it up.

    def test_shoot_enemy(self):
        # Simulate seeing enemy
        self.ai.GetObservationsClean()
        self.ai.GetObservations(["enemy#5"])
        cmd = self.ai.GetDecision()
        self.assertEqual(cmd, "atacar")

    def test_avoid_breeze(self):
        # Logic test: if breeze, don't move forward carelessly?
        # This is harder to test without map state, but let's see if it runs.
        self.ai.GetObservationsClean()
        self.ai.GetObservations(["breeze"])
        cmd = self.ai.GetDecision()
        print(f"Decision with breeze: {cmd}")

if __name__ == '__main__':
    unittest.main()
