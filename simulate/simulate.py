#!/usr/bin/env python3
"""Reference simulator for the TFT fight-prediction task.

Reads a unit database and a directory of team files, plays out a deterministic
tick-based fight between every pair of teams under the simplified ruleset in
instruction.md, and writes, for each pair, the winner (or "tie") followed by one
record per surviving unit to /app/results.json.

All quantities that feed a comparison or a rounded output are kept as integers
(ticks, squared distances, integer-ceil distances, half-down damage) so the
result is bit-for-bit reproducible with no floating-point drift.
"""

import json
import math
import os
import sys

TICKS_PER_SECOND = 100          # 0.01s granularity
MAX_TICK = 55 * TICKS_PER_SECOND  # 55.00s -> tick 5500 (inclusive) is the tie cap
MOVE_TICKS = 25                 # 0.25s to step into an adjacent cell

# The six hex neighbours: two horizontal (dx=+-2) and four diagonal (dx,dy=+-1).
# Every offset preserves the x%2==y%2 parity of a valid cell.
NEIGHBOR_OFFSETS = ((-2, 0), (2, 0), (-1, -1), (1, -1), (-1, 1), (1, 1))


def round_half_down(x):
    """Round to the nearest integer; an exact .5 rounds down."""
    f = math.floor(x)
    return f + 1 if (x - f) > 0.5 else f


def scale_stat(base, level):
    """base * 1.5^(level-1) (level 3 -> 2.25x), rounded to the nearest integer
    with halves rounding down. Done as base * 3^(level-1) / 2^(level-1) with
    integer division so it is exact."""
    num = base * 3 ** (level - 1)
    den = 2 ** (level - 1)
    q, r = divmod(num, den)
    return q + 1 if 2 * r > den else q


def damage_hit(attacker, defense):
    """Damage one auto-attack from `attacker` deals against `defense`:
    damage * 100 / (100 + defense), rounded to nearest int, .5 rounds down.
    `attacker.damage` is already the level-scaled, rounded value."""
    numerator = attacker.damage * 100
    denominator = 100 + defense
    q, r = divmod(numerator, denominator)
    # Round up only when the remainder is strictly more than half.
    return q + 1 if 2 * r > denominator else q


def ceil_dist(ax, ay, bx, by):
    """Euclidean distance between two cells, always rounded up (integer-exact)."""
    n = (ax - bx) ** 2 + (ay - by) ** 2
    r = math.isqrt(n)
    return r if r * r == n else r + 1


def sq_dist(ax, ay, bx, by):
    """Squared euclidean distance (monotonic in true distance, so safe for
    comparisons that the spec phrases in terms of raw euclidean distance)."""
    return (ax - bx) ** 2 + (ay - by) ** 2


def load_units(path):
    """Parse units.json into a template dict keyed by unit name."""
    with open(path) as fp:
        raw = json.load(fp)
    db = {}
    for name, u in raw.items():
        mr, armor, dmg = u["mr"], u["armor"], u["damage"]
        # The ruleset's arithmetic is integer-exact only if these are whole
        # numbers; every shipped unit satisfies this.
        assert float(mr).is_integer() and float(armor).is_integer(), name
        assert float(dmg).is_integer(), name
        parts = u["role"].split()
        first = parts[0] if parts else ""
        if "Tank" in parts:
            rank = 0          # highest targeting priority
        elif "Assassin" in parts:
            rank = 2          # lowest targeting priority
        else:
            rank = 1
        db[name] = {
            "hp": u["hp"],
            "damage": int(dmg),
            "mr": int(mr),
            "armor": int(armor),
            "rng": u["range"],
            "interval": round_half_down(TICKS_PER_SECOND / u["speed"]),
            "role_first": first,
            "rank": rank,
        }
    return db


def load_team(path):
    """Return (team_name, [(unit_name, level, position), ...]) for a team file.

    Each line is "unit name:level:position". Unit names may contain spaces,
    '&' and "'", but never a colon, so split off the last two fields.
    """
    name = os.path.basename(path)
    if name.endswith(".txt"):
        name = name[:-4]
    entries = []
    with open(path) as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            unit_name, level, pos = line.rsplit(":", 2)
            entries.append((unit_name.strip(), int(level), pos.strip()))
    return name, entries


def ally_cell(pos):
    """Translate an ally board notation (e.g. 'A4') into (x, y)."""
    row = pos[0]
    col = int(pos[1:])
    y = {"A": 4, "B": 3, "C": 2, "D": 1}[row]
    x = 2 * col if row in ("A", "C") else 2 * col + 1
    return x, y


def enemy_cell(pos):
    """Enemy positioning is the ally board rotated 180 degrees with two empty
    rows inserted between the teams: x -> 15 - x, y -> 11 - y."""
    x, y = ally_cell(pos)
    return 15 - x, 11 - y


def in_bounds(x, y):
    return 0 <= x <= 15 and 1 <= y <= 10 and (x % 2) == (y % 2)


def neighbors(x, y):
    out = []
    for dx, dy in NEIGHBOR_OFFSETS:
        nx, ny = x + dx, y + dy
        if in_bounds(nx, ny):
            out.append((nx, ny))
    return out


class Unit:
    __slots__ = (
        "name", "side", "x", "y", "hp", "damage", "mr", "armor",
        "rng", "interval", "role_first", "rank", "ready_tick", "target",
        "in_transit", "dest", "arrival_tick", "alive", "foes", "level",
        "max_hp",
    )

    def __init__(self, tmpl, name, side, cell, level):
        self.name = name
        self.side = side          # 'ally' or 'enemy'
        self.level = level
        self.x, self.y = cell
        # hp and damage scale with level (1.5x per level above 1), rounded to
        # the nearest integer with halves rounding down; other stats are flat.
        self.hp = scale_stat(tmpl["hp"], level)
        self.max_hp = self.hp
        self.damage = scale_stat(tmpl["damage"], level)
        self.mr = tmpl["mr"]
        self.armor = tmpl["armor"]
        self.rng = tmpl["rng"]
        self.interval = tmpl["interval"]
        self.role_first = tmpl["role_first"]
        self.rank = tmpl["rank"]
        self.ready_tick = 0       # first attack is "loaded" at t=0
        self.target = None        # locked, in-range enemy (or None)
        self.in_transit = False
        self.dest = None
        self.arrival_tick = None
        self.alive = True
        self.foes = []            # opposing team's unit list


def attack_damage(attacker, target):
    """Damage one auto-attack from attacker deals to target (by damage type)."""
    if attacker.role_first == "Magic":
        return damage_hit(attacker, target.mr)
    if attacker.role_first == "Attack":
        return damage_hit(attacker, target.armor)
    # Riven ("Hybrid"): use whichever damage type is larger, physical on a tie.
    magic = damage_hit(attacker, target.mr)
    phys = damage_hit(attacker, target.armor)
    return magic if magic > phys else phys


def target_key(u, c, use_ceil):
    """Sort key for selecting which enemy unit `c` unit `u` prefers.

    Chain: distance -> role -> team-side -> center -> lowest y -> lowest x.
    All candidates share a team, so the team-side term is internally consistent
    (ally candidates prefer smallest x, enemy candidates prefer largest x).
    """
    dist = ceil_dist(u.x, u.y, c.x, c.y) if use_ceil else sq_dist(u.x, u.y, c.x, c.y)
    side = c.x if c.side == "ally" else -c.x
    center = sq_dist(c.x, c.y, 8, 5)
    return (dist, c.rank, side, center, c.y, c.x)


def cell_key(u, cell, tx, ty):
    """Sort key for which adjacent cell `u` moves into, aiming at (tx, ty).

    Chain (role step does not apply to cells): euclidean-to-target ->
    mover's team-side -> center -> lowest y -> lowest x.
    """
    cx, cy = cell
    dist = sq_dist(cx, cy, tx, ty)
    side = cx if u.side == "ally" else -cx
    center = sq_dist(cx, cy, 8, 5)
    return (dist, side, center, cy, cx)


def contest_winner(units):
    """Pick the unit that wins a contested destination cell.

    Movement contests start at tiebreak step 3 (team-side). When all
    contestants share a team, that team's directional preference applies;
    a mixed-team contest cannot be decided by team-side and falls through to
    center -> lowest y -> lowest x.
    """
    same_team = len({u.side for u in units}) == 1

    def key(u):
        center = sq_dist(u.x, u.y, 8, 5)
        if same_team:
            side = u.x if u.side == "ally" else -u.x
            return (side, center, u.y, u.x)
        return (center, u.y, u.x)

    return min(units, key=key)


def acquire(u):
    """Refresh u.target: keep a still-valid locked target, otherwise lock the
    closest in-range enemy (or leave it None, meaning the unit must move)."""
    if u.target is not None and u.target.alive:
        if ceil_dist(u.x, u.y, u.target.x, u.target.y) <= 2 * u.rng:
            return  # sticky: keep the current target while it stays in range
    enemies = [e for e in u.foes if e.alive]
    if not enemies:
        u.target = None
        return
    best = min(enemies, key=lambda c: target_key(u, c, True))
    if ceil_dist(u.x, u.y, best.x, best.y) <= 2 * u.rng:
        u.target = best
    else:
        u.target = None


def start_movement(units, now):
    """Assign destination cells to every unit that needs to move this tick."""
    movers = [u for u in units if u.alive and not u.in_transit and u.target is None]
    if not movers:
        return

    occupied = {(u.x, u.y) for u in units if u.alive}
    reserved = {u.dest for u in units if u.alive and u.in_transit}

    # Each mover heads toward the closest enemy (raw euclidean + tiebreak).
    move_target = {}
    for u in movers:
        enemies = [e for e in u.foes if e.alive]
        if enemies:
            move_target[u] = min(enemies, key=lambda c: target_key(u, c, False))

    pending = [u for u in movers if u in move_target]
    claimed = {}   # cell -> winning unit

    # Iterative contest resolution: everyone proposes their best available
    # cell, each contested cell is awarded to one unit, losers re-propose
    # against the shrinking set of free cells until nobody new can move.
    while True:
        proposals = {}
        for u in pending:
            if u in claimed.values():
                continue
            tx, ty = move_target[u].x, move_target[u].y
            avail = [
                c for c in neighbors(u.x, u.y)
                if c not in occupied and c not in reserved and c not in claimed
            ]
            if not avail:
                continue  # fully blocked this round
            best = min(avail, key=lambda c: cell_key(u, c, tx, ty))
            proposals.setdefault(best, []).append(u)
        if not proposals:
            break
        for cell, contenders in proposals.items():
            claimed[cell] = contest_winner(contenders)

    for cell, u in claimed.items():
        u.in_transit = True
        u.dest = cell
        u.arrival_tick = now + MOVE_TICKS


def simulate(ally, enemy):
    """Run one fight to completion; return 'ally', 'enemy', or 'tie'."""
    units = ally + enemy
    for now in range(0, MAX_TICK + 1):
        # 1. Complete movements that land on this tick.
        for u in units:
            if u.alive and u.in_transit and u.arrival_tick == now:
                u.x, u.y = u.dest
                u.in_transit = False
                u.dest = None
                u.arrival_tick = None

        # 2. Lock targets (units mid-move do not re-target).
        for u in units:
            if u.alive and not u.in_transit:
                acquire(u)

        # 3. Attacks fire simultaneously; collect damage before applying it.
        incoming = {}
        for u in units:
            if (u.alive and not u.in_transit and u.target is not None
                    and now >= u.ready_tick):
                incoming[u.target] = incoming.get(u.target, 0) + attack_damage(u, u.target)
                u.ready_tick = now + u.interval

        # 4. Apply damage and remove the dead.
        for tgt, dmg in incoming.items():
            tgt.hp -= dmg
        for u in units:
            if u.alive and u.hp <= 0:
                u.alive = False
                u.target = None
                u.in_transit = False
                u.dest = None
                u.arrival_tick = None
        for u in units:
            if u.alive and u.target is not None and not u.target.alive:
                u.target = None

        # 5. Resolve the fight: a wipe wins; the 55s cap is a tie.
        ally_alive = any(u.alive for u in ally)
        enemy_alive = any(u.alive for u in enemy)
        if not ally_alive and not enemy_alive:
            return "tie"
        if not ally_alive:
            return "enemy"
        if not enemy_alive:
            return "ally"
        if now == MAX_TICK:
            return "tie"

        # 6. Re-acquire for units whose target just died (mid-move units skip).
        for u in units:
            if u.alive and not u.in_transit and u.target is None:
                acquire(u)

        # 7. Begin movements for units still without an in-range target.
        start_movement(units, now)

    return "tie"


def run_fight(db, ally_name, ally_entries, enemy_name, enemy_entries):
    ally = [Unit(db[n], n, "ally", ally_cell(p), lvl) for n, lvl, p in ally_entries]
    enemy = [Unit(db[n], n, "enemy", enemy_cell(p), lvl) for n, lvl, p in enemy_entries]
    for u in ally:
        u.foes = enemy
    for u in enemy:
        u.foes = ally
    outcome = simulate(ally, enemy)
    if outcome == "ally":
        winner = ally_name
    elif outcome == "enemy":
        winner = enemy_name
    else:
        winner = "tie"
    # Survivors are reported ally-side first, each side in team-file order.
    # Damage taken (not remaining hp) so the output never discloses a unit's
    # level-scaled maximum, which would make scale_stat directly invertible.
    survivors = [
        {"name": u.name, "level": u.level, "damage_taken": u.max_hp - u.hp}
        for u in ally + enemy if u.alive
    ]
    return [winner] + survivors


def main():
    if len(sys.argv) != 4:
        print("Usage: python simulate/simulate.py {units.json} {teams_directory} {output_file}")
        return 1
    units_path = sys.argv[1]
    teams_dir = sys.argv[2]
    out_files = sys.argv[3]

    db = load_units(units_path)
    teams = {}
    for fn in os.listdir(teams_dir):
        if not fn.endswith(".txt"):
            continue
        name, entries = load_team(os.path.join(teams_dir, fn))
        teams[name] = entries

    names = sorted(teams)
    results = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]  # a is lexicographically lower (the ally)
            results[f"{a}_{b}"] = run_fight(db, a, teams[a], b, teams[b])

    with open(sys.argv[3], "w") as fp:
        fp.write(json.dumps(results, indent=4, sort_keys=True))


if __name__ == "__main__":
    main()
