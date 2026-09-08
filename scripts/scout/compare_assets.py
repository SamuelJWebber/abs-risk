"""Compare assetNumber persistence between two EX-102 files.
Usage: compare_assets.py <earlier.xml> <later.xml> <out.json>"""
import sys, json, random, collections
from lxml import etree

KEEP = ('reportingPeriodEndingDate', 'reportingPeriodActualEndBalanceAmount', 'zeroBalanceCode',
        'currentDelinquencyStatus', 'originationDate', 'originalLoanAmount', 'obligorCreditScore')


def local(t):
    return t.split('}', 1)[1] if '}' in t else t


def load(path):
    ctx = etree.iterparse(path, events=('end',))
    ids = {}
    rec_tag = None
    for ev, el in ctx:
        if local(el.tag) == 'assetNumber':
            par = el.getparent()
            rec_tag = par.tag
            d = {local(c.tag): (c.text or '').strip() for c in par if len(c) == 0}
            ids[(el.text or '').strip()] = {k: d.get(k, '') for k in KEEP}
        if rec_tag is not None and el.tag == rec_tag:
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]
    return ids


a, b, out = sys.argv[1:4]
A = load(a)
B = load(b)
random.seed(7)
sample = random.sample(sorted(B.keys()), 20)
rows = []
for k in sample:
    rows.append({'assetNumber': k, 'in_earlier': k in A, 'earlier': A.get(k), 'later': B[k]})
res = {
    'earlier_file': a, 'later_file': b, 'n_earlier': len(A), 'n_later': len(B),
    'later_in_earlier': sum(1 for k in B if k in A), 'earlier_in_later': sum(1 for k in A if k in B),
    'only_in_earlier': len(set(A) - set(B)), 'only_in_later': len(set(B) - set(A)),
    'earlier_periods': dict(collections.Counter(v['reportingPeriodEndingDate'] for v in A.values())),
    'later_periods': dict(collections.Counter(v['reportingPeriodEndingDate'] for v in B.values())),
    'sample20': rows,
    'example_only_in_earlier': sorted(set(A) - set(B))[:5], 'example_only_in_later': sorted(set(B) - set(A))[:5],
    'sample_in_earlier': sum(1 for r in rows if r['in_earlier']),
    'sample_stable_origination_amount_score': sum(
        1 for r in rows if r['in_earlier']
        and r['earlier']['originationDate'] == r['later']['originationDate']
        and r['earlier']['originalLoanAmount'] == r['later']['originalLoanAmount']
        and r['earlier']['obligorCreditScore'] == r['later']['obligorCreditScore']),
    'only_in_earlier_zeroBalanceCode_counts': dict(collections.Counter(A[k]['zeroBalanceCode'] for k in set(A) - set(B))),
}
json.dump(res, open(out, 'w'), indent=1)
print(json.dumps({k: res[k] for k in ['n_earlier', 'n_later', 'later_in_earlier', 'only_in_earlier', 'only_in_later',
                                       'sample_in_earlier', 'sample_stable_origination_amount_score']}))
