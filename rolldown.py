"""Simulate rolls in TFT."""

# Standard libraries
import json
import os
from pathlib import Path
import random
import sys


# Third party libraries
# pylint: disable=import-error
from termcolor import colored
if os.name == 'nt':
    from msvcrt import getwch as getch
else:
    from getch import getch


# Local files
# pylint: disable=wrong-import-position
from resources import Game


# random.seed(112358)


def main(input_dir):
    """Simulate a rolldown."""
    # The team that the user will be building
    game = Game(input_dir)
    game.rolldown()


if __name__ == '__main__':
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print('Usage: python rolldown.py {set_info}')
        sys.exit()
    main(sys.argv[1])
