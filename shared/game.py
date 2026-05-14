"""Definition of Game class used by rolldown."""

# Standard libraries
from copy import deepcopy
import json
import os
import random
import subprocess
import sys
import time


# Third party libraries
from termcolor import colored
if os.name == 'nt':
    from msvcrt import getwch as getch
else:
    from getch import getch


# Local imports
from shared.networking_client import init_rolldown_client, send_message
from shared.resources import read_database
from shared.rolldown_classes import Team, Unit
from shared.rolldown_enums import CHAMPION_POOL, LEVEL_EXP, LEVEL_ODDS, SERVER_LOG_FILE,\
    SHOP_SLOTS, THREE_STARRED


class Game:
    """Class that runs and manages the rolldown."""
    def __init__(self, input_dir, gold=None, level=None):
        # Read in database
        champions_dict, traits_dict = read_database(input_dir)
        self.champions_dict = champions_dict
        self.traits_dict = traits_dict

        # Gold and level member variables
        # This is set by user input in self.rolldown()
        self.gold = gold
        self.level = level
        self.exp = 0

        # Keep track of the current shop
        self.cur_shop = None

        # Check if server is running.
        try:
            # self.client_socket = init_rolldown_client(0)
            raise ConnectionRefusedError
        except ConnectionRefusedError:
            # Start server and reset log if not running.
            SERVER_LOG_FILE.unlink(missing_ok=True)
            with open(str(SERVER_LOG_FILE), mode='a', encoding='utf-8') as outfile:
                subprocess.Popen(['python', 'networking_server.py', input_dir], \
                    stdout=outfile, stderr=outfile)

            # Indicate that a new server is being started
            print('No active server found, starting new server...')

            # Wait before trying to connect to server
            time.sleep(0.5)
            self.client_socket = init_rolldown_client(0)

        # Create new team
        self.team = Team(self.champions_dict, self.traits_dict, self.client_socket)

    def __str__(self):
        """Display the current team"""
        return str(self.team)

    def build_champion_pool(self):
        """Rebuild the champion pool using message from the server."""
        full_pool = json.loads(send_message(self.client_socket, 'pool'))
        cur_pool = {1: [], 2: [], 3: [], 4: [], 5: []}
        for name, amount in full_pool.items():
            # Three starred units can no longer be rolled
            if name not in THREE_STARRED:
                cur_unit = self.champions_dict[name]
                cur_pool[cur_unit.rarity] += ([cur_unit] * amount)

        return cur_pool

    # Helper function that rolls a loaded dice shop
    def loaded_dice(self, unit):
        """Roll the loaded dice."""
        level = self.level
        assert isinstance(unit, Unit), 'Error: invalid input for unit type'
        assert isinstance(level, int), 'Error: invalid input for level'

        # Get odds at current level
        odds = LEVEL_ODDS[level]

        # Get unit's traits
        traits = unit.traits

        # Get current champion pool
        cur_pool = self.build_champion_pool()
        print(cur_pool)

        # For each slot in the shop, roll a rarity depending on current level
        costs = random.choices(population=[1, 2, 3, 4, 5], weights=odds, k=SHOP_SLOTS)

        # Rolled units
        results = []

        # For each rarity that was rolled
        for i in costs:
            # Find a valid champion
            candidates = []
            for possible in cur_pool[i]:
                # If at least one trait is shared, add as potential candidate
                if set(possible.traits) & set(traits):
                    candidates.append(possible)

            # If candidates is empty, reroll rarities until candidate is available
            # Remove already rolled rarity from contention
            remaining_odds = deepcopy(LEVEL_ODDS[level])
            remaining_odds[i - 1] = 0
            while not candidates:
                # If we run out of rarities, just choose a random unit with the same rarity
                if sum(remaining_odds) == 0:
                    # Choose random rarity
                    odds = LEVEL_ODDS[level]
                    cost = random.choices(population=[1, 2, 3, 4, 5], weights=odds, k=1)[0]

                    # If all units of that rarity are unavailable, just pick a random unit
                    if not cur_pool[cost]:
                        total_pool = [unit for ls in cur_pool.values() for unit in ls]
                        replacement = random.choice(total_pool)
                        candidates.append(replacement)

                    # Otherwise, pick a unit of the same cost
                    else:
                        replacement = random.choice(cur_pool[cost])
                        candidates.append(replacement)

                else:
                    # Get new rarity and remove that rarity from contention
                    cost = random.choices(population=[1, 2, 3, 4, 5], weights=remaining_odds, k=1)
                    cost = cost[0]
                    remaining_odds[cost - 1] = 0

                    # Attempt to find more candidates
                    for possible in CHAMPION_POOL[cost]:
                        # If at least one trait is shared, add as potential candidate
                        if set(possible.traits) & set(traits):
                            candidates.append(possible)

            # Choose a random candidate
            chosen = random.choice(candidates)
            results.append(chosen)

            # Remove chosen champion from pool
            cur_pool[chosen.rarity].remove(chosen)

        # Return rolled shop
        return results

    # Helper function that simulates a single roll based on level
    def roll(self, first_roll=False):
        """Roll for champions based on level."""
        assert self.level in range(1, 12)

        # Rebuild current champion pool
        cur_pool = self.build_champion_pool()

        # If this roll is a reroll, cost 2 gold
        if not first_roll:
            self.gold -= 2

        # 5 Slots
        # For each slot, we roll a random cost
        odds = LEVEL_ODDS[self.level]
        costs = random.choices(population=[1, 2, 3, 4, 5], weights=odds, k=5)

        # For each result, we choose a random champion from cur_pool
        results = []
        for cost in costs:
            # If there are no more champions of the cost (unlikely but possible),
            # simply choose a random champion. Also keep in mind that 3 starred
            # units can no longer be rolled
            can_roll = []
            for unit in cur_pool[cost]:
                can_roll.append(unit)

            # If no unit can be rolled, add any eligible unit
            if not can_roll:
                # print('Out of', cost, 'costs!')

                # Build a pool of all champions to choose a replacement
                total_pool = [unit for ls in cur_pool.values() for unit in ls]
                replacement = random.choice(total_pool)

                # Remove chosen champion from pool
                cur_pool[replacement.rarity].remove(replacement)

                # Add chosen champion to results
                results.append(replacement)

                # print('The replacement unit is', replacement)

            else:
                # Roll random eligible champion
                resulting_champ = random.choice(can_roll)

                # Remove chosen champion from pool
                cur_pool[resulting_champ.rarity].remove(resulting_champ)

                # Add result to list of resulting rolls
                results.append(resulting_champ)

        # Take each rolled champion out of the pool
        for unit in results:
            send_message(self.client_socket, f'buy: {unit.name}')

        return results

    def display_roll(self):
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
        for idx, champ in enumerate(self.cur_shop):
            if champ in self.team:
                str_roll += colored('[' + str(idx + 1) + '] ' + str(champ), 'green')
            else:
                str_roll += '[' + str(idx + 1) + '] ' + str(champ)

        # Display current roll
        print(str_roll, end='')

    def buy_unit(self, next_in):
        """Buy a unit for the team (1-indexed)."""
        idx = int(next_in) - 1
        # Remove cost from current gold and add gold to team
        cur_unit = self.cur_shop[idx]
        if cur_unit.name != 'BLANK' and self.gold >= cur_unit.cost:
            self.gold -= cur_unit.cost
            self.team.add_unit(cur_unit.name)
            self.cur_shop[idx] = Unit(None, 'BLANK', None, None)
        else:
            # print("You don't have enough gold!")
            pass

    def sell_unit(self, index):
        """Sell a unit from the team (0-indexed)."""
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
            # If leveling to 10, break
            if self.level == 9:
                self.level += 1
                self.exp = 0
                break

            # Increment level by 1 and decrease exp
            self.exp -= LEVEL_EXP[self.level]
            self.level += 1

    def quit(self):
        """Quit the game and print results."""
        print('Quitting...')
        print('Final results:')
        print(self.team)

        # Return units on the team to the pool
        for unit in self.team.team:
            send_message(self.client_socket, f'sell: {unit.name}: {unit.level}')

        # Return units in shop to the pool
        for unit in self.cur_shop:
            if unit.name != 'BLANK':
                send_message(self.client_socket, f'sell: {unit.name}: {unit.level}')

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
                # Add previously rolled champions back to the pool
                if not first_roll:
                    for unit in self.cur_shop:
                        if unit.name != 'BLANK':
                            send_message(self.client_socket, f'sell: {unit.name}: 1')

                # Roll new shop
                self.cur_shop = self.roll(first_roll)

            # Display shop
            self.display_roll()
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
                    self.buy_unit(next_in)

                # Display current team using 's' (also allows selling)
                elif next_in == 's':
                    self.check_team()

                # Use 'p' to restart
                elif next_in == 'p':
                    print('restarting...')
                    os.execv(sys.executable, ['python'] + sys.argv)

                # Use 'm' to quit
                elif next_in == 'm':
                    self.quit()
                    sys.exit()

                # Display current shop
                self.display_roll()

                # Read in next input
                next_in = getch()

            # Check if we can reroll
            reroll = self.gold >= 2
