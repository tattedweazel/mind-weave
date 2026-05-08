"""Sandbox defaults (documented in docs/SANDBOX.md)."""

# Grid
DEFAULT_GRID_WIDTH = 16
DEFAULT_GRID_HEIGHT = 16
SANDBOX_GRID_MIN_SIZE = 8
SANDBOX_GRID_MAX_SIZE = 64

# Initial pet (placeholders)
DEFAULT_PET_HUNGER = 45
DEFAULT_PET_ENERGY = 70
DEFAULT_PET_MOOD = 50

# Stat drift per tick (V1 placeholders)
HUNGER_PASSIVE_PER_TICK = 1
ENERGY_DRAIN_IDLE_PER_TICK = 0
SLEEP_ENERGY_PER_TICK = 18
EAT_HUNGER_RELIEF_PER_TICK = 12
EAT_FOOD_DRAIN_PER_TICK = 12
EAT_ENERGY_BONUS_PER_TICK = 6

# Food
DEFAULT_FOOD_ENERGY = 48

# Starter workflow thresholds (also tunable in workflow via sandbox_behavior)
STARTER_HUNGER_SEEK_THRESHOLD = 60
STARTER_ENERGY_SLEEP_THRESHOLD = 30

RECENT_ACTIONS_MAX = 10
MAX_RETRY = 3

# ``DecisionIntent.action`` string literals (aligned with ``DecisionAction`` in ``schemas.sandbox``).
DECISION_ACTION_STRINGS = frozenset({"move_to", "wander", "eat_nearby", "sleep", "idle"})
