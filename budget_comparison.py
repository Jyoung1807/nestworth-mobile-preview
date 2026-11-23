"""Fictional historical baseline, shared-entry edits and explicit finalisation."""
from budget_period import BudgetPeriod,period_end,month_starts
from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
from category_catalog import category_id,tag,normalized
from finance import money,add_months
from planning import result,event_total,approve,aggregate

UNKNOWN='Uncategorised'


def needs_category(row):
    return not row.get('category') or normalized(row['category']) in ('uncategorised','uncategorized')


def historical_rows(transactions,start):
    begin=add_months(start,-12)
    return [r for r in transactions if begin<=date.fromisoformat(r['date'])<start]


def historical_totals(transactions,start):
    rows=historical_rows(transactions,start)
    full=sum((money(r['amount']) for r in rows),Decimal(0))
    adjusted=sum((money(r['amount']) for r in rows if not r.get('exclude_baseline')),Decimal(0))
    return {'full':full,'adjusted':adjusted,'excluded':full-adjusted,'uncategorised':sum(needs_category(r) for r in rows)}


def category_comparison(state,transactions,threshold=15):
    start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    values=defaultdict(lambda:{'historical':Decimal(0),'baseline':Decimal(0),'proposed':Decimal(0)})
    for row in historical_rows(transactions,start):
        name=UNKNOWN if needs_category(row) else row['category']; id=category_id(name)
        values[id]['name']=name; values[id]['historical']+=money(row['amount'])
        if not row.get('exclude_baseline'):values[id]['baseline']+=money(row['amount'])
    events,_=result(state)
    for row in events:
        if row['kind']!='expense' or not start<=row['date']<end:continue
        id=category_id(row['category']);values[id]['name']=row['category'];values[id]['proposed']+=row['amount']
    rows=[]
    for id,v in sorted(values.items(),key=lambda item:item[1]['name']):
        variance=v['proposed']-v['baseline'];percent=variance/v['baseline']*100 if v['baseline'] else None
        fingerprint=hashlib.sha256(json.dumps([id,str(v['historical']),str(v['baseline']),str(v['proposed'])]).encode()).hexdigest()
        significant=abs(variance)>=Decimal(500) and (percent is None or abs(percent)>=Decimal(str(threshold)))
        review=state.get('comparison_reviews',{}).get(id,{})
        rows.append(dict(v,id=id,variance=variance,percent=percent,significant=significant,
                         fingerprint=fingerprint,reviewed=review.get('fingerprint')==fingerprint and review.get('reviewed',False),note=review.get('note','')))
    return rows


def mark_reviewed(state,row,note='',reviewed=True):
    state.setdefault('comparison_reviews',{})[row['id']]={'fingerprint':row['fingerprint'],'note':note.strip(),'reviewed':reviewed}


def edit_historical(state,transactions,id,category,subcategory='',excluded=None,reason=None,allowance_id=None):
    if category not in state['categories'] and category!=UNKNOWN:raise ValueError('Choose a category')
    row=next(r for r in transactions if r['id']==id)
    if allowance_id:
        allocation=next((e for e in state['draft']['expenses'] if e['id']==allowance_id and e.get('allowance')),None)
        if allocation is None or allocation['category']!=category:raise ValueError('Choose a matching allowance and category')
    row['reviewed']=False
    row.update(category=category,subcategory=subcategory,allowance_id=allowance_id,
               exclude_baseline=row.get('exclude_baseline',False) if excluded is None else bool(excluded),
               exclusion_reason=row.get('exclusion_reason','') if reason is None else reason.strip())
    tag(state,row)


def finalise(state,transactions,confirmed=False,keep_stretch=False):
    if not confirmed:raise ValueError('Review and confirm the proposed position first')
    start=date.fromisoformat(state['draft']['start'])
    if historical_totals(transactions,start)['uncategorised']:raise ValueError('Categorise all historical transactions before approval')
    comparisons=category_comparison(state,transactions,state.get('variance_threshold',15))
    if any(r['significant'] and not r['reviewed'] for r in comparisons):raise ValueError('Review the highlighted category differences before approval')
    aspiration=money(state['draft']['goal']) if keep_stretch else None
    version=approve(state,stretch_goal=aspiration)
    state['versions'][-1]['comparison']=[{k:v for k,v in row.items()} for row in comparisons]
    state['versions'][-1]['historical_totals']=historical_totals(transactions,start)
    return deepcopy(state['versions'][-1])


def month_position(state,when,spending=None):
    """Unknown spending remains unknown. A baseline allocation is not a bank balance."""
    start=when.replace(day=1);end=add_months(start,1)
    if not state['versions']:return {'budget':None,'spent':None,'remaining':None}
    version=state['versions'][-1]
    allocation=event_total(version['events'],'expense',start,end)
    spent=None if spending is None else sum((money(r['amount']) for r in spending if start<=date.fromisoformat(r['date'])<end),Decimal(0))
    return {'budget':allocation,'spent':spent,'remaining':None if spent is None else allocation-spent}
