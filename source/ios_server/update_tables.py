"""Pure optional native transforms for the recorded revival update policy."""
import re

from ios_server.table_codec import master_rows, patch_master, append_master
from revival_update import document
from revival_select import extra_rows


def transform(name, row):
    if name == 'F_MAP_EXT_RESOURCE_MST':
        packs = [p for p in str(row.get('Y4PER0gB') or '').split(',') if p]
        kept = [p for p in packs if p not in ('390001201', '390001213')]
        if kept != packs:
            row['Y4PER0gB'] = ','.join(kept)
            if not kept:
                row['a3u6d1re'] = ''
    elif name == 'F_UNIT_MST':
        price = document('summon_exclusions.json')['sell_prices'].get(str(row.get('3HriTp6B')))
        if price and str(row.get('u18nfD7p') or '0') == '0':
            row['u18nfD7p'] = str(price)
    elif name == 'F_ABILITY_EXPLAIN_MST':
        text = (document('restored_unit_text.json')['abilities'].get(str(row.get('Ga5V42LZ'))) or {}).get('description')
        old = str(row.get('T7aEx3Mj') or '')
        if text and (old in ('', 'Test Data') or re.search('[\u3040-\u30ff\u3400-\u9fff]', old)):
            row['T7aEx3Mj'] = text
    return row


NAMES = {'F_MAP_EXT_RESOURCE_MST', 'F_UNIT_MST', 'F_ABILITY_EXPLAIN_MST'}


def prepare(outputs, changes, tables, *, select_limited=True):
    for table in tables:
        if table.name in NAMES:
            outputs[table.name], count = patch_master(outputs[table.name], table.key,
                lambda row: transform(table.name, row), mode=table.cipher)
            changes[table.name] += count
    by_name = {t.name: t for t in tables}
    if not select_limited or 'F_GACHA_SELECT_UNIT_MST' not in by_name or 'F_UNIT_MST' not in by_name:
        return
    unit_table, select_table = by_name['F_UNIT_MST'], by_name['F_GACHA_SELECT_UNIT_MST']
    units = {str(row['3HriTp6B']): row for _, row, _ in master_rows(outputs[unit_table.name], unit_table.key, mode=unit_table.cipher)}
    source = master_rows(outputs[select_table.name], select_table.key, mode=select_table.cipher)
    added = extra_rows(units, {str(row['3HriTp6B']) for _, row, _ in source})
    outputs[select_table.name] = append_master(outputs[select_table.name], select_table.key,
                                               added, mode=select_table.cipher)
    changes[select_table.name] += len(added)
