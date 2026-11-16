"""iOS roster commands. Caller owns the request transaction and state lock."""
import copy

from revival_unit_rules import ConversionRules


def convert(player, nodes, *, nv=False):
    from exvius_actions_shops import deployed_unit_ids
    from player_state import _load_ndjson
    from exvius_rewards import parse
    if player.mode != 'live' or not isinstance(nodes, list) or not nodes:
        return None
    rules = ConversionRules(_load_ndjson('F_UNIT_MST.ndjson', '3HriTp6B'),
                            _load_ndjson('F_SACRIFICE_MST.ndjson', 'woghJa61'))
    deployed = deployed_unit_ids(player)
    ids, rewards, results = set(), [], []
    for node in nodes:
        if not isinstance(node, dict):
            return None
        uid = str(node.get('og2GHy49') or '')
        unit = player.roster_row(uid)
        mode = '1' if nv else str(node.get('ijEey5f7', '1'))
        if mode not in ('0', '1') or not unit or uid in ids or uid in deployed or unit.get('favourite'):
            return None
        text = rules.rewards(unit['master_id'], 'prism' if mode == '0' else 'fragments')
        rows = parse(text)
        if not rows or any(not player._can_credit(row) for row in rows):
            return None
        ids.add(uid)
        rewards.extend(rows)
        results.append({'og2GHy49': uid, 'ijEey5f7': mode,
                        'tL6G9egd': str(rows[0]['id']) if mode == '0' else '0',
                        '1swM3H4T': '' if mode == '0' else text})
    if len(ids) >= len(player.data['roster']):
        return None
    candidate = copy.deepcopy(player)
    if set(candidate.drop_units(ids)) != ids or candidate._grant_items(rewards) != rewards:
        raise ValueError('Unit conversion did not settle completely')
    player.data, player.dirty = candidate.data, candidate.dirty
    return results


def mix(spec, plaintext: str | None):
    """UnitMixRequest (`UiSC9y8R`): fuse the materials into the base and serve `UnitMixResponse`.

    WHY THIS EXISTS: without it the request got an EMPTY body and the client showed "Connection error (api
    call)" (observed live 2026-09-24) -- unlike `UnitExchangeRequest`, which tolerates an empty reply, this
    one does not. The request group is the reply tag `f08du6EW` carrying `og2GHy49` (base instance id) and
    `WbGYcN17` (materials, CSV).

    Reply tokens (`UnitMixResponse::readParam` `0x196f874`, all 10 mapped in the field map):
      `og2GHy49` / `WbGYcN17` echo what was fused, `B6H34Mea` = exp gained, `UDMIFB72` = LB exp gained,
      `1dT7ha9H` = success type, `7UR4J2SE` = gil, `Qic38SuC` = the LevelUp channel, `E90oBqct` = the
      SP-affinity-reward display flag (optional). `9mu4boy7` is inert (the map's own note).
    The EXP is the client's OWN formula (`GameUtils::getMixExp`, see `player_state.unit_mix_exp`) so the
    number we serve agrees with the preview the player just looked at.
    Trust progress and newly mastered items are projected through the refreshed player groups.

    Two values are AUTHORED, labelled, and to be checked on screen:
      * `7UR4J2SE` (gil) = 0 -- there is NO unit-mix gil function in the binary (only
        `VisionCardUtils::getMixGil`), so unit fusion is treated as free.
      * `1dT7ha9H` (success type) = 1 -- no reader of `getSuccessType` could be found in the unit path, so
        the value is a placeholder rather than a recovered enum.
    """
    from ffbe_state import State, _note
    from ffbe_player import _request_json, MIX_GROUP, _lv_half, score_quest_action, score_daily
    from player_state import unit_stats
    req = _request_json(plaintext)
    rows = req.get(MIX_GROUP) if req else None
    if not isinstance(rows, list) or not rows or State.player is None:
        return spec
    # One node per base unit. The Fuse Units screen sends one; Bulk Fusion sends one for every base it fuses
    # (`UnitMixAutoSelectConnectScene::createRequestList` 0x26b1900 calls `UnitMixRequest::setMixInfo` per base,
    # `createBody` 0x19a5890 writes a node each). Only the first was read until 2026-11-13, so a Bulk Fusion
    # fused one unit's copies and the reply's unit list brought every other material back (GitHub #8).
    pairs, used = [], set()
    for node in rows:
        node = node if isinstance(node, dict) else {}
        base_id = str(node.get("og2GHy49") or "").strip()
        materials = [x.strip() for x in str(node.get("WbGYcN17") or "").split(",") if x.strip()]
        if not base_id or not materials:
            return spec
        pairs.append((base_id, materials))
    if not pairs:
        return spec
    out = dict(spec) if isinstance(spec, dict) else {}
    # All or nothing. The phone has already taken every material off its own list, so a request done in part
    # would leave its list and the save apart. Each node needs its base and at least one of its materials in
    # the roster (within a node, unknown and repeated materials are dropped, as before), and no unit may be in
    # two nodes (a material of two bases, or a base that is another node's material).
    problem = None
    for base_id, materials in pairs:
        if State.player.roster_row(base_id) is None:
            problem = f"base {base_id} is not in the roster"
            break
        mine = {base_id} | {iid for iid in materials if State.player.roster_row(iid) is not None}
        if len(mine) < 2:
            problem = f"none of base {base_id}'s materials is in the roster"
        elif mine & used:
            problem = f"unit {sorted(mine & used)[0]} is in two nodes"
        if problem:
            break
        used |= mine
    if problem:
        _note(f"unit-mix: refused ({problem}); nothing was fused")
        return out
    before_all, dirty_all = copy.deepcopy(State.player.data), State.player.dirty
    results = []
    for base_id, materials in pairs:
        base = State.player.roster_row(base_id) or {}
        affinity_before = list(base.get('affinity_points') or ('', ''))
        res = State.player.mix_units(base_id, materials)
        if not res:
            State.player.data, State.player.dirty = before_all, dirty_all
            _note(f"unit-mix: refused (base {base_id} or its materials could not be fused, or frozen); "
                  f"nothing was fused")
            return out
        results.append((base_id, res, affinity_before))
    mix_rows = []
    for base_id, res, affinity_before in results:
        base = State.player.roster_row(base_id)
        State.player.record_archive({'TOTAL_UNIT_MIX': 1})
        if any(int(after or 0) > int(before or 0) for before, after in
               zip(affinity_before, base.get('affinity_points') or ())):
            score_quest_action('31')
        score_daily('unit_fuse')
        lb_level = int(base.get("lb_level", 0) or 0)
        lb_exp = int(base.get("lb_exp", 0) or 0)
        (b_lv, b_ex), (a_lv, a_ex) = res["before"], res["after"]
        before = _lv_half(b_lv, b_ex, unit_stats(base["master_id"], b_lv), lb_level, lb_exp)
        after = _lv_half(a_lv, a_ex, unit_stats(base["master_id"], a_lv), lb_level, lb_exp, gained=res["gain"])
        mix_rows.append({"og2GHy49": base_id,
                         "WbGYcN17": ",".join(res["materials"]),
                         "B6H34Mea": str(res["gain"]),          # Exp
                         "UDMIFB72": str(res["lb_gain"]),       # LbExp
                         "1dT7ha9H": "1",                        # success type (authored; see docstring)
                         "7UR4J2SE": "0",                        # gil (authored; no unit-mix gil exists)
                         "Qic38SuC": f"{base_id}@{before}_{after}",
                         "E90oBqct": "0"})
        lb_note = f" +{res['lb_gain']} lb" if res["lb_gain"] else ""
        print(f"unit: MIX {len(res['removed'])} material(s) into {base_id} -> +{res['gain']} exp{lb_note}; "
              f"level {b_lv} -> {a_lv}, roster {len(State.player.data['roster'])}", flush=True)
    # One row per base, in the request's order (the phone keeps one result, `UserUnitMixResult`, so the last
    # row is the one the single-fusion screen shows; Bulk Fusion's result window reads the unit list instead).
    out[MIX_GROUP] = mix_rows
    # ...and let the client relearn the roster (materials gone, bases levelled) from the same reply. The
    # FULL player groups, not `currency_groups()`: fusion changes the ROSTER, and the roster group
    # (`B71MekS8`) is what makes the consumed materials disappear client-side.
    out.update(State.player.groups())
    return out


def awaken(spec, req):
    """UnitClassUpRequest (awakening): group `sWc7EH69`, `og2GHy49` = the base unit. F_UNIT_CLASS_UP_MST
    names the next rarity (`t74crqAL`), its gil (`7UR4J2SE`) and materials (`KCk8u0am`). The reply is
    UnitClassUpResponse on the same tag (UserUnitClassUpResult: og2GHy49 unit, 5u7VYNEX new unit,
    KCk8u0am materials, WbGYcN17/02CI3bpE element info, p9Xj4Anc all-kigen flag)."""
    from exvius_actions import _node, _mst, _refresh
    from ffbe_state import State, _note
    from revival_messages import refuse
    def _refuse_awakening(spec, reason):
        refuse("The awakening couldn't be completed (" + reason + "). Nothing was used.")
        return spec
    node = _node(req, "sWc7EH69")
    iid = str(node.get("og2GHy49") or "") if node else ""
    unit = next((u for u in State.player.data["roster"] if str(u["instance_id"]) == iid), None)
    if unit is None or State.player.mode != 'live':
        _note(f"unit-class-up: unit {iid or '?'} not in the roster")
        return _refuse_awakening(spec, "the unit isn't in your unit list")
    step = _mst("F_UNIT_CLASS_UP_MST.ndjson", "3HriTp6B").get(str(unit["master_id"]))
    if not step:
        _note(f"unit-class-up: no F_UNIT_CLASS_UP_MST row for {unit['master_id']}")
        return _refuse_awakening(spec, "this unit has no further awakening")
    from player_state import unit_mst
    if unit_mst(step.get("t74crqAL")) is None:
        # One shipped row awakens into a unit the game has no data for (Kevin 312000306 -> 312000307).
        _note(f"unit-class-up: {unit['master_id']} awakens into {step.get('t74crqAL')}, which is not in F_UNIT_MST")
        return _refuse_awakening(spec, "this unit has no further awakening")
    materials = str(step.get("KCk8u0am") or "")
    gil = int(step.get("7UR4J2SE") or 0)
    rows = [m.split(":") for m in materials.split(",") if m.count(":") == 2]
    # The Omniprism. The awakening screen offers it in place of a 6-star unit's own prism
    # (UnitEnhanceClassUpMaterialObj::init: item material, unit rarity 6), and the request then carries
    # `p9Xj4Anc` = 1 (UnitClassUpRequest AllKigenFlg). Its item is F_DEFINE_MST CLASS_UP_PRISM_ALL_ITEM_ID, one per
    # awakening (UnitClassupUtils::getAllKigenItemNum). Gil is unchanged.
    # The flag is only written when FUNCTION_SP_CLASSUP is on (UnitClassUpRequest::createBody). Should a request come
    # without it for a unit whose own prism is missing, the Omniprism was still what the player chose: the screen
    # enables its button for a missing prism only with the Omniprism ticked (isEnoughItemCnt).
    from player_state import unit_mst
    item = str((_mst("F_DEFINE_MST.ndjson", "AK8Nn7ta").get("CLASS_UP_PRISM_ALL_ITEM_ID") or {}).get("YjIUDJ97") or "")
    takes_one = bool(item) and (unit_mst(unit["master_id"]) or {}).get("9fW0TePj") == "6" and \
        len(rows) == 1 and rows[0][0] == "20" and rows[0][2] == "1"
    omniprism = str(node.get("p9Xj4Anc") or "0") == "1"
    if omniprism and not takes_one:
        _note(f"unit-class-up: Omniprism asked for {unit['master_id']}, which does not take one")
        return _refuse_awakening(spec, "the Omniprism can't be used for this awakening")
    if "p9Xj4Anc" not in node and takes_one and State.player.item_count(20, rows[0][1]) < 1 \
            and State.player.item_count(20, item) >= 1:
        omniprism = True
    paid = [["20", item, "1"]] if omniprism else rows
    if any(State.player.item_count(int(k), i) < int(c) for k, i, c in paid) or \
            int(State.player.currencies.get("gil", 0)) < gil:
        _note(f"unit-class-up: {unit['master_id']} lacks materials or gil; not awakened")
        return _refuse_awakening(spec, "not enough materials or gil")
    for k, i, c in paid:
        State.player.spend_item(int(k), i, int(c))
    State.player.spend_currency("gil", gil)
    before = unit["master_id"]
    unit["master_id"] = str(step["t74crqAL"])
    unit = State.player.renew_unit_instance(iid)
    from player_state import unit_mst
    destination = unit_mst(unit['master_id']) or {}
    State.player.record_archive({'TOTAL_UNIT_CLASS_UP': 1, 'TOTAL_UNIT_RARE7_CLASS_UP':
                                 int(destination.get('9fW0TePj') == '7' and destination.get('JPW8Vs40') == '0')})
    State.player.dirty = True
    spent = ",".join(":".join(row) for row in paid)
    print(f"unit: awakened {iid} {before} -> {unit['master_id']} for {gil} gil + {spent}", flush=True)
    out = _refresh(spec)
    out["sWc7EH69"] = [{"og2GHy49": iid, "5u7VYNEX": unit['instance_id'], "KCk8u0am": materials, "WbGYcN17": "",
                        "02CI3bpE": "", "p9Xj4Anc": "1" if omniprism else "0"}]
    return out
