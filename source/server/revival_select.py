"""One pure Select catalogue for native preparation and purchase authorization."""
from revival_update import document


def extra_rows(units, shipped):
    from revival_deals import limited_units
    limited = set(limited_units())
    metadata = document('unit_release_global.json')
    global_units = metadata['units']
    for uid, row in global_units.items():
        if row.get('limited') in ('Yes', 'Collaboration', 'Seasonal'):
            limited.add(uid)
        elif row.get('limited') == 'No' and not str(row.get('page', '')).endswith('/JP'):
            limited.discard(uid)
    excluded = document('summon_exclusions.json')['excluded']
    return [{'3HriTp6B': uid, 'e4mG8jTc': '10', 'VjJQ51uG': '2017-01-01 00:00:00',
             'm8ivD4NX': '2030-12-31 23:59:59'}
            for uid, row in sorted(units.items(), key=lambda pair: int(pair[0]))
            if uid not in shipped and uid in limited and uid not in excluded
            and uid == str(row.get('woghJa61')) and str(row.get('9fW0TePj')) == '5'
            and uid in global_units and not str(global_units[uid].get('page', '')).endswith('/JP')]
