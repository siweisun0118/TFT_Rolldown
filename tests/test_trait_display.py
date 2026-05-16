"""Trait ordering by closeness + 'show the next breakpoint' display rule."""

from shared.rolldown_classes import Team, Trait


def _team(traits_dict):
    return Team({}, traits_dict, client_socket=None, player_level=9)


def test_breakpoint_target_shows_next_when_at_a_breakpoint():
    # Psionic-style: breakpoints 2 / 4.
    team = _team({'Psionic': Trait('Psionic', [2, 4], [1, 2])})
    # At the first breakpoint (2) -> show the *next* one (4).
    assert team.breakpoint_target('Psionic', 2) == 4
    assert team.breakpoint_target('Psionic', 1) == 2
    assert team.breakpoint_target('Psionic', 3) == 4
    # At/over the final breakpoint -> show the final breakpoint.
    assert team.breakpoint_target('Psionic', 4) == 4
    assert team.breakpoint_target('Psionic', 7) == 4


def test_single_breakpoint_one_one():
    team = _team({'Solo': Trait('Solo', [1], [1])})
    assert team.breakpoint_target('Solo', 1) == 1  # 1/1


def test_sorted_traits_orders_by_closeness():
    traits_dict = {
        'Maxed': Trait('Maxed', [1], [1]),       # 1/1  -> ratio 1.0
        'TwoThree': Trait('TwoThree', [3], [1]),  # 2/3  -> ratio 0.667
        'OneTwo': Trait('OneTwo', [2], [1]),      # 1/2  -> ratio 0.5
    }
    team = _team(traits_dict)
    team.traits = {'OneTwo': 1, 'TwoThree': 2, 'Maxed': 1}

    order = [name for name, _, _ in team.sorted_traits()]
    assert order == ['Maxed', 'TwoThree', 'OneTwo']

    rows = {name: (amount, target) for name, amount, target in team.sorted_traits()}
    assert rows['Maxed'] == (1, 1)
    assert rows['TwoThree'] == (2, 3)
    assert rows['OneTwo'] == (1, 2)


def test_get_traits_uses_sorted_order_and_next_breakpoint():
    traits_dict = {
        'Psionic': Trait('Psionic', [2, 4], [1, 2]),
        'OneTwo': Trait('OneTwo', [2], [1]),
    }
    team = _team(traits_dict)
    team.traits = {'OneTwo': 1, 'Psionic': 2}

    strings = team.get_traits()
    # Psionic 2/4 (ratio .5) ties with OneTwo 1/2 (ratio .5); higher count
    # wins the tie, so Psionic comes first.
    assert strings[0] == 'Psionic 2/4'
    assert 'OneTwo 1/2' in strings
