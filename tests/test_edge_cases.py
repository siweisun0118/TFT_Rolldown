"""Edge-case tests for the buy / upgrade / three-star pipeline.

Covers:

* Bench full + buying triggers upgrade → purchase succeeds, bench is
  freed by the merge (already covered in :file:`test_units_and_team.py`,
  duplicated here as a pinning test).
* Bench full + 1 copy already owned + 2 same-name copies in the shop →
  the buy purchases both shop copies and produces the 2-star.
* 3-star units never appear in the shop after they have been minted.
"""

# Standard libraries
import random

import pytest

# Local
from shared.rolldown_classes import Unit


def _set_shop(game, names):
    """Replace the current shop with units matching *names* (1-indexed)."""
    game.cur_shop = []
    for name in names:
        if name is None:
            game.cur_shop.append(Unit(None, 'BLANK', None, None))
            continue
        unit = game.champions_dict[name]
        game.cur_shop.append(unit.copy())
        if unit in game._local_pool[unit.rarity]:
            game._local_pool[unit.rarity].remove(unit)
    while len(game.cur_shop) < 5:
        game.cur_shop.append(Unit(None, 'BLANK', None, None))


def _pool_count(game, name):
    rarity = game.champions_dict[name].rarity
    return sum(1 for u in game._local_pool[rarity] if u.name == name)


# --------------------------------------------------------------- §1 bench-full upgrade
def test_full_bench_single_buy_completes_upgrade(game):
    """Two same-name copies on the bench + buying a third (bench full)."""
    name = 'Akali'
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
    assert game.gold == gold_before - 2  # 1 buy at 2 gold each

    matches = [u for u in game.team.all_units() if u.name == name]
    assert len(matches) == 1
    assert matches[0].level == 2


# ---------------------------------------------------------- §2 chained shop upgrade
def test_full_bench_chain_buy_two_shop_copies_into_upgrade(game):
    """1 on bench + 2 in shop + full bench → game auto-buys both shop copies."""
    name = 'Akali'
    # One existing copy on the bench, eight different fillers.
    game.team.bench[0] = game.champions_dict[name].copy()
    filler = ['Caitlyn', 'Ezreal', 'Fiora', 'Leona',
              'Diana', 'Lissandra', 'Lulu', 'Karma']
    for idx, fname in enumerate(filler):
        game.team.bench[idx + 1] = game.champions_dict[fname].copy()
    assert game.team.bench_is_full()
    assert sum(1 for u in game.team.bench if u and u.name == name) == 1

    gold_before = game.gold
    _set_shop(game, [name, 'Caitlyn', name, None, None])
    # Buying the FIRST Akali should also auto-buy the SECOND Akali so the
    # merge can free bench space.
    assert game.buy_unit(1) is True
    # Gold spent = 2 copies × 2 gold each.
    assert game.gold == gold_before - 4

    # Both shop slots holding Akali are now empty.
    akali_slots_left = [u.name for u in game.cur_shop if u.name == name]
    assert akali_slots_left == []

    # Exactly one Akali survives (the 2-star).
    matches = [u for u in game.team.all_units() if u.name == name]
    assert len(matches) == 1
    assert matches[0].level == 2


def test_full_bench_chain_buy_alternate_click_slot(game):
    """Clicking the second copy in the shop also triggers the chain buy."""
    name = 'Akali'
    game.team.bench[0] = game.champions_dict[name].copy()
    filler = ['Caitlyn', 'Ezreal', 'Fiora', 'Leona',
              'Diana', 'Lissandra', 'Lulu', 'Karma']
    for idx, fname in enumerate(filler):
        game.team.bench[idx + 1] = game.champions_dict[fname].copy()
    assert game.team.bench_is_full()

    _set_shop(game, [name, 'Caitlyn', name, None, None])
    # Click the *second* Akali (slot 3, 1-indexed).
    assert game.buy_unit(3) is True
    # Exactly one Akali survives.
    matches = [u for u in game.team.all_units() if u.name == name]
    assert len(matches) == 1 and matches[0].level == 2


def test_chain_buy_rejects_when_not_enough_gold(game):
    """If the chain would cost more than the player has, the buy must fail."""
    name = 'Akali'
    game.team.bench[0] = game.champions_dict[name].copy()
    filler = ['Caitlyn', 'Ezreal', 'Fiora', 'Leona',
              'Diana', 'Lissandra', 'Lulu', 'Karma']
    for idx, fname in enumerate(filler):
        game.team.bench[idx + 1] = game.champions_dict[fname].copy()

    game.gold = 3  # only enough for one 2-cost
    _set_shop(game, [name, 'Caitlyn', name, None, None])
    assert game.buy_unit(1) is False
    assert game.last_notification == 'Not enough gold'
    # Both Akali shop slots are still occupied.
    assert sum(1 for u in game.cur_shop if u.name == name) == 2


def test_chain_buy_only_when_bench_full(game):
    """When the bench has free slots, the chain is unnecessary."""
    name = 'Akali'
    game.team.bench[0] = game.champions_dict[name].copy()
    # Plenty of empty bench slots remaining.
    _set_shop(game, [name, 'Caitlyn', name, None, None])
    gold_before = game.gold
    assert game.buy_unit(1) is True
    # Only the first shop slot was purchased.
    assert game.cur_shop[0].name == 'BLANK'
    assert game.cur_shop[2].name == name
    assert game.gold == gold_before - 2


# ---------------------------------------------------------- §3 three-star exclusion
def test_three_starred_unit_does_not_appear_in_shop(game):
    """After marking a champion as 3-starred, it must never roll in the shop."""
    game.three_starred.add('Aatrox')

    # Roll many shops to make the chance of accidentally drawing Aatrox vanish.
    random.seed(2024)
    for _ in range(200):
        game.gold = 100  # plenty of gold so rerolls always go through
        game.cur_shop = game.roll(first_roll=True)
        for unit in game.cur_shop:
            assert unit.name != 'Aatrox', (
                'Three-starred Aatrox should never appear in the shop, but '
                f'rolled this shop: {[u.name for u in game.cur_shop]}'
            )


def test_three_starred_unit_excluded_from_pool_listing(game):
    """``build_champion_pool`` should hide three-starred champions."""
    game.three_starred.add('Akali')
    pool = game.build_champion_pool()
    for rarity_pool in pool.values():
        for unit in rarity_pool:
            assert unit.name != 'Akali', (
                'Three-starred Akali should be filtered from the rolled pool.'
            )


def test_three_starred_clears_when_unit_sold(game):
    """Selling a 3-star unit should put the champion back into rotation."""
    # Manually create a 3-star Aatrox on the board.
    aatrox = game.champions_dict['Aatrox']
    three_star = Unit(aatrox.rarity, aatrox.name, aatrox.traits, aatrox.id_name, level=3)
    game.team.board_positions[('A', 1)] = three_star
    game.three_starred.add('Aatrox')

    # Sell the 3-star.
    assert game.sell_board_unit(('A', 1)) is True
    # The tracker should have cleared so future rolls can produce Aatrox.
    assert 'Aatrox' not in game.three_starred


def test_two_to_three_star_path_marks_three_starred(game):
    """Buying 9 copies of a 1-cost unit should eventually 3-star it."""
    name = 'Aatrox'
    game.gold = 100
    # Buy 9 copies via the API.
    for _ in range(9):
        _set_shop(game, [name])
        game.buy_unit(1)
    # One 3-star unit should now exist.
    matches = [u for u in game.team.all_units() if u.name == name]
    assert len(matches) == 1 and matches[0].level == 3
    assert name in game.three_starred
