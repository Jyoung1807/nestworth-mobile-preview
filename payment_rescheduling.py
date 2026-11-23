"""Occurrence-preserving future payment moves, over the existing dated engine.

No amounts change, no event is dropped, and no approved snapshot is edited.
Series reuse the existing recurrence anchor rules. Moves outside the active
budget period are rejected, rather than making an obligation disappear.
"""
from copy import deepcopy
from datetime import date,timedelta
from uuid import uuid4
from finance import add_months,money
from budget_period import BudgetPeriod,period_end


def apply_reschedules(events,commands):
    if not commands:return events
    rows=deepcopy(events);by_id={e['id']:e for e in rows}
    for command in commands:
        for move in command['moves']:
            event=by_id.get(move['event_id'])
            if event is None or str(event['date'])!=move['old_date']:
                raise ValueError('A rescheduled payment changed. Reverse or amend its dependent reschedule first.')
            event['date']=date.fromisoformat(move['new_date'])
    return rows


def proposal(state,event_id,new_date,scope='occurrence'):
    from planning import result
    if not state['versions']:raise ValueError('Approve a budget before rescheduling payments.')
    if scope not in ('occurrence','future_series'):raise ValueError('Choose this occurrence or this and future occurrences.')
    bounds=BudgetPeriod.from_plan(state);today=date.fromisoformat(state.get('tracking_date',str(bounds.start)))
    if not isinstance(new_date,date):new_date=date.fromisoformat(str(new_date))
    if new_date<today or not bounds.contains(new_date):raise ValueError('Choose today or a future date within this budget period.')
    events=result(state,accounting=False)[0]
    selected=next((e for e in events if e['id']==event_id),None)
    protected={a['payment_id'] for a in state.get('actuals',[])}
    if not selected or selected['kind']!='expense' or selected.get('allowance') or selected['amount']<=0 or selected['paid'] or selected['id'] in protected or selected['date']<today:
        raise ValueError('Choose an existing unpaid scheduled payment dated today or later.')
    funded={r['event_id'] for record in state.get('recoveries',[]) for r in record.get('reductions',[])}|{c['event_id'] for record in state.get('plan_recoveries',[]) for c in record.get('changes',[])}
    if event_id in funded:raise ValueError('This payment funds a recovery. Amend or reverse that commitment before changing its date.')
    if selected['date']==new_date:raise ValueError('Choose a different payment date.')
    affected=[selected]
    if scope=='future_series':
        if any(any(m['event_id'].startswith(selected['item_id']+':') for m in c['moves']) for c in state.get('payment_reschedules',[])):
            raise ValueError('This item already has a reschedule. Reverse it or move individual occurrences to preserve the recurrence cadence.')
        affected=sorted([e for e in events if e['item_id']==selected['item_id'] and e['kind']=='expense' and not e.get('allowance') and e['date']>=selected['date']],key=lambda e:(e['date'],e['id']))
        if any(e['id'] in funded for e in affected):raise ValueError('A future payment funds a recovery. Move only an uncommitted occurrence or reverse the recovery first.')
        if any(e['paid'] or e['id'] in protected for e in affected):raise ValueError('A future occurrence already has an actual payment. Move only an unpaid occurrence.')
        if len(affected)<2:raise ValueError('No further scheduled occurrences exist; choose this occurrence only.')
    entries=[e for group in ('expenses','projects') for e in state['draft'][group]]
    entry=next((e for e in entries if e['id']==selected['item_id']),{})
    # A frequency revision makes the original item's cadence ambiguous. Reject
    # series movement rather than guessing; occurrence moves remain supported.
    if scope=='future_series' and any(r.get('target')==selected['item_id'] and r.get('mode')=='schedule' for r in state.get('revisions',[])):
        raise ValueError('This schedule has a frequency revision. Reschedule one occurrence at a time.')
    frequency=entry.get('frequency','One-off');moves=[]
    for index,event in enumerate(affected):
        if selected.get('project_id'):
            destination=new_date+(event['date']-selected['date'])
        elif frequency in ('Monthly','Quarterly','Six-monthly','Annual'):
            stride={'Monthly':1,'Quarterly':3,'Six-monthly':6,'Annual':12}[frequency]
            # Use original recurrence-index distance, not list position: this
            # preserves gaps and never recreates an omitted/paid occurrence.
            count=((event['date'].year-selected['date'].year)*12+event['date'].month-selected['date'].month)//stride
            destination=add_months(new_date,count*stride)
        else:destination=new_date+(event['date']-selected['date'])
        if destination<today or not bounds.contains(destination):
            raise ValueError('The move would place a payment outside this budget period. No payment has been removed; use a smaller move or this occurrence only.')
        moves.append(dict(event_id=event['id'],old_date=str(event['date']),new_date=str(destination),amount=str(event['amount'])))
    return dict(event_id=event_id,name=selected['name'],scope=scope,moves=moves,effective=str(today))


def preview(state,event_id,new_date,scope='occurrence'):
    from planning import result,summarize,aggregate
    command=proposal(state,event_id,new_date,scope);candidate=deepcopy(state)
    candidate.setdefault('payment_reschedules',[]).append(command)
    before=result(state)[0];after=result(candidate)[0];start=date.fromisoformat(state['draft']['start'])
    end=period_end(state)
    known=state.get('setup',{}).get('opening_cash_known',state['draft']['opening_cash']>0)
    def financial(events):
        totals=summarize(events,start,end)
        cash=aggregate(events,start,opening_cash=state['draft']['opening_cash'],end=end) if known else None
        return dict(spending=totals['expenses'],additional_savings=totals['income']-totals['expenses'],closing=cash[-1]['closing_cash'] if cash else None,lowest=min(r['lowest_cash'] for r in cash) if cash else None)
    return dict(command=command,before=financial(before),after=financial(after))


def save(state,event_id,new_date,scope='occurrence',command_id=None):
    identity=command_id or uuid4().hex
    existing=next((c for c in state.get('payment_reschedules',[]) if c.get('id')==identity),None)
    if existing:
        if existing['event_id']!=event_id or existing['scope']!=scope or existing['moves'][0]['new_date']!=str(new_date):raise ValueError('This confirmation was already used for a different change.')
        return deepcopy(existing)
    details=preview(state,event_id,new_date,scope)
    command=dict(details['command'],id=identity)
    state.setdefault('payment_reschedules',[]).append(command)
    state.setdefault('forecast_history',[]).append(dict(type='Payment rescheduled',decision=deepcopy(command),before=details['before'],after=details['after']))
    return deepcopy(command)


def reverse(state,identity):
    from planning import result
    candidate=deepcopy(state);commands=candidate.get('payment_reschedules',[])
    command=next((c for c in commands if c['id']==identity),None)
    if not command:raise ValueError('Choose an existing reschedule.')
    today=date.fromisoformat(state['tracking_date']);paid={a['payment_id'] for a in state.get('actuals',[])}
    if any(m['event_id'] in paid or min(date.fromisoformat(m['new_date']),date.fromisoformat(m['old_date']))<today for m in command['moves']):raise ValueError('Paid or historical reschedules cannot be reversed.')
    candidate['payment_reschedules']=[c for c in commands if c['id']!=identity]
    result(candidate)  # Full dependency/recovery validation before any write.
    state['payment_reschedules']=candidate['payment_reschedules']
    state.setdefault('forecast_history',[]).append(dict(type='Payment reschedule reversed',decision=deepcopy(command)))


def financial_position(state):
    """Same dated forecast used by reschedules and recovery confirmation."""
    from planning import result,summarize,dated_cash
    start=date.fromisoformat(state['draft']['start']);end=period_end(state);events=result(state)[0]
    totals=summarize(events,start,end)
    known=state.get('setup',{}).get('opening_cash_known',state['draft']['opening_cash']>0)
    cash=dated_cash(events,start,end,state['draft']['opening_cash']) if known else []
    return dict(additional_savings=totals['income']-totals['expenses'],closing=cash[-1]['closing'] if cash else money(state['draft']['opening_cash']) if known else None,lowest=min((min(r['opening'],r['closing']) for r in cash),default=money(state['draft']['opening_cash']) if known else None))
