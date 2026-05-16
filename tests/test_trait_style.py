"""Trait background tier mapping (bronze/silver/gold/prismatic)."""

from shared.rolldown_classes import Trait


def make(breakpoints):
    return Trait("T", breakpoints, [1] * len(breakpoints))


def test_inactive_returns_none():
    trait = make([3, 6])
    assert trait.style_tier(0) is None
    assert trait.style_tier(2) is None


def test_two_breakpoints_low_is_bronze_high_is_gold():
    trait = make([3, 6])
    assert trait.style_tier(3) == "bronze"
    assert trait.style_tier(5) == "bronze"
    assert trait.style_tier(6) == "gold"
    assert trait.style_tier(99) == "gold"


def test_middle_breakpoints_are_silver():
    trait = make([2, 4, 6, 8])
    tiers = [trait.style_tier(b) for b in (2, 4, 6, 8)]
    assert tiers[0] == "bronze"
    assert "silver" in tiers
    assert tiers[-1] == "gold"
    # Lowest is never higher than the highest.
    order = ["bronze", "silver", "gold"]
    assert order.index(tiers[0]) <= order.index(tiers[-1])


def test_breakpoint_ten_or_more_is_prismatic_and_prior_is_gold():
    trait = make([4, 7, 10])
    assert trait.style_tier(4) == "bronze"
    assert trait.style_tier(7) == "gold"        # the one right before 10
    assert trait.style_tier(9) == "gold"
    assert trait.style_tier(10) == "prismatic"
    assert trait.style_tier(15) == "prismatic"


def test_single_breakpoint_is_bronze():
    trait = make([1])
    assert trait.style_tier(1) == "bronze"
    assert trait.style_tier(50) == "bronze"


def test_consistency_same_count_same_tier():
    trait = make([2, 4, 6, 8])
    assert trait.style_tier(5) == trait.style_tier(5)
    assert trait.style_tier(4) == trait.style_tier(4)
