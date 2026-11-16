"""Read-only upgrade planning and explicit digest-checked atomic application."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile

from ios_server.queries import _saved
from ios_server.runtime import InstanceLock, private_path
from revival_update import REVISION, initialize, settings
from revival_unit_rules import summon_unit


def masters(config, name, key=None):
    folder = Path(config.engine_environment()['MST_DIR'])
    path = folder / (name + '.ndjson')
    if not path.resolve().is_relative_to(config.data):
        raise ValueError('Upgrade master source escapes content root')
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError('Invalid upgrade master: ' + name)
    return {str(row[key]): row for row in rows} if key else rows


def build(data, *, units, steps, switches, missions, experience):
    """Return candidate and report. Historical absence of a receipt is unknown."""
    candidate = copy.deepcopy(data)
    report = {'revision': REVISION, 'repairs': [], 'compensation': [], 'unresolved': []}
    if settings(candidate) is not None:
        report['already_upgraded'] = True
        return candidate, report
    initialize(candidate)
    candidate.setdefault('ios_reward_claims', {'version':1,'baseline':list(candidate.get('progress', {}).get('cleared_missions', [])), 'paid':{}})
    buckets = candidate.setdefault('progress', {}).setdefault('switches', {})
    def grant(raw, reason):
        for token in str(raw or '').split(','):
            row = switches.get(token)
            if row:
                kind, index = str(row['5opcUT9t']), int(row['QLfe23bu'])
                bucket = buckets.setdefault(kind, [])
                if index not in bucket:
                    bucket.append(index)
                    bucket.sort()
                    report['repairs'].append({'switch': token, 'reason': reason})
    for sid, saved in candidate.get('exvius_map', {}).get('quests', {}).items():
        step = steps.get(str(sid))
        if step and str(saved.get('4kcAD9fW')) == '2' and str(saved.get('Z34jU7ue')) == str(step['Z34jU7ue']):
            grant(step.get('dIPkNn61'), 'completed quest ' + str(sid))
    for mid in candidate.get('progress', {}).get('cleared_missions', []):
        row = missions.get(str(mid)) or {}
        for token in str(row.get('dIPkNn61') or '').split(','):
            if str((switches.get(token) or {}).get('5opcUT9t')) in ('103', '9002'):
                grant(token, 'cleared mission ' + str(mid))
        if row.get('1x4bG2J8') not in (None, '', '0'):
            report['unresolved'].append({'mission': str(mid), 'reason': 'historical reward payment not proven'})
    for unit in candidate.get('roster', []):
        old = str(unit['master_id'])
        try:
            new = summon_unit(old, units)
        except ValueError as exc:
            report['unresolved'].append({'unit': str(unit['instance_id']), 'reason': str(exc)})
            continue
        if new == old:
            continue
        master = units[new]
        cap = int(master.get('aU3o2D4t') or 0)
        level = min(int(unit['level']), cap) if cap else 0
        pattern = {int(r['7wV3QZ80']): int(r['93fnYUJG']) for r in experience
                   if str(r.get('0W7g6YXS')) == str(master.get('0W7g6YXS'))}
        if level < 1 or any(l not in pattern for l in range(2, level + 1)):
            report['unresolved'].append({'unit': str(unit['instance_id']), 'reason': 'missing destination EXP data'})
            continue
        residual = int(unit.get('exp') or 0)
        residual = residual if level == int(unit['level']) and level < cap and residual < pattern.get(level + 1, 0) else 0
        unit.update(master_id=new, level=level, exp=residual,
                    total_exp=sum(pattern[l] for l in range(2, level + 1)) + residual)
        previous_lb = int(unit.get('lb_level') or 0)
        cap_lb = int(master.get('ENwn42DV') or 0)
        unit['lb_level'] = min(previous_lb, cap_lb)
        if unit['lb_level'] != previous_lb or unit['lb_level'] >= cap_lb:
            unit['lb_exp'] = 0
        if str(master.get('5Mgpv8hJ') or '0') not in ('1', '2'):
            unit['nv_ex_level'] = 0
        if 'granted_rarity' in unit:
            unit['granted_rarity'] = type(unit['granted_rarity'])(master['9fW0TePj'])
        if str(unit.get('first_get_unit_id')) == old:
            unit['first_get_unit_id'] = type(unit['first_get_unit_id'])(new)
        report['repairs'].append({'unit': str(unit['instance_id']), 'from': old, 'to': new})
    owned = {str(r['item_id']): int(r['count']) for r in candidate.get('inventory', {}).get('items', [])
             if str(r['item_type']) == '20'}
    kept = []
    for row in sorted(candidate.get('inventory', {}).get('carry_items', []), key=lambda r: int(r['disp_order'])):
        row = dict(row)
        uid = str(row['item_id'])
        count = min(int(row['count']), max(0, owned.get(uid, 0)))
        owned[uid] = owned.get(uid, 0) - count
        if count != int(row['count']):
            report['repairs'].append({'carry_item': uid, 'from': row['count'], 'to': count})
        if count:
            kept.append(dict(row, count=count))
    candidate.setdefault('inventory', {})['carry_items'] = kept
    candidate['ios_revival_update']['upgrade'] = copy.deepcopy(report)
    return candidate, report


def plan(config):
    data = _saved(config)
    from replay_calendar import read_anchor
    if data is None or read_anchor(data) is None:
        raise ValueError('Initialize the iOS campaign before upgrading it.')
    if data.get('meta', {}).get('engine_profile') not in (None, 'ios-revival'):
        raise ValueError('Only an isolated iOS campaign can be upgraded.')
    raw = config.state_file.read_bytes()
    # Read exactly one snapshot: reject an intervening write while a query assembled it.
    if json.loads(raw) != data:
        raise ValueError('Campaign changed while planning; retry the query.')
    candidate, report = build(data, units=masters(config, 'F_UNIT_MST', '3HriTp6B'),
        steps=masters(config, 'F_QUEST_SUB_MST', '7Svg2kdT'), switches=masters(config, 'F_SWITCH_MST', '8vAYn3IX'),
        missions=masters(config, 'F_MISSION_MST', 'qo3PECw6'), experience=masters(config, 'F_UNIT_EXP_PATTERN_MST'))
    return candidate, dict(report, save_sha256=hashlib.sha256(raw).hexdigest(), changed=candidate != data)


def _atomic(path, raw):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.campaign-upgrade-', dir=path.parent, delete=False) as out:
            temporary = Path(out.name)
            os.fchmod(out.fileno(), 0o600)
            out.write(raw); out.flush(); os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def apply(config, expected):
    if not expected or len(expected) != 64:
        raise ValueError('upgrade-campaign requires --expected-save-sha256 from plan-campaign-upgrade.')
    with InstanceLock(config.root):
        candidate, report = plan(config)
        if report['save_sha256'] != expected:
            raise ValueError('Campaign changed since planning; no upgrade was applied.')
        if not report['changed']:
            return report
        backup = private_path(config.root, 'state/backups/' + config.slot + '-' + expected + '.json')
        backup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw = config.state_file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Campaign changed before backup; no upgrade was applied.')
        if backup.exists():
            if backup.read_bytes() != raw:
                raise ValueError('Conflicting campaign backup')
        else:
            _atomic(backup, raw)
        _atomic(config.state_file, (json.dumps(candidate, indent=1) + '\n').encode())
        return dict(report, backup=str(backup), applied=True)
