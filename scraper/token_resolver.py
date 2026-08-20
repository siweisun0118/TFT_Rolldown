"""
Resolves the @Token@ placeholders and Riot calculation trees found in metatft's raw
TFT ability data (data.metatft.com's `ability.desc` + `ability.variables` +
`ability.calculations`) into a readable description string with real numbers
substituted in - replicating (a validated subset of) the client-side tooltip math
metatft's own frontend performs, evaluated at baseline stats (no bonus items), which
is what the tooltip shows by default.

How this was derived: there's no separate "resolved text" API - metatft computes the
tooltip client-side from this same data. That was confirmed by cross-referencing the
raw `variables`/`calculations` arithmetic against the live site's rendered numbers for
several champions (Jhin, Bel'Veth, Gragas, Maokai, Briar), which is also how the
formulas below were reverse-engineered (no official schema exists for this data).

Validated behavior for `SubPartScaledProportionalToStat` (the workhorse of most
ability damage/healing numbers):
  - mStat=3 (Attack Damage): self-scaling stat, baseline ratio is 1, so the result is
    just `part_value * mRatio`.
  - mStat omitted (implicit Ability Power): baseline AP is conventionally 100, so the
    result is `part_value * mRatio * 100`.
  - mStat=12 (Health): unlike AD/AP this reads the champion's actual current HP (not
    a baseline-1 ratio), so the result is `part_value * mRatio * champion_hp_at_level`.
    This requires the champion's real per-level HP; metatft's `stats.hp` is only the
    1-star value, but every Set 17 champion scales health by exactly 1.8x per star, so
    it's derived as `[hp, hp*1.8, hp*1.8**2]` (confirmed against all 63 champions).

NOT validated - deliberately left unresolved rather than guessed, because ground truth
was inconsistent or unavailable across the roster for these:
  - Any other `mStat` value used within `SubPartScaledProportionalToStat` (only 1 was
    seen elsewhere, on Aatrox, whose cached ability data itself turned out to be stale
    versus the live site - see scrape_all's staleness check - so there was no reliable
    ground truth to validate against).
  - `StatByCoefficientCalculationPart`, `StatByNamedDataValueCalculationPart`,
    `StatBySubPartCalculationPart`, `BuffCounterByCoefficientCalculationPart`,
    `BuffCounterByNamedDataValueCalculationPart` - these read live/bonus/stack-based
    stats whose baseline convention couldn't be confirmed generically.

Unresolved tokens are left as their raw `@Token@` text in the output (nothing is
silently guessed), and their names are returned separately so callers can report
coverage.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TOKEN_RE = re.compile(r'@([A-Za-z0-9_]+)(?:\*(-?[0-9.]+))?@')
TAG_RE = re.compile(r'<[^>]+>')
ICON_PLACEHOLDER_RE = re.compile(r'%i:[A-Za-z0-9]+%')

AD_STAT = 3
HEALTH_STAT = 12
HEALTH_STAR_MULTIPLIER = 1.8


@dataclass
class ResolvedAbility:
    text: str
    unresolved_tokens: List[str] = field(default_factory=list)


class _Unresolved:
    """Sentinel: this calculation subtree couldn't be confidently evaluated."""


UNRESOLVED = _Unresolved()


def health_levels_from_base(base_hp: float) -> List[float]:
    """Derive [star1, star2, star3] HP from the 1-star value (all Set 17 champions scale by 1.8x/star)."""
    return [base_hp, base_hp * HEALTH_STAR_MULTIPLIER, base_hp * HEALTH_STAR_MULTIPLIER ** 2]


def _lookup_variable(name: str, variables: Dict[str, List[float]]) -> Optional[List[float]]:
    """Look up a variable by name, falling back to a case-insensitive match.

    Riot's own data has real casing mismatches between a variable's declared name
    (e.g. "HEALING") and how a calculation/desc token references it (e.g. "Healing"),
    so an exact-only lookup silently drops otherwise-resolvable tokens.
    """
    values = variables.get(name)
    if values:
        return values
    lowered = name.lower()
    for key, value in variables.items():
        if key.lower() == lowered and value:
            return value
    return None


def _broadcast(values: Any, length: int) -> List[float]:
    if isinstance(values, list):
        if len(values) == length:
            return values
        if len(values) == 1:
            return values * length
        # Mismatched lengths (e.g. a 2-level Aatrox-style array meeting a 3-level
        # one) can't be zipped meaningfully - bail rather than guess an alignment.
        return [values[-1]] * length if values else []
    return [values] * length


def _combine(parts: List[Any], binary_op) -> Any:
    if any(p is UNRESOLVED for p in parts):
        return UNRESOLVED
    lengths = [len(p) for p in parts if isinstance(p, list) and p]
    length = max(lengths) if lengths else 1
    normalized = [_broadcast(p, length) for p in parts]
    if any(len(p) != length for p in normalized):
        return UNRESOLVED
    result = normalized[0]
    for other in normalized[1:]:
        result = [binary_op(a, b) for a, b in zip(result, other)]
    return result


def _evaluate_calc(name: str, calculations: Dict[str, Any], variables: Dict[str, List[float]],
                    health_levels: Optional[List[float]], stack: Tuple[str, ...]) -> Any:
    entries = calculations.get(name)
    if not entries:
        return UNRESOLVED
    if not isinstance(entries, list):
        entries = [entries]
    # A calculation key can map to multiple top-level parts (e.g. Leona's ModifiedDamage
    # is [armor-scaling term, MR-scaling term, base damage]) that implicitly sum together.
    nodes = [_evaluate(entry, variables, calculations, health_levels, stack + (name,)) for entry in entries]
    if len(nodes) == 1:
        return nodes[0]
    return _combine(nodes, lambda a, b: a + b)


def _evaluate(node: Any, variables: Dict[str, List[float]], calculations: Dict[str, Any],
              health_levels: Optional[List[float]], stack: Tuple[str, ...]) -> Any:
    """Evaluate a calculation-part node into a per-level list of numbers, or UNRESOLVED."""
    if not isinstance(node, dict):
        return UNRESOLVED

    node_type = node.get('type')

    if node_type == 'NamedDataValueCalculationPart':
        name = node.get('name')
        values = _lookup_variable(name, variables)
        if values:
            return list(values)
        if name in calculations and name not in stack:
            return _evaluate_calc(name, calculations, variables, health_levels, stack)
        return UNRESOLVED

    if node_type == 'NumberCalculationPart':
        return node.get('mNumber', 0)

    if node_type == 'SumOfSubPartsCalculationPart':
        parts = [_evaluate(p, variables, calculations, health_levels, stack) for p in node.get('parts', [])]
        if not parts:
            return UNRESOLVED
        return _combine(parts, lambda a, b: a + b)

    if node_type == 'ProductOfSubPartsCalculationPart':
        p1 = _evaluate(node.get('part1'), variables, calculations, health_levels, stack)
        p2 = _evaluate(node.get('part2'), variables, calculations, health_levels, stack)
        return _combine([p1, p2], lambda a, b: a * b)

    if node_type == 'ExponentSubPartsCalculationPart':
        p1 = _evaluate(node.get('part1'), variables, calculations, health_levels, stack)
        p2 = _evaluate(node.get('part2'), variables, calculations, health_levels, stack)
        return _combine([p1, p2], lambda a, b: a ** b)

    if node_type == 'ClampSubPartsCalculationPart':
        parts = node.get('parts', [])
        if not parts:
            return UNRESOLVED
        value = _evaluate(parts[0], variables, calculations, health_levels, stack)
        if value is UNRESOLVED:
            return UNRESOLVED
        floor = node.get('mFloor')
        ceiling = node.get('mCeiling')

        def clamp(v):
            if floor is not None:
                v = max(v, floor)
            if ceiling is not None:
                v = min(v, ceiling)
            return v

        if isinstance(value, list):
            return [clamp(v) for v in value]
        return clamp(value)

    if node_type == 'SubPartScaledProportionalToStat':
        part_value = _evaluate(node.get('part'), variables, calculations, health_levels, stack)
        if part_value is UNRESOLVED:
            return UNRESOLVED
        ratio = node.get('mRatio', 1)
        m_stat = node.get('mStat')

        if m_stat is None:
            # Implicit Ability Power scaling; baseline AP is conventionally 100.
            multiplier = ratio * 100
            return [v * multiplier for v in part_value]

        if m_stat == AD_STAT:
            # Self-ratio stat (Attack Damage): baseline ratio is 1.
            return [v * ratio for v in part_value]

        if m_stat == HEALTH_STAT:
            if not health_levels:
                return UNRESOLVED
            broadcast_part = _broadcast(part_value, len(health_levels))
            return [v * ratio * hp for v, hp in zip(broadcast_part, health_levels)]

        # Unvalidated mStat convention for this calc type - don't guess.
        return UNRESOLVED

    # Same-ability calculation cross-reference. The exact `type` for this varies
    # (metatft/Riot use opaque hashed type names that differ across data pulls), so
    # detect it structurally by the presence of `mSpellCalculationKey` instead.
    if 'mSpellCalculationKey' in node:
        key = node['mSpellCalculationKey']
        if key in stack:
            return UNRESOLVED  # guard against cyclical references
        return _evaluate_calc(key, calculations, variables, health_levels, stack)

    # StatByCoefficientCalculationPart / StatByNamedDataValueCalculationPart /
    # StatBySubPartCalculationPart: "current stat value * something". Validated
    # against the live site for mStat=12 (Health - reads the champion's real,
    # always-nonzero, per-level HP, e.g. Nasus/Cho'Gath's damage-per-missing-health
    # effects) and for other mStat values (Leona's Armor/MR-scaling shield/damage
    # terms evaluated to exactly 0 with no items equipped) - so only Health uses an
    # absolute per-level value here; every other stat represents a bonus-from-items
    # reading that's legitimately 0 at baseline (no items on a fresh board).
    if node_type in ('StatByCoefficientCalculationPart', 'StatByNamedDataValueCalculationPart',
                      'StatBySubPartCalculationPart'):
        m_stat = node.get('mStat')
        if m_stat != HEALTH_STAT:
            return 0

        if node_type == 'StatByCoefficientCalculationPart':
            coefficient = node.get('mCoefficient', 1)
            if not health_levels:
                return UNRESOLVED
            return [coefficient * hp for hp in health_levels]

        if node_type == 'StatByNamedDataValueCalculationPart':
            values = _lookup_variable(node.get('name'), variables)
            if not values or not health_levels:
                return UNRESOLVED
            broadcast_values = _broadcast(values, len(health_levels))
            return [v * hp for v, hp in zip(broadcast_values, health_levels)]

        # StatBySubPartCalculationPart
        part_value = _evaluate(node.get('part'), variables, calculations, health_levels, stack)
        if part_value is UNRESOLVED or not health_levels:
            return UNRESOLVED
        broadcast_part = _broadcast(part_value, len(health_levels))
        return [v * hp for v, hp in zip(broadcast_part, health_levels)]

    # BuffCounterByCoefficientCalculationPart, BuffCounterByNamedDataValueCalculationPart,
    # and any other unrecognized type: not validated, left unresolved rather than guessed.
    return UNRESOLVED


# --- Manual overrides for tokens the calculation engine can't resolve --------------
#
# A handful of tokens across the roster read live game state (buff/stack counters like
# "how many Meeps does the player own") that has no meaningful baseline value to compute
# generically - the engine correctly leaves these unresolved (see the BuffCounterBy*
# handling above). For these specific champion/token pairs, the user validated the
# actual formula against the live game and provided it directly. Keyed by champion name
# + token name (not just token name), since e.g. "ModifiedNumMeeps" means something
# different for each champion that has it.
#
# Each override is one of:
#   - ('stat', part_variable_or_None, ratio, stat_label, plain) - a "value * ratio%Label"
#     scaling term, generalizing SubPartScaledProportionalToStat's AD/Health convention
#     (baseline ratio 1, no absolute-stat lookup) to labels the engine doesn't natively
#     recognize (e.g. "Meeps", "AS"). part_variable_or_None=None means a constant 1 (the
#     term IS the stat itself, e.g. Bard's "100% of Meeps").
#   - ('literal', text, plain) - literal resolved text with no further breakdown.
#
# `plain` controls whether this also resolves in the plain (non-scaling) description;
# when False, the plain description leaves the token unresolved - either because the
# value depends on live game state that can't be shown as one flat number (Bard's ally
# count), or because the user only validated the scaling form.
MANUAL_TOKEN_OVERRIDES: Dict[str, Dict[str, tuple]] = {
    'Aatrox': {
        'ModifiedDamage': ('stat', 'DamageAD', 1.6, 'AD', True),
        'ModifiedNovaDamage': ('stat', 'DamageAD', 1.04, 'AD', True),
    },
    'Bard': {
        'ModifiedNumAllies': ('stat', None, 1.0, 'Meeps', False),
    },
    "Bel'Veth": {
        'TotalNumSlashes': ('stat', 'BaseNumSlashes', 0.25, 'AS', False),
    },
    'Corki': {
        'ModifiedMeepCooldown': ('literal', '(1 - 10%Meeps) * 8', False),
    },
    'Fizz': {
        'ModifiedNumMeeps': ('literal', '1', True),
        'ModifiedChompDamage': ('stat', 'BiteDamageMeep', 1.0, 'Meeps', False),
        'ModifiedMeepBonusDamage': ('stat', 'BiteDamageMeep', 1.0, 'Meeps', False),
    },
}


def _override_stat_values(part_name: Optional[str], variables: Dict[str, List[float]],
                           health_levels: Optional[List[float]]) -> Optional[List[float]]:
    if part_name is None:
        length = len(health_levels) if health_levels else 3
        return [1.0] * length
    values = _lookup_variable(part_name, variables)
    return list(values) if values else None


def _describe_stat_override(values: List[float], ratio: float, label: str) -> str:
    if all(abs(v - 1) < 1e-9 for v in values):
        return f'{_percent_str(ratio)}%{label}'
    return f'{_format_values(values)} * {_percent_str(ratio)}%{label}'


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 0.005:
        return str(int(round(value)))
    if abs(value) >= 10:
        # Riot's tooltips round large computed values (damage, healing, etc.) to whole
        # numbers, but keep natural precision for small values (attack speed, duration,
        # percentages) - there's no per-field formatting hint in this data to know
        # which is which for certain, so magnitude is used as a practical proxy: real
        # designed decimals (0.9 AS, 1.5s stun, 2.5 AS) are always small, while a
        # damage/heal formula's messy fractional remainder (e.g. 495.75) is always large.
        return str(int(round(value)))
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def _format_values(values: List[float]) -> str:
    formatted = [_format_number(v) for v in values]
    if len(set(formatted)) == 1:
        return formatted[0]
    return '/'.join(formatted)


def _strip_markup(text: str) -> str:
    text = ICON_PLACEHOLDER_RE.sub('', text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('<br>', '\n')
    text = TAG_RE.sub('', text)
    # Icon placeholders like "(%i:scaleAD%%i:scaleAP%)" leave behind an empty "()"
    # once stripped - drop those (and the stray leading space they leave) too.
    text = re.sub(r' ?\(\s*\)', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def resolve_ability_text(ability: Dict[str, Any], base_hp: Optional[float] = None,
                          champion_name: Optional[str] = None) -> ResolvedAbility:
    """Resolve an ability's raw templated `desc` into readable text with numbers filled in.

    `ability` is metatft's raw ability dict (with `desc`, `variables`, `calculations`).
    `base_hp` is the champion's 1-star HP, needed only for effects that scale off max
    Health (mStat=12); omit it if unknown - Health-scaling tokens will just be left
    unresolved. `champion_name` enables MANUAL_TOKEN_OVERRIDES for tokens the engine
    can't resolve generically.
    """
    desc = ability.get('desc') or ability.get('description') or ''
    variables = {v['name']: (v.get('value') or []) for v in ability.get('variables', [])}
    calculations = ability.get('calculations', {})
    health_levels = health_levels_from_base(base_hp) if base_hp else None
    overrides = MANUAL_TOKEN_OVERRIDES.get(champion_name, {})

    unresolved: List[str] = []

    def substitute(match: 're.Match') -> str:
        name = match.group(1)
        multiplier = match.group(2)

        override = overrides.get(name)
        if override is not None:
            kind = override[0]
            if kind == 'stat':
                _, part_name, ratio, _label, plain = override
                if plain:
                    values = _override_stat_values(part_name, variables, health_levels)
                    if values is not None:
                        resolved_values = [v * ratio for v in values]
                        if multiplier is not None:
                            factor = float(multiplier)
                            resolved_values = [v * factor for v in resolved_values]
                        return f'**{_format_values(resolved_values)}**'
            else:  # literal
                _, text, plain = override
                if plain:
                    return f'**{text}**'
            unresolved.append(name)
            return match.group(0)

        values = _lookup_variable(name, variables)
        if values is None:
            if name in calculations:
                calc_result = _evaluate_calc(name, calculations, variables, health_levels, ())
                values = None if calc_result is UNRESOLVED else calc_result
            else:
                values = None

        if values is None:
            unresolved.append(name)
            return match.group(0)

        # A calculation can bottom out in a bare scalar (e.g. a bonus-stat term that's
        # legitimately 0 at baseline) rather than a per-level list - normalize so
        # formatting always has a list to work with.
        if not isinstance(values, list):
            values = [values]

        if multiplier is not None:
            factor = float(multiplier)
            values = [v * factor for v in values]

        return f'**{_format_values(values)}**'

    substituted = TOKEN_RE.sub(substitute, desc)
    cleaned = _strip_markup(substituted)
    return ResolvedAbility(text=cleaned, unresolved_tokens=unresolved)


# --- Symbolic scaling breakdown -------------------------------------------------
#
# `resolve_ability_text` collapses a formula like `ADDamage*100%AD + APDamage*1%AP`
# into one final number (e.g. "45/68/688"). `resolve_ability_scaling_text` instead
# keeps each stat-scaling term visible - e.g. "41/62/644 * 100%AD + 4/6/44 * 1%AP" -
# so the underlying scaling (how much a term grows per point of AD/AP/etc.) stays
# legible instead of being baked into one baseline-stats number.

_STAT_LABELS = {AD_STAT: 'AD', HEALTH_STAT: 'Health'}


def _percent_str(ratio: float) -> str:
    percent = ratio * 100
    if abs(percent - round(percent)) < 0.005:
        return str(int(round(percent)))
    return f'{percent:.2f}'.rstrip('0').rstrip('.')


def _describe_scaled_term(node: Dict[str, Any], variables: Dict[str, List[float]],
                           calculations: Dict[str, Any], health_levels: Optional[List[float]],
                           stack: Tuple[str, ...]) -> Optional[str]:
    """Describe a single SubPartScaledProportionalToStat leaf as '<value> * <ratio>%<Stat>'."""
    part_value = _evaluate(node.get('part'), variables, calculations, health_levels, stack)
    if part_value is UNRESOLVED or not isinstance(part_value, list):
        return None

    m_stat = node.get('mStat')
    ratio = node.get('mRatio', 1)

    if m_stat == HEALTH_STAT:
        # Health scaling reads an absolute stat rather than a %ratio, so "X%Health"
        # wouldn't mean the same thing as "X%AD" - show its resolved contribution
        # (still visibly distinct from the AD/AP terms) instead of a percent label.
        if not health_levels:
            return None
        return f'{_format_values([v * ratio * hp for v, hp in zip(part_value, health_levels)])} (Health scaling)'

    label = _STAT_LABELS.get(m_stat) if m_stat is not None else 'AP'
    if label is None:
        return None

    return f'{_format_values(part_value)} * {_percent_str(ratio)}%{label}'


def _describe_node(node: Any, variables: Dict[str, List[float]], calculations: Dict[str, Any],
                    health_levels: Optional[List[float]], stack: Tuple[str, ...]) -> Optional[str]:
    """Describe a calculation node symbolically, breaking Sums into '+'-joined scaling terms."""
    if not isinstance(node, dict):
        return None

    node_type = node.get('type')

    if node_type == 'SubPartScaledProportionalToStat':
        return _describe_scaled_term(node, variables, calculations, health_levels, stack)

    if node_type in ('StatByCoefficientCalculationPart', 'StatByNamedDataValueCalculationPart',
                      'StatBySubPartCalculationPart') and node.get('mStat') == HEALTH_STAT:
        value = _evaluate(node, variables, calculations, health_levels, stack)
        if value is UNRESOLVED:
            return None
        if not isinstance(value, list):
            value = [value]
        return f'{_format_values(value)} (Health scaling)'

    if node_type == 'SumOfSubPartsCalculationPart':
        parts = node.get('parts', [])
        if not parts:
            return None
        descriptions = []
        for part in parts:
            described = _describe_node(part, variables, calculations, health_levels, stack)
            if described is None:
                # Fall back to the resolved number for parts that aren't a scaling
                # term (e.g. a flat NamedDataValue mixed into the sum).
                value = _evaluate(part, variables, calculations, health_levels, stack)
                if value is UNRESOLVED:
                    return None
                if not isinstance(value, list):
                    value = [value]
                described = _format_values(value)
            descriptions.append(described)
        return ' + '.join(descriptions)

    if 'mSpellCalculationKey' in node:
        key = node['mSpellCalculationKey']
        if key in stack:
            return None
        entries = calculations.get(key)
        if not entries:
            return None
        if not isinstance(entries, list):
            entries = [entries]
        return _describe_node(entries[0], variables, calculations, health_levels, stack + (key,)) \
            if len(entries) == 1 else None

    return None


def resolve_ability_scaling_text(ability: Dict[str, Any], base_hp: Optional[float] = None,
                                  champion_name: Optional[str] = None) -> ResolvedAbility:
    """Like resolve_ability_text, but keeps each stat-scaling term visible instead of
    collapsing them into one baseline number - e.g. Jhin's combined "45/68/688" becomes
    "41/62/644 * 100%AD + 4/6/44 * 1%AP".

    Tokens that aren't built from stat-scaling terms (a plain variable, or a calculation
    shape this can't describe symbolically) fall back to the same resolved number
    `resolve_ability_text` would show - there's nothing meaningful to break down.
    `champion_name` enables MANUAL_TOKEN_OVERRIDES for tokens the engine can't resolve
    generically.
    """
    desc = ability.get('desc') or ability.get('description') or ''
    variables = {v['name']: (v.get('value') or []) for v in ability.get('variables', [])}
    calculations = ability.get('calculations', {})
    health_levels = health_levels_from_base(base_hp) if base_hp else None
    overrides = MANUAL_TOKEN_OVERRIDES.get(champion_name, {})

    unresolved: List[str] = []

    def substitute(match: 're.Match') -> str:
        name = match.group(1)
        multiplier = match.group(2)

        override = overrides.get(name)
        if override is not None:
            if multiplier is None:
                kind = override[0]
                if kind == 'stat':
                    _, part_name, ratio, label, _plain = override
                    values = _override_stat_values(part_name, variables, health_levels)
                    if values is not None:
                        return f'**{_describe_stat_override(values, ratio, label)}**'
                else:  # literal
                    _, text, _plain = override
                    return f'**{text}**'
            unresolved.append(name)
            return match.group(0)

        if name in calculations:
            entries = calculations.get(name)
            if not isinstance(entries, list):
                entries = [entries]
            if len(entries) == 1:
                described = _describe_node(entries[0], variables, calculations, health_levels, (name,))
                if described is not None and multiplier is None:
                    return f'**{described}**'

        # Plain variable, or a calculation shape without a symbolic breakdown: fall
        # back to the fully-resolved number (same behavior as resolve_ability_text).
        values = _lookup_variable(name, variables)
        if values is None:
            if name in calculations:
                calc_result = _evaluate_calc(name, calculations, variables, health_levels, ())
                values = None if calc_result is UNRESOLVED else calc_result
            else:
                values = None

        if values is None:
            unresolved.append(name)
            return match.group(0)

        if not isinstance(values, list):
            values = [values]

        if multiplier is not None:
            factor = float(multiplier)
            values = [v * factor for v in values]

        return f'**{_format_values(values)}**'

    substituted = TOKEN_RE.sub(substitute, desc)
    cleaned = _strip_markup(substituted)
    return ResolvedAbility(text=cleaned, unresolved_tokens=unresolved)
