"""Non-game classes used by rolldown."""

from shared.networking_client import send_message
from shared.rolldown_enums import THREE_STARRED


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
