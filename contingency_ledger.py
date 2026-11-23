"""Progressive, session-only reserve ledger; no future contribution is spendable.

Fictional scheduled income is assumed received on its date unless a matched
actual overrides it. Reserve policy changes are explicit forecast commands effective next calendar
month; earned tranches never change retrospectively. Legacy reapprovals retain
their existing rules. Fixed contributions also cap accrual by dates actually due.
"""
from budget_period import BudgetPeriod,period_end,month_starts
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal,ROUND_DOWN
from uuid import uuid4
from finance import money,add_months

ZERO=Decimal('0.00')


def approved_tranches(state,as_of=None):
    if not state['versions']:return []
    start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    today=min(as_of or date.fromisoformat(state['tracking_date']),end-timedelta(days=1))
    from contingency_policy import policy_versions
    policies=[(day,v) for day,_,v in policy_versions(state)]
    actuals={a['payment_id']:a for a in state.get('actuals',[])};rows=[]
    spans=BudgetPeriod.from_plan(state).months()
    for n,(left,right) in enumerate(spans):
        available=[(day,v) for day,v in policies if day<right and day<=today]
        if not available:continue
        effective,version=available[-1];begin=max(left,effective)
        if begin>today:continue
        target=next((e['amount'] for e in version['events'] if e['id']==f'reserve:{n}'),ZERO)+money(version.get('approval_context',{}).get('contingency_uses',{}).get(f'reserve:{n}',0))
        elapsed=max(0,(min(today+timedelta(days=1),right)-begin).days)
        pro_rata=(target*Decimal(elapsed)/Decimal((right-left).days)).quantize(Decimal('.01'),rounding=ROUND_DOWN)
        event=next((e for e in version['events'] if e['id']==f'reserve:{n}'),{})
        if event.get('reserve_policy',{}).get('method')=='fixed':
            due=sum((money(c['amount']) for c in event.get('contributions',[]) if c['date']<=str(today)),ZERO)
            pro_rata=min(pro_rata,due)
        receipts=ZERO
        for event in version['events']:
            if event['kind']!='income':continue
            actual=actuals.get(event['id']);day=date.fromisoformat(actual['date']) if actual else event['date'];amount=money(actual['amount']) if actual else event['amount']
            if left<=day<right and day<=today:receipts+=amount
        rows.append(dict(event_id=f'reserve:{n}',start=str(begin),end=str(right),target=target,earned=min(pro_rata,receipts)))
    return rows


def reserve_balance(state):
    from planning import result
    tranches=approved_tranches(state);uses=state.get('contingency_uses',[])
    current={e['id']:e['amount'] for e in result(state,accounting=False)[0] if e['kind']=='reserve'}
    buckets=[]
    for tranche in tranches:
        used=sum((a['amount'] for use in uses for a in use['allocations'] if a['event_id']==tranche['event_id']),ZERO)
        buckets.append(dict(tranche,used=used,available=min(max(ZERO,tranche['earned']-used),max(ZERO,current.get(tranche['event_id'],ZERO)))))
    accumulated=sum((r['earned'] for r in buckets),ZERO);ledger_committed=sum((r['amount'] for r in uses),ZERO)
    funded_capacity=None;unfunded=ZERO
    if state['draft'].get('contingency_policy') or state.get('reserve_changes'):
        # Targets need not be affordable. Usable earmarks must be backed by net
        # dated resources, without assuming opening cash is an opening reserve
        # or treating unverified recovery promises as generated savings.
        from planning import dated_cash
        start=date.fromisoformat(state['draft']['start']);today=date.fromisoformat(state['tracking_date'])
        baseline=deepcopy(state);baseline['recoveries']=[];baseline['plan_recoveries']=[]
        path=dated_cash(result(baseline)[0],start,min(period_end(state),today+timedelta(days=1)))
        generated=path[-1]['closing'] if path else ZERO
        # Funding classifies an already-incurred overrun; it is not another
        # payment. Add back only still-unresolved overrun costs. Once funded,
        # accepted or allocated to another recovery, those costs stay consumed.
        # Closed coverage can prove underspending; pending reductions cannot.
        from action_finance import collect_actions
        unresolved=sum((a['remaining'] for a in collect_actions(deepcopy(state)) if a['type']=='overspend' and a['status']=='Needs decision'),ZERO)
        funded_capacity=max(ZERO,generated+unresolved)
        remaining=funded_capacity
        for bucket in buckets:
            prior=bucket['available'];bucket['available']=min(prior,remaining)
            remaining-=bucket['available'];unfunded+=prior-bucket['available']
    external=sum((max(ZERO,r['earned']-r['used']-r['available']) for r in buckets),ZERO)
    committed=ledger_committed+max(ZERO,external-unfunded)
    annual=state['versions'][-1]['summary']['contingency']+sum((money(a) for a in state['versions'][-1].get('approval_context',{}).get('contingency_uses',{}).values()),ZERO) if state['versions'] else ZERO
    balance=dict(annual_target=annual,accumulated=accumulated,committed=committed,shortfall=max(ZERO,ledger_committed-accumulated),available=sum((r['available'] for r in buckets),ZERO),buckets=buckets)

    if state['draft'].get('contingency_policy') or state.get('reserve_changes'):
        balance.update(funding_capacity=funded_capacity,unfunded_accrual=unfunded,forecast_target=sum(current.values(),ZERO)+ledger_committed,forecast_remaining=sum(current.values(),ZERO),approved_target=annual)
    return balance


def apply_reserve_uses(events,uses):
    rows=deepcopy(events);mapping={e['id']:e for e in rows if e['kind']=='reserve'}
    for use in uses:
        for allocation in use['allocations']:
            event=mapping.get(allocation['event_id'])
            if event is None or allocation['amount']>event['amount']:raise ValueError('A reserve contribution already funds an overspend. Reverse that funding before reducing the reserve policy.')
            event['amount']-=allocation['amount']
            if event.get('reserve_policy',{}).get('method')=='fixed':
                event.setdefault('reserve_releases',[]).append(dict(date=use['effective'],amount=allocation['amount']))
    return rows


def fund_from_reserve(state,source,amount):
    from action_finance import remaining_source
    amount=money(amount);balance=reserve_balance(state)
    if not state['versions'] or amount<=0 or amount>min(balance['available'],remaining_source(state,source)):raise ValueError('Use only accumulated, available contingency within the unresolved overspend.')
    remaining=amount;allocations=[]
    for row in balance['buckets']:
        take=min(remaining,row['available'])
        if take:allocations.append(dict(event_id=row['event_id'],amount=take));remaining-=take
        if not remaining:break
    record=dict(id=uuid4().hex,source=source,funded_category='Recovery shortfall' if source.startswith('shortfall:') else source.rsplit(':',1)[-1],category='Contingency',kind='contingency',amount=amount,effective=state['tracking_date'],end=str(period_end(state)),allocations=allocations)
    state.setdefault('contingency_uses',[]).append(record)
    state.setdefault('forecast_history',[]).append(dict(type='Funded from accumulated contingency',decision=deepcopy(record)))
    return deepcopy(record)
