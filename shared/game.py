"""Definition of Game class used by rolldown."""

# Standard libraries
from copy import deepcopy
import json
import os
import random
import socket
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
from shared.rolldown_enums import BOARD_LAYOUT, CHAMPION_AMOUNTS, CHAMPION_POOL, \
    LEVEL_EXP, LEVEL_ODDS, SERVER_LOG_FILE, SHOP_SLOTS, THREE_STARRED


class Game:
    """Class that runs and manages the rolldown."""
    def __init__(self, input_dir, gold=None, level=None, offline=False):
        # Read in database
        champions_dict, traits_dict = read_database(input_dir)
        self.champions_dict = champions_dict
        self.traits_dict = traits_dict
        self.input_dir = input_dir

        # Gold and level member variables
        self.gold = gold
        self.level = level
        self.exp = 0

        # Keep track of the current shop
        self.cur_shop = None

        # Transient notification consumed by the GUI/tests.
        self.last_notification = None

        # Perf §1.11: per-instance "three starred" tracker so tests no
        # longer mutate global state.
        self.three_starred = set()

        # Perf §1.1: client-side pool cache.  Maintained in lockstep with
        # local buys/sells; resynced from the server on demand.
        self._pool_cache = None
        self._pool_dirty = True

        # Perf §1.9: precomputed splash path for each champion so the GUI
        # does not stat the filesystem on every frame.
        self._splash_paths = self._build_splash_path_cache()

        # Offline mode keeps the champion pool in-process.
        self.offline = offline
        self._local_pool = None
        self.client_socket = None

        if offline:
            self._local_pool = self._build_local_pool()
        else:
            self._connect_to_server(input_dir)

        # Create new team, sharing this game's THREE_STARRED tracker so the
        # global is no longer mutated.
        self.team = Team(
            self.champions_dict,
            self.traits_dict,
            self.client_socket,
            board_layout=BOARD_LAYOUT,
            three_starred=self.three_starred,
        )

    def _build_splash_path_cache(self):
        """Map champion name -> Path to the splash PNG (resolved once)."""
        from pathlib import Path
        root = Path(self.input_dir) / 'champions'
        cache = {}
        for name, unit in self.champions_dict.items():
            candidate = root / f'{name}.png'
            if not candidate.is_file():
                candidate = root / f'{unit.id_name}.png'
            cache[name] = candidate if candidate.is_file() else None
        return cache

    def splash_path(self, unit):
        """Return the absolute path to *unit*'s splash, or ``None`` if missing."""
        if unit is None:
            return None
        return self._splash_paths.get(unit.name)

    def _build_local_pool(self):
        """Populate an in-memory champion pool for offline play."""
        pool = {1: [], 2: [], 3: [], 4: [], 5: []}
        for name, unit in self.champions_dict.items():
            amount = CHAMPION_AMOUNTS.get(unit.rarity, 0)
            pool[unit.rarity].extend([unit] * amount)
        return pool

    def _connect_to_server(self, input_dir):
        """Establish a connection to the networking server, starting it if needed.

        Implements server improvement §2.1: replace the fixed 0.5s sleep
        with exponential backoff polling, raising a clear error when the
        deadline is exceeded.  Also probes the protocol so a stale legacy
        server on the same port surfaces an immediate error instead of
        silently hanging on the first ``recv``.
        """
        try:
            sock = init_rolldown_client(0)
            if self._probe_protocol(sock):
                self.client_socket = sock
                return
            # Protocol mismatch – likely a stale server from a prior run.
            sock.close()
            raise RuntimeError(
                f'A server on port {input_dir} responded but did not speak '
                'the length-prefixed protocol – likely a stale legacy '
                'server.  Kill the existing process listening on '
                'TCP port 8000 and try again.'
            )
        except ConnectionRefusedError:
            pass

        # Start the server, scoping its environment (server improvement
        # §2.10) to avoid GUI environment variables leaking through.
        SERVER_LOG_FILE.unlink(missing_ok=True)
        env = {
            'PATH': os.environ.get('PATH', ''),
            'PYTHONPATH': os.environ.get('PYTHONPATH', ''),
            'PYTHONIOENCODING': os.environ.get('PYTHONIOENCODING', 'utf-8'),
            'HOME': os.environ.get('HOME', ''),
        }
        if 'SystemRoot' in os.environ:
            env['SystemRoot'] = os.environ['SystemRoot']  # Windows requires this.
        with open(str(SERVER_LOG_FILE), mode='a', encoding='utf-8') as outfile:
            subprocess.Popen(
                ['python', '-m', 'shared.networking_server', input_dir],
                stdout=outfile, stderr=outfile, env=env,
            )

        print('No active server found, starting new server...')

        # Poll the new server with exponential backoff.
        backoffs = (0.05, 0.1, 0.2, 0.4, 0.8, 1.5)
        last_err = None
        for delay in backoffs:
            time.sleep(delay)
            try:
                sock = init_rolldown_client(0)
                if self._probe_protocol(sock):
                    self.client_socket = sock
                    return
                sock.close()
            except ConnectionRefusedError as err:
                last_err = err
        raise RuntimeError(
            'Failed to start rolldown server: '
            f'still refusing connections after {sum(backoffs):.2f}s'
        ) from last_err

    def _probe_protocol(self, sock, timeout=1.0):
        """Confirm *sock* speaks the length-prefixed framing protocol.

        Sends a ``pool`` request and waits up to *timeout* seconds for a
        framed JSON reply.  Returns ``True`` on success.  A legacy server
        replies with raw bytes (no length prefix), which the framing
        helper interprets as an enormous body length, hangs forever, or
        decodes to garbage – we surface those as ``False`` via a
        ``socket.timeout``.
        """
        original_timeout = sock.gettimeout()
        try:
            sock.settimeout(timeout)
            send_message(sock, 'pool')
            return True
        except (socket.timeout, ConnectionError, ValueError, OSError):
            return False
        finally:
            try:
                sock.settimeout(original_timeout)
            except OSError:
                pass

    @property
    def max_board_size(self):
        """Maximum number of units that may live on the board at once."""
        # In real TFT the board size is equal to player level.
        return self.level if self.level else 1

    def __str__(self):
        """Display the current team"""
        return str(self.team)

    def build_champion_pool(self):
        """Return the current champion pool, using a client-side cache.

        Perf §1.1: ``_pool_cache`` is the authoritative copy maintained by
        :meth:`_send_buy_message` / :meth:`_send_sell_message`.  We only
        re-fetch from the server on first call or after an explicit
        :meth:`invalidate_pool_cache`.
        """
        if self.offline:
            # The offline pool is mutated directly so it's always fresh.
            cur_pool = {rarity: [] for rarity in self._local_pool}
            for rarity, units in self._local_pool.items():
                for cur_unit in units:
                    if cur_unit.name not in self.three_starred:
                        cur_pool[rarity].append(cur_unit)
            return cur_pool

        if self._pool_dirty or self._pool_cache is None:
            full_pool = json.loads(send_message(self.client_socket, 'pool'))
            cache = {1: {}, 2: {}, 3: {}, 4: {}, 5: {}}
            for name, amount in full_pool.items():
                cur_unit = self.champions_dict[name]
                cache[cur_unit.rarity][name] = amount
            self._pool_cache = cache
            self._pool_dirty = False

        # Materialise the cache into the historical list form expected by
        # callers, filtering out 3-starred units.
        cur_pool = {1: [], 2: [], 3: [], 4: [], 5: []}
        for rarity, names in self._pool_cache.items():
            for name, amount in names.items():
                if name in self.three_starred:
                    continue
                cur_unit = self.champions_dict[name]
                cur_pool[rarity].extend([cur_unit] * amount)
        return cur_pool

    def invalidate_pool_cache(self):
        """Force the next :meth:`build_champion_pool` to refetch from the server."""
        self._pool_cache = None
        self._pool_dirty = True

    def _notify(self, message):
        """Record a transient, non-blocking notification for the GUI/tests."""
        self.last_notification = message

    def _adjust_cache(self, unit, delta):
        """Apply a delta to the client-side pool cache (perf §1.1)."""
        if self.offline or self._pool_cache is None:
            return
        bucket = self._pool_cache.setdefault(unit.rarity, {})
        bucket[unit.name] = bucket.get(unit.name, 0) + delta
        if bucket[unit.name] <= 0:
            bucket.pop(unit.name, None)

    def _send_buy_message(self, unit):
        """Inform the server (if any) that *unit* was bought."""
        if self.offline:
            self._local_pool[unit.rarity].remove(unit)
            return
        # Server improvement §2.9: the server now returns an ack with the
        # new state; treat a non-OK response as a transactional failure.
        response = send_message(self.client_socket, f'buy: {unit.name}')
        if response and response.startswith('ERROR'):
            self._notify(response)
            raise RuntimeError(f'Server rejected buy: {response}')
        self._adjust_cache(unit, -1)

    def _send_sell_message(self, unit):
        """Inform the server (if any) that *unit* was sold."""
        if self.offline:
            from shared.rolldown_enums import UNIT_AMOUNT_LEVEL
            amount = UNIT_AMOUNT_LEVEL.get(unit.level, 1)
            for _ in range(amount):
                self._local_pool[unit.rarity].append(unit)
            return
        response = send_message(self.client_socket, f'sell: {unit.name}: {unit.level}')
        if response and response.startswith('ERROR'):
            self._notify(response)
            raise RuntimeError(f'Server rejected sell: {response}')
        from shared.rolldown_enums import UNIT_AMOUNT_LEVEL
        self._adjust_cache(unit, UNIT_AMOUNT_LEVEL.get(unit.level, 1))

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

            # If candidates is empty, reroll rarities until candidate is available.
            # Perf §1.2 supplement: shallow-copy the weight list (five ints)
            # rather than ``deepcopy`` it.
            remaining_odds = list(LEVEL_ODDS[level])
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
        """Roll for champions based on level.

        Perf §1.6: ``random.choices`` is invoked once for the cost roll
        (already batched) and the per-slot unit selection uses
        ``cur_pool[cost]`` directly instead of re-copying it into a fresh
        ``can_roll`` list, eliminating an O(N) allocation per slot.
        """
        assert self.level in range(1, 12)

        cur_pool = self.build_champion_pool()

        if not first_roll:
            self.gold -= 2

        odds = LEVEL_ODDS[self.level]
        costs = random.choices(population=[1, 2, 3, 4, 5], weights=odds, k=SHOP_SLOTS)

        results = []
        for cost in costs:
            bucket = cur_pool[cost]
            if not bucket:
                # Fallback – grab any remaining unit.
                total_pool = [unit for ls in cur_pool.values() for unit in ls]
                if not total_pool:
                    continue
                chosen = random.choice(total_pool)
            else:
                chosen = random.choice(bucket)
            cur_pool[chosen.rarity].remove(chosen)
            results.append(chosen)

        # Take each rolled champion out of the pool (informs server + cache).
        for unit in results:
            self._send_buy_message(unit)

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
        """Buy a unit for the team (1-indexed).

        The unit lands on the bench unless purchasing it triggers an
        upgrade, in which case the upgraded copy lands wherever the merge
        resolves.  Returns ``True`` if the purchase succeeded.

        **Edge case** – when the bench is full but the shop contains
        additional copies of the same unit such that the player already
        owns at least one copy and buying enough extras would complete an
        upgrade, every needed copy is auto-purchased and the merge is
        applied atomically.  This mirrors how the real game handles the
        "full bench, lucky shop" scenario without requiring the GUI to
        pre-empt the user.
        """
        idx = int(next_in) - 1
        cur_unit = self.cur_shop[idx]
        if cur_unit.name == 'BLANK':
            return False

        if self.gold < cur_unit.cost:
            self._notify('Not enough gold')
            return False

        owned = (
            self.team._count_on_board(cur_unit)
            + self.team._count_on_bench(cur_unit)
        )

        # Buying just this slot already triggers an upgrade *or* the bench
        # has room – either way we can use the simple add-to-bench path.
        triggers_upgrade = owned >= 2
        if triggers_upgrade or not self.team.bench_is_full():
            self.gold -= cur_unit.cost
            success = self.team.add_unit_to_bench(cur_unit.name)
            if not success:
                self.gold += cur_unit.cost
                self._notify('Bench is full')
                return False
            self.cur_shop[idx] = Unit(None, 'BLANK', None, None)
            return True

        # ---------- chained buy: bench full + owned >= 1 + extras in shop ----
        if owned < 1:
            self._notify('Bench is full')
            return False

        extras = [
            i for i, u in enumerate(self.cur_shop)
            if i != idx and u.name == cur_unit.name
        ]
        need = 3 - owned - 1  # extras required beyond the clicked one
        if need < 0 or len(extras) < need:
            self._notify('Bench is full')
            return False

        chain_indices = [idx] + extras[:need]
        total_cost = cur_unit.cost * len(chain_indices)
        if self.gold < total_cost:
            self._notify('Not enough gold')
            return False

        # Execute the chain as a direct merge: remove the existing
        # copies, mint an upgraded copy, and place it in one of the freed
        # slots.  This bypasses ``add_unit_to_bench`` whose bench-full
        # check would otherwise reject the very first purchase.
        template = self.champions_dict[cur_unit.name]
        proto = template.copy()
        board_removed, bench_removed = self.team._remove_copies(proto)
        upgraded = proto.upgrade(self.team.three_starred)
        placed = self.team._place_upgraded(upgraded, board_removed, bench_removed)
        if placed is None:
            # Should never happen – we just freed at least one slot.
            return False

        self.gold -= total_cost
        for shop_idx in chain_indices:
            self.cur_shop[shop_idx] = Unit(None, 'BLANK', None, None)

        # Cascade in the rare case that the new 2-star completes a 3-star.
        if self.team._count_on_board(upgraded) + self.team._count_on_bench(upgraded) >= 3:
            self.team._maybe_upgrade(upgraded)
        return True

    def sell_unit(self, index):
        """Sell a unit from the team via the legacy flat index."""
        if index < 0 or index >= len(self.team):
            return False
        sold_unit = self.team.team[index]
        if sold_unit is None:
            return False
        self.gold += sold_unit.sell_cost
        removed = self.team.remove_unit(index)
        if removed is not None:
            # The offline pool is owned by Game (Team only sends network
            # messages); restore the unit here so book-keeping is symmetrical.
            if self.offline:
                self._send_sell_message(removed)
            return True
        return False

    def sell_board_unit(self, board_index):
        """Sell the unit at ``board_index`` (position tuple or legacy int)."""
        if isinstance(board_index, int):
            if not 0 <= board_index < self.team.board_count():
                return False
            positions = list(self.team.board_positions.keys())
            position = positions[board_index]
        else:
            position = board_index
        unit = self.team.board_positions.get(position)
        if unit is None:
            return False
        self.gold += unit.sell_cost
        self.team.remove_unit_from_board(position)
        if self.offline:
            self._send_sell_message(unit)
        return True

    def sell_bench_unit(self, bench_index):
        """Sell the unit at ``bench_index`` (0-indexed) from the bench."""
        if not 0 <= bench_index < self.team.bench_size:
            return False
        unit = self.team.bench[bench_index]
        if unit is None:
            return False
        self.gold += unit.sell_cost
        self.team.remove_unit_from_bench(bench_index)
        if self.offline:
            self._send_sell_message(unit)
        return True

    def move_bench_to_board(self, bench_index, target_position=None):
        """Drag a unit from the bench onto the board.

        ``target_position`` is the destination ``(row, col)`` tile.  If
        omitted, the first empty board tile (in layout order) is used.
        Returns ``True`` on success.  When the target is occupied the two
        units are swapped.
        """
        if not 0 <= bench_index < self.team.bench_size:
            return False
        if self.team.bench[bench_index] is None:
            return False
        # When the target is empty we must respect the board cap; swaps
        # don't change the board population so they bypass the limit.
        target_occupied = (
            target_position is not None and target_position in self.team.board_positions
        )
        if not target_occupied and self.team.board_count() >= self.max_board_size:
            self._notify('Team is full')
            return False
        return self.team.place_on_board(
            bench_index, self.max_board_size, target_position=target_position
        )

    def move_board_to_board(self, src_position, dst_position):
        """Move/swap a unit between two board tiles."""
        if src_position not in self.team.board_positions:
            return False
        if dst_position not in self.team.board_layout:
            return False
        return self.team.move_within_board(src_position, dst_position)

    def move_board_to_bench(self, board_index, bench_index=None):
        """Drag a unit from the board onto the bench.

        ``board_index`` may be a position tuple ``(row, col)`` or the legacy
        flat integer index.  When ``bench_index`` is occupied the two
        units swap; otherwise the unit moves into the empty slot.
        """
        if isinstance(board_index, int):
            if not 0 <= board_index < self.team.board_count():
                return False
        else:
            if board_index not in self.team.board_positions:
                return False
        if bench_index is not None and not 0 <= bench_index < self.team.bench_size:
            return False
        # Allow swap when destination occupied; otherwise we need a free slot.
        if bench_index is None and self.team.first_open_bench_slot() is None:
            self._notify('Bench is full')
            return False
        # If bench_index is occupied, move_to_bench swaps – allowed even
        # when the rest of the bench is full.
        return self.team.move_to_bench(board_index, bench_index)

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
        for unit in self.team.all_units():
            self._send_sell_message(unit)

        # Return units in shop to the pool
        for unit in self.cur_shop:
            if unit.name != 'BLANK':
                self._send_sell_message(unit)

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
                            self._send_sell_message(unit)

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
