"""Simulate a loaded dice roll."""

# Standard libaries
from copy import deepcopy
import random
from sys import argv, exit


# Local files
from constants import CHAMPION_POOL, LEVEL_ODDS, SHOP_SLOTS
from rolldown import read_database, Unit


def loaded_dice(unit, level):
    """Roll the loaded dice."""
    assert isinstance(unit, Unit), 'Error: invalid input for unit type'
    assert isinstance(level, int), 'Error: invalid input for level'

    # Get odds at current level
    odds = LEVEL_ODDS[level]

    # Get unit's traits
    traits = unit.traits

    # For each slot in the shop, roll a rarity depending on current level
    costs = random.choices(population=[1, 2, 3, 4, 5], weights=odds, k=SHOP_SLOTS)

    # Rolled units
    results = []

    # For each rarity that was rolled
    for i in costs:
        # Find a valid champion
        candidates = []
        for possible in CHAMPION_POOL[i]:
            # If at least one trait is shared, add as potential candidate
            if (set(possible.traits) & set(traits)):
                candidates.append(possible)

        # If candidates is empty, reroll rarities until candidate is available
        # Remove already rolled rarity from contention
        remaining_odds = deepcopy(LEVEL_ODDS[level])
        remaining_odds[i - 1] = 0
        while not candidates:
            # If we run out of rarities, just choose a random unit with the same rarity
            if sum(remaining_odds) == 0:
                # Choose random rarity
                cost = random.choices(population=[1, 2, 3, 4, 5], weights=LEVEL_ODDS[level], k=1)[0]

                # If all units of that rarity are unavailable, just pick a random unit
                if not CHAMPION_POOL[cost]:
                    total_pool = [unit for ls in CHAMPION_POOL.values() for unit in ls]
                    replacement = random.choice(total_pool)
                    candidates.append(replacement)
                # Otherwise, pick a unit of the same cost
                else:
                    replacement = random.choice(CHAMPION_POOL[cost])
                    candidates.append(replacement)

            else:
                # Get new rarity and remove that rarity from contention
                cost = random.choices(population=[1, 2, 3, 4, 5], weights=remaining_odds, k=1)[0]
                remaining_odds[cost - 1] = 0

                # Attempt to find more candidates
                for possible in CHAMPION_POOL[cost]:
                    # If at least one trait is shared, add as potential candidate
                    if (set(possible.traits) & set(traits)):
                        candidates.append(possible)

        # Choose a random candidate
        results.append(random.choice(candidates))

    # Return rolled shop
    return results


def main(argv):
    """Simulate the loaded dice."""
    # Read in database
    champions, _ = read_database(argv[1])

    # Read in target unit (check that unit exists)
    assert argv[2] in champions, 'Error: Invalid unit'
    unit = champions[argv[2]]

    # Read in current level for level odds
    level = int(argv[3])
    assert level in range(1, 12), 'Error: Invalid level'

    # Roll
    print(loaded_dice(unit, level))


if __name__ == '__main__':
    if len(argv) != 4:
        print('Usage: python loaded_dice.py {input_dir} {unit_name} {level}')
        exit()
    main(argv)
