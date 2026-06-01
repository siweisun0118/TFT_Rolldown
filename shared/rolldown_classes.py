"""Non-game classes used by rolldown."""

from collections import OrderedDict

from shared.networking_client import send_message
from shared.rolldown_enums import BENCH_SLOTS, BOARD_LAYOUT, THREE_STARRED


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

    def upgrade(self, three_starred=None):
        """Return an upgraded version of the unit.

        ``three_starred`` is an optional set used to mark 3-star units so the
        server stops rolling them.  When omitted the module-level
        :data:`THREE_STARRED` global is updated (legacy behaviour).
        """
        if three_starred is None:
            three_starred = THREE_STARRED
        if self.level == 2:
            three_starred.add(self.name)

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

    def active_breakpoint_index(self, amount):
        """Return the index of the highest breakpoint reached by *amount*."""
        active = -1
        for idx, bp in enumerate(self.breakpoints):
            if amount >= bp:
                active = idx
            else:
                break
        return active

    def next_breakpoint(self, amount):
        """Return the next breakpoint that *amount* needs to reach."""
        for bp in self.breakpoints:
            if amount < bp:
                return bp
        return self.breakpoints[-1]

    def style_tier(self, amount):
        """Return the display tier (bronze/silver/gold/prismatic/inactive)."""
        idx = self.active_breakpoint_index(amount)
        if idx < 0:
            return 'inactive'

        bp = self.breakpoints[idx]
        style = self.styles[idx]

        if style == 4:
            return 'prismatic'
        if bp >= 10:
            return 'prismatic'
        if idx + 1 < len(self.breakpoints) and self.breakpoints[idx + 1] >= 10:
            return 'gold'
        if style == 1:
            return 'bronze'
        if style == 2:
            return 'silver'
        return 'gold'


class Team:
    """Class that represents a team of units (positional board + bench).

    The board now stores units in an :class:`collections.OrderedDict` keyed by
    a ``(row, column)`` tuple.  Units may be placed anywhere on the board
    (subject to the player's level), and the GUI's drag/drop logic uses the
    same coordinate system to address tiles.

    Traits are derived from **unique** unit names on the board – having
    multiple star-level copies of the same champion does not double-count
    their traits.
    """

    def __init__(self, champions_dict, traits_dict, client_socket,
                 bench_size=BENCH_SLOTS, board_layout=BOARD_LAYOUT,
                 three_starred=None):
        # OrderedDict keeps a stable iteration order which is handy for tests
        # and for backwards-compatible board listing.
        self.board_positions = OrderedDict()  # {(row, col): Unit}
        self.bench = [None] * bench_size
        self.bench_size = bench_size

        # Layout of board positions (sequence of (row, col)).  Used when a
        # placement does not specify an exact target tile.
        self.board_layout = tuple(board_layout)

        # Backwards-compat: index of (name, level) -> set of locations.
        # Locations are either ``('board', (row, col))`` or
        # ``('bench', bench_idx)``.  This lets us answer "how many copies of
        # X do I own?" in O(1) for buy / upgrade decisions (perf §1.3).
        self._unit_index = {}

        # Dictionary of all champions and traits
        self.champions_dict = champions_dict
        self.traits_dict = traits_dict

        # Socket to send messages (may be ``None`` for offline play)
        self.client_socket = client_socket

        # 3-star tracker – when provided, this is the Game-owned set used by
        # all upgrade calls.  Falls back to the module-level global.
        self.three_starred = three_starred if three_starred is not None else THREE_STARRED

    # ---------------------------------------------------------------- compat
    @property
    def team(self):
        """Backwards-compat alias for ``board + bench`` units."""
        return self.all_units()

    @property
    def board(self):
        """List of board units (in insertion order).

        Older callers expect ``team.board`` to be a list of units; we keep
        that as a derived view of :attr:`board_positions`.
        """
        return list(self.board_positions.values())

    @property
    def traits(self):
        """Live trait counts derived from unique board units."""
        return self._compute_traits()

    def all_units(self):
        return self.board + [u for u in self.bench if u is not None]

    def __str__(self):
        all_units = self.all_units()
        str_team = [
            f'[{idx + 1}] {unit.name} {unit.level} (sells for {unit.sell_cost})\n'
            for idx, unit in enumerate(all_units)
        ]
        str_traits = '\n'.join(self.get_traits())
        units = "\nThis is the current team:\n" + ''.join(str_team) + '\n'
        traits = "Here are the current traits:\n" + str_traits
        return units + traits

    def __repr__(self):
        return str(self)

    def __len__(self):
        return len(self.all_units())

    def __contains__(self, item):
        return item in self.all_units()

    # ----------------------------------------------------------------- index
    def _index_insert(self, unit, location):
        """Record that *unit* lives at *location*."""
        key = (unit.name, unit.level)
        self._unit_index.setdefault(key, set()).add(location)

    def _index_remove(self, unit, location):
        """Remove *unit* from the index at *location*."""
        key = (unit.name, unit.level)
        bucket = self._unit_index.get(key)
        if not bucket:
            return
        bucket.discard(location)
        if not bucket:
            self._unit_index.pop(key, None)

    def count_in_index(self, unit):
        """Return ``(board_count, bench_count)`` by inspecting actual storage."""
        return self.count_on_board(unit), self.count_on_bench(unit)

    def count_on_board(self, unit):
        """Return copies of unit on the board."""
        return sum(
            1 for u in self.board_positions.values() if u.unit_compare_level(unit)
        )

    def count_on_bench(self, unit):
        """Return copies of unit on the bench."""
        return sum(
            1 for u in self.bench if u is not None and u.unit_compare_level(unit)
        )

    # ---------------------------------------------------------------- traits
    def _compute_traits(self):
        """Aggregate trait counts from unique board champions.

        Multiple star-level copies of the same champion (same ``name``) only
        contribute once.  Mirrors the original behaviour from the pre-refactor
        :meth:`add_unit` implementation.
        """
        result = {}
        seen = set()
        for unit in self.board_positions.values():
            if unit.name in seen:
                continue
            seen.add(unit.name)
            for trait in unit.traits:
                result[trait] = result.get(trait, 0) + 1
            if 'Dragon' in unit.traits:
                result[unit.traits[0]] = result.get(unit.traits[0], 0) + 2
        return result

    # ----------------------------------------------------------------- helpers
    def board_count(self):
        return len(self.board_positions)

    def bench_count(self):
        return sum(1 for slot in self.bench if slot is not None)

    def bench_is_full(self):
        return self.bench_count() >= self.bench_size

    def first_open_bench_slot(self):
        for idx, slot in enumerate(self.bench):
            if slot is None:
                return idx
        return None

    def first_open_board_position(self):
        for pos in self.board_layout:
            if pos not in self.board_positions:
                return pos
        return None

    def remove_copies(self, unit):
        """Remove every copy of *unit* (matching name + level)."""
        board_removed = []
        for pos in list(self.board_positions.keys()):
            u = self.board_positions[pos]
            if u.unit_compare_level(unit):
                del self.board_positions[pos]
                self._index_remove(u, ('board', pos))
                board_removed.append(pos)
        bench_removed = []
        for idx, slot in enumerate(self.bench):
            if slot is not None and slot.unit_compare_level(unit):
                self._index_remove(slot, ('bench', idx))
                self.bench[idx] = None
                bench_removed.append(idx)
        return board_removed, bench_removed

    def place_upgraded(self, upgraded, board_removed, bench_removed):
        """Place an upgraded unit into a freed slot."""
        if board_removed:
            target = board_removed[0]
            self.board_positions[target] = upgraded
            self._index_insert(upgraded, ('board', target))
            return ('board', target)
        if bench_removed:
            target = bench_removed[0]
            self.bench[target] = upgraded
            self._index_insert(upgraded, ('bench', target))
            return ('bench', target)
        # No freed slot – fall back to first available.
        slot = self.first_open_bench_slot()
        if slot is not None:
            self.bench[slot] = upgraded
            self._index_insert(upgraded, ('bench', slot))
            return ('bench', slot)
        return None

    def maybe_upgrade(self, unit):
        """Trigger a 3-copy upgrade if the threshold is met.

        Returns the resulting (possibly upgraded) unit; callers can ignore
        the return value when they only care about the side effects.
        """
        board, bench = self.count_in_index(unit)
        if board + bench < 3:
            return unit
        board_removed, bench_removed = self.remove_copies(unit)
        upgraded = unit.upgrade(self.three_starred)
        self.place_upgraded(upgraded, board_removed, bench_removed)
        # Cascade for 2→3 star.
        if sum(self.count_in_index(upgraded)) >= 3:
            return self.maybe_upgrade(upgraded)
        return upgraded

    # -------------------------------------------------------------- buying
    def add_unit_to_bench(self, unit_name):
        """Buy a unit and place it on the bench (or merge if upgrade triggers)."""
        if unit_name == 'BLANK':
            return False
        try:
            unit_template = self.champions_dict[unit_name]
        except KeyError:
            print('KeyError raised, check champion spelling: ' + unit_name)
            return False
        new_unit = unit_template.copy()

        # Perf §1.5: single pass to find the leftmost open bench slot.
        first_open = None
        for idx, slot in enumerate(self.bench):
            if slot is None:
                first_open = idx
                break

        board_cnt = self.count_on_board(new_unit)
        bench_cnt = self.count_on_bench(new_unit)
        triggers_upgrade = board_cnt + bench_cnt >= 2

        if triggers_upgrade:
            # Remove the two existing copies *first* to free up space, then
            # mint the upgraded unit and place it in one of the freed slots.
            # This avoids the previous "synthetic position" hack.
            board_removed, bench_removed = self.remove_copies(new_unit)
            upgraded = new_unit.upgrade(self.three_starred)
            placed = self.place_upgraded(upgraded, board_removed, bench_removed)
            if placed is None:
                # Pool was somehow exhausted – revert: re-insert what we had.
                return False
            # Cascade: if the upgraded unit now has 3 copies somewhere on
            # the team (rare), recursively merge again.
            if self.count_on_board(upgraded) + self.count_on_bench(upgraded) >= 3:
                self.maybe_upgrade(upgraded)
            return True

        if first_open is None:
            return False

        self.bench[first_open] = new_unit
        self._index_insert(new_unit, ('bench', first_open))
        return True

    def add_unit(self, unit):
        """Legacy shim."""
        assert isinstance(unit, str), 'Error attempting to add unknown type to team.'
        return self.add_unit_to_bench(unit)

    # ----------------------------------------------------------- placement
    def place_on_board(self, source, max_board_size, target_position=None):
        """Move a unit identified by *source* onto the board.

        ``source`` may be:
            * an int: bench index
            * a tuple ``(row, col)``: board position
            * a :class:`Unit` instance (used by tests; appended at first free
              position)

        ``target_position`` is the destination tile.  When the destination is
        occupied the two units are swapped.  Returns ``True`` on success.
        """
        # Resolve the source.
        if isinstance(source, Unit):
            unit = source
            source_kind = 'external'
            source_idx = None
        elif isinstance(source, int):
            if not 0 <= source < self.bench_size or self.bench[source] is None:
                return False
            unit = self.bench[source]
            source_kind = 'bench'
            source_idx = source
        elif isinstance(source, tuple):
            if source not in self.board_positions:
                return False
            unit = self.board_positions[source]
            source_kind = 'board'
            source_idx = source
        else:
            raise TypeError(f'Unknown source for place_on_board: {source!r}')

        # Determine the destination position.
        if target_position is None:
            if source_kind == 'board':
                return True
            target_position = self.first_open_board_position()
            if target_position is None:
                return False
        else:
            if target_position not in self.board_layout:
                return False

        # Source/destination identical – no-op.
        if source_kind == 'board' and target_position == source_idx:
            return True

        target_occupied = target_position in self.board_positions
        if target_occupied:
            # Swap with existing unit at target.
            displaced = self.board_positions[target_position]
            self._index_remove(displaced, ('board', target_position))
            if source_kind == 'bench':
                self.bench[source_idx] = displaced
                self._index_remove(unit, ('bench', source_idx))
                self._index_insert(displaced, ('bench', source_idx))
            elif source_kind == 'board':
                # Move displaced back to source position.
                self.board_positions[source_idx] = displaced
                self._index_remove(unit, ('board', source_idx))
                self._index_insert(displaced, ('board', source_idx))
            else:  # external unit – just drop displaced
                pass
            self.board_positions[target_position] = unit
            self._index_insert(unit, ('board', target_position))
            return True

        # Target empty.
        if source_kind == 'bench':
            if self.board_count() >= max_board_size:
                return False
            self.bench[source_idx] = None
            self._index_remove(unit, ('bench', source_idx))
        elif source_kind == 'board':
            del self.board_positions[source_idx]
            self._index_remove(unit, ('board', source_idx))
        self.board_positions[target_position] = unit
        self._index_insert(unit, ('board', target_position))

        # Possible upgrade now that the unit is on the board.
        if source_kind == 'external':
            self.maybe_upgrade(unit)
        return True

    def move_to_bench(self, board_pos, target_bench=None):
        """Move the unit at *board_pos* back to the bench (swap allowed)."""
        # Backwards compatibility: accept a flat int index from old tests.
        if isinstance(board_pos, int):
            positions = list(self.board_positions.keys())
            if not 0 <= board_pos < len(positions):
                return False
            board_pos = positions[board_pos]
        if board_pos not in self.board_positions:
            return False

        if target_bench is None:
            target_bench = self.first_open_bench_slot()
        if target_bench is None or not 0 <= target_bench < self.bench_size:
            return False

        unit = self.board_positions[board_pos]
        if self.bench[target_bench] is None:
            self.bench[target_bench] = unit
            self._index_insert(unit, ('bench', target_bench))
            del self.board_positions[board_pos]
            self._index_remove(unit, ('board', board_pos))
            return True
        # Swap.
        displaced = self.bench[target_bench]
        self.bench[target_bench] = unit
        self._index_remove(displaced, ('bench', target_bench))
        self._index_insert(unit, ('bench', target_bench))
        self.board_positions[board_pos] = displaced
        self._index_remove(unit, ('board', board_pos))
        self._index_insert(displaced, ('board', board_pos))
        return True

    def move_within_bench(self, src_index, dst_index):
        if not 0 <= src_index < self.bench_size:
            return False
        if not 0 <= dst_index < self.bench_size:
            return False
        a, b = self.bench[src_index], self.bench[dst_index]
        if a is not None:
            self._index_remove(a, ('bench', src_index))
        if b is not None:
            self._index_remove(b, ('bench', dst_index))
        self.bench[src_index], self.bench[dst_index] = b, a
        if a is not None:
            self._index_insert(a, ('bench', dst_index))
        if b is not None:
            self._index_insert(b, ('bench', src_index))
        return True

    def move_within_board(self, src_pos, dst_pos):
        """Move/swap units between two board positions."""
        # Backwards compat: accept integer indices.
        if isinstance(src_pos, int):
            positions = list(self.board_positions.keys())
            if not 0 <= src_pos < len(positions):
                return False
            src_pos = positions[src_pos]
        if isinstance(dst_pos, int):
            positions = list(self.board_positions.keys())
            if dst_pos >= len(positions):
                # Treat as "move to a new (empty) position" – pick the first
                # free coordinate.
                dst_pos = self.first_open_board_position()
                if dst_pos is None:
                    return False
            else:
                dst_pos = positions[dst_pos]
        if src_pos not in self.board_positions:
            return False
        if dst_pos not in self.board_layout:
            return False
        if dst_pos in self.board_positions:
            a = self.board_positions[src_pos]
            b = self.board_positions[dst_pos]
            self._index_remove(a, ('board', src_pos))
            self._index_remove(b, ('board', dst_pos))
            self.board_positions[src_pos] = b
            self.board_positions[dst_pos] = a
            self._index_insert(a, ('board', dst_pos))
            self._index_insert(b, ('board', src_pos))
            return True
        a = self.board_positions.pop(src_pos)
        self._index_remove(a, ('board', src_pos))
        self.board_positions[dst_pos] = a
        self._index_insert(a, ('board', dst_pos))
        return True

    # --------------------------------------------------------------- selling
    def remove_unit_from_board(self, board_pos):
        """Sell a unit from the board.  Accepts a position tuple or legacy int."""
        if isinstance(board_pos, int):
            positions = list(self.board_positions.keys())
            if not 0 <= board_pos < len(positions):
                return None
            board_pos = positions[board_pos]
        if board_pos not in self.board_positions:
            return None
        sold_unit = self.board_positions.pop(board_pos)
        self._index_remove(sold_unit, ('board', board_pos))
        self._finish_sell(sold_unit)
        return sold_unit

    def remove_unit_from_bench(self, bench_index):
        if not 0 <= bench_index < self.bench_size:
            return None
        sold_unit = self.bench[bench_index]
        if sold_unit is None:
            return None
        self.bench[bench_index] = None
        self._index_remove(sold_unit, ('bench', bench_index))
        self._finish_sell(sold_unit)
        return sold_unit

    def _finish_sell(self, sold_unit):
        if sold_unit.name in self.three_starred and sold_unit.level == 3:
            self.three_starred.remove(sold_unit.name)
        if self.client_socket is not None:
            message = f'sell: {sold_unit.name}: {sold_unit.level}'
            send_message(self.client_socket, message)

    def remove_unit(self, unit_index):
        """Legacy flat-index sell.

        Treats indices in ``[0, board_count)`` as board sells (in
        insertion order), and indices past that as bench sells (over the
        compact list of non-empty bench slots).
        """
        if 0 <= unit_index < self.board_count():
            positions = list(self.board_positions.keys())
            return self.remove_unit_from_board(positions[unit_index])

        offset = unit_index - self.board_count()
        seen = 0
        for slot_idx, slot in enumerate(self.bench):
            if slot is None:
                continue
            if seen == offset:
                return self.remove_unit_from_bench(slot_idx)
            seen += 1
        return None

    # ---------------------------------------------------------------- traits
    def get_traits(self):
        """List of human-readable trait strings (``'TraitName n/breakpoint'``)."""
        return [
            f'{name} {amount}/{next_break}'
            for name, amount, next_break, _tier in self.active_traits()
        ]

    def active_traits(self):
        """Return ``(name, amount, next_breakpoint, tier)`` tuples sorted by tier."""
        traits = self._compute_traits()
        result = []
        for trait_name, amount in traits.items():
            if amount <= 0:
                continue
            trait = self.traits_dict.get(trait_name)
            if trait is None:
                continue
            idx = trait.active_breakpoint_index(amount)
            if idx < 0:
                next_break = trait.breakpoints[0]
                result.append((trait_name, amount, next_break, 'inactive'))
                continue
            if idx == len(trait.breakpoints) - 1:
                next_break = trait.breakpoints[-1]
            else:
                next_break = trait.breakpoints[idx + 1]
            tier = trait.style_tier(amount)
            result.append((trait_name, amount, next_break, tier))

        tier_order = {
            'prismatic': 0,
            'gold': 1,
            'silver': 2,
            'bronze': 3,
            'inactive': 4,
        }
        result.sort(key=lambda r: (tier_order.get(r[3], 99), r[0]))
        return result
