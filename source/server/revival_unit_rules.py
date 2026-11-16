"""Pure Global conversion rules from revival d6e8858; no engine or I/O dependencies."""
from dataclasses import dataclass


def is_nv(master):
    return str(master.get('5Mgpv8hJ') or '0') in ('1', '2')


def awakened_flag(master):
    return '1' if is_nv(master) and str(master.get('k9GFaWm1') or '0') == '1' else None


def allows(row, rarity):
    values = [int(v) for v in str((row or {}).get('jBVop84T') or '').split(',') if v.isascii() and v.isdigit()]
    return any(v <= rarity for v in values)


@dataclass(frozen=True)
class ConversionRules:
    units: dict
    sacrifices: dict

    def rewards(self, master_id, mode):
        """Native reward CSV; reject unsupported modes rather than guessing a payment."""
        master = self.units.get(str(master_id)) or {}
        family = self.sacrifices.get(str(master.get('woghJa61') or ''))
        rarity = int(master.get('9fW0TePj') or 0)
        if not allows(family, rarity):
            return ''
        if mode == 'prism':
            item = str(family.get('tL6G9egd') or '0')
            return f'20:{item}:1' if rarity != 7 and not is_nv(master) and item.isdigit() and int(item) else ''
        if mode != 'fragments':
            raise ValueError('Unknown unit conversion mode')
        form = master
        if int(master.get('I3SKJ4q0') or 0) >= 1:
            form = self.units.get(str(master.get('JPW8Vs40'))) or master
        pure = is_nv(master) and awakened_flag(master) is None
        row = self.sacrifices.get(str(form.get('woghJa61') if pure else form.get('3HriTp6B')))
        return str((row.get('1swM3H4T') if pure else row.get('q1PJQ3eE')) or '') \
            if allows(row, int(form.get('9fW0TePj') or rarity)) else ''


def summon_unit(uid, units):
    """Normalize a standalone shift form to the summonable family root."""
    uid = str(uid)
    row = units.get(uid) or {}
    if str(row.get('I3SKJ4q0')) != '1' or str(row.get('JPW8Vs40') or '0') in ('0', uid):
        return uid
    named = str(row.get('JPW8Vs40'))
    root = str((units.get(named) or {}).get('woghJa61') or named)
    for key in (root, named):
        target = units.get(key)
        if target and str(target.get('I3SKJ4q0')) != '1':
            return key
    raise ValueError(f'Unresolved summon form {uid}')
