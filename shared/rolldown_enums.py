"""Enums and globals for rolldown."""

from pathlib import Path
import threading

# region Logging
SERVER_LOG_FILE = Path('server_log')
# endregion

# region Locks
POOL_LOCK = threading.Lock()
# endregion


# region Game Globals
# Number of slots in shop and on bench
SHOP_SLOTS = 5
BENCH_SLOTS = 9

# List of all champions in pool by cost
CHAMPION_POOL = {1: [], 2: [], 3: [], 4: [], 5: []}

# Amount of each unit in pool for each cost
CHAMPION_AMOUNTS = {
    1: 29,
    2: 22,
    3: 18,
    4: 12,
    5: 10
}

# Unit amounts by star level
UNIT_AMOUNT_LEVEL = {1: 1, 2: 3, 3: 9}

# Odds at each level
LEVEL_ODDS = {
    1: [100, 0, 0, 0, 0],
    2: [100, 0, 0, 0, 0],
    3: [75, 25, 0, 0, 0],
    4: [55, 30, 15, 0, 0],
    5: [45, 33, 20, 2, 0],
    6: [25, 40, 30, 5, 0],
    7: [19, 30, 35, 15, 1],
    8: [16, 20, 35, 25, 4],
    9: [9, 15, 30, 30, 16],
    10: [5, 10, 20, 40, 25],
    11: [1, 2, 12, 50, 35]
}

# EXP needed to level
LEVEL_EXP = {
    1: 2,
    2: 2,
    3: 6,
    4: 10,
    5: 20,
    6: 36,
    7: 50,
    8: 80,
    9: 100,
    10: 0,
    11: 0
}

# 3 starred units cannot be rolled anymore
THREE_STARRED = set()
# endregion


# region UI Elements
# Size of splash art
SPLASH_SIZE = (1006, 596)

# Path to local resources
GEN_ASSETS = Path('General Assets')
# endregion

# region Port number for rolldown server
SERVER_PORT = 8000
# endregion
