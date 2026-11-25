"""Quest LB EXP command calculation, adapted from revival d6e8858.

Call only while settling a recorded successful attempt under its save boundary.
"""
from functools import lru_cache
RATES = {'0':100, '1':250, '2':100}

def points(player, mid) -> int:
    """LB EXP one party unit gains for clearing `mid`."""
    from player_state import _load_ndjson
    row = _load_ndjson("F_MISSION_MST.ndjson", "qo3PECw6").get(str(mid)) or {}
    kind = str(row.get("CQN15Hgr") or "0")
    try:
        cost = int(row.get("B6kyCQ9M") or 0)
    except ValueError:
        cost = 0
    if cost <= 0 or kind not in RATES:
        return 0
    return cost * RATES[kind]

@lru_cache(maxsize=None)
def _levels(lb_id: str) -> tuple:
    """((level, exp needed to reach it), ...) for one LB, ascending."""
    from player_state import _load_ndjson
    return tuple(sorted((int(r["7wV3QZ80"]), int(r["T3Zcf40Q"]))
                        for r in _load_ndjson("F_LIMITBURST_LV_MST.ndjson").get("__rows__", [])
                        if str(r.get("PR2HIc71")) == lb_id))

def advance(master_id, level: int, exp: int, gain: int) -> tuple[int, int]:
    """(level, exp) after `gain` LB EXP, walking the unit's LB level table up to its max LB level."""
    from player_state import limit_burst, unit_mst
    lb = limit_burst(master_id)
    if not lb:
        return level, exp
    levels = _levels(str(lb["PR2HIc71"]))
    if not levels:
        return level, exp
    steps = dict(levels)
    try:
        cap = int((unit_mst(master_id) or {}).get("ENwn42DV") or 1)
    except ValueError:
        cap = 1
    maximum = min(levels[-1][0], cap)
    level, exp = max(1, level), exp + gain
    while level < maximum and level + 1 in steps and exp >= steps[level + 1]:
        exp -= steps[level + 1]
        level += 1
    if level >= maximum:
        exp = 0
    return level, exp

def plan(player, mid) -> dict:
    gain = points(player, mid)
    out = {}
    if gain <= 0:
        return out
    for iid in player.party_instance_ids(mid):
        u = player.roster_row(iid)
        if u is None:
            continue
        lv, ex = int(u.get("lb_level") or 1), int(u.get("lb_exp") or 0)
        new = advance(u["master_id"], lv, ex, gain)
        if new != (lv, ex):
            out[str(iid)] = (lv, ex, new[0], new[1])
    return out

def apply(player, changes: dict) -> None:
    for iid, (_lv, _ex, lv, ex) in changes.items():
        u = player.roster_row(iid)
        if u is not None:
            u["lb_level"], u["lb_exp"] = lv, ex
    if changes:
        player.dirty = True
