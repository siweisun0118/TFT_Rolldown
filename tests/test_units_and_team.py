"""Tests for the :class:`shared.rolldown_classes.Team` API.

These tests cover the canonical user actions:

* buying a unit, then immediately selling it (gold, pool and trait state)
* upgrading by acquiring three copies of a unit, then selling the upgrade
* failing to buy when the bench is full (no state changes)
* board capacity gated by player level
* prismatic / gold / silver / bronze trait tiers
"""

# Standard libraries
import pytest

# Local imports
from shared.rolldown_classes import Trait


def _pool_count(game, name):
    """Helper – how many copies of *name* are currently in the offline pool."""
    rarity = game.champions_dict[name].rarity
    return sum(1 for u in game._local_pool[rarity] if u.name == name)


def _set_shop(game, names):
    """Replace the current shop with units matching *names* (1-indexed)."""
    from shared.rolldown_classes import Unit
    game.cur_shop = []
    for name in names:
        if name is None:
            game.cur_shop.append(Unit(None, 'BLANK', None, None))
        else:
            unit = game.champions_dict[name]
            game.cur_shop.append(unit.copy())
            # Make the offline pool consistent with the synthetic shop.
            if unit in game._local_pool[unit.rarity]:
                game._local_pool[unit.rarity].remove(unit)
    while len(game.cur_shop) < 5:
        game.cur_shop.append(Unit(None, 'BLANK', None, None))


# -------------------------------------------------------- buy then sell
def test_buy_then_sell_single_unit_restores_state(game):
    """Buying a unit and immediately selling restores gold, pool, and traits."""
    aatrox_pool_before = _pool_count(game, 'Aatrox')
    gold_before = game.gold

    _set_shop(game, ['Aatrox'])
    assert game.buy_unit(1) is True
    assert game.gold == gold_before - 1
    assert _pool_count(game, 'Aatrox') == aatrox_pool_before - 1

    # The unit is on the bench, not the board – so traits should not be active.
    assert game.team.bench[0].name == 'Aatrox'
    assert game.team.board == []
    assert game.team.active_traits() == []

    # Sell from the bench.
    sold = game.sell_bench_unit(0)
    assert sold is True
    assert game.gold == gold_before  # 1-cost sells for full price
    assert _pool_count(game, 'Aatrox') == aatrox_pool_before
    assert game.team.bench[0] is None
    assert game.team.active_traits() == []


def test_traits_track_board_only(game):
    """Putting a unit on the board activates its traits; bench does not."""
    _set_shop(game, ['Aatrox'])
    game.buy_unit(1)
    assert game.team.active_traits() == []
    assert game.move_bench_to_board(0)
    # Aatrox has Bastion + N.O.V.A.; both should appear at amount=1.
    names = {t[0] for t in game.team.active_traits()}
    assert 'Bastion' in names and 'N.O.V.A.' in names


# -------------------------------------------------------- buy x3, upgrade, sell
def test_upgrade_then_sell_costs_one_less_than_sum_of_purchases(game):
    """Buying 3 copies of a 2-cost unit upgrades; selling refunds (3*cost - 1)."""
    # Akali is a 2-cost in Set 17.
    name = 'Akali'
    assert game.champions_dict[name].cost == 2
    gold_before = game.gold

    pool_before = _pool_count(game, name)

    for _ in range(3):
        _set_shop(game, [name])
        assert game.buy_unit(1) is True

    assert game.gold == gold_before - (2 * 3)
    assert _pool_count(game, name) == pool_before - 3

    # The merged 2-star is somewhere in the team (bench likely).
    upgraded = next(u for u in game.team.all_units() if u.name == name)
    assert upgraded.level == 2

    # Sell the 2-star.  Sell value should be 3 * 2 - 1 = 5.
    if upgraded in game.team.board:
        idx = game.team.board.index(upgraded)
        game.sell_board_unit(idx)
    else:
        idx = game.team.bench.index(upgraded)
        game.sell_bench_unit(idx)

    # Gold spent (2 * 3) refunded as 5 → net spent = 1.
    assert game.gold == gold_before - 1

    # Pool: 3 copies returned to pool, so net 0 change.
    assert _pool_count(game, name) == pool_before


def test_one_cost_upgrade_sell_returns_full_purchase_price(game):
    """1-cost 2-star sells for exactly the purchase price (3 gold)."""
    name = 'Aatrox'  # 1-cost
    assert game.champions_dict[name].cost == 1
    gold_before = game.gold
    for _ in range(3):
        _set_shop(game, [name])
        game.buy_unit(1)

    upgraded = next(u for u in game.team.all_units() if u.name == name)
    assert upgraded.level == 2

    # Sell value of 1-cost 2-star = 3 (per Unit class).
    if upgraded in game.team.board:
        game.sell_board_unit(game.team.board.index(upgraded))
    else:
        game.sell_bench_unit(game.team.bench.index(upgraded))

    assert game.gold == gold_before


# ------------------------------------------------------------- bench full
def test_buying_with_full_bench_fails_cleanly(game):
    """Buying a non-upgrading unit when the bench is full must roll back."""
    # Fill the bench with 9 different units (no chance of upgrade).
    names = ['Akali', 'Caitlyn', 'Ezreal', 'Fiora', 'Leona',
             'Diana', 'Lissandra', 'Lulu', 'Karma']
    for idx, name in enumerate(names):
        game.team.bench[idx] = game.champions_dict[name].copy()
    assert game.team.bench_is_full()

    gold_before = game.gold
    _set_shop(game, ['Pyke'])
    # Compute the baseline after `_set_shop` has placed Pyke into the shop;
    # the buy should not move any additional copies out of the pool.
    pool_before = _pool_count(game, 'Pyke')
    assert game.buy_unit(1) is False
    assert game.last_notification == 'Bench is full'
    assert game.gold == gold_before
    assert _pool_count(game, 'Pyke') == pool_before
    # Bench composition unchanged.
    for idx, name in enumerate(names):
        assert game.team.bench[idx].name == name


def test_upgrade_buy_succeeds_even_with_full_bench(game):
    """If buying triggers an upgrade, the buy is allowed despite a full bench."""
    name = 'Akali'  # 2-cost
    # Two of the bench slots hold Akali copies; the rest is anything else.
    game.team.bench[0] = game.champions_dict[name].copy()
    game.team.bench[1] = game.champions_dict[name].copy()
    filler = ['Caitlyn', 'Ezreal', 'Fiora', 'Leona',
              'Diana', 'Lissandra', 'Lulu']
    for idx, fname in enumerate(filler):
        game.team.bench[idx + 2] = game.champions_dict[fname].copy()
    assert game.team.bench_is_full()

    gold_before = game.gold
    _set_shop(game, [name])
    assert game.buy_unit(1) is True
    assert game.gold == gold_before - 2

    # Exactly one Akali survives (the 2-star).
    matches = [u for u in game.team.all_units() if u.name == name]
    assert len(matches) == 1
    assert matches[0].level == 2


# ------------------------------------------------------------- board capacity
@pytest.mark.parametrize('level,cap', [(1, 1), (2, 2), (5, 5), (8, 8), (11, 11)])
def test_board_capacity_equals_player_level(game, level, cap):
    game.level = level
    assert game.max_board_size == cap


def test_cannot_overfill_board(game):
    game.level = 1
    aatrox = game.champions_dict['Aatrox']
    game.team.bench[0] = aatrox.copy()
    game.team.bench[1] = game.champions_dict['Caitlyn'].copy()

    assert game.move_bench_to_board(0) is True
    assert game.move_bench_to_board(1) is False
    assert game.last_notification == 'Team is full'
    # The Caitlyn that was rejected is still on the bench.
    assert game.team.bench[1].name == 'Caitlyn'


# ------------------------------------------------------------- bench<->board
def test_drag_unit_between_board_and_bench(game):
    aatrox = game.champions_dict['Aatrox']
    game.team.bench[0] = aatrox.copy()
    assert game.move_bench_to_board(0) is True
    assert len(game.team.board) == 1
    assert game.team.bench[0] is None

    # Drag back to bench.
    assert game.move_board_to_bench(0, 5) is True
    assert game.team.bench[5].name == 'Aatrox'
    assert game.team.board == []


def test_drag_within_bench_swaps_slots(game):
    a = game.champions_dict['Aatrox'].copy()
    b = game.champions_dict['Akali'].copy()
    game.team.bench[1] = a
    game.team.bench[4] = b
    assert game.team.move_within_bench(1, 4)
    assert game.team.bench[1].name == 'Akali'
    assert game.team.bench[4].name == 'Aatrox'


# ------------------------------------------------------------- trait tiers
def test_trait_tier_mapping():
    """Bronze / silver / gold / prismatic mapping for various traits."""
    # Style-1/2/3 trait with a normal max breakpoint.
    bastion = Trait('Bastion', [2, 4, 6], [1, 2, 3])
    assert bastion.style_tier(2) == 'bronze'
    assert bastion.style_tier(4) == 'silver'
    assert bastion.style_tier(6) == 'gold'

    # Single-style unique trait should be prismatic when active.
    bulwark = Trait('Bulwark', [1], [4])
    assert bulwark.style_tier(0) == 'inactive'
    assert bulwark.style_tier(1) == 'prismatic'

    # Trait with breakpoint >= 10 must show prismatic, prior breakpoint gold.
    meeple = Trait('Meeple', [3, 5, 7, 10], [1, 2, 3, 3])
    assert meeple.style_tier(2) == 'inactive'
    assert meeple.style_tier(3) == 'bronze'
    assert meeple.style_tier(5) == 'silver'
    assert meeple.style_tier(7) == 'gold'
    assert meeple.style_tier(10) == 'prismatic'

    # Trait where two adjacent breakpoints share style 3 -- both display gold
    # unless one of them is >=10.
    dark_star = Trait('Dark Star', [2, 4, 6, 9], [1, 2, 3, 3])
    assert dark_star.style_tier(6) == 'gold'
    assert dark_star.style_tier(9) == 'gold'
