"""Session-only accountability. Amounts are Decimal; no bank or persistence calls.

Transactions are immutable source observations. Coverage is explicit and synthetic.
Recovery reductions are forecasts until their destination period is closed.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from finance import money, add_months
from category_catalog import category_id
from household_calendar import week_bounds

ZERO=Decimal('0.00')


def window(start, when, period='Weekly'):
    end=add_months(start,12)
    if not start<=when<end: raise ValueError('Choose a date in the budget year')
    if period=='Weekly':return week_bounds(when)
    left=when.replace(day=1)
    return max(start,left),min(end,add_months(left,1))


def revise_events(events, revisions):
    rows=deepcopy(events)
    base={e['id']:e['amount'] for e in events}
    for revision in revisions:
        day=date.fromisoformat(revision['effective'])
        if revision['mode'] in ('schedule','plan_schedule'):
            paid_ids=set(revision.get('protected_paid_ids',[]))
            rows=[r for r in rows if r['item_id']!=revision['target'] or r['date']<day or r['paid'] or r['id'] in paid_ids]
            rows.extend(deepcopy(revision['schedule_events']))
            base.update({r['id']:r['amount'] for r in revision['schedule_events']})
            continue
        for row in rows:
            match=row['item_id']==revision['target'] if revision['scope']=='item' else category_id(row['category'])==category_id(revision['target'])
            if match and row['kind']==revision.get('kind','expense') and row['date']>=day and not row['paid']:
                if revision['mode']=='percentage':row['amount']=(row['amount']*(1+Decimal(str(revision['value']))/100)).quantize(Decimal('.01'))
                else:
                    # Preserve proration of flexible allowances at horizon boundaries.
                    ratio=money(revision['value'])/money(revision['old_amount']) if money(revision['old_amount']) else None
                    row['amount']=(base[row['id']]*ratio).quantize(Decimal('.01')) if ratio is not None else money(revision['value'])
    return rows


def reduce_window(events, category, left, right, amount):
    from planning import reduce_events
    candidates=[e for e in events if e['kind']=='expense' and category_id(e['category'])==category_id(category) and left<=e['date']<right and not e['paid']]
    if amount:reduce_events(candidates,money(amount))


def apply_recoveries(events, recoveries):
    rows=deepcopy(events)
    for r in recoveries:
        if r.get('reductions') is not None:
            by_id={e['id']:e for e in rows}
            for reduction in r['reductions']:
                event=by_id.get(reduction['event_id'])
                if event is None:raise ValueError('A recovery payment no longer exists; amend the pending commitment.')
                if event['paid']:continue
                if str(event['date'])!=reduction['date']:raise ValueError('A recovery payment date changed; amend dependent pending commitments first.')
                value=money(reduction['amount'])
                if value>event['amount']:raise ValueError('A recovery exceeds the remaining payment; amend the pending commitment.')
                event['amount']-=value
            continue
        reduce_window(rows,r['category'],date.fromisoformat(r['effective']),date.fromisoformat(r['end']),money(r['amount']))
    return rows



def dated_allocations(events):
    """Spread flexible limits over their own periods, preserving every cent.

    Bills retain their actual due date. A fortnight/month crossing a tracker
    boundary contributes only the days within that window, with no rollover.
    """
    result=[]
    for event in events:
        boundary=event.get('allocation_end')
        if not event.get('allowance') or not boundary:
            result.append(deepcopy(event));continue
        days=(boundary-event['date']).days
        daily=(event['amount']/days).quantize(Decimal('.01'))
        remaining=event['amount']
        for i in range(days):
            row=deepcopy(event)
            row.update(id=event['id']+':day:'+str(i),date=event['date']+timedelta(days=i),amount=remaining if i==days-1 else min(remaining,daily),allocation_end=None)
            remaining-=row['amount'];result.append(row)
    return result


def tracker(events, transactions, start, when, period='Weekly', covered=False,as_of=None):
    left,right=window(start,when,period)
    end=add_months(start,12)
    events=[e for e in dated_allocations(events) if start<=e['date']<end]
    transactions=[t for t in transactions if start<=date.fromisoformat(t['date'])<end]
    as_of=as_of or when
    categories={e['category'] for e in events if e['kind']=='expense' and left<=e['date']<right}
    categories.update(t['category'] for t in transactions if left<=date.fromisoformat(t['date'])<right)
    rows=[]
    for category in sorted(categories):
        matching=[e for e in events if e['kind']=='expense' and category_id(e['category'])==category_id(category) and left<=e['date']<right]
        allocation=sum((e['amount'] for e in matching),ZERO)
        expected=ZERO
        for e in matching:
            if e.get('allowance') and e.get('allocation_end'):
                # Allocation is spread only within its own scheduled allowance period.
                span=max(1,(right-e['date']).days)
                expected+=e['amount']*Decimal(min(span,max(0,(as_of-e['date']).days+1)))/span
            elif e['date']<=as_of:expected+=e['amount']
        spent=sum((money(t['amount']) for t in transactions if category_id(t['category'])==category_id(category) and left<=date.fromisoformat(t['date'])<right and date.fromisoformat(t['date'])<=as_of),ZERO) if covered else None
        closed=as_of>=right-timedelta(days=1)
        status='No statement coverage'
        if spent is not None:
            status=('Period completed with overspending' if closed else "Over the period's total allocation") if spent>allocation else ('Period completed with underspending' if closed and spent<allocation else 'On track')
            if not closed and spent<=allocation and spent>expected:status='Spending ahead of expected pace'
        rows.append(dict(category=category,allocation=allocation,spent=spent,remaining=None if spent is None else allocation-spent,status=status,left=left,right=right))
    return rows


def observed_events(events,state):
    """Replace covered closed periods; active periods only add genuine excess.

    Explicit nonoverlapping coverage prevents week/month duplication. No observation
    is counted as a new expense on top of its matched allocation.
    """
    rows=deepcopy(events)
    transactions=state.get('period_transactions',[])
    for coverage in state.get('coverage',[]):
        left=date.fromisoformat(coverage['start']);right=date.fromisoformat(coverage['end'])
        as_of=date.fromisoformat(state['tracking_date'])
        cats={e['category'] for e in rows if e['kind']=='expense' and left<=e['date']<right}
        cats.update(t['category'] for t in transactions if left<=date.fromisoformat(t['date'])<right)
        for category in cats:
            matches=[e for e in rows if e['kind']=='expense' and category_id(e['category'])==category_id(category) and left<=e['date']<right]
            forecast=sum((e['amount'] for e in matches),ZERO)
            actual=sum((money(t['amount']) for t in transactions if category_id(t['category'])==category_id(category) and left<=date.fromisoformat(t['date'])<right and date.fromisoformat(t['date'])<=as_of),ZERO)
            delta=actual-forecast if as_of>=right-timedelta(days=1) else max(ZERO,actual-forecast)
            if delta:
                # Signed reconciliation adjustment, not a second transaction.
                rows.append(dict(id='observed:'+str(left)+':'+category,item_id='observed',project_id=None,name='Fictional period reconciliation',category=category,category_id=category_id(category),subcategory='',kind='expense',date=min(as_of,right-timedelta(days=1)),amount=delta,paid=True))
    return rows


def recovery_status(state,commitment,base_events):
    def period(record):
        if record.get('reductions') is not None:
            return date.fromisoformat(record.get('period_start',record['effective'])),min(date.fromisoformat(record.get('period_end',record['end'])),add_months(date.fromisoformat(state['draft']['start']),12))
        return date.fromisoformat(record['effective']),date.fromisoformat(record['end'])
    left,right=period(commitment)
    as_of=date.fromisoformat(state['tracking_date'])
    covered=any(date.fromisoformat(c['start'])<=left and date.fromisoformat(c['end'])>=right for c in state.get('coverage',[]))
    recovered=ZERO
    if covered and as_of>=right-timedelta(days=1):
        baseline=sum((e['amount'] for e in base_events if e['kind']=='expense' and category_id(e['category'])==category_id(commitment['category']) and left<=e['date']<right),ZERO)
        spent=sum((money(t['amount']) for t in state.get('period_transactions',[]) if category_id(t['category'])==category_id(commitment['category']) and left<=date.fromisoformat(t['date'])<right),ZERO)
        earlier=sum((money(r['amount']) for r in state.get('recoveries',[])[:state.get('recoveries',[]).index(commitment)] if r['category']==commitment['category'] and period(r)==(left,right)),ZERO)
        recovered=min(money(commitment['amount']),max(ZERO,baseline-spent-earlier))
    return dict(recovered=recovered,remaining=money(commitment['amount'])-recovered,status='Achieved' if recovered==money(commitment['amount']) else 'Unfulfilled' if covered and as_of>=right-timedelta(days=1) else 'Pending · not confirmed savings')


def save_revision(state,revision):
    from planning import result, summarize
    if not state['versions']:raise ValueError('Approve a budget first')
    start=date.fromisoformat(state['draft']['start']);day=date.fromisoformat(revision['effective'])
    if not max(start,date.fromisoformat(state.get('tracking_date',str(start))))<=day<add_months(start,12):raise ValueError('Effective date must be in the remaining forecast year')
    if revision['scope']=='category' and revision['mode']!='percentage':raise ValueError('Category revisions use a percentage')
    if revision['mode']=='percentage':
        if not Decimal(str(revision['value'])).is_finite() or Decimal(str(revision['value'])) < -100:raise ValueError('Invalid percentage')
    else:money(revision['value'])
    if revision['scope'] not in ('item','category') or revision['mode'] not in ('percentage','amount','schedule','plan_schedule'):raise ValueError('Invalid revision')
    if revision['scope']=='item' and revision['target'] not in {e['id'] for collection in ('income','expenses','projects') for e in state['draft'][collection]}:raise ValueError('Choose an existing entry')
    if revision['scope']=='category' and revision['target'] not in state['categories']:raise ValueError('Choose an existing category')
    if revision['mode'] in ('schedule','plan_schedule'):
        from planning import scheduled_events,uid
        revision=deepcopy(revision);identity=uid()
        protected={a['payment_id'] for a in state.get('actuals',[])}
        source=revise_events(scheduled_events(state['draft']),state.get('revisions',[]))
        paid_dates={r['date'] for r in source if r['id'] in protected and r['item_id']==revision['target']}
        target_paid={r['id'] for r in source if r['item_id']==revision['target'] and r['id'] in protected}
        paid_dates.update(date.fromisoformat(str(a['date'])) for a in state.get('actuals',[]) if a['payment_id'] in target_paid)
        if revision['mode']=='schedule':
            from finance import FREQUENCIES
            if revision.get('new_frequency') not in FREQUENCIES[:-1]:raise ValueError('Choose a recurring frequency')
            collection='income' if revision.get('kind')=='income' else 'expenses'
            entry=deepcopy(next(e for e in state['draft'][collection] if e['id']==revision['target']))
            entry.update(amount=money(revision['value']),frequency=revision['new_frequency'],first_payment=revision['effective'])
            temporary=deepcopy(state['draft']);temporary.update(income=[],expenses=[],projects=[]);temporary[collection]=[entry]
            from accountability import dated_allocations
            future=[r for r in dated_allocations(scheduled_events(temporary)) if r['item_id']==entry['id']]
        else:
            future=[deepcopy(r) for r in source if r['item_id']==revision['target'] and r['date']>=day and r['id'] not in protected]
            if not future:raise ValueError('No unpaid planned payments remain in the eligible period')
            action=revision.get('plan_action')
            if action=='Cancel':future=[]
            elif action=='Postpone':
                new_date=date.fromisoformat(revision['new_date'])
                if not future or new_date<=min(r['date'] for r in future):raise ValueError('Choose a date after the first unpaid instalment')
                shift=new_date-min(r['date'] for r in future)
                for row in future:row['date']+=shift
            elif action=='Reduce':
                from planning import reduce_events
                reduce_events(future,money(revision['value']))
            else:raise ValueError('Choose a supported plan change')
        revision['schedule_events']=[dict(r,id='revision:'+identity+':'+r['id']) for r in future if r['date']>=day and r['date'] not in paid_dates and r['id'] not in protected]
        revision['protected_paid_ids']=list(protected)
    if revision['mode']=='amount' and revision['scope']=='item':
        schedule=next((r for r in reversed(state.get('revisions',[])) if r['target']==revision['target'] and r['mode']=='schedule' and date.fromisoformat(r['effective'])<=day),None)
        if schedule:revision=dict(revision,old_amount=schedule['value'])
    before=result(state)[0];candidate=deepcopy(state);candidate.setdefault('revisions',[]).append(deepcopy(revision))
    after=result(candidate)[0]
    state['revisions']=candidate['revisions']
    state.setdefault('forecast_history',[]).append(dict(type='Revision',decision=deepcopy(revision),before=summarize(before,start),after=summarize(after,start)))




def recovery_source(state,category,left,right):
    """One source per observed coverage window, independent of week/month view.

    Switching views must not turn the same $35 expense into a second recoverable
    source. Recovery cannot exceed the excess actually included in the forecast.
    """
    from planning import result
    start=date.fromisoformat(state['draft']['start']);end=add_months(start,12)
    left=max(start,left);right=min(end,right)
    coverage=next((c for c in state.get('coverage',[]) if date.fromisoformat(c['start'])<=left and date.fromisoformat(c['end'])>=right),None)
    if coverage:left=date.fromisoformat(coverage['start']);right=date.fromisoformat(coverage['end'])
    base=deepcopy(state);base['recoveries']=[]
    events=result(base,accounting=False)[0]
    allocation=sum((e['amount'] for e in events if e['kind']=='expense' and category_id(e['category'])==category_id(category) and left<=e['date']<right),ZERO)
    as_of=date.fromisoformat(state['tracking_date'])
    spent=sum((money(t['amount']) for t in state.get('period_transactions',[]) if category_id(t['category'])==category_id(category) and left<=date.fromisoformat(t['date'])<right and date.fromisoformat(t['date'])<=as_of),ZERO)
    return str(left)+':'+str(right)+':'+category,max(ZERO,spent-allocation)

def recovery_eligibility(state,events,category,left,right):
    """One eligibility rule for the preview and the save-time validation.

    A category's annual total is not a promise of spending in a particular week.
    Exclude past/today, paid events, out-of-horizon events and conflicting windows.
    `events` already includes existing commitments, so capacity cannot be reused.
    """
    start=date.fromisoformat(state['draft']['start']);end=add_months(start,12)
    as_of=date.fromisoformat(state['tracking_date'])
    effective=max(start,left,as_of+timedelta(days=1));boundary=min(end,right)
    reason=''
    if right<=as_of+timedelta(days=1):reason='This period is completed; choose a current or future period.'
    elif effective>=boundary:reason='No future spending within this budget year is available in this period.'
    elif any(category_id(r['category'])==category_id(category) and date.fromisoformat(r['effective'])<boundary and date.fromisoformat(r['end'])>effective and ((r.get('period_start')!=str(left) or r.get('period_end')!=str(right)) if r.get('reductions') is not None else (r['effective']!=str(effective) or r['end']!=str(boundary))) for r in state.get('recoveries',[])):
        reason='An existing commitment uses an overlapping window; choose another period.'
    matches=[e for e in events if e['kind']=='expense' and category_id(e['category'])==category_id(category)
             and effective<=e['date']<boundary and not e['paid'] and e['amount']>0] if not reason else []
    available={e['id']:e['amount'] for e in matches}
    # An allowance can already have been consumed even if its future daily
    # allocation events have not occurred. Reserve that consumption first.
    for coverage in state.get('coverage',[]):
        a=date.fromisoformat(coverage['start']);b=date.fromisoformat(coverage['end'])
        spent=sum((money(t['amount']) for t in state.get('period_transactions',[]) if category_id(t['category'])==category_id(category) and a<=date.fromisoformat(t['date'])<b and date.fromisoformat(t['date'])<=as_of),ZERO)
        dated=sum((e['amount'] for e in events if e['kind']=='expense' and category_id(e['category'])==category_id(category) and a<=e['date']<b and e['date']<=as_of),ZERO)
        consumed=max(ZERO,spent-dated)
        future_in_coverage=sorted((e for e in events if e['kind']=='expense' and category_id(e['category'])==category_id(category) and as_of<e['date']<b and e['date']>=a and not e['paid'] and e['amount']>0),key=lambda e:(e['date'],e['id']))
        for event in future_in_coverage:
            take=min(consumed,event['amount']);consumed-=take
            if event['id'] in available:available[event['id']]-=take
    amount=sum(available.values(),ZERO)
    future=[e['date'] for e in events if e['kind']=='expense' and category_id(e['category'])==category_id(category)
            and max(start,as_of+timedelta(days=1))<=e['date']<end and not e['paid'] and e['amount']>0]
    if not reason and not amount:reason='No unpaid scheduled spending or unspent flexible allowance is available in this period.'
    return dict(amount=amount,effective=effective,end=boundary,reason=reason,next_date=min(future) if future else None,available=available)


def commit_recovery(state,source,category,left,right,amount):
    from planning import result
    amount=money(amount)
    if not state['versions'] or amount<=0:raise ValueError('Approve a budget and enter a positive recovery')
    events=result(state,accounting=False)[0]
    eligible=recovery_eligibility(state,events,category,left,right)
    if amount>eligible['amount']:
        raise ValueError(eligible['reason'] or f"Only ${eligible['amount']:,.2f} is eligible in this category and period.")
    spent_sources=state.get('recovery_sources',{})
    used=sum((money(r['amount']) for r in [*state.get('recoveries',[]),*state.get('plan_recoveries',[]),*state.get('contingency_uses',[])] if r['source']==source),ZERO)
    if source not in spent_sources or used+amount>money(spent_sources[source]):raise ValueError('Recovery exceeds the unresolved source cost')
    record=dict(source=source,category=category,effective=str(eligible['effective']),end=str(eligible['end']),amount=amount,
                period_start=str(left),period_end=str(right))
    state.setdefault('recoveries',[]).append(record)
    state.setdefault('forecast_history',[]).append(dict(type='Recovery commitment',decision=deepcopy(record)))


def simulate_period(state,events,when,period,category,variance):
    start=date.fromisoformat(state['draft']['start']);left,right=window(start,when,period)
    for c in state.get('coverage',[]):
        a=date.fromisoformat(c['start']);b=date.fromisoformat(c['end'])
        if a<right and b>left and (a!=left or b!=right):raise ValueError('This period overlaps existing coverage. Use the same weekly or monthly boundaries to avoid duplicate observations.')
    rows=tracker(events,[],start,when,period)
    transactions=[]
    for row in rows:
        amount=row['allocation']+(Decimal(str(variance)) if row['category']==category else ZERO)
        if amount<0:raise ValueError('Simulated spending cannot be negative')
        transactions.append(dict(id='sim:'+str(left)+':'+row['category'],date=str(when),description='Fictional '+row['category'],category=row['category'],amount=amount,source='synthetic'))
    state['period_transactions']=[t for t in state.get('period_transactions',[]) if not left<=date.fromisoformat(t['date'])<right]+transactions
    state['coverage']=[c for c in state.get('coverage',[]) if c['start']!=str(left) or c['end']!=str(right)]+[dict(start=str(left),end=str(right),source='synthetic')]


def revision_entry(state,collection,target,when):
    """Display current assumptions while retaining the replay amount basis."""
    entry=deepcopy(next(e for e in state['draft'][collection] if e['id']==target))
    entry['_revision_basis']=entry.get('amount',0)
    for r in state.get('revisions',[]):
        if date.fromisoformat(r['effective'])>when:continue
        match=r['target']==target if r['scope']=='item' else category_id(r['target'])==category_id(entry.get('category','Income'))
        if not match or r.get('kind','expense')!=('income' if collection=='income' else 'expense'):continue
        if r['mode']=='schedule':entry.update(amount=money(r['value']),frequency=r['new_frequency'],_revision_basis=money(r['value']))
        elif r['mode']=='amount':entry['amount']=money(r['value'])
        elif r['mode']=='percentage' and 'amount' in entry:entry['amount']=money(entry['amount']*(1+Decimal(str(r['value']))/100))
    if collection=='projects':
        from planning import result
        entry['total']=sum((r['amount'] for r in result(state)[0] if r.get('project_id')==target),ZERO)
    return entry


def reverse_latest_revision(state):
    """Reverse only the latest still-future amendment; replay validates dependants."""
    from planning import result,summarize
    if not state['versions'] or not state.get('revisions'):raise ValueError('No forecast amendment is available to reverse.')
    latest=state['revisions'][-1];today=date.fromisoformat(state.get('tracking_date',state['draft']['start']))
    if date.fromisoformat(latest['effective'])<today:raise ValueError('This amendment already affects elapsed periods. Make a new prospective amendment instead.')
    ids={r['id'] for r in latest.get('schedule_events',[])}
    if any(a['payment_id'] in ids for a in state.get('actuals',[])):raise ValueError('Recorded payments protect this amendment. Make a prospective change instead.')
    start=date.fromisoformat(state['draft']['start']);before=summarize(result(state)[0],start)
    candidate=deepcopy(state);candidate['revisions'].pop()
    try:after=summarize(result(candidate)[0],start)
    except (ValueError,KeyError) as error:raise ValueError('Later funding depends on this amendment. Review that funding first.') from error
    state['revisions']=candidate['revisions']
    state.setdefault('forecast_history',[]).append(dict(type='Reversed revision',date=str(today),decision=deepcopy(latest),before=before,after=after))
