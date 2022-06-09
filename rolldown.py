"""Simulate rolls in TFT."""

# Standard libraries
import json
import os
from pathlib import Path
import random
import sys


# Pip managed packages
# pylint: disable=import-error
from termcolor import colored
if os.name == 'nt':
    from msvcrt import getwch as getch
else:
    from getch import getch


# Local files
# pylint: disable=wrong-import-position
from constants import CHAMPION_POOL, CHAMPION_AMOUNTS, LEVEL_ODDS, LEVEL_EXP


# random.seed(112358)


# Make sure odds make sense
assert all((sum(odds) == 100 for odds in LEVEL_ODDS.values())), "Error in level odds."


# Helper function to read input directory
def read_database(input_dir):
    """Read in units and traits."""
    # Read in units
    with open(Path(input_dir) / 'champions.json', encoding='utf-8') as champions_file:
        champions_list = json.loads(champions_file.read())

    # Read in traits
    with open(Path(input_dir) / 'traits.json', encoding='utf-8') as traits_file:
        traits_list = json.loads(traits_file.read())

    # Parse unit data
    champions = {}
    for champ in champions_list:
        # If champion has fewer than 2 traits, ignore it
        # Since it is a target dummy, voidspawn, tome, Veigar, etc.
        if len(champ['traits']) < 2:
            continue

        # Add to champions list
        champions[champ['name']] = Unit(champ['cost'], champ['name'], \
            champ['traits'], champ['championId'])

        # Add to champion pool
        CHAMPION_POOL[champ['cost']] += [champions[champ['name']]] * CHAMPION_AMOUNTS[champ['cost']]

    # Parse trait data
    traits = {}
    for trait in traits_list:
        # Extract trait breakpoints and styles from trait data
        breakpoints = []
        styles = []
        for b_p in trait['sets']:
            breakpoints.append(b_p['min'])
            styles.append(b_p['style'])

        # Add to traits list
        traits[trait['name']] = Trait(trait['name'], breakpoints, styles)

    return champions, traits


class Unit:
    """Class containing unit information."""
    def __init__(self, cost, name, traits, id_name, level=1):
        # Check if unit is a BLANK placeholder
        if name == 'BLANK':
            self.name = name
            return

        # Information that the unit needs
        self.cost = cost
        self.name = name
        self.traits = [trait.strip() for trait in traits]
        self.id_name = id_name

        self.level = level

        # Calculate sell cost
        if level == 1:
            self.sell_cost = cost
        elif cost == 1 and level == 2:
            self.sell_cost = 3
        else:
            self.sell_cost = 3 ** (level - 1) * cost - 1

    def __str__(self):
        """Return string representation of a unit."""
        if self.name == 'BLANK':
            return 'BLANK\n'
        return self.name + ', ' + str(self.cost) + ', ' + ', '.join(self.traits) + '\n'

    def __repr__(self):
        """Return self representation of a unit."""
        return str(self)

    def __hash__(self):
        """Hash units by name only."""
        return hash(self.name)

    # This one is used by the in and == builtin!
    def __eq__(self, other):
        """Compare units by name."""
        if not isinstance(other, Unit):
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
        return Unit(self.cost, self.name, self.traits, self.id_name, self.level + 1)


class Trait:
    """Class containing trait information (inclding breakpoints and icon style)."""
    def __init__(self, name, breakpoints, styles):
        self.name = name
        self.breakpoints = breakpoints
        self.styles = styles
        assert len(breakpoints) == len(styles), 'Error reading in traits'

    def __str__(self):
        """Return string representation of a trait."""
        str_breaks = '/'.join([str(breaks) for breaks in self.breakpoints])
        str_styles = '/'.join([str(styles) for styles in self.styles])
        return self.name + ': ' + str_breaks + ' ' + 'with style(s) ' + str_styles + '\n'

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
        str_traits = '\n'.join(self.get_traits())

        # Put it all together
        units = "\nThis is the current team:\n" + ''.join(str_team) + '\n'
        traits = "Here are the current traits:\n" + str_traits
        return units + traits

    def __repr__(self):
        """Return the self representation of a team."""
        return str(self)

    def __len__(self):
        """Return the length of a team."""
        return len(self.team)

    def __contains__(self, item):
        """Make Team play nicely with 'in'."""
        return item in self.team

    def add_unit(self, unit):
        """Add unit to a team."""
        assert isinstance(unit, str), "Error attempting to add unknown type to team."
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
                twos = [1 if unit.unit_compare_level(upgraded_unit) else 0 for unit in self.team]
                amount_2 = sum(twos)
                if amount_2 == 3:
                    # Remove previous copies
                    self.team = [u for u in self.team if not u.unit_compare_level(upgraded_unit)]

                    # Add upgraded copy
                    upgraded_unit = upgraded_unit.upgrade()
                    self.team.append(upgraded_unit)

            # Otherwise, just add the unit
            else:
                self.team.append(new_unit)

    def remove_unit(self, unit_index):
        """Sell a unit from your board."""
        assert isinstance(unit_index, int), "Error in trying to sell unit"
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
        base_unit = Unit(sold_unit.cost, sold_unit.name, sold_unit.traits, sold_unit.id_name)
        quantities = [0, 1, 3, CHAMPION_AMOUNTS[sold_unit.cost]]
        for _ in range(quantities[sold_unit.level]):
            CHAMPION_POOL[sold_unit.cost].append(base_unit)


    def get_traits(self):
        """Extract the activated traits from a team."""
        str_traits = []
        for trait, amount in self.traits.items():
            if amount >= self.traits_dict[trait].breakpoints[-1]:
                last_break = str(self.traits_dict[trait].breakpoints[-1])
                str_traits.append(str(trait) + ' '  + str(amount) + '/' + last_break)
            else:
                next_bp = next(bp for bp in self.traits_dict[trait].breakpoints if bp >= amount)
                str_traits.append(str(trait) + ' '  + str(amount) + '/' + str(next_bp))

        return str_traits


class Game:
    """Class that runs and manages the rolldown."""
    def __init__(self, input_dir, gold=None, level=None):
        # Read in database
        champions_dict, traits_dict = read_database(input_dir)
        self.champions_dict = champions_dict
        self.traits_dict = traits_dict

        # Create new team
        self.team = Team(self.champions_dict, self.traits_dict)

        # Gold and level member variables
        # This is set by user input in self.rolldown()
        self.gold = gold
        self.level = level
        self.exp = 0

    def __str__(self):
        """Display the current team"""
        return str(self.team)

    # Helper function that simulates a single roll based on level
    def roll(self, first_roll=False):
        """Roll for champions based on level."""
        assert self.level in range(1, 12)

        # If this roll is a reroll, cost 2 gold
        if not first_roll:
            self.gold -= 2

        # 5 Slots
        # For each slot, we roll a random cost
        odds = LEVEL_ODDS[self.level]
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

    def display_roll(self, current_roll):
        """Display the champions in the current shop."""
        # Clear console
        os.system('cls' if os.name == 'nt' else 'clear')

        # Instructions
        print("Use number keys to buy, 'd' to reroll, and 's' to see current team and traits.")
        print("Press 'p' to restart.")
        print("Press 'm' to quit.")
        print("Press 'f' to buy exp (4 gold for 4 exp).")
        print('Your current gold amount is:', self.gold)
        print(f'Your current level is: {self.level}   {self.exp} / {LEVEL_EXP[self.level]}')
        if self.gold < 2:
            print('You do not have enough gold to reroll!')

        # Convert current roll to string form
        str_roll = ''
        for idx, champ in enumerate(current_roll):
            if champ in self.team:
                str_roll += colored('[' + str(idx + 1) + '] ' + str(champ), 'green')
            else:
                str_roll += '[' + str(idx + 1) + '] ' + str(champ)

        # Display current roll
        print(str_roll, end='')

    def buy_unit(self, cur_roll, next_in):
        """Buy a unit for the team."""
        idx = int(next_in) - 1
        # Remove cost from current gold and add gold to team
        cur_unit = cur_roll[idx]
        if cur_unit.name != 'BLANK' and self.gold >= cur_unit.cost:
            self.gold -= cur_unit.cost
            self.team.add_unit(cur_unit.name)
            cur_roll[idx] = Unit(None, 'BLANK', None, None)
        else:
            # print("You don't have enough gold!")
            pass

    def sell_unit(self, index):
        """Sell a unit from the team."""
        # Add gold equal to sell cost of unit
        self.gold += self.team.team[index].sell_cost

        # Remove unit from team
        self.team.remove_unit(index)

    def check_team(self):
        """Check team and/or sell unit."""
        # Clear console
        os.system('cls' if os.name == 'nt' else 'clear')

        # Display team
        print(self.team)

        # If user wants to sell a unit
        while True:
            next_in_sell = input("Use numbers + 'enter' to sell.\n" +
                "Press any other key to see the shop again.\n" +
                "Your current gold amount is: " + str(self.gold) + '\n' +
                f'Your current level is: {self.level}   {self.exp} / {LEVEL_EXP[self.level]}\n')
            try:
                # If user does not attempt to sell a valid champion, return to shop
                index_to_sell = int(next_in_sell)
                if index_to_sell not in range(1, len(self.team) + 1):
                    break

                # Otherwise, sell the unit and add its sell cost to your total gold
                # Remember that the shop is 1 indexed but lists are 0 indexed
                self.sell_unit(index_to_sell - 1)

                # Clear console
                os.system('cls' if os.name == 'nt' else 'clear')

                # Display team
                print(self.team)

            # If user enters a value that is not an int, return to shop
            except ValueError:
                break

    def buy_exp(self):
        """Buy experience to level up."""
        # Can't buy exp if not enough gold or level 10
        if self.gold < 4 or self.level > 9:
            return

        # Add exp, subtract gold
        self.exp += 4
        self.gold -= 4

        # Check for level up
        while self.exp >= LEVEL_EXP[self.level]:
            self.exp -= LEVEL_EXP[self.level]
            self.level += 1

    def rolldown(self):
        """Simulate the rolldown."""
        # First, read in a level between 1 and 11 inclusive
        # Lots of error checking to make sure user doesn't enter in an invalid value
        while True:
            try:
                # Set level
                user_in = input('Enter your current level between 1 and 11 inclusive: ')
                start_level = int(user_in)
                while start_level not in range(1, 12):
                    user_in = input('Enter your current level between 1 and 11 inclusive: ')
                    start_level = int(user_in)

                # Set starting gold
                start_gold = int(input('Enter the amount of gold you want to start with: '))
                break
            except ValueError:
                print('Invalid input, restarting...')
                os.execv(sys.executable, ['python'] + sys.argv)

        # Update member variables
        self.gold = start_gold
        self.level = start_level

        # Now we can start generating rolls
        first_roll = True
        reroll = True
        while True:
            # Generate new roll
            # Do not generate a new roll if gold is too low
            if reroll:
                cur_roll = self.roll(first_roll)

            # Display shop
            self.display_roll(cur_roll)
            first_roll = False

            # Read in input
            next_in = getch()
            while True:
                # Reroll
                if next_in == 'd':
                    break

                # Buy EXP
                if next_in == 'f':
                    self.buy_exp()

                # Buy a unit using numbers
                elif next_in in ['1', '2', '3', '4', '5']:
                    self.buy_unit(cur_roll, next_in)

                # Display current team using 's' (also allows selling)
                elif next_in == 's':
                    self.check_team()

                # Use 'p' to restart
                elif next_in == 'p':
                    print('restarting...')
                    os.execv(sys.executable, ['python'] + sys.argv)

                # Use 'm' to quit
                elif next_in == 'm':
                    print('Quitting...')
                    print('Final results:')
                    print(self.team)
                    sys.exit()

                # Display current shop
                self.display_roll(cur_roll)

                # Read in next input
                next_in = getch()

            # Check if we can reroll
            reroll = self.gold >= 2


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
