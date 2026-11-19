"""Session-only recovery decisions layered over the tested financial engine."""
from collections import defaultdict
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal,ROUND_DOWN
from uuid import uuid4
import hashlib,json
from finance import money,add_months
from category_catalog import category_id
from household_calendar import week_start,week_label
from accountability import recovery_eligibility,recovery_status,recovery_source

ZERO=Decimal('0.00')


def record_id(record):
    return record.get('id') or hashlib.sha256(json.dumps(record,sort_keys=True,default=str).encode()).hexdigest()[:16]


def pending(state,record):
    payment_ids={c['event_id'] for c in record.get('changes',[])}
    if any(a['payment_id'] in payment_ids for a in state.get('actuals',[])):return False
    return date.fromisoformat(record['effective'])>date.fromisoformat(state['tracking_date'])


def available_events(state,category,left,right,mode='flexible'):
    from planning import result
    events=result(state,accounting=False)[0]
    eligibility=recovery_eligibility(state,events,category,left,right)
    available=eligibility.get('available',{})
    committed_plans={r['project_id'] for r in state.get('plan_recoveries',[])}
    return [dict(e,capacity=available[e['id']]) for e in events if e['id'] in available and available[e['id']]>0 and e.get('project_id') not in committed_plans
            and (mode=='all' or bool(e.get('allowance'))==(mode=='flexible'))]


def split_money(amount,capacities,weights=None):
    """Deterministic cent-exact capped allocation, including uneven partial periods."""
    amount=money(amount);capacities={k:money(v) for k,v in capacities.items() if v>0}
    if amount>sum(capacities.values(),ZERO):raise ValueError('The reduction exceeds remaining eligible spending.')
    allocated={k:ZERO for k in capacities};remaining=amount
    while remaining:
        active=[k for k in capacities if allocated[k]<capacities[k]]
        denominator=sum((Decimal(str((weights or {}).get(k,1))) for k in active),ZERO)
        if denominator<=0:raise ValueError('Choose positive allocation weights.')
        before=remaining
        shares={k:min(capacities[k]-allocated[k],(before*Decimal(str((weights or {}).get(k,1)))/denominator).quantize(Decimal('.01'),rounding=ROUND_DOWN)) for k in active}
        if not any(shares.values()):
            residual=remaining
            for k in active:
                shares[k]=min(Decimal('.01'),residual,capacities[k]-allocated[k]);residual-=shares[k]
                if not residual:break
        for k,value in shares.items():allocated[k]+=value;remaining-=value
    return allocated


def distribution_preview(state,category,left,right,amount,custom=None,mode='flexible'):
    events=available_events(state,category,left,right,mode)
    capacity={e['id']:e['capacity'] for e in events}
    by_week=defaultdict(list)
    for event in events:by_week[week_start(event['date'])].append(event)
    if custom is not None:
        if sum((money(v) for v in custom.values()),ZERO)!=money(amount):raise ValueError('Weekly amounts must add up to the recovery amount.')
        if set(custom)-set(by_week):raise ValueError('Choose only weeks with eligible spending in this month.')
        amounts={}
        for week,rows in by_week.items():
            caps={e['id']:e['capacity'] for e in rows}
            amounts.update(split_money(custom.get(week,ZERO),caps))
    elif mode=='flexible':
        # One weight per eligible calendar day, regardless of the original payment frequency.
        by_day=defaultdict(list)
        for e in events:by_day[e['date']].append(e)
        daily=split_money(amount,{d:sum((e['capacity'] for e in rows),ZERO) for d,rows in by_day.items()})
        amounts={}
        for day,rows in by_day.items():amounts.update(split_money(daily[day],{e['id']:e['capacity'] for e in rows}))
    else:
        amounts=split_money(amount,capacity,capacity)  # Fixed bills stay on their scheduled dates.
    reductions=[dict(event_id=e['id'],date=str(e['date']),amount=amounts.get(e['id'],ZERO)) for e in events if amounts.get(e['id'],ZERO)>0]
    weeks=[dict(week=str(w),label=week_label(w),days=len({e['date'] for e in rows}),capacity=sum((e['capacity'] for e in rows),ZERO),amount=sum((amounts.get(e['id'],ZERO) for e in rows),ZERO)) for w,rows in sorted(by_week.items())]
    return dict(reductions=reductions,weeks=weeks,capacity=sum(capacity.values(),ZERO),amount=money(amount),mode=mode)


def source_used(state,source):
    return sum((money(r['amount']) for r in [*state.get('recoveries',[]),*state.get('plan_recoveries',[]),*state.get('contingency_uses',[])] if r['source']==source),ZERO)


def remaining_source(state,source):
    return max(ZERO,money(state.get('recovery_sources',{}).get(source,0))-source_used(state,source))


def record_category_recovery(state,source,category,left,right,amount,custom=None,mode='flexible',replace_id=None):
    from planning import result
    candidate=deepcopy(state)
    if replace_id:remove_pending(candidate,replace_id,record_history=False)
    if not candidate['versions']:raise ValueError('Approve a budget before making recovery commitments.')
    amount=money(amount)
    if amount<=0 or amount>remaining_source(candidate,source):raise ValueError('Choose an amount within the unresolved overspend.')
    preview=distribution_preview(candidate,category,left,right,amount,custom,mode)
    if not preview['reductions']:raise ValueError('No eligible future spending is available.')
    record=dict(id=replace_id or uuid4().hex,source=source,category=category,amount=amount,
                effective=min(r['date'] for r in preview['reductions']),end=str(min(add_months(date.fromisoformat(candidate['draft']['start']),12),right)),
                period_start=str(left),period_end=str(right),reductions=preview['reductions'],distribution=preview['weeks'],mode=mode,custom=deepcopy(custom))
    candidate.setdefault('recoveries',[]).append(record)
    result(candidate)  # Validate the exact resulting forecast before committing anything.
    candidate.setdefault('forecast_history',[]).append(dict(type='Amended recovery' if replace_id else 'Recovery commitment',decision=deepcopy(record)))
    state.update(candidate)
    return deepcopy(record)


def remove_pending(state,identity,record_history=True):
    from planning import result
    candidate=deepcopy(state)
    for collection in ('recoveries','plan_recoveries','contingency_uses'):
        record=next((r for r in candidate.get(collection,[]) if record_id(r)==identity),None)
        if record:
            if collection!='contingency_uses' and not pending(candidate,record):raise ValueError('Only future pending commitments can be amended or reversed.')
            candidate[collection].remove(record);result(candidate)
            if record_history:candidate.setdefault('forecast_history',[]).append(dict(type='Reversed reserve funding' if collection=='contingency_uses' else 'Reversed commitment',date=candidate.get('tracking_date'),decision=deepcopy(record)))
            state.update(candidate);return
    raise ValueError('This pending commitment no longer exists.')


def accept_impact(state,source):
    amount=remaining_source(state,source)
    state.setdefault('accepted_overspends',{})[source]=amount
    state.setdefault('forecast_history',[]).append(dict(type='Accepted impact',decision=dict(source=source,category=source.rsplit(':',1)[-1],effective=state['tracking_date'],amount=amount)))


def apply_plan_recoveries(events,records):
    rows=deepcopy(events)
    for record in records:
        changes={c['event_id']:c for c in record['changes']}
        for e in rows:
            if e['id'] in changes and not e['paid']:
                change=changes[e['id']];e.update(amount=money(change['amount']),date=date.fromisoformat(change['date']))
    return rows


def plan_preview(state,source,project_id,action,amount=0,new_date=None,replace_id=None):
    from planning import result,summarize
    candidate=deepcopy(state)
    if replace_id:remove_pending(candidate,replace_id,record_history=False)
    if not candidate['versions']:raise ValueError('Approve a budget first.')
    today=date.fromisoformat(candidate['tracking_date']);start=date.fromisoformat(candidate['draft']['start']);end=add_months(start,12)
    before=result(candidate)[0]
    rows=sorted((e for e in result(candidate,accounting=False)[0] if e.get('project_id')==project_id and not e['paid'] and today<e['date']<end and e['amount']>0),key=lambda e:(e['date'],e['id']))
    if not rows:raise ValueError('This plan has no eligible future unpaid payments.')
    if plan_category_conflict(candidate,rows):raise ValueError('This planned payment already funds a category recovery. Amend or reverse that commitment first.')
    if any(r['project_id']==project_id for r in candidate.get('plan_recoveries',[])):raise ValueError('Amend the existing pending plan decision first.')
    total=sum((e['amount'] for e in rows),ZERO)
    if action=='Reduce':
        amount=money(amount)
        if amount<=0:raise ValueError('Enter a positive reduction.')
        reductions=split_money(amount,{e['id']:e['amount'] for e in rows},{e['id']:e['amount'] for e in rows})
        changes=[dict(event_id=e['id'],date=str(e['date']),amount=e['amount']-reductions[e['id']]) for e in rows]
    elif action=='Cancel':changes=[dict(event_id=e['id'],date=str(e['date']),amount=ZERO) for e in rows]
    elif action=='Postpone':
        if new_date is None or new_date<=rows[0]['date']:raise ValueError('Choose a date later than the first unpaid payment.')
        shift=new_date-rows[0]['date']
        changes=[dict(event_id=e['id'],date=str(e['date']+shift),amount=e['amount']) for e in rows]
    else:raise ValueError('Choose Reduce, Postpone or Cancel.')
    record=dict(id=replace_id or uuid4().hex,source=source,project_id=project_id,category=rows[0]['category'],name=rows[0]['name'].split(' · ')[0],action=action,
                effective=str(rows[0]['date']),end=str(end),changes=changes,amount=ZERO,total=total)
    candidate.setdefault('plan_recoveries',[]).append(record)
    after=result(candidate)[0]
    impact=summarize(after,start)['savings']-summarize(before,start)['savings']
    record['impact']=impact;record['amount']=min(remaining_source(state,source)+(next((r['amount'] for r in state.get('plan_recoveries',[]) if record_id(r)==replace_id),ZERO)),max(ZERO,impact))
    return candidate,record,impact


def save_plan_recovery(state,*args,**kwargs):
    candidate,record,impact=plan_preview(state,*args,**kwargs)
    candidate.setdefault('forecast_history',[]).append(dict(type='Planned expense recovery',decision=deepcopy(record)))
    state.update(candidate);return deepcopy(record)



def plan_category_conflict(state,rows):
    ids={e['id'] for e in rows}
    return any(any(r['event_id'] in ids for r in record['reductions']) if record.get('reductions') is not None else any(category_id(e['category'])==category_id(record['category']) and record['effective']<=str(e['date'])<record['end'] for e in rows) for record in state.get('recoveries',[]))


def plan_recovery_status(state,record):
    """Only matched actual payment evidence can verify a planned change."""
    today=date.fromisoformat(state['tracking_date'])
    ids={c['event_id'] for c in record['changes']}
    actuals=[a for a in state.get('actuals',[]) if a['payment_id'] in ids and date.fromisoformat(a['date'])<=today]
    complete={a['payment_id'] for a in actuals}==ids
    start=date.fromisoformat(state['draft']['start']);end=add_months(start,12)
    spent=sum((money(a['amount']) for a in actuals if start<=date.fromisoformat(a['date'])<end),ZERO)
    recovered=min(money(record['amount']),max(ZERO,money(record['total'])-spent)) if complete else ZERO
    remaining=money(record['amount'])-recovered
    return dict(recovered=recovered,remaining=remaining,status='Achieved' if complete and not remaining else 'Unfulfilled' if complete else 'Pending · not confirmed savings')

def collect_actions(state):
    from planning import result,aggregate
    from budget_comparison import historical_totals
    start=date.fromisoformat(state['draft']['start']);today=date.fromisoformat(state.get('tracking_date',str(start)))
    state.setdefault('tracking_date',str(today))
    actions=[];sources={}
    base=deepcopy(state);base['recoveries']=[]
    baseline=result(base,accounting=False)[0]
    for coverage in state.get('coverage',[]):
        left=date.fromisoformat(coverage['start']);right=date.fromisoformat(coverage['end'])
        categories={t['category'] for t in state.get('period_transactions',[]) if left<=date.fromisoformat(t['date'])<right}
        for category in sorted(categories):
            source,amount=recovery_source(state,category,left,right)
            if not amount:continue
            state.setdefault('recovery_sources',{})[source]=amount;sources[source]=(category,amount)
    for r in state.get('recoveries',[]):
        status=recovery_status(state,r,baseline);identity=record_id(r)
        failed=status['status']=='Unfulfilled' and status['remaining']>0
        if failed:
            source='shortfall:'+identity;state.setdefault('recovery_sources',{})[source]=status['remaining'];sources[source]=(r['category'],status['remaining'])
        actions.append(dict(id=identity,type='commitment',source=r['source'],category=r['category'],amount=r['amount'],reason='Future category reduction',status='Resolved' if status['remaining']==0 else 'Recovery shortfall' if failed else 'Recovery committed' if pending(state,r) else 'Awaiting verification',next='Review spending' if failed else 'Verify when covered' if not pending(state,r) else 'Wait for the destination period',record=r,recovered=status['recovered']))
    for r in state.get('plan_recoveries',[]):
        status=plan_recovery_status(state,r);identity=record_id(r)
        failed=status['status']=='Unfulfilled' and status['remaining']>0
        if failed:
            source='shortfall:'+identity;state.setdefault('recovery_sources',{})[source]=status['remaining'];sources[source]=(r['name'],status['remaining'])
        actions.append(dict(id=identity,type='plan_commitment',source=r['source'],category=r['name'],amount=r['amount'],reason=r['action']+' planned spending',status='Resolved' if status['status']=='Achieved' else 'Recovery shortfall' if failed else 'Recovery committed' if pending(state,r) else 'Awaiting verification',next='Review actual payment' if failed else 'Check actual payment after its date',record=r,recovered=status['recovered']))
    for source,(category,amount) in sources.items():
        used=source_used(state,source);accepted=min(max(ZERO,amount-used),money(state.get('accepted_overspends',{}).get(source,0)))
        unresolved=max(ZERO,amount-used-accepted)
        actions.insert(0,dict(id=source,type='overspend',source=source,category=category,amount=amount,remaining=unresolved,committed=used,accepted=accepted,reason='Observed spending exceeds the covered forecast',status='Needs decision' if unresolved else 'Accepted impact' if accepted else 'Recovery committed',next='Choose how to handle '+f'${unresolved:,.2f}' if unresolved else 'No new decision needed'))
    unknown=historical_totals(state.get('spending',[]),start)['uncategorised']
    if unknown and state.get('setup',{}).get('history_choice')!='declined':actions.append(dict(id='categorisation',type='review',category='Spending',amount=ZERO,reason=f'{unknown} historical records need a category',status='Needs decision',next='Review uncategorised records',page='Review Your Spending'))
    if not state.get('profile_complete'):actions.append(dict(id='profile',type='review',category='Household',amount=ZERO,reason='Check your household details',status='Needs decision',next='Review household profile',page='Your Household'))
    if not state['versions']:actions.append(dict(id='approval',type='review',category='Budget',amount=ZERO,reason='Your budget is still a draft',status='Needs decision',next='Review and approve',page='Compare & Finalise'))
    events=result(state)[0]
    if any(r['lowest_cash']<0 for r in aggregate(events,start,opening_cash=state['draft']['opening_cash'])):actions.append(dict(id='cash',type='review',category='Cash flow',amount=ZERO,reason='Projected cash cannot cover a dated payment',status='Needs decision',next='Review dated cash flow',page='Your Year Ahead'))
    upcoming=sorted((e for e in events if e.get('project_id') and not e['paid'] and e['amount']>0 and today<e['date']<=today+timedelta(days=30)),key=lambda e:(e['date'],e['id']))
    if state['versions'] and not state.get('plan_reviewed') and upcoming:
        event=upcoming[0]
        actions.append(dict(id='plans',type='review',category=event['name'],amount=event['amount'],reason='Planned payment due '+str(event['date']),status='Needs decision',next='Review upcoming plan',page='Build Your Budget',project_id=event['project_id']))
    for r in state.get('contingency_uses',[]):
        actions.append(dict(id=record_id(r),type='reserve_commitment',source=r['source'],category='Contingency',amount=r['amount'],reason='Funded from accumulated reserve',status='Completed',next='No new decision needed',record=r,recovered=ZERO))
    if state.get('setup'):
        from setup_model import requirements
        # The setup model, not a second checklist, owns routine completion.
        actions=[a for a in actions if not (a['type']=='review' and a['id'] in ('profile','approval','categorisation'))]
        seen=set()
        for step,message in requirements(state,state.get('spending',[])):
            if step in seen:continue
            seen.add(step)
            actions.append(dict(id='setup:'+step,type='review',category=step,amount=ZERO,reason=message,status='Setup reminder',next='Review '+step,page='Setup',setup_step=step))
        for action in actions:
            if action['type']=='review' and (action['id']!='cash' or not state['versions']):action['status']='Setup reminder'
    return actions


def approval_observed_impact(version):
    context=version.get('approval_context')
    if context is not None:return context.get('observed_savings_impact',ZERO)
    # Older locked versions already recorded reconciliation events. Read them;
    # never rewrite a snapshot to add provenance retrospectively.
    return sum((e['amount'] for e in version.get('events',[]) if e['kind']=='expense' and e['id'].startswith('observed:')),ZERO)


def recovery_decision_preview(state,source,sources,replace_id=None,accept_remainder=True):
    """Validate all sources atomically against the same dated forecast.

    Every source consumes capacity before the next is evaluated. Acceptance is
    metadata only: observations already changed the forecast, so no extra debit.
    """
    candidate=deepcopy(state)
    if replace_id:remove_pending(candidate,replace_id,record_history=False)
    records=[]
    for index,selection in enumerate(sources):
        available=remaining_source(candidate,source)
        if not replace_id:available=max(ZERO,available-money(candidate.get('accepted_overspends',{}).get(source,0)))
        if selection['response']=='Use contingency':
            from contingency_ledger import fund_from_reserve
            if money(selection['amount'])>available:raise ValueError('Reserve funding exceeds the unresolved spending decision.')
            record=fund_from_reserve(candidate,source,selection['amount']);collection='contingency_uses'
        elif selection['response']=='Offset another spending category':
            if money(selection['amount'])>available:raise ValueError('Choose an amount within the unresolved overspend; previously accepted impact stays accepted.')
            record=record_category_recovery(candidate,source,selection['category'],date.fromisoformat(selection['left']),date.fromisoformat(selection['right']),selection['amount'],selection.get('custom'),selection['mode'])
            collection='recoveries'
        elif selection['response']=='Adjust a planned one-off expense':
            record=save_plan_recovery(candidate,source,selection['project'],selection['plan_action'],selection.get('plan_amount',0),date.fromisoformat(selection['new_date']) if selection.get('new_date') else None)
            collection='plan_recoveries'
            record['amount']=min(record['amount'],available)
            candidate[collection][-1]['amount']=record['amount']
            candidate['forecast_history'][-1]['decision']['amount']=record['amount']
        else:raise ValueError('Choose a category or planned expense recovery source.')
        if index==0 and replace_id:
            record['id']=replace_id;candidate[collection][-1]['id']=replace_id
            candidate['forecast_history'][-1]['decision']['id']=replace_id
        records.append(record)
    accepted=remaining_source(candidate,source)
    if accept_remainder:accept_impact(candidate,source)
    return candidate,records,accepted


def recovery_totals(actions):
    records=[a for a in actions if a['type'] in ('commitment','plan_commitment')]
    return dict(pending=sum((a['amount']-a.get('recovered',ZERO) for a in records if a['status'] in ('Recovery committed','Awaiting verification')),ZERO),verified=sum((a.get('recovered',ZERO) for a in records),ZERO))
