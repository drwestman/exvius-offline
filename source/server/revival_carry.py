"""Carried inventory projection and attempt-bound consumption commands."""
from collections import Counter
import json

ENDS = {'x5Unqg2d', 'JiglLZx6', 'BQG1rm3y', 'v51PM7wj', '4cACW7y3', 'fyp10Rrc',
        'e0R3iDm1', '3cuPF20R', 'yW35iC40', '3zgbapQ7', '2pe3Xa8b'}


def counts(rows):
    result = Counter()
    for row in rows:
        result[str(row['item_id'])] += max(0, int(row['count']))
    return result


def fit(rows, owned):
    remaining = dict(owned)
    result = []
    slots = set()
    for row in sorted(rows, key=lambda r: int(r['disp_order'])):
        slot, iid = int(row['disp_order']), str(row['item_id'])
        if slot < 0 or slot in slots:
            continue
        slots.add(slot)
        amount = min(max(0, int(row['count'])), max(0, remaining.get(iid, 0)))
        remaining[iid] = remaining.get(iid, 0) - amount
        if amount:
            result.append(dict(row, count=amount))
    return result


def parse(req):
    rows = req.get('nE7pV2wr')
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return None
    text = rows[0].get('jsvoa0I2')
    if not isinstance(text, str) or not text:
        return None  # empty is ambiguous on the native client
    result = {}
    for entry in text.split(','):
        fields = entry.split(':')
        if len(fields) != 3 or not all(f.isascii() and f.isdigit() for f in fields):
            return None
        slot, iid, amount = map(int, fields)
        if slot in result or iid <= 0:
            return None
        result[slot] = (iid, amount)
    return result


def settle(player, req, mid):
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    if (player.mode != 'live' or not mid or attempt.get('mid') != str(mid)
            or attempt.get('carry_settled') or 'carry_at_load' not in attempt):
        return
    report = parse(req)
    if report is None:
        return
    kept, debits = [], Counter()
    loaded = {int(r['disp_order']): r for r in attempt['carry_at_load']}
    for row in player.data['inventory']['carry_items']:
        slot, iid, amount = int(row['disp_order']), int(row['item_id']), int(row['count'])
        initial = loaded.get(slot)
        if not initial or int(initial['item_id']) != iid:
            kept.append(row)
            continue
        got = report.get(slot)
        left = amount if got is not None and got[0] != iid else min(amount, got[1] if got else 0)
        debits[iid] += amount - left
        if left:
            kept.append(dict(row, count=left))
    for iid, amount in debits.items():
        player.spend_item(20, iid, min(amount, player.item_count(20, iid)))
    player.data['inventory']['carry_items'] = kept
    attempt['carry_settled'] = True
    player.dirty = True


def step(spec, reply_id, plaintext, state, mid):
    from engine_profile import current_profile
    if current_profile().name != 'ios-revival' or state.player is None:
        return spec
    if reply_id == 'X07iYtp5':
        return dict(spec or {}, nE7pV2wr=state.player.carry_item_rows())
    if reply_id in ENDS:
        try:
            req = json.JSONDecoder().raw_decode(plaintext or '{}')[0]
        except ValueError:
            return spec
        if isinstance(req, dict):
            settle(state.player, req, mid)
    return spec
