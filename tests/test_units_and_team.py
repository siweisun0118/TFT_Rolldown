"""Core gameplay: buying, selling, upgrades, board/bench, traits, pool."""

import pytest

from shared.rolldown_classes import Unit
from shared.rolldown_enums import BENCH_SLOTS, UNIT_AMOUNT_LEVEL
from shared.networking_client import send_message


def _unit_of_cost(game, cost):
    """Return the name of some champion with the given cost."""
    for name, unit in game.champions_dict.items():
        if unit.cost == cost:
            return name
    raise AssertionError(f"no champion of cost {cost}")


def _stock_shop(game, fake_pool, name, copies=1):
    """Put ``copies`` of ``name`` into the shop and mimic the roll's pool draw.

    A real roll removes rolled units from the pool, so we replicate that here
    to keep the pool bookkeeping faithful.
    """
    unit = game.champions_dict[name]
    shop = [unit.copy() for _ in range(copies)]
    while len(shop) < 5:
        shop.append(Unit(None, 'BLANK', None, None))
    game.cur_shop = shop
    for _ in range(copies):
        send_message(fake_pool, f'buy: {name}')


def test_buy_then_sell_restores_gold_and_pool(game, fake_pool):
    name = _unit_of_cost(game, 1)
    base_pool = fake_pool.count(name)
    base_gold = game.gold

    _stock_shop(game, fake_pool, name, copies=1)
    assert fake_pool.count(name) == base_pool - 1  # roll removed it

    assert game.buy_unit(1) == 'ok'
    assert game.gold == base_gold - 1
    assert game.team.bench[0].name == name
    # Bench-only units never contribute to traits.
    assert game.team.traits == {}

    # Sell it straight back.
    assert game.sell_bench(0)
    assert game.gold == base_gold                 # 1-cost: sell == buy
    assert all(slot is None for slot in game.team.bench)
    assert fake_pool.count(name) == base_pool      # fully restored


def test_buy_blank_and_insufficient_gold(game, fake_pool):
    name = _unit_of_cost(game, 1)
    _stock_shop(game, fake_pool, name, copies=1)

    # Slot 2 is BLANK.
    assert game.buy_unit(2) == 'blank'

    game.gold = 0
    assert game.buy_unit(1) == 'no_gold'
    assert game.team.bench == [None] * BENCH_SLOTS


def test_upgrade_one_cost_then_sell(game, fake_pool):
    name = _unit_of_cost(game, 1)
    base_pool = fake_pool.count(name)
    base_gold = game.gold

    _stock_shop(game, fake_pool, name, copies=3)
    assert fake_pool.count(name) == base_pool - 3

    for slot in (1, 2, 3):
        assert game.buy_unit(slot) == 'ok'

    # The three copies combined into a single 2-star unit.
    owned = game.team.all_units()
    assert len(owned) == 1
    assert owned[0].level == 2
    assert game.gold == base_gold - 3            # spent 3 * cost(1)

    # 1-cost, level 2 sells for the combined purchase price (3).
    assert owned[0].sell_cost == 3
    game.sell_bench(game.team.bench.index(owned[0]))
    assert game.gold == base_gold                # net zero for a 1-cost
    assert fake_pool.count(name) == base_pool     # 3 copies returned


def test_upgrade_three_cost_sell_price_rule(game, fake_pool):
    name = _unit_of_cost(game, 3)
    base_pool = fake_pool.count(name)

    _stock_shop(game, fake_pool, name, copies=3)
    for slot in (1, 2, 3):
        assert game.buy_unit(slot) == 'ok'

    unit = game.team.all_units()[0]
    assert unit.level == 2
    # Not a 1-cost: sell price is one less than combined purchase price.
    assert unit.sell_cost == 3 * 3 - 1

    game.sell_bench(game.team.bench.index(unit))
    assert fake_pool.count(name) == base_pool
    assert UNIT_AMOUNT_LEVEL[2] == 3


def test_bench_full_purchase_fails(game, fake_pool):
    one = _unit_of_cost(game, 1)
    # Fill every bench slot with distinct units (avoid accidental upgrades).
    distinct = [n for n, u in game.champions_dict.items()][:BENCH_SLOTS]
    for slot, n in enumerate(distinct):
        game.team.bench[slot] = game.champions_dict[n].copy()
    assert game.team.bench_is_full()

    gold_before = game.gold
    bench_before = list(game.team.bench)

    _stock_shop(game, fake_pool, one, copies=1)
    assert game.buy_unit(1) == 'bench_full'

    # Nothing changed: no gold spent, team identical, app still usable.
    assert game.gold == gold_before
    assert game.team.bench == bench_before
    assert game.buy_unit  # method still callable afterwards


def _fill_bench_distinct(game, exclude, count):
    """Fill ``count`` bench slots with distinct champs not named ``exclude``."""
    used = 0
    for n in game.champions_dict:
        if used >= count:
            break
        if n == exclude:
            continue
        game.team.bench[used] = game.champions_dict[n].copy()
        used += 1
    return used


def test_bench_full_but_purchase_upgrades_is_allowed(game, fake_pool):
    """Bench full + buying the 3rd copy -> let it through and upgrade."""
    name = _unit_of_cost(game, 1)

    # Two copies already owned on the bench; the other 7 slots are distinct.
    others = [n for n in game.champions_dict if n != name][:BENCH_SLOTS - 2]
    for i, n in enumerate(others):
        game.team.bench[i] = game.champions_dict[n].copy()
    game.team.bench[BENCH_SLOTS - 2] = game.champions_dict[name].copy()
    game.team.bench[BENCH_SLOTS - 1] = game.champions_dict[name].copy()
    assert game.team.bench_is_full()
    assert sum(1 for u in game.team.all_units()
               if u.name == name and u.level == 1) == 2

    gold_before = game.gold
    _stock_shop(game, fake_pool, name, copies=1)

    assert game.buy_unit(1) == 'ok'
    assert game.gold == gold_before - game.champions_dict[name].cost

    owned = [u for u in game.team.all_units() if u.name == name]
    assert len(owned) == 1
    assert owned[0].level == 2


def test_bench_full_one_owned_two_in_shop_auto_upgrades(game, fake_pool):
    """Bench full, 1 owned + 2 in shop -> buying one auto-buys the other."""
    name = _unit_of_cost(game, 1)
    cost = game.champions_dict[name].cost

    # Exactly one copy owned; remaining 8 bench slots are distinct units.
    _fill_bench_distinct(game, name, BENCH_SLOTS - 1)
    game.team.bench[BENCH_SLOTS - 1] = game.champions_dict[name].copy()
    assert game.team.bench_is_full()
    assert sum(1 for u in game.team.all_units()
               if u.name == name and u.level == 1) == 1

    gold_before = game.gold
    _stock_shop(game, fake_pool, name, copies=2)

    # Buying just one copy pulls the second one and upgrades.
    assert game.buy_unit(1) == 'ok'
    assert game.gold == gold_before - 2 * cost

    owned = [u for u in game.team.all_units() if u.name == name]
    assert len(owned) == 1
    assert owned[0].level == 2
    # Both shop copies were consumed.
    assert [u.name for u in game.cur_shop if u.name != 'BLANK'].count(name) == 0


def test_bench_full_no_upgrade_still_fails_with_no_side_effects(game, fake_pool):
    name = _unit_of_cost(game, 1)
    _fill_bench_distinct(game, name, BENCH_SLOTS)
    assert game.team.bench_is_full()
    gold_before = game.gold
    bench_before = list(game.team.bench)

    _stock_shop(game, fake_pool, name, copies=1)  # 0 owned, only 1 in shop
    assert game.buy_unit(1) == 'bench_full'
    assert game.gold == gold_before
    assert game.team.bench == bench_before


def test_traits_only_count_board_units(game):
    name = _unit_of_cost(game, 1)
    trait = game.champions_dict[name].traits[0]

    game.team.bench[0] = game.champions_dict[name].copy()
    game.team._recompute_traits()
    assert trait not in game.team.traits

    assert game.team.move_bench_to_board(0, (0, 0))
    assert game.team.traits.get(trait) == 1
    assert game.team.bench[0] is None


def test_board_capacity_is_player_level(game):
    game.team.player_level = 2
    names = [n for n in game.champions_dict][:3]
    for slot, n in enumerate(names):
        game.team.bench[slot] = game.champions_dict[n].copy()

    assert game.team.move_bench_to_board(0, (0, 0)) is True
    assert game.team.move_bench_to_board(1, (0, 1)) is True
    # Third unit would exceed level (2) -> rejected, stays on bench.
    assert game.team.move_bench_to_board(2, (0, 2)) is False
    assert game.team.bench[2] is not None
    assert len(game.team.board) == 2


def test_move_board_to_bench_and_swap(game):
    a, b = [n for n in game.champions_dict][:2]
    game.team.bench[0] = game.champions_dict[a].copy()
    game.team.bench[1] = game.champions_dict[b].copy()
    game.team.move_bench_to_board(0, (1, 1))

    # Move back to a specific empty bench slot.
    assert game.team.move_board_to_bench((1, 1), 4)
    assert game.team.bench[4].name == a
    assert (1, 1) not in game.team.board
