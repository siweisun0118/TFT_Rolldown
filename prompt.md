This is a Python/PyQt5 TFT (Teamfight Tactics) rolldown simulator. Read through the repository — GUI, shared game/networking layer, the combat simulator in simulate/, the data directories, and the test suite — and produce an implementation for the following features. For systems like unit stats and items, refer specifically to `TFT_Set_17/`. Some information in `TFT_Set_17/champion_stats.json` and `TFT_Set_17/items_semantic.json` (specifically, both mana fields, all ability fields), will not be used for this task.

1. A "lobby" system where GUI users who have finished their rolldowns can see the status of other users on the same server.
2. Users can challenge others in the lobby, starting a simulated fight using `simulate/simulate.py`. Users watch the fight play out in the GUI, with a slider controlling playback speed — simulate.py ticks every 0.01s, and the slider should range from each tick taking 1 second of real time down to 0.01 seconds. There must also be buttons to replay the fight from the beginning and to return to the lobby.
3. Health bars in the GUI that update as units take damage. Health bars should be green on a red background, and the amount of green should be proportional to the %current hp.
4. "Hooks" that fire when combat events happen (combat start, unit dies, unit attacks, unit drops below % HP, etc.). Hooks should be enumerated in `simulate/hooks.py`.
5. "Keywords" that have specific effects: "Burn" means the unit loses X% hp per second over the next Y seconds, "Sunder" means that the unit loses 30% armor, "Shred" means the unit loses 30% MR, and "Wound" means the unit heals for that % less. "Precision" is also mentioned, and it means the unit's ability can crit, but you do NOT need to implement abilities yet. "Untargetable," "Sheds negative effects," and "crowd-control immunity" can also be ignored for now.
6. "Items" that grant stats and have effects driven by those hooks. `TFT_Set_17/items_semantic.json` currently contains the list of items to implement, their stats (to be added to the equipped unit), and prose describing what the item does. Convert the prose to a list of hooks to trigger before implementing the items, and write the results to `TFT_Set_17/items.json` (replace the "effect" value with a JSON array of hooks to trigger). Generate a random list of six items at the start of rolldown for the user. Users can equip items to a unit (up to three items per unit) by dragging the items over the unit on the board, and unequip items by right clicking the unit. The item bar should be to the left of the map.
    6a. Certain items (specifically, items that have to do with mana or abilities, or crowd control) will not have effects; those should not yet be implemented. The full list is:
        Blue Buff
        Spear of Shojin
        Edge of Night
        Quicksilver
        Nashor's Tooth
    Other items will interact with abilities or mana, but are not wholly dependent on it. Ignore the mana components, but implement rest of the items' functionality.
    6b. Thief's Gloves count as 1 item unless they are equipped to a unit, then it counts as 3 items. Cannot be equipped to a unit that already has any item equipped, and units with a Thief's Gloves equipped cannot equip any more items. The "random items" should be decided at the start of the rolldown phase (decided items do not change, multiple TGs decide individually).
7. In a fight, right clicking a unit should bring up a tab showing all the unit's stats, including current HP. It should NOT stop the fight from progressing.

Assume these constraints: same-machine multiplayer only (multiple GUI processes against one shared server) — cross-machine support is currently out of scope. `simulate/simulate.py`'s batch CLI output format may be changed if necessary, but current functionality should always be kept as an option. For "%HP" hooks, use remaining HP crossing the threshold, latched to fire once. Implement the speed slider mapping literally as described. Health bars should not appear outside of combat. Challenges may be declined, one at a time, with boards snapshotted when accepted.

`simulate/simulate.py` updates:
1. The "damage" stat should be scaled based on the unit's AP (for units with the Magic role) or AD (for units with the Attack role); Hybrid units should scale with whichever is higher. The scaling is always "damage * (AD or AP) / 100", rounded the same way as everything else is rounded in `simulate/simulate.py`. Damage scaling is done after stat scaling from star levels.
2. "omnivamp" means the unit heals for that percentage of all damage they deal.
3. "Durability" means that the unit takes X% reduced damage. Multiple sources of durability stack multiplicatively instead of additively.
4. "Shield" means that damage dealt to the unit is dealt to the shield instead. Shield is removed when its effect ends, regardless of how much is left (nothing happens if shield is completely used up when its effect ends). Shields take damage in the order that they're applied (e.g. if a unit is shielded for 200 and then for 100, the 200 hp shield takes damage until it has taken 200 damage or its effect runs out, then the 100 hp shield takes damage). On the healthbar, shield amount should show up as gray instead of green.
5. A "crit" means the unit's attack or ability does (crit_damage / 100) times more damage (so 150 means 1.5x). A unit has crit_chance% to crit on each attack.

`gui` updates:
1. Currently, right clicking a unit sells it (conflicts with the item removal stated above). That should be removed; instead selling should only happen the the unit is dragged to the bottom of the screen, or when the user presses 'E' while hovering the unit (both new functionality).
2. Champion icons on the board should fill up as much of the hex as possible instead of being tiny.

Hooks to implement (non-exhaustive; implement more if necessary):
1. COMBAT_START
2. ON_ATTACK
3. ON_CRIT
4. ON_ATTACKED
5. ON_DAMAGE_DEALT
6. ON_DAMAGE_TAKEN
7. ON_HP_THRESHOLD
8. ON_INTERVAL
9. ON_EFFECT_EXPIRED
10. ON_TARGETING_CHANGED
11. ON_UNIT_DEATH

Code should be reused whenever possible. Repeating and redundant code will be penalized.
