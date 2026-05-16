"""Non-game classes used by rolldown."""

from shared.networking_client import send_message
from shared.rolldown_enums import BENCH_SLOTS, BOARD_COLS, BOARD_ROWS, THREE_STARRED


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
    """Class containing trait information (including breakpoints and icon style)."""
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

    def active_index(self, count):
        """Index of the highest breakpoint that ``count`` satisfies (or None)."""
        active = None
        for idx, breakpoint in enumerate(self.breakpoints):
            if count >= breakpoint:
                active = idx
        return active

    def style_tier(self, count):
        """Return the background tier for the trait at ``count`` units.

        Tiers (low -> high): ``'bronze'``, ``'silver'``, ``'gold'``,
        ``'prismatic'``.  Returns ``None`` when the trait is not active.

        Rules:
        * The lowest breakpoints are bronze, the middle ones silver and the
          upper ones gold.
        * A breakpoint of 10 or more is prismatic/diamond, and the breakpoint
          immediately before it is gold.
        * Multiple breakpoints may map to the same tier (this is fine as long
          as it is consistent).
        """
        idx = self.active_index(count)
        if idx is None:
            return None

        breakpoints = self.breakpoints

        # A breakpoint of 10+ is always prismatic.
        if breakpoints[idx] >= 10:
            return 'prismatic'

        # The breakpoint right before a 10+ (prismatic) breakpoint is gold.
        if idx + 1 < len(breakpoints) and breakpoints[idx + 1] >= 10:
            return 'gold'

        # Distribute the remaining (non-prismatic) breakpoints across
        # bronze (low) / silver (middle) / gold (high), consistently.
        non_prismatic = [i for i, b in enumerate(breakpoints) if b < 10
                         and not (i + 1 < len(breakpoints) and breakpoints[i + 1] >= 10)]
        if not non_prismatic:
            return 'gold'

        position = non_prismatic.index(idx)
        total = len(non_prismatic)
        if total == 1:
            return 'bronze'

        # First third -> bronze, middle third -> silver, last third -> gold.
        ratio = position / (total - 1)
        if ratio < 1 / 3:
            return 'bronze'
        if ratio < 2 / 3:
            return 'silver'
        return 'gold'


class Team:
    """A team of units split between a hex ``board`` and a square ``bench``.

    Only units on the ``board`` contribute to traits.  The number of units
    allowed on the board is capped at ``player_level``.
    """
    def __init__(self, champions_dict, traits_dict, client_socket, player_level=1):
        # Bench: fixed list of BENCH_SLOTS slots (None == empty).
        self.bench = [None] * BENCH_SLOTS

        # Board: mapping of (row, col) -> Unit. row in [0, BOARD_ROWS),
        # col in [0, BOARD_COLS).
        self.board = {}

        # Maximum number of units allowed on the board.
        self.player_level = player_level

        # Transient holding area used only inside a buy transaction. Lets a
        # purchase that would immediately upgrade go through even when the
        # bench is full (the copies combine away before the bench is needed).
        self._pending = []

        # Current activated traits (recomputed from the board only).
        self.traits = {}

        # Dictionary of all champions and traits
        self.champions_dict = champions_dict
        self.traits_dict = traits_dict

        # Socket to send messages
        self.client_socket = client_socket

    # region representation / compatibility helpers
    def ordered_units(self):
        """Return [(location, unit), ...] (bench first, then board)."""
        result = []
        for idx, unit in enumerate(self.bench):
            if unit is not None:
                result.append((('bench', idx), unit))
        for pos in sorted(self.board):
            result.append((('board', pos), self.board[pos]))
        return result

    @property
    def team(self):
        """Backward-compatible flat list of every owned unit."""
        return [unit for _, unit in self.ordered_units()]

    def all_units(self):
        """Every unit currently owned (board + bench), order unspecified."""
        return self.team

    def __str__(self):
        """Return the String representation of a team."""
        str_team = [str([idx + 1]) + ' ' + unit.name + ' ' + str(unit.level) +
                    ' (sells for ' + str(unit.sell_cost) + ')\n'
                    for idx, unit in enumerate(self.team)]
        str_traits = '\n'.join(self.get_traits())
        units = "\nThis is the current team:\n" + ''.join(str_team) + '\n'
        traits = "Here are the current traits:\n" + str_traits
        return units + traits

    def __repr__(self):
        """Return the self representation of a team."""
        return str(self)

    def __len__(self):
        """Return the total number of owned units."""
        return len(self.team)

    def __contains__(self, item):
        """Make Team play nicely with 'in' (checks board + bench)."""
        return item in self.team

    def __iter__(self):
        """Iterate over every owned unit."""
        return iter(self.team)
    # endregion

    # region bench / board placement
    def first_empty_bench(self):
        """Return the index of the leftmost empty bench slot (or None)."""
        for idx, unit in enumerate(self.bench):
            if unit is None:
                return idx
        return None

    def bench_is_full(self):
        """True when every bench slot is occupied."""
        return self.first_empty_bench() is None

    def board_is_full(self):
        """True when the board already holds ``player_level`` units."""
        return len(self.board) >= self.player_level

    def add_unit(self, unit):
        """Add a single bought unit.

        Normally placed on the leftmost empty bench slot.  Returns ``True`` on
        success and ``False`` if the bench is full *and* the purchase would
        not immediately upgrade (the caller must not charge gold then).
        """
        return self.add_units(unit, 1)

    def add_units(self, unit, count):
        """Add ``count`` copies of ``unit`` as a single atomic purchase.

        Copies that do not fit on the bench go to a transient buffer; if they
        all combine away via upgrades the purchase succeeds even with a full
        bench.  If any copy is left stranded the whole transaction is rolled
        back and ``False`` is returned (no side effects).
        """
        assert isinstance(unit, str), "Error attempting to add unknown type to team."

        # BLANKS are units that were already bought.
        if unit == 'BLANK':
            print('There is no unit in this slot')
            return False

        # Error checking
        try:
            new_unit = self.champions_dict[unit]
        except KeyError:
            print('KeyError raised, check champion spelling: ' + unit)
            return False

        snapshot = self._snapshot()

        for _ in range(count):
            slot = self.first_empty_bench()
            if slot is not None:
                self.bench[slot] = new_unit.copy()
            else:
                # No bench room - hold it transiently; it must combine away.
                self._pending.append(new_unit.copy())

        # Buying a third copy can trigger (cascading) star-ups.
        self._resolve_upgrades()

        if self._pending:
            # A copy could not be placed and did not combine -> reject.
            self._restore(snapshot)
            return False

        # Recompute in case an upgrade happened on the board.
        self._recompute_traits()
        return True

    def _snapshot(self):
        """Capture enough state to roll back a failed buy transaction."""
        return (list(self.bench), dict(self.board),
                list(self._pending), set(THREE_STARRED))

    def _restore(self, snapshot):
        """Roll back to a previously captured snapshot."""
        bench, board, pending, three = snapshot
        self.bench = list(bench)
        self.board = dict(board)
        self._pending = list(pending)
        THREE_STARRED.clear()
        THREE_STARRED.update(three)
    # endregion

    # region upgrades
    def _locations_of(self, name, level):
        """Return [(location, unit), ...] for every copy matching name+level."""
        matches = []
        for idx, unit in enumerate(self.bench):
            if unit is not None and unit.name == name and unit.level == level:
                matches.append((('bench', idx), unit))
        for pos, unit in self.board.items():
            if unit.name == name and unit.level == level:
                matches.append((('board', pos), unit))
        for unit in self._pending:
            if unit.name == name and unit.level == level:
                matches.append((('pending', unit), unit))
        return matches

    def _remove_at(self, location):
        """Remove and return the unit at ``location`` without side effects."""
        kind, key = location
        if kind == 'bench':
            unit = self.bench[key]
            self.bench[key] = None
            return unit
        if kind == 'pending':
            for i, unit in enumerate(self._pending):
                if unit is key:
                    return self._pending.pop(i)
            return None
        unit = self.board.pop(key)
        return unit

    def _all_owned_pairs(self):
        """Every (name, level) currently owned, including pending copies."""
        pairs = {(u.name, u.level) for u in self.team}
        pairs |= {(u.name, u.level) for u in self._pending}
        return pairs

    def _resolve_upgrades(self):
        """Combine any three matching units, cascading to higher stars."""
        changed = True
        while changed:
            changed = False
            # Look at a snapshot of every (name, level) currently owned.
            seen = self._all_owned_pairs()
            for name, level in seen:
                matches = self._locations_of(name, level)
                if len(matches) < 3:
                    continue

                # Use exactly three copies for the combine.
                used = matches[:3]
                prefer_board = any(loc[0] == 'board' for loc, _ in used)
                template = used[0][1]

                for loc, _ in used:
                    self._remove_at(loc)

                upgraded = template.upgrade()

                placed = False
                if prefer_board:
                    # Reuse one of the freed board cells if possible.
                    for loc, _ in used:
                        if loc[0] == 'board' and loc[1] not in self.board:
                            self.board[loc[1]] = upgraded
                            placed = True
                            break
                if not placed:
                    slot = self.first_empty_bench()
                    if slot is not None:
                        self.bench[slot] = upgraded
                        placed = True
                if not placed:
                    # Board was preferred but somehow taken - fall back to it.
                    for loc, _ in used:
                        if loc[0] == 'board':
                            self.board[loc[1]] = upgraded
                            placed = True
                            break
                if not placed:
                    # Nowhere to put it yet - hold it transiently so it can
                    # cascade-combine (or fail the transaction cleanly).
                    self._pending.append(upgraded)

                changed = True
                break
    # endregion

    # region selling
    def _sell(self, sold_unit):
        """Shared bookkeeping when a unit leaves the team for good."""
        # If unit was 3 starred, allow it to be rolled again.
        if sold_unit.name in THREE_STARRED and sold_unit.level == 3:
            THREE_STARRED.remove(sold_unit.name)

        # Send message about selling unit to the server.
        message = f'sell: {sold_unit.name}: {sold_unit.level}'
        send_message(self.client_socket, message)

        self._recompute_traits()
        return sold_unit

    def sell_from_bench(self, idx):
        """Sell the unit in bench slot ``idx``; return the sold Unit."""
        unit = self.bench[idx]
        assert isinstance(unit, Unit), "Error in trying to sell unit"
        self.bench[idx] = None
        return self._sell(unit)

    def sell_from_board(self, pos):
        """Sell the unit at board position ``pos``; return the sold Unit."""
        unit = self.board.get(pos)
        assert isinstance(unit, Unit), "Error in trying to sell unit"
        del self.board[pos]
        return self._sell(unit)

    def remove_unit(self, unit_index):
        """Backward-compatible sell by flat index (bench first, then board)."""
        assert isinstance(unit_index, int), "Error in trying to sell unit"
        location, _ = self.ordered_units()[unit_index]
        if location[0] == 'bench':
            return self.sell_from_bench(location[1])
        return self.sell_from_board(location[1])
    # endregion

    # region moving
    def move_within_bench(self, src, dst):
        """Swap two bench slots."""
        self.bench[src], self.bench[dst] = self.bench[dst], self.bench[src]
        return True

    def move_within_board(self, src, dst):
        """Swap two board positions (does not change board count)."""
        src_unit = self.board.get(src)
        dst_unit = self.board.get(dst)
        if src_unit is None:
            return False
        if dst_unit is None:
            del self.board[src]
            self.board[dst] = src_unit
        else:
            self.board[src], self.board[dst] = dst_unit, src_unit
        self._recompute_traits()
        return True

    def move_bench_to_board(self, bench_idx, pos):
        """Move a bench unit onto the board.

        Swaps if the target cell is occupied.  Moving onto an empty cell is
        rejected (returns ``False``) when it would exceed ``player_level``.
        """
        unit = self.bench[bench_idx]
        if unit is None:
            return False

        occupant = self.board.get(pos)
        if occupant is None:
            if self.board_is_full():
                return False
            self.board[pos] = unit
            self.bench[bench_idx] = None
        else:
            self.board[pos] = unit
            self.bench[bench_idx] = occupant

        self._recompute_traits()
        return True

    def move_board_to_bench(self, pos, bench_idx=None):
        """Move a board unit to the bench (specific slot or leftmost empty)."""
        unit = self.board.get(pos)
        if unit is None:
            return False

        if bench_idx is None:
            bench_idx = self.first_empty_bench()
            if bench_idx is None:
                return False

        occupant = self.bench[bench_idx]
        if occupant is None:
            self.bench[bench_idx] = unit
            del self.board[pos]
        else:
            self.bench[bench_idx] = unit
            self.board[pos] = occupant

        self._recompute_traits()
        return True
    # endregion

    # region traits
    def _recompute_traits(self):
        """Rebuild the activated traits using the board units only."""
        traits = {}

        # Each unique champion on the board contributes its traits once.
        unique = {}
        for unit in self.board.values():
            unique.setdefault(unit.name, unit)

        for unit in unique.values():
            for trait in unit.traits:
                traits[trait] = traits.get(trait, 0) + 1

            # If unit is a dragon, its origin (first) trait is tripled.
            if 'Dragon' in unit.traits:
                traits[unit.traits[0]] += 2

        self.traits = {t: c for t, c in traits.items() if c > 0}

    def breakpoint_target(self, trait_name, amount):
        """Breakpoint to display for ``amount`` units of ``trait_name``.

        When the count has reached a breakpoint, the *next* breakpoint is
        shown (e.g. Psionic 2/4 breakpoints with 2 units -> ``2/4``). Once the
        final breakpoint is reached the final breakpoint is shown.
        """
        breakpoints = self.traits_dict[trait_name].breakpoints
        higher = [bp for bp in breakpoints if bp > amount]
        return higher[0] if higher else breakpoints[-1]

    def sorted_traits(self):
        """Active traits ordered by closeness to their next breakpoint.

        Returns ``[(name, amount, target), ...]`` sorted so a trait that is
        nearer its next breakpoint appears first (1/1 before 2/3 before 1/2).
        Ties break on higher count, then name.
        """
        rows = []
        for name, amount in self.traits.items():
            target = self.breakpoint_target(name, amount)
            rows.append((name, amount, target))

        rows.sort(key=lambda r: (-(r[1] / r[2]), -r[1], r[0]))
        return rows

    def get_traits(self):
        """Extract the activated traits from the board (closest first)."""
        return [f'{name} {amount}/{target}'
                for name, amount, target in self.sorted_traits()]
    # endregion
