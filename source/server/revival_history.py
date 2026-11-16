"""Pure replay update catalogue; all source documents are checksum pinned."""
import copy
from datetime import date, timedelta
from revival_update import document


def late_banners():
    return [copy.deepcopy(b) for b in document('late_banners.json')['banners'] if not b.get('unconfirmed')]


def unit_dates(original):
    out = dict(original)
    doc = document('unit_release_global.json')
    for uid, row in doc.get('units', {}).items():
        if row.get('global') and uid in out:
            out[uid] = date.fromisoformat(row['global']).isoformat()
    for uid, day in doc.get('later', {}).items():
        if uid in out and isinstance(day, dict) and day.get('global'):
            out[uid] = min(out[uid], date.fromisoformat(day['global']).isoformat())
    for uid in doc.get('launch', {}).get('units', {}):
        out[str(uid)] = min(out.get(str(uid), '2016-06-30'), '2016-06-30')
    return out


def banner_run(banner):
    community = banner.get('community') or {}
    raw = community.get('release') or banner.get('release')
    if not raw:
        return None
    try:
        start = date.fromisoformat(raw if len(raw) == 10 else raw + '-01')
    except ValueError:
        return None
    end = community.get('until') or banner.get('until') or (document('banner_runs.json').get('runs', {}).get(str(banner['id'])) or {}).get('until')
    return start, max(start, date.fromisoformat(end) if end else start + timedelta(days=13))


def overlaps(run, begin, end):
    return run is not None and run[0] < date.fromisoformat(end) and run[1] >= date.fromisoformat(begin)


def event_runs(row):
    doc = document('event_runs.json')
    area = str(row['area'])
    known = doc.get('runs', {}).get(area, [])
    bad = set(doc.get('bad_starts', {}).get(area, []))
    runs = [(date.fromisoformat(r['start']), date.fromisoformat(r['end'])) for r in known]
    for raw in row.get('runs') or [row.get('release')]:
        if raw and raw not in bad:
            start = date.fromisoformat(raw)
            if not any(abs((start - a).days) <= 3 for a, _ in runs):
                runs.append((start, start + timedelta(days=13)))
    if area in {'1199', '9961', '402', '1899', '1044'} and runs:
        return [(min(a for a, _ in runs), date(2024,10,30))]
    return runs

def apply(by_id: dict) -> None:
    """Redate the existing banners and drop the hidden placeholders, in place."""
    doc = document("late_banners.json")
    for bid, fix in (doc.get("existing") or {}).items():
        banner = by_id.get(str(bid))
        if banner is None:
            continue
        banner = by_id[str(bid)] = dict(banner)
        community = dict(banner.get("community") or {})
        if fix.get("release"):
            banner["release"] = community["release"] = fix["release"]
        if fix.get("until"):
            community["until"] = fix["until"]
        if fix.get("alias_ids"):   # the same Global banner under another id: hidden, still resolvable
            banner["alias_ids"] = list(dict.fromkeys([*(banner.get("alias_ids") or []), *fix["alias_ids"]]))
        if fix.get("name"):
            banner["name"] = fix["name"]          # Global's title (e.g. the FFXI Lady Shantotto/Lion banner)
        featured = [str(u) for u in fix.get("featured_units") or []]
        if featured:
            community["unit_ids"] = list(dict.fromkeys([*(community.get("unit_ids") or []), *featured]))
            pool = banner.get("pool")
            if isinstance(pool, dict) and pool.get("tiers"):
                tiers = [dict(t) for t in pool["tiers"]]
                top = max(range(len(tiers)), key=lambda i: int(tiers[i].get("rarity") or 0))
                tiers[top]["featured"] = list(dict.fromkeys([*(tiers[top].get("featured") or []), *featured]))
                banner["pool"] = dict(pool, tiers=tiers)
        banner["community"] = community
    for bid in doc.get("hide") or {}:
        by_id.pop(str(bid), None)
