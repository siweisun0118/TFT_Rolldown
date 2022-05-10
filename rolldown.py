"""Simulate rolls in TFT."""


import json
from pathlib import Path
import random
import sys


# Amount of each unit in pool
TFT_1_COSTS_AMOUNT = 29
TFT_2_COSTS_AMOUNT = 22
TFT_3_COSTS_AMOUNT = 18
TFT_4_COSTS_AMOUNT = 12
TFT_5_COSTS_AMOUNT = 10


# Odds at each level
TFT_LEVEL_1_ODDS = [100, 0, 0, 0, 0]
TFT_LEVEL_2_ODDS = [100, 0, 0, 0, 0]
TFT_LEVEL_3_ODDS = [75, 25, 0, 0, 0]
TFT_LEVEL_4_ODDS = [55, 30, 15, 0, 0]
TFT_LEVEL_5_ODDS = [45, 33, 20, 2, 0]
TFT_LEVEL_6_ODDS = [25, 40, 30, 5, 0]
TFT_LEVEL_7_ODDS = [19, 30, 35, 15, 1]
TFT_LEVEL_8_ODDS = [16, 20, 35, 25, 4]
TFT_LEVEL_9_ODDS = [9, 15, 30, 30, 16]
TFT_LEVEL_10_ODDS = [5, 10, 20, 40, 25]
TFT_LEVEL_11_ODDS = [1, 2, 12, 50, 35]


# Make sure odds make sense
assert all([
    sum(TFT_LEVEL_1_ODDS) == 100, 
    sum(TFT_LEVEL_2_ODDS) == 100,
    sum(TFT_LEVEL_3_ODDS) == 100,
    sum(TFT_LEVEL_4_ODDS) == 100,
    sum(TFT_LEVEL_5_ODDS) == 100,
    sum(TFT_LEVEL_6_ODDS) == 100,
    sum(TFT_LEVEL_7_ODDS) == 100,
    sum(TFT_LEVEL_8_ODDS) == 100,
    sum(TFT_LEVEL_9_ODDS) == 100,
    sum(TFT_LEVEL_10_ODDS) == 100,
    sum(TFT_LEVEL_11_ODDS) == 100]), "Error in level odds."


def read_database(input_dir):
    """Read in units and traits."""
    # Read in units
    with open(Path(input_dir) / 'champions.json') as champions_file:
        champions_list = json.loads(champions_file.read())

    # Read in traits
    with open(Path(input_dir) / 'traits.json') as traits_file:
        traits_list = json.loads(traits_file.read())

    return champions_list, traits_list


def main(input_dir):
    """Simulate a rolldown."""
    champions, traits = read_database(input_dir)
    print(champions)
    print(traits)


if __name__ == '__main__':
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print('Usage: python rolldown.py {set_info}')
        sys.exit()
    main(sys.argv[1])
