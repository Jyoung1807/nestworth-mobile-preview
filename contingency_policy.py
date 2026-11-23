"""Versioned contingency earmarks. Never an expense or cash movement.

v2 percentage: actual dated planned normal recurring costs, excluding one-offs,
projects and explicitly non-household purposes. Fixed: count actual anchored
contribution dates. Monthly reserve IDs remain stable for the existing ledger.
"""
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
from finance import money,add_months
from budget_period import BudgetPeriod,period_end

FREQUENCIES=('Weekly','Fortnightly','Monthly','Annual')
EXCLUDED={'holiday','holidays','renovation','renovations','major one-off purchase','major purchases','internal transfer','internal transfers','savings','savings contribution','savings contributions','contingency','standalone project','projects'}
PURPOSES=['Normal household spending','Holiday','Renovation','Major one-off purchase','Savings contribution','Internal transfer']


def default_policy():return dict(version=2,method='percentage',percentage=10)


def validate(policy):
    p=deepcopy(policy)
    if p.get('version')!=2:raise ValueError('Choose a supported contingency policy.')
    if p.get('method')=='percentage':
        rate=Decimal(str(p.get('percentage',10)))
        if not rate.is_finite() or not 0<=rate<=100:raise ValueError('Contingency percentage must be between 0 and 100.')
        p['percentage']=rate
    elif p.get('method')=='fixed':
        p['amount']=money(p.get('amount',0))
        if p['amount']<0:raise ValueError('Fixed contingency cannot be negative.')
        if p.get('frequency') not in FREQUENCIES:raise ValueError('Choose weekly, fortnightly, monthly or annual contingency.')
        date.fromisoformat(str(p['first_contribution']))
    else:raise ValueError('Choose percentage or fixed contingency.')
    return p


def eligible(item):
    if item.get('frequency') not in ('Weekly','Fortnightly','Monthly','Quarterly','Six-monthly','Annual'):return False
    if item.get('project_id') or item.get('contingency_eligible') is False:return False
    # Only explicit type/category labels and exact legacy names; never merchant
    # substring inference ("holiday care" can be ordinary childcare).
    labels=[item.get(k,'') for k in ('category','name','transaction_type','expense_kind')]
    if any(str(label).strip().casefold() in EXCLUDED for label in labels):return False
    return item.get('spending_purpose','Normal household spending')=='Normal household spending'


def monthly_events(plan,expenses,policy=None,active_start=None):
    from planning import payment_dates
    bounds=BudgetPeriod.from_plan(plan);p=validate(policy or plan['contingency_policy']);active_start=max(bounds.start,active_start or bounds.start)
    items={i['id']:i for i in plan['expenses'] if eligible(i)}
    contributions=[]
    if p['method']=='fixed':
        contributions=[dict(date=str(d),amount=money(p['amount'])) for d in payment_dates(date.fromisoformat(str(p['first_contribution'])),p['frequency'],bounds.start,bounds.end)]
    rows=[];cumulative=Decimal(0);allocated=Decimal(0)
    for n,(left,right) in enumerate(bounds.months()):
        base=sum((e['amount'] for e in expenses if e['kind']=='expense' and not e.get('project_id') and e.get('contingency_eligible',e['item_id'] in items) and max(left,active_start)<=e['date']<right),Decimal(0))
        due=[c for c in contributions if str(max(left,active_start))<=c['date']<str(right)]
        cumulative+=base
        amount=money(cumulative*p['percentage']/100)-allocated if p['method']=='percentage' else sum((c['amount'] for c in due),Decimal(0))
        allocated+=amount
        rows.append(dict(id=f'reserve:{n}',item_id='reserve',project_id=None,name='Contingency reserve',category='Contingency',subcategory='',kind='reserve',date=left,amount=amount,paid=False,reserve_policy=deepcopy(p),eligible_spending=base,contributions=due))
    return rows


def sequence(state):return max([0,*[v.get('reserve_sequence',i) for i,v in enumerate(state['versions'])],*[c.get('sequence',0) for c in state.get('reserve_changes',[])]])+1


def policy_versions(state):
    rows=[]
    start=date.fromisoformat(state['draft']['start'])
    for i,v in enumerate(state['versions']):
        context=v.get('approval_context',{});review=date.fromisoformat(context.get('review_date') or str(start))
        effective=date.fromisoformat(context.get('reserve_policy_effective') or str(max(start,review) if i==0 else add_months(review.replace(day=1),1)))
        rows.append((effective,v.get('reserve_sequence',i),v))
    for c in state.get('reserve_changes',[]):rows.append((date.fromisoformat(c['effective']),c['sequence'],dict(events=c['snapshot_events'],approval_context={})))
    return sorted(rows,key=lambda r:(r[0],r[1]))


def forecast_events(state,events,plan,source=None):
    """Project dated policy targets; earned ledger tranches remain immutable.

    Expense amendments change the forecast base, not retrospectively earned
    reserve. Only explicit approval/policy commands set ledger accrual bases.
    """
    changes=state.get('reserve_changes',[])
    if not plan.get('contingency_policy') and not changes:return events
    events=deepcopy(events)
    catalog={item['id']:item for v in state['versions'] for item in v['plan']['expenses']}
    catalog.update({item['id']:item for item in plan['expenses']})
    for event in events:
        if event['kind']=='expense' and 'contingency_eligible' not in event:
            event['contingency_eligible']=eligible(catalog[event['item_id']]) if event['item_id'] in catalog and not event.get('project_id') else False
    current={e['id']:e for e in events if e['kind']=='reserve'};out=[e for e in events if e['kind']!='reserve']
    bounds=BudgetPeriod.from_plan(plan);cache={}
    for n,(left,right) in enumerate(bounds.months()):
        identity=f'reserve:{n}'
        applicable=sorted([c for c in changes if date.fromisoformat(c['effective'])<=left],key=lambda c:(c['effective'],c['sequence']))
        p=applicable[-1]['policy'] if applicable else plan.get('contingency_policy')
        if p is None:
            if identity in current:out.append(current[identity])
            continue
        active_start=date.fromisoformat(applicable[-1]['effective']) if applicable else bounds.start
        signature=repr(p)+str(active_start)
        if signature not in cache:cache[signature]=monthly_events(plan,events,p,active_start)
        out.append(cache[signature][n])
    if source is not None:
        baseline={e['id']:e['amount'] for e in source if e['kind']=='reserve'}
        for row in out:
            if row['kind']=='reserve' and row['id'] in current:
                reduction=max(Decimal(0),baseline.get(row['id'],current[row['id']]['amount'])-current[row['id']]['amount'])
                if reduction>row['amount']:raise ValueError('This reserve already funds a forecast expense. Reverse or amend that funding before reducing the policy.')
                row['amount']-=reduction
    return sorted(out,key=lambda e:(e['date'],e['id']))


def preview_change(state,policy):
    from planning import result,summarize
    if not state['versions']:raise ValueError('Approve the budget before changing forecast contingency.')
    p=validate(policy);today=date.fromisoformat(state['tracking_date']);effective=max(date.fromisoformat(state['draft']['start']),add_months(today.replace(day=1),1))
    if effective>=period_end(state):raise ValueError('No future month remains. Existing accrued contingency stays protected.')
    candidate=deepcopy(state);command=dict(id=uuid4().hex,effective=str(effective),policy=p,sequence=sequence(state),snapshot_events=[])
    candidate.setdefault('reserve_changes',[]).append(command)
    before=result(state)[0];after=result(candidate)[0];command['snapshot_events']=deepcopy(after)
    start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    return candidate,command,dict(before=summarize(before,start,end),after=summarize(after,start,end),effective=effective)


def save_change(state,policy):
    candidate,command,impact=preview_change(state,policy)
    previous=state.get('reserve_changes',[])[-1] if state.get('reserve_changes') else None
    if previous and all(previous[k]==command[k] for k in ('effective','policy','snapshot_events')):return deepcopy(previous)
    state['reserve_changes']=candidate['reserve_changes']
    state.setdefault('forecast_history',[]).append(dict(type='Contingency policy changed',decision=deepcopy(command),before=impact['before'],after=impact['after']))
    return deepcopy(command)


def dated_earmarks(events):
    """Read-only date projection; monthly ledger identities remain unchanged.

    Fixed contributions appear on their actual dates. Reserve used to classify
    an incurred expense is released on its decision date, never retroactively
    moved into the original contribution week. No cash movement is added.
    """
    rows=[]
    for event in events:
        if event['kind']!='reserve' or event.get('reserve_policy',{}).get('method')!='fixed' or event.get('reserve_projection'):
            rows.append(event);continue
        releases=event.get('reserve_releases',[])
        gross=sum((money(c['amount']) for c in event.get('contributions',[])),Decimal(0))
        reduction=gross-event['amount']-sum((money(r['amount']) for r in releases),Decimal(0))
        if reduction<0:raise ValueError('Fixed reserve contribution schedule does not reconcile to its target.')
        for n,contribution in enumerate(event.get('contributions',[])):
            amount=money(contribution['amount']);take=min(reduction,amount);reduction-=take
            rows.append(dict(event,id=event['id']+':contribution:'+str(n),date=date.fromisoformat(contribution['date']),amount=amount-take,reserve_projection=True))
        if reduction:raise ValueError('Reserve funding exceeds its fixed contribution schedule.')
        for n,release in enumerate(releases):
            rows.append(dict(event,id=event['id']+':release:'+str(n),date=date.fromisoformat(release['date']),amount=-money(release['amount']),reserve_projection=True))
    return rows
