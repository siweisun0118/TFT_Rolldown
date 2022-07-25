"""FInd the best unit to loaded dice at each level."""

# Standard libaries
import sys


# Local files
from resources import LEVEL_ODDS, SHOP_SLOTS, read_database, Unit


def loaded_dice_odds(desired_unit, champions):
    """Calculate the loaded dice odds."""
    assert isinstance(desired_unit, Unit), 'Error: invalid input for desired unit'
    assert isinstance(champions, dict), 'Error: invalid input for dictionary of champions'

    # Calculate the odds of rolling the desired champion
    # For each champion, and for each level
    # results: dict{champion: [levels]}
    at_least_one_results = {}
    expected_number_results = {}

    # Get unit's traits
    traits = desired_unit.traits

    # For each champion that shares a trait
    for _, champion in champions.items():
        if set.intersection(set(champion.traits), set(traits)):
            # Calculate the odds of rolling desired champion from current champion
            # Calculate odds for each level
            current_champion_odds = []
            expected_champion_amount = []

            # In order to calculate odds, we need the other champions that
            # also share a trait with the current champion
            possible_champions = {}
            for _, champ_candidate in champions.items():
                if set.intersection(set(champ_candidate.traits), set(champion.traits)):
                    if champ_candidate.rarity not in possible_champions:
                        possible_champions[champ_candidate.rarity] = [champ_candidate]
                    else:
                        possible_champions[champ_candidate.rarity].append(champ_candidate)

            # Now for each level, calculate the odds of hitting the desired champion
            # For each champion candidate
            for level in range(1, 12):
                current_odds = reweight_odds(LEVEL_ODDS[level], possible_champions)

                probability = current_odds[desired_unit.rarity - 1] \
                    / len(possible_champions[desired_unit.rarity])

                # Calculate probabilities for:
                # At least 1 copy of the desired champion
                # Expected number of the desired champion
                current_champion_odds.append(f'{(1 - ((1 - probability / 100) ** SHOP_SLOTS)):.4f}')
                expected_champion_amount.append(f'{(probability * SHOP_SLOTS / 100):.4f}')

            # Add final probablity to results
            at_least_one_results[champion.name] = current_champion_odds
            expected_number_results[champion.name] = expected_champion_amount

    return at_least_one_results, expected_number_results


def main(argv):
    """Calculate the loaded dice odds."""
    # Read in database
    champions, _ = read_database(argv[1])

    # Read in desired unit (check that unit exists)
    assert argv[2] in champions, 'Error: Invalid unit'
    desired_unit = champions[argv[2]]

    # Calculate odds of rolling desired champion
    at_least_one, expected_number = loaded_dice_odds(desired_unit, champions)

    # Print results
    # At least one copy of desired champion
    print(f'Probability of hitting at least one {desired_unit.name}')
    print_column_names()
    for item in sorted(at_least_one.items(), key=lambda x: x[1][-1], reverse=True):
        print(f'{(item[0] + ":"): <13} {" ".join(item[1])}')

    # Expected number of desired champions
    print()
    print(f'Expected number of {desired_unit.name}s')
    print_column_names()
    for item in sorted(expected_number.items(), key=lambda x: x[1][-1], reverse=True):
        print(f'{(item[0] + ":"): <13} {" ".join(item[1])}')


def print_column_names():
    """Print the levels as column names."""
    print(f'{"Level:" :<13}', end='')
    for i in range(1, 12):
        print(f' {i: <6}', end='')
    print()


def reweight_odds(odds, possible_champions):
    """Reweight roll odds in case one rarity is not available for the champion."""
    adjusted_odds = odds.copy()
    available_rarities = [True, True, True, True, True]

    # Check if any rarity is unavailable
    for rarity in range(1, 6):
        if rarity not in possible_champions:
            available_rarities[rarity - 1] = False

    # If any rarities are unavailable, set their odds to 0
    for idx, available in enumerate(available_rarities):
        if not available:
            adjusted_odds[idx] = 0

    # And then reweight the odds so that they add up to 100
    try:
        adjusted_odds = [x * 100 / sum(adjusted_odds) for x in adjusted_odds]
    except ZeroDivisionError:
        return [0, 0, 0, 0, 0]

    # Return reweighted odds
    return adjusted_odds


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python loaded_dice_odds.py {input_dir} {desired_unit_name}')
        sys.exit()
    main(sys.argv)
