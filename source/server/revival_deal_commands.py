"""iOS summon command boundary: stage the canonical transaction, then publish once.

Re-summons replace only the unchanged main result. Bonuses belong to the paid
purchase; using/training/equipping a result keeps it and prevents replacement.
"""
import copy


def execute(player, banner, repeats=1, ticket_id=None, offer=None):
    from revival_summons import authorize_pull
    if player.mode == 'frozen':
        return None
    configured = authorize_pull(player.data, banner)
    if configured is None:
        return None
    state_id = str(configured.get('state_id', configured['id']))
    maximum = int(configured.get('resummon') or 0)
    redo = bool(maximum and (offer or {}).get('resummon'))
    pending = player.data.get('gacha', {}).get('resummon', {}).get(state_id)
    if redo and not _replaceable(player, pending):
        return None
    candidate = copy.deepcopy(player)
    counts = copy.deepcopy(candidate.data.get('gacha', {}).get('user_banners', {}).get(state_id))
    if redo:
        configured['purchase_limit'] = 0  # A redo belongs to the original paid purchase.
    result = candidate._roll_gacha(configured, repeats, ticket_id, offer=offer)
    if result is None:
        return None
    if maximum:
        main = result['awards'][:result['count']]
        if len(main) != result['count']:
            raise ValueError('Re-summon main result is incomplete; original result preserved.')
        ids = {str(row['instance_id']) for row in main}
        if redo:
            old = set(pending['units'])
            if set(candidate.drop_units(old)) != old:
                raise ValueError('Re-summon could not replace its previous result.')
            candidate.data['vision_cards'] = [row for row in candidate.data.get('vision_cards', [])
                                               if str(row.get('user_vc_id')) not in pending['cards']]
            candidate.data['gacha']['user_banners'][state_id] = counts
        candidate.data['gacha'].setdefault('resummon', {})[state_id] = {
            'version': 1, 'units': sorted(ids), 'left': int(pending['left']) - 1 if redo else maximum,
            'snapshots': {str(row['instance_id']): copy.deepcopy(row) for row in candidate.data['roster']
                          if str(row['instance_id']) in ids},
            'cards': {str(row['user_vc_id']): copy.deepcopy(row) for row in candidate.data.get('vision_cards', [])
                      if str(row.get('user_vc_id')) in ids}}
    player.data, player.dirty = candidate.data, candidate.dirty
    return result


def _replaceable(player, pending):
    if not pending or pending.get('version') != 1 or int(pending.get('left', 0)) <= 0:
        return False
    ids = set(pending.get('units', []))
    if not ids or ids != set(pending.get('snapshots', {})):
        return False
    from exvius_actions_shops import deployed_unit_ids
    if ids.intersection(deployed_unit_ids(player)):
        return False
    owned = {str(row['instance_id']): row for row in player.data['roster']}
    if any(owned.get(uid) != pending['snapshots'][uid] for uid in ids):
        return False
    cards = {str(row['user_vc_id']): row for row in player.data.get('vision_cards', [])}
    return all(cards.get(key) == row for key, row in pending.get('cards', {}).items())


def remaining(player, banner):
    state_id = str(banner.get('state_id', banner['id']))
    pending = player.data.get('gacha', {}).get('resummon', {}).get(state_id)
    return min(int(banner.get('resummon') or 0), int(pending['left'])) if _replaceable(player, pending) else 0
