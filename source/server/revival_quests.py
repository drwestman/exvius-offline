"""Pure native quest-report projection."""
def report(saved, steps):
    groups = {}
    for sid, step in steps.items():
        groups.setdefault(str(step.get('Z34jU7ue')), []).append(str(sid))
    wanted = {str(row.get('Z34jU7ue')) for sid, row in saved.items()
              if isinstance(row, dict) and sid in steps and str(row.get('Z34jU7ue')) == str(steps[sid].get('Z34jU7ue'))}
    return [{'Z34jU7ue': qid, '4kcAD9fW': '2' if all(str((saved.get(sid) or {}).get('4kcAD9fW')) == '2'
             for sid in groups[qid]) else '1'} for qid in sorted(wanted, key=int)]
