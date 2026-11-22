"""Usage: apply_trace5.py ID[=partial|done][:note] ...  Sets status and tests for ids."""
import csv, sys
sys.path.insert(0, 'scripts/dev')
from trace import found
wanted = {}
for arg in sys.argv[1:]:
    head, _, note = arg.partition(':')
    i, _, status = head.partition('=')
    wanted[i] = (status or 'done', note)
rows = list(csv.DictReader(open('docs/traceability.csv', newline='')))
fields = list(rows[0].keys())
for r in rows:
    if r['id'] not in wanted: continue
    status, note = wanted[r['id']]
    tests = sorted(set(found[r['id']]))
    if not tests: print('NO TESTS', r['id'])
    r['tests'] = '; '.join(t.split('::')[1] for t in tests)
    r['status'] = status
    if note: r['notes'] = note
with open('docs/traceability.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields, lineterminator='\r\n'); w.writeheader(); w.writerows(rows)
