"""Evidence-based read projections; decisions use existing financial commands.

Acknowledge is not acceptance or resolution. Stable action IDs and a condition
fingerprint prevent duplicate notifications and reopen materially changed issues.
"""
from datetime import date,timedelta
from decimal import Decimal
from copy import deepcopy
from budget_period import period_end


def needs_decision(action):
    return action['status']=='Needs decision' and (action['type'] in ('overspend','financial_alert') or action['id']=='cash')


def period_for(state,action):
    if action.get('period_start') and action.get('period_end'):
        return date.fromisoformat(str(action['period_start'])),date.fromisoformat(str(action['period_end']))
    source=action.get('source','')
    try:
        left,right,_=source.split(':',2)
        return date.fromisoformat(left),date.fromisoformat(right)
    except ValueError:
        if source.startswith('shortfall:'):
            from action_finance import record_id
            record=next((r for r in [*state.get('recoveries',[]),*state.get('plan_recoveries',[])] if record_id(r)==source[len('shortfall:'):]),None)
            if record:return date.fromisoformat(record.get('period_start',record['effective'])),date.fromisoformat(record.get('period_end',record['end']))
    return None,None


def extras(state,events,actions):
    """Conditions absent from the older action list; no automatic money changes."""
    if not state['versions']:return []
    from observations import current
    from budget_comparison import needs_category
    today=date.fromisoformat(state['tracking_date']);start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    pending=[t for t in current(state) if start<=date.fromisoformat(t['date'])<end and date.fromisoformat(t['date'])<=today and (needs_category(t) or t.get('reviewed') is False)]
    result=[]
    if pending:result.append(dict(id='current:categorisation',type='financial_alert',category='Transaction review',amount=Decimal(0),reason=f'{len(pending)} recorded transactions need review; category insights may be incomplete.',status='Needs decision',next='Review transactions',page='Spending',count=len(pending)))
    # Only explicit typed targets may create a financial warning. Never treat a
    # legacy aspiration, unknown cash or missing opening savings as a shortfall.
    target=state['draft'].get('target')
    if target:
        from planning import summarize,aggregate
        from savings_projection import project
        totals=summarize(events,start,end)
        known=state.get('setup',{}).get('opening_cash_known',state['draft']['opening_cash']>0)
        cash=aggregate(events,start,opening_cash=state['draft']['opening_cash'],end=end)[-1]['closing_cash'] if known else None
        outcome=project(state['draft'],totals,cash)['target']
        if outcome['variance'] is not None and outcome['variance']<0:
            result.append(dict(id='target:'+target['kind'],type='financial_alert',category='Savings target' if target['kind']!='closing_cash' else 'Cash target',amount=-outcome['variance'],reason='Projected outcome is below the selected period-end target; not a realised loss.',status='Needs decision',next='Review forecast',page='Outlook'))
    for reminder in state.get('reminders',[]):
        if reminder.get('due_date') and not reminder.get('completed') and not reminder.get('dismissed') and date.fromisoformat(reminder['due_date'])<today:
            result.append(dict(id='reminder:'+reminder['id'],type='financial_alert',category=reminder['name'],amount=Decimal(0),reason='Overdue since '+reminder['due_date'],status='Needs decision',next='Review overdue reminder',page='Actions'))
    return result


def alerts(state,actions=None):
    from action_finance import collect_actions
    from planning import result,summarize
    from home_view_model import category_view
    from household_calendar import week_bounds
    actions=collect_actions(deepcopy(state)) if actions is None else actions
    start=date.fromisoformat(state['draft']['start']);today=date.fromisoformat(state.get('tracking_date',str(start)))
    totals=summarize(result(state)[0],start,period_end(state));approved=state['versions'][-1]['summary'] if state['versions'] else None
    seen=set();rows=[]
    for a in actions:
        if not needs_decision(a) or a['id'] in seen:continue
        seen.add(a['id']);left,right=period_for(state,a)
        amount=a.get('remaining',a['amount']);fingerprint=str(amount)+':'+a['reason']
        row=dict(a,amount=amount,period_start=left,period_end=right,severity='critical' if a['id']=='cash' else 'warning',fingerprint=fingerprint,
            acknowledged=state.get('alert_acknowledgements',{}).get(a['id'])==fingerprint,
            forecast_savings=totals['savings'],forecast_variance=totals['savings']-approved['savings'] if approved else None)
        rows.append(row)
    # A useful pace warning requires coverage and no pending transaction review.
    left,right=week_bounds(today);left=max(start,left);right=min(period_end(state),right)
    if left<right and not any(a['id']=='current:categorisation' for a in actions):
        data=category_view(state,left,right)
        if data['covered'] and Decimal((today-left).days+1)/Decimal((right-left).days)<=Decimal('.6'):
            for category in data['rows']:
                if category['budget']>0 and category['actual'] is not None and category['budget']*Decimal('.8')<=category['actual']<=category['budget']:
                    rows.append(dict(id='pace:'+str(left)+':'+category['category'],type='pace',category=category['category'],amount=category['actual'],severity='info',status='Approaching limit',reason='At least 80% of this week’s plan is used early in the week.',period_start=left,period_end=right,acknowledged=False,fingerprint=str(category['actual'])))
    return sorted(rows,key=lambda a:({'critical':0,'warning':1,'info':2}[a['severity']],a.get('acknowledged',False),-a['amount'],a['id']))


def acknowledge(state,alert):
    state.setdefault('alert_acknowledgements',{})[alert['id']]=alert['fingerprint']
