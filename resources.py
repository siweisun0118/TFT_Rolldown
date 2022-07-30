"""File containing all resources used by rolldown."""


# Standard libraries
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import threading
import time


# Third party libraries
# pylint: disable=import-error
from termcolor import colored
if os.name == 'nt':
    from msvcrt import getwch as getch
else:
    from getch import getch


####### LOGGING RESOURCES #######
SERVER_LOG_FILE = Path('server_log')
####### END LOGGING RESOURCES #######


####### LOCKS #######
POOL_LOCK = threading.Lock()
####### END LOCKS #######


####### GAME RESOURCES #######
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

# Make sure odds make sense
assert all((sum(odds) == 100 for odds in LEVEL_ODDS.values())), "Error in level odds."
####### END GAME RESOURCES #######


####### UI ELEMENTS #######
# Size of splash art
SPLASH_SIZE = (1006, 596)

# Path to local resources
GEN_ASSETS = Path('General Assets')

# Port number for rolldown server
SERVER_PORT = 8000
####### END UI ELEMENTS #######


####### HELPER FUNCTIONS #######
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


# Helper function to serialize custom classes
def serialize(obj):
    """Serialize the object by converting its contents to a string."""
    return obj.name


### NETWORKING CLIENT FUNCTIONS ###
# Send a message over the socket
def send_message(client_socket, message):
    """Send a message to the server and get response."""
    client_socket.send(message.encode())

    # Get response
    response = ''
    while True:
        # Get message in chunks
        chunk = client_socket.recv(1024).decode()
        response += chunk
        if not chunk or chunk[-1] == '\0':
            break

    return response[:-1]


# Initialize the client socket
def init_rolldown_client(port):
    """Initialize the rolldown client on the given port number."""
    # Make sure that the client is not trying to use the same port as the server
    assert port != SERVER_PORT, 'Port 8000 is used by the server!'

    # Initialize the client socket and bind it to the given port
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = socket.gethostname()
    client_socket.bind((host, port))

    # Connect to server
    client_socket.connect((host, SERVER_PORT))

    # Return client socket
    return client_socket
### END NETWORKING CLIENT FUNCTIONS ###
####### END HELPER FUNCTIONS #######


####### OBJECT DEFINITIONS #######
class Unit:
    """Class containing unit information."""
    def __init__(self, rarity, name, traits, id_name, level=1):
        # Check if unit is a BLANK placeholder
        if name == 'BLANK':
            self.name = name
            return

        # Information that the unit needs
        self.rarity = rarity
        self.name = name
        self.traits = [trait.strip() for trait in traits]
        self.id_name = id_name

        self.level = level

        # SET 7: Added support for dragon units
        self.cost = self.rarity * 2 if 'Dragon' in self.traits else self.rarity

        # Calculate sell cost
        if level == 1:
            self.sell_cost = self.cost
        elif rarity == 1 and level == 2:
            self.sell_cost = 3
        else:
            self.sell_cost = 3 ** (level - 1) * self.cost - 1

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

    def copy(self):
        """Return a copy of the unit."""
        return Unit(self.rarity, self.name, self.traits, self.id_name, self.level)

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
        # 3 star units can no longer be rolled
        if self.level == 2:
            # Remove all remaining instances of this champion from the pool
            THREE_STARRED.add(self.name)

        # Sell cost changes when unit is upgraded
        return Unit(self.rarity, self.name, self.traits, self.id_name, self.level + 1)


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
    def __init__(self, champions_dict, traits_dict, client_socket):
        # Current team and traits
        self.team = []
        self.traits = {}

        # Dictionary of all champions and traits
        self.champions_dict = champions_dict
        self.traits_dict = traits_dict

        # Socket to send messages
        self.client_socket = client_socket

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
        """Add unit to a team. Do not send message to remove champion from pool."""
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

        # If it's a unique unit, add its traits to the team
        if new_unit not in self.team:
            for trait in new_unit.traits:
                if trait not in self.traits:
                    self.traits[trait] = 1
                else:
                    self.traits[trait] += 1

            # If unit is a dragon, origin trait is tripled
            if 'Dragon' in new_unit.traits:
                self.traits[new_unit.traits[0]] += 2

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
        # Error checking
        assert isinstance(unit_index, int), "Error in trying to sell unit"
        sold_unit = self.team[unit_index]
        assert isinstance(sold_unit, Unit)

        # Check if unit was unique
        count = 0
        for cur_unit in self.team:
            if cur_unit == sold_unit:
                count += 1

        # If unit is unique, remove its traits
        if count == 1:
            # If unit is a dragon, origin trait is tripled
            if 'Dragon' in sold_unit.traits:
                self.traits[sold_unit.traits[0]] -= 2

            for trait in sold_unit.traits:
                self.traits[trait] -= 1

                # If that brings the trait count to 0, remove that trait from the team's traits
                if not self.traits[trait]:
                    self.traits.pop(trait, None)

        # If unit was 3 starred, allow it to be rolled again
        if sold_unit.name in THREE_STARRED and sold_unit.level == 3:
            THREE_STARRED.remove(sold_unit.name)

        # Remove unit from team
        self.team.pop(unit_index)

        # Send message about selling unit to server
        message = f'sell: {sold_unit.name}: {sold_unit.level}'
        send_message(self.client_socket, message)


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

        # Gold and level member variables
        # This is set by user input in self.rolldown()
        self.gold = gold
        self.level = level
        self.exp = 0

        # Keep track of the current shop
        self.cur_shop = None

        # Check if server is running.
        try:
            self.client_socket = init_rolldown_client(0)
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
####### END OBJECT DEFINITIONS #######
