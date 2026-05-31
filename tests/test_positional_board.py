"""Tests for the positional board, swap semantics, and unique-name traits."""

# Standard libraries
import pytest


def _set_shop(game, names):
    """Replace the current shop with units matching *names* (1-indexed)."""
    from shared.rolldown_classes import Unit
    game.cur_shop = []
    for name in names:
        if name is None:
            game.cur_shop.append(Unit(None, 'BLANK', None, None))
            continue
        unit = game.champions_dict[name]
        game.cur_shop.append(unit.copy())
        # Mirror the side effect of rolling so the offline pool stays sane.
        if unit in game._local_pool[unit.rarity]:
            game._local_pool[unit.rarity].remove(unit)
    while len(game.cur_shop) < 5:
        game.cur_shop.append(Unit(None, 'BLANK', None, None))


# --------------------------------------------------------------- placement at any tile
def test_place_unit_at_arbitrary_position(game):
    game.team.bench[0] = game.champions_dict['Aatrox'].copy()
    assert game.move_bench_to_board(0, target_position=('C', 4)) is True
    assert game.team.board_positions[('C', 4)].name == 'Aatrox'
    assert game.team.bench[0] is None


def test_place_unit_does_not_require_top_left(game):
    """The unit can land in row D column 7 even when row A column 1 is empty."""
    game.team.bench[0] = game.champions_dict['Aatrox'].copy()
    assert game.move_bench_to_board(0, target_position=('D', 7))
    assert game.team.board_positions == {('D', 7): game.team.bench[0] or game.champions_dict['Aatrox']}
    # Make sure no other tile is occupied.
    occupied = set(game.team.board_positions.keys())
    assert occupied == {('D', 7)}


# --------------------------------------------------------------- swap on drop
def test_drag_to_occupied_board_tile_swaps(game):
    """Dropping a bench unit on an occupied tile swaps the two units."""
    bench_unit = game.champions_dict['Aatrox'].copy()
    board_unit = game.champions_dict['Akali'].copy()
    game.team.bench[0] = bench_unit
    game.team.bench[1] = board_unit
    assert game.move_bench_to_board(1, target_position=('A', 1))
    assert game.team.board_positions[('A', 1)].name == 'Akali'

    # Now drop Aatrox onto ('A', 1) - should swap with Akali.
    assert game.move_bench_to_board(0, target_position=('A', 1))
    assert game.team.board_positions[('A', 1)].name == 'Aatrox'
    assert game.team.bench[0].name == 'Akali'


def test_board_to_board_swap(game):
    a = game.champions_dict['Aatrox'].copy()
    b = game.champions_dict['Akali'].copy()
    game.team.bench[0] = a
    game.team.bench[1] = b
    game.move_bench_to_board(0, target_position=('A', 1))
    game.move_bench_to_board(1, target_position=('B', 3))

    # Move B → A1 → swap.
    assert game.move_board_to_board(('B', 3), ('A', 1)) is True
    assert game.team.board_positions[('A', 1)].name == 'Akali'
    assert game.team.board_positions[('B', 3)].name == 'Aatrox'


def test_board_to_bench_swap_preserves_units(game):
    """Dropping a board unit onto an occupied bench slot swaps them."""
    board_unit = game.champions_dict['Aatrox'].copy()
    bench_unit = game.champions_dict['Akali'].copy()
    game.team.bench[0] = board_unit
    game.team.bench[3] = bench_unit
    game.move_bench_to_board(0, target_position=('B', 2))
    assert game.team.bench[0] is None  # Aatrox moved to board

    # Drag Aatrox from (B,2) onto bench[3] (occupied by Akali).
    assert game.move_board_to_bench(('B', 2), 3)
    assert game.team.bench[3].name == 'Aatrox'
    assert game.team.board_positions[('B', 2)].name == 'Akali'


# ---------------------------------------------------------- unique-name traits
def test_traits_count_unique_champions_only(game):
    """Three star-2 + one star-1 of the same champion still counts traits once."""
    aatrox = game.champions_dict['Aatrox']
    # Two copies on the board – they must only contribute their traits once.
    game.team.board_positions[('A', 1)] = aatrox.copy()
    game.team.board_positions[('A', 2)] = aatrox.copy()
    traits = game.team.traits
    for trait in aatrox.traits:
        assert traits[trait] == 1, f'{trait} should count once, got {traits[trait]}'


def test_traits_count_unique_with_different_levels(game):
    """A star-1 and a star-2 of the same name still count traits once."""
    aatrox = game.champions_dict['Aatrox']
    one_star = aatrox.copy()
    two_star = aatrox.copy()
    two_star.level = 2
    game.team.board_positions[('A', 1)] = one_star
    game.team.board_positions[('B', 2)] = two_star
    traits = game.team.traits
    for trait in aatrox.traits:
        assert traits[trait] == 1


def test_traits_include_each_distinct_champion(game):
    a = game.champions_dict['Aatrox'].copy()  # Bastion + N.O.V.A.
    b = game.champions_dict['Akali'].copy()   # Marauder + N.O.V.A.
    game.team.board_positions[('A', 1)] = a
    game.team.board_positions[('A', 2)] = b
    traits = game.team.traits
    assert traits['N.O.V.A.'] == 2  # both champions share this trait
    assert traits.get('Bastion', 0) == 1
    assert traits.get('Marauder', 0) == 1


# -------------------------------------------------------------------- board cap
def test_board_full_blocks_new_placement_not_swap(game):
    game.level = 2  # cap = 2
    a = game.champions_dict['Aatrox'].copy()
    b = game.champions_dict['Akali'].copy()
    c = game.champions_dict['Caitlyn'].copy()
    game.team.bench[0] = a
    game.team.bench[1] = b
    game.team.bench[2] = c
    assert game.move_bench_to_board(0, target_position=('A', 1))
    assert game.move_bench_to_board(1, target_position=('A', 2))
    # Empty placement fails because of the cap.
    assert game.move_bench_to_board(2, target_position=('B', 3)) is False
    assert game.last_notification == 'Team is full'
    # But swap with an occupied tile is allowed (does not grow the board).
    assert game.move_bench_to_board(2, target_position=('A', 1))
    assert game.team.board_positions[('A', 1)].name == 'Caitlyn'
    assert game.team.bench[2].name == 'Aatrox'
