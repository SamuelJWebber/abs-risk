"""Stream-profile an ABS-EE EX-102 auto-loan XML. Usage: analyze_ex102.py <xml> <out.json>
Never loads the whole file; iterparse + clear()."""
import sys, json, os, collections, statistics
from lxml import etree

path, out = sys.argv[1], sys.argv[2]


def local(tag):
    return tag.split('}', 1)[1] if '}' in tag else tag


size = os.path.getsize(path)
# 1) find the record tag: first element at depth 2 (child of root)
ctx = etree.iterparse(path, events=('start', 'end'))
root = None
depth = 0
record_tag = None
for ev, el in ctx:
    if ev == 'start':
        depth += 1
        if depth == 1:
            root = el
        elif depth == 2 and record_tag is None:
            record_tag = el.tag
    else:
        depth -= 1
        if record_tag is not None and depth == 1:
            break
del ctx
print('root', root.tag, 'record tag', record_tag, 'nsmap', root.nsmap, file=sys.stderr)

n = 0
fields = collections.OrderedDict()
samples = []
asset_numbers = []
asset_set = set()
credit_scores = []
score_missing = 0
score_zero = 0
score_nonnum = 0
score_types = collections.Counter()
orig_amt = []
apr = []
term = []
pti = []
vval = []
delinq = collections.Counter()
delinq_num = []
zb = collections.Counter()
zb_date_nonempty = 0
chargeoff_nonempty = 0
recovered_nonempty = 0
repo = collections.Counter()
newused = collections.Counter()
subv = collections.Counter()
incver = collections.Counter()
empver = collections.Counter()
geo = collections.Counter()
rp_begin = collections.Counter()
rp_end = collections.Counter()
orig_dates = []
begbal = []
endbal = []


def num(v):
    try:
        return float(v)
    except Exception:
        return None


ctx = etree.iterparse(path, events=('end',), tag=record_tag)
for ev, rec in ctx:
    n += 1
    d = collections.OrderedDict()
    for ch in rec.iter():
        if ch is rec:
            continue
        if len(ch) == 0:
            name = local(ch.tag)
            val = (ch.text or '').strip()
            if name in d:
                name = name + '__dup'
            d[name] = val
    for k, v in d.items():
        f = fields.get(k)
        if f is None:
            f = fields[k] = {'example': None, 'nonempty': 0, 'distinct': set()}
        if v != '':
            f['nonempty'] += 1
            if f['example'] is None:
                f['example'] = v
            if len(f['distinct']) < 50:
                f['distinct'].add(v)
    if len(samples) < 3:
        samples.append(d)
    an = d.get('assetNumber', '')
    if len(asset_numbers) < 25:
        asset_numbers.append(an)
    asset_set.add(an)
    cs = d.get('obligorCreditScore', '')
    if cs == '':
        score_missing += 1
    else:
        x = num(cs)
        if x is None:
            score_nonnum += 1
        elif x == 0:
            score_zero += 1
        else:
            credit_scores.append(x)
    score_types[d.get('obligorCreditScoreType', '')] += 1
    for lst, key in ((orig_amt, 'originalLoanAmount'), (apr, 'originalInterestRatePercentage'), (term, 'originalLoanTerm'),
                     (pti, 'paymentToIncomePercentage'), (vval, 'vehicleValueAmount'),
                     (begbal, 'reportingPeriodBeginningLoanBalanceAmount'), (endbal, 'reportingPeriodActualEndBalanceAmount')):
        x = num(d.get(key, ''))
        if x is not None:
            lst.append(x)
    ds = d.get('currentDelinquencyStatus', '')
    delinq[ds] += 1
    x = num(ds)
    if x is not None:
        delinq_num.append(x)
    zb[d.get('zeroBalanceCode', '')] += 1
    if d.get('zeroBalanceEffectiveDate', '') != '':
        zb_date_nonempty += 1
    if d.get('chargedoffPrincipalAmount', '') != '':
        chargeoff_nonempty += 1
    if d.get('recoveredAmount', '') != '':
        recovered_nonempty += 1
    repo[d.get('repossessedIndicator', '')] += 1
    newused[d.get('vehicleNewUsedCode', '')] += 1
    subv[d.get('subvented', '')] += 1
    incver[d.get('obligorIncomeVerificationLevelCode', '')] += 1
    empver[d.get('obligorEmploymentVerificationCode', '')] += 1
    geo[d.get('obligorGeographicLocation', '')] += 1
    rp_begin[d.get('reportingPeriodBeginningDate', '')] += 1
    rp_end[d.get('reportingPeriodEndingDate', '')] += 1
    if len(orig_dates) < 200000:
        orig_dates.append(d.get('originationDate', ''))
    rec.clear()
    while rec.getprevious() is not None:
        del rec.getparent()[0]

buckets = collections.Counter()
for s in credit_scores:
    lo = int(s // 20) * 20
    buckets['%d-%d' % (lo, lo + 19)] += 1


def mean(l):
    return statistics.fmean(l) if l else None


def med(l):
    return statistics.median(l) if l else None


def mm(l):
    return {'n': len(l), 'mean': mean(l), 'median': med(l), 'min': min(l) if l else None, 'max': max(l) if l else None}


od = [x for x in orig_dates if x]
res = {
    'file': path, 'size_bytes': size, 'root_tag': root.tag, 'record_tag': record_tag,
    'nsmap': {str(k): v for k, v in root.nsmap.items()},
    'n_records': n, 'n_distinct_assetNumber': len(asset_set),
    'fields': [{'name': k, 'example': v['example'], 'nonempty': v['nonempty'],
                'nonempty_share': round(v['nonempty'] / n, 4) if n else None,
                'n_distinct_capped50': len(v['distinct']),
                'distinct_if_small': sorted(v['distinct']) if len(v['distinct']) <= 12 else None}
               for k, v in fields.items()],
    'samples': samples, 'assetNumber_first25': asset_numbers,
    'credit_score': {'n_numeric_positive': len(credit_scores), 'n_missing_empty': score_missing, 'n_zero': score_zero,
                     'n_nonnumeric': score_nonnum,
                     'share_missing_or_zero': round((score_missing + score_zero + score_nonnum) / n, 4) if n else None,
                     'mean': mean(credit_scores), 'median': med(credit_scores),
                     'min': min(credit_scores) if credit_scores else None, 'max': max(credit_scores) if credit_scores else None,
                     'buckets_20pt': dict(sorted(buckets.items(), key=lambda kv: int(kv[0].split('-')[0]))),
                     'n_distinct_scores': len(set(credit_scores)), 'score_type_counts': dict(score_types)},
    'originalLoanAmount': mm(orig_amt),
    'originalInterestRatePercentage': mm(apr),
    'originalLoanTerm': mm(term),
    'paymentToIncomePercentage': mm(pti),
    'vehicleValueAmount': mm(vval),
    'reportingPeriodBeginningLoanBalanceAmount': {'n': len(begbal), 'mean': mean(begbal), 'sum': sum(begbal)},
    'reportingPeriodActualEndBalanceAmount': {'n': len(endbal), 'mean': mean(endbal), 'sum': sum(endbal),
                                              'n_zero': sum(1 for x in endbal if x == 0)},
    'currentDelinquencyStatus': {'value_counts_top': dict(delinq.most_common(15)), 'n_numeric': len(delinq_num),
                                 'share_ge1': round(sum(1 for x in delinq_num if x >= 1) / n, 4) if n else None,
                                 'share_ge30': round(sum(1 for x in delinq_num if x >= 30) / n, 4) if n else None,
                                 'share_ge60': round(sum(1 for x in delinq_num if x >= 60) / n, 4) if n else None},
    'zeroBalanceCode': {'value_counts': dict(zb), 'zeroBalanceEffectiveDate_nonempty': zb_date_nonempty},
    'chargedoffPrincipalAmount_nonempty': chargeoff_nonempty, 'recoveredAmount_nonempty': recovered_nonempty,
    'repossessedIndicator': dict(repo), 'vehicleNewUsedCode': dict(newused), 'subvented': dict(subv),
    'obligorIncomeVerificationLevelCode': dict(incver), 'obligorEmploymentVerificationCode': dict(empver),
    'obligorGeographicLocation_top10': dict(geo.most_common(10)), 'obligorGeographicLocation_n_distinct': len(geo),
    'reportingPeriodBeginningDate': dict(rp_begin), 'reportingPeriodEndingDate': dict(rp_end),
    'originationDate_minmax': [min(od) if od else None, max(od) if od else None],
}
json.dump(res, open(out, 'w'), indent=1, default=str)
print(json.dumps({k: res[k] for k in ['size_bytes', 'n_records', 'n_distinct_assetNumber', 'record_tag']}), file=sys.stderr)
