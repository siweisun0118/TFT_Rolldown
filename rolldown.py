"""Simulate rolls in TFT."""


import json
import os
from pathlib import Path
import random
import sys


from termcolor import colored


random.seed(112358)


# Amount of each unit in pool for each cost
CHAMPION_AMOUNTS = {
    1: 29,
    2: 22,
    3: 18,
    4: 12,
    5: 10
}


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
# Make sure odds make sense
assert all([sum(odds) == 100 for odds in LEVEL_ODDS.values()]), "Error in level odds."


# List of all champions in pool by cost
CHAMPION_POOL = {1: [], 2: [], 3: [], 4: [], 5: []}


class Unit:
    """Class containing unit information."""
    def __init__(self, cost, name, traits, level=1):
        # Check if unit is a BLANK placeholder
        if name == 'BLANK':
            self.name = name
            return
        
        # Information that the unit needs
        self.cost = cost
        self.name = name
        self.traits = [trait.strip() for trait in traits]

        self.level = level

        # Calculate sell cost
        if level == 1:
            self.sell_cost = cost
        elif cost == 1 and level == 2:
            self.sell_cost = 3
        else:
            self.sell_cost = 3 ** (level - 1) * cost - 1

    def __str__(self):
        """String representation of a unit."""
        if self.name == 'BLANK':
            return 'BLANK\n'
        return self.name + ', ' + str(self.cost) + ', ' + ', '.join(self.traits) + '\n'

    def __repr__(self):
        """Self representation of a unit."""
        return str(self)

    def __hash__(self):
        """Hash units by name only."""
        return hash(self.name)

    # This one is used by the in and == builtin!
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
        # Newly created 3 star units can no longer be rolled
        if self.level == 2:
            # Remove all remaining instances of this champion from the pool
            CHAMPION_POOL[self.cost] = [unit for unit in CHAMPION_POOL[self.cost] if unit != self]
        
        # Sell cost changes when unit is upgraded
        return Unit(self.cost, self.name, self.traits, self.level + 1)


class Trait:
    """Class containing trait information (inclding breakpoints and icon style)."""
    def __init__(self, name, breakpoints, styles):
        self.name = name
        self.breakpoints = breakpoints
        self.styles = styles
        assert len(breakpoints) == len(styles), 'Error reading in traits'

    def __str__(self):
        """Return string representation of a trait."""
        str_breaks = [str(breaks) for breaks in self.breakpoints]
        str_styles = [str(styles) for styles in self.styles]
        return self.name + ': ' + '/'.join(str_breaks) + ' ' + 'with style(s) ' + '/'.join(str_styles) + '\n'

    def __repr__(self):
        """Return self representation of a trait."""
        return str(self)


class Team:
    """Class that represents a team of units."""
    def __init__(self, champions_dict, traits_dict):
        self.team = []
        self.traits = {}

        self.champions_dict = champions_dict
        self.traits_dict = traits_dict

    def __str__(self):
        """Return the String representation of a team."""
        # Represent the units
        str_team = [str([idx + 1]) + ' ' + unit.name + ' ' + str(unit.level) + \
            ' (sells for ' + str(unit.sell_cost) + ')\n' for idx, unit in enumerate(self.team)]
    
        # Represent the traits
        str_traits = ''
        for trait, amount in self.traits.items():
            if amount >= self.traits_dict[trait].breakpoints[-1]:
                str_traits += str(trait) + ' '  + str(amount) + '/' + str(self.traits_dict[trait].breakpoints[-1]) + '\n'
            else:
                next_breakpoint = next(bp for bp in self.traits_dict[trait].breakpoints if bp >= amount)
                str_traits += str(trait) + ' '  + str(amount) + '/' + str(next_breakpoint) + '\n'

        # Put it all together
        units = "This is the current team:\n" + ''.join(str_team) + '\n'
        traits = "Here are the current traits:\n" + str_traits
        return units + traits

    def __repr__(self):
        """Return the self representation of a team."""
        return str(self)

    def __len__(self):
        """Return the length of a team."""
        return len(self.team)

    def add_unit(self, unit):
        """Add unit to a team."""
        assert type(unit) == str, "Error attempting to add unknown type to team."
        # BLANKS are units that were already bought
        # Do nothing if user attempts to buy an empty slot
        if unit == 'BLANK':
            print('There is no unit in this slot')
            return

        # Error checking
        try:
            new_unit = self.champions_dict[unit]
        except KeyError:
            print('KeyError raised, check champion spelling: ' + unit)
            return

        # Remove the unit from the champion pool
        CHAMPION_POOL[new_unit.cost].remove(new_unit)

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
                upgraded_unit = new_unit.upgrade()
                self.team.append(upgraded_unit)

                # This can trigger a second upgrade
                amount_2 = sum([1 if unit.unit_compare_level(upgraded_unit) else 0 for unit in self.team])
                if amount_2 == 3:
                    # Remove previous copies
                    self.team = [unit for unit in self.team if not unit.unit_compare_level(upgraded_unit)]

                    # Add upgraded copy
                    upgraded_unit = upgraded_unit.upgrade()
                    self.team.append(upgraded_unit)

            # Otherwise, just add the unit
            else:
                self.team.append(new_unit)

    def sell_unit(self, unit_index):
        """Sell a unit from your board."""
        assert type(unit_index) == int, "Error in trying to sell unit"
        # Check if unit was unique
        count = 0
        sold_unit = self.team[unit_index]
        for cur_unit in self.team:
            if cur_unit == sold_unit:
                count += 1

        # If unit is unique, remove its traits
        if count == 1:
            for trait in sold_unit.traits:
                self.traits[trait] -= 1

                # If that brings the trait count to 0, remove that trait from the team's traits
                if not self.traits[trait]:
                    self.traits.pop(trait, None)

        # Remove unit from team
        self.team.pop(unit_index)

        # Return it to the champion pool
        base_unit = Unit(sold_unit.cost, sold_unit.name, sold_unit.traits)
        quantities = [0, 1, 3, CHAMPION_AMOUNTS[sold_unit.cost]]
        for _ in range(quantities[sold_unit.level]):
            CHAMPION_POOL[sold_unit.cost].append(base_unit)


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

        # Add to champion pool
        CHAMPION_POOL[champ['cost']] += [champions[champ['name']]] * CHAMPION_AMOUNTS[champ['cost']]

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


def roll(level):
    """Roll for champions based on level."""
    assert level in range(1, 12)
    # 5 Slots
    # For each slot, we roll a random cost
    odds = LEVEL_ODDS[level]
    costs = random.choices(population=[1, 2, 3, 4, 5], weights=odds, k=5)

    # For each result, we choose a random champion from CHAMPION_POOL
    # We don't need global keyword because CHAMPION_POOL is mutable
    results = []
    for cost in costs:
        # If there are no more champions of the cost (unlikely but possible),
        # simply choose a random champion
        if not CHAMPION_POOL[cost]:
            print('Out of', cost, 'costs!')

            # Build a pool of all champions to choose a replacement
            total_pool = [unit for ls in CHAMPION_POOL.values() for unit in ls]
            replacement = random.choice(total_pool)
            results.append(replacement)
            print('The replacement unit is', replacement)

        else:
            # Add result to list of resulting rolls
            resulting_champ = random.choice(CHAMPION_POOL[cost])
            results.append(resulting_champ)

    return results


def display_roll(current_roll, gold, cur_team):
    """Display the champions in the current shop."""
    # Clear console
    os.system('cls' if os.name == 'nt' else 'clear')

    # Instructions
    print("Use number keys to buy, 'd' to reroll, and 's' to see current team and traits.")
    print("Press 'p' to restart.")
    print('Your current gold amount is:', gold)
    if gold < 2:
        print('You do not have enough gold to reroll!')

    # Convert current roll to string form
    str_roll = ''
    for idx, champ in enumerate(current_roll):
        if champ in cur_team:
            str_roll += colored('[' + str(idx + 1) + '] ' + str(champ), 'green')
        else:
            str_roll += '[' + str(idx + 1) + '] ' + str(champ)

    # Display current roll
    print(str_roll, end='')


def main(input_dir):
    """Simulate a rolldown."""
    # champions is dict of names to Units, traits is dict of names to Traits
    champions_dict, traits_dict = read_database(input_dir)

    # The team that the user will be building
    cur_team = Team(champions_dict, traits_dict)

    # First, read in a level between 1 and 11 inclusive
    # Lots of error checking to make sure user doesn't enter in an invalid value
    while True:
        try:
            # Set level
            level = int(input('Please enter your current level between 1 and 11 inclusive: '))
            while level not in range(1, 12):
                level = int(input('Please enter your current level between 1 and 11 inclusive: '))

            # Set starting gold
            gold = int(input('Please enter the amount of gold you want to start with: '))
            break
        except ValueError:
            print('Invalid input, restarting...')
            os.execv(sys.executable, ['python'] + sys.argv)

    # Now we can start generating rolls
    reroll = True
    while True:
        # Generate new roll
        # Do not generate a new roll if gold is negative
        if reroll:
            cur_roll = roll(level)

        # Display shop
        display_roll(cur_roll, gold, cur_team.team)

        # Reroll using 'd'
        # Just break out of this look to generate a new shop
        next_in = input().strip()
        while next_in != 'd':
            # Buy a unit using numbers
            if next_in in ['1', '2', '3', '4', '5']:
                idx = int(next_in) - 1
                # Remove cost from current gold and add gold to team
                if gold >= cur_roll[idx].cost:
                    gold -= cur_roll[idx].cost
                    cur_team.add_unit(cur_roll[idx].name)
                    cur_roll[idx] = Unit(None, 'BLANK', None)
                else:
                    # print("You don't have enough gold!")
                    pass

            # Display current team using 's' (also allows selling)
            if next_in == 's':
                # Clear console
                os.system('cls' if os.name == 'nt' else 'clear')

                # Display team
                print(cur_team)

                # If user wants to sell a unit
                while True:
                    next_in_sell = input("Use numbers to sell. Press any other key to see the shop again.\nYour current gold amount is: " + str(gold) + '\n')
                    try:
                        # If user does not attempt to sell a valid champion, return to shop screen
                        index_to_sell = int(next_in_sell)
                        if index_to_sell not in range(1, len(cur_team) + 1):
                            break
                        # Otherwise, sell the unit and add its sell cost to your total gold
                        else:
                            # Remember that the shop is 1 indexed but lists are 0 indexed
                            gold += cur_team.team[index_to_sell - 1].sell_cost
                            cur_team.sell_unit(index_to_sell - 1)

                            # Clear console
                            os.system('cls' if os.name == 'nt' else 'clear')

                            # Display team
                            print(cur_team)

                    # If user enters a value that cannot be interpreted as an integer, return to shop
                    except ValueError:
                        break

            # Use 'p' to restart
            if next_in == 'p':
                print('restarting...')
                os.execv(sys.executable, ['python'] + sys.argv)

            # Display current shop
            display_roll(cur_roll, gold, cur_team.team)

            # Read in next input
            next_in = input().strip()

        # Since we rerolled, reduce gold by 2
        if gold >= 2:
            gold -= 2
            reroll = True
        else:
            reroll = False


if __name__ == '__main__':
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print('Usage: python rolldown.py {set_info}')
        sys.exit()
    main(sys.argv[1])
