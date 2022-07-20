"""FInd the best unit to loaded dice at each level."""

# Standard libaries
from sys import argv, exit


# Local files
from constants import LEVEL_ODDS, SHOP_SLOTS
from rolldown import read_database, Unit


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
                current_odds = LEVEL_ODDS[level]

                probability = current_odds[desired_unit.rarity - 1] / len(possible_champions[desired_unit.rarity])

                # Calculate probabilities for:
                # At least 1 copy of the desired champion
                # Expected number of the desired champion
                current_champion_odds.append('%0.4f' % (1 - ((1 - probability / 100) ** SHOP_SLOTS)))
                expected_champion_amount.append('%0.4f' % (probability * SHOP_SLOTS / 100))

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
    for item in sorted(at_least_one.items(), key=lambda x: x[1][-1], reverse=True):
        print(f'{item[0]: <12} {item[1]}')

    # Expected number of desired champions
    print()
    print(f'Expected number of {desired_unit.name}s')
    for item in sorted(expected_number.items(), key=lambda x: x[-1], reverse=True):
        print(f'{item[0]: <12} {item[1]}')


if __name__ == '__main__':
    if len(argv) != 3:
        print('Usage: python loaded_dice_odds.py {input_dir} {desired_unit_name}')
        exit()
    main(argv)
