"""Sandbox defaults (documented in docs/SANDBOX.md)."""

# Grid
DEFAULT_GRID_WIDTH = 16
DEFAULT_GRID_HEIGHT = 16
SANDBOX_GRID_MIN_SIZE = 8
SANDBOX_GRID_MAX_SIZE = 64

# Creature
DEFAULT_CREATURE_FACING = "N"

# Food (board items only; not consumable in navigation model)
DEFAULT_FOOD_ENERGY = 48

# Fixture placeholder visual (docs/SANDBOX.md)
FIXTURE_FILL = "#8B5CF6"

RECENT_ACTIONS_MAX = 10

DECISION_ACTION_STRINGS = frozenset({"move_forward", "turn_left", "turn_right", "idle"})
FACING_STRINGS = frozenset({"N", "E", "S", "W"})
