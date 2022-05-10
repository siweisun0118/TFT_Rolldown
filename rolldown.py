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


class Unit:
    """Class containing unit information."""
    def __init__(self, cost, name, traits, level=1):
        self.cost = cost
        self.name = name
        self.traits = [trait.strip() for trait in traits]

        self.level = level

    def __str__(self):
        """String representation of a unit."""
        return self.name + ', ' + str(self.cost) + ', ' + ', '.join(self.traits) + '\n'

    def __repr__(self):
        """Self representation of a unit."""
        return str(self)

    # This one is used by the __in__ builtin!
    def __eq__(self, other):
        """Compare units by name."""
        if type(other) != Unit:
            return False

        # Check only name
        return self.name == other.name

    def unit_compare_level(self, other):
        """Compare units by name and star level."""
        return self.name == other.name and self.level == other.level

    def upgrade(self):
        """Return an upgraded version of the unit."""
        return Unit(self.cost, self.name, self.traits, self.level + 1)


class Trait:
    """Class containing trait information (incld. breakpoints and icon style)."""
    def __init__(self, name, breakpoints, styles):
        self.name = name
        self.breakpoints = breakpoints
        self.styles = styles
        assert len(breakpoints) == len(styles), 'Error reading in traits'

    def __str__(self):
        """String representation of a trait."""
        str_breaks = [str(breaks) for breaks in self.breakpoints]
        str_styles = [str(styles) for styles in self.styles]
        return self.name + ': ' + '/'.join(str_breaks) + ' ' + 'with styles ' + '/'.join(str_styles) + '\n'

    def __repr__(self):
        """Self representation of a trait."""
        return str(self)


class Team:
    """Class that represents a team of units."""
    def __init__(self, champions_dict, traits_dict):
        self.team = []
        self.traits = {}

        self.champions_dict = champions_dict
        self.traits_dict = traits_dict

    def __str__(self):
        """The String representation of a team."""
        str_team = [unit.name + ' ' + str(unit.level) + '\n' for unit in self.team]
        str_traits = [str(trait) + ' ' + str(amount) for trait, amount in self.traits.items()]
        units = "This is the current team:\n" + ''.join(str_team) + '\n'
        traits = "Here are the current traits:\n" + '\n'.join(str_traits)
        return units + traits

    def __repr__(self):
        """The self representation of a team."""
        return str(self)

    def add_unit(self, unit):
        """Add unit to a team."""
        # Error checking
        assert type(unit) == str, "Error attempting to add unknown type to team."
        try:
            new_unit = self.champions_dict[unit]
        except ValueError:
            print("ValueError raised, check champion spelling.")
            sys.exit()

        # If it's a unique unit, add its traits to the team
        if new_unit not in self.team:
            for trait in new_unit.traits:
                if trait not in self.traits:
                    self.traits[trait] = 1
                else:
                    self.traits[trait] += 1
            
            # Finally, add the unit to the team
            self.team.append(new_unit)

        # If it's not a unique unit, check if it triggers an upgrade
        else:
            # We need to include the unit star level for this comparison
            amount = sum([1 if unit.unit_compare_level(new_unit) else 0 for unit in self.team])

            # If it triggers an upgrade, add the upgraded unit and remove the previous copies
            if amount == 2:
                # Remove previous copies
                self.team = [unit for unit in self.team if not unit.unit_compare_level(new_unit)]

                # Add upgraded copy
                self.team.append(new_unit.upgrade())

            # Otherwise, just add the unit
            else:
                self.team.append(new_unit)


    def get_traits(self):
        """Extract the activated traits from a team."""
        activated_traits = []
        for trait, amount in self.traits.enumerate():
            activated_traits.append(trait, amount)

        return activated_traits


def read_database(input_dir):
    """Read in units and traits."""
    # Read in units
    with open(Path(input_dir) / 'champions.json') as champions_file:
        champions_list = json.loads(champions_file.read())

    # Read in traits
    with open(Path(input_dir) / 'traits.json') as traits_file:
        traits_list = json.loads(traits_file.read())

    # Parse unit data
    champions = {}
    for champ in champions_list:
        # If champion has fewer than 2 traits, ignore it
        # Since it is a target dummy, voidspawn, tome, Veigar, etc.
        if len(champ['traits']) < 2:
            continue

        # Add to champions list
        champions[champ['name']] = Unit(champ['cost'], champ['name'], champ['traits'])

    # Parse trait data
    traits = {}
    for trait in traits_list:
        # Extract trait breakpoints and styles from trait data
        # TODO: Make exception for Rival
        breakpoints = []
        styles = []
        for breakpoint in trait['sets']:
            breakpoints.append(breakpoint['min'])
            styles.append(breakpoint['style'])

        # Add to traits list
        traits[trait['name']] = Trait(trait['name'], breakpoints, styles)

    return champions, traits


def main(input_dir):
    """Simulate a rolldown."""
    # champions is dict of names to Units, traits is dict of names to Traits
    champions, traits = read_database(input_dir)
    cur_team = Team(champions, traits)
    cur_team.add_unit('Lux')
    cur_team.add_unit('Lux')
    cur_team.add_unit('Garen')
    cur_team.add_unit('Lux')
    cur_team.add_unit('Lux')
    print(cur_team)


if __name__ == '__main__':
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print('Usage: python rolldown.py {set_info}')
        sys.exit()
    main(sys.argv[1])
