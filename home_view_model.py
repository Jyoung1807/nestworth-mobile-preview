"""Presentation projections of existing dated engine output. No writes or new allocation rules."""
from budget_period import BudgetPeriod,period_end,month_starts
from datetime import date
from decimal import Decimal
from finance import money,add_months
from planning import result,summarize,aggregate
from accountability import dated_allocations

ZERO=Decimal('0.00')


def annual_view(state):
    start=date.fromisoformat(state['draft']['start']);events=result(state)[0]
    summary=summarize(events,start,end=period_end(state))
    approved=state['versions'][-1] if state['versions'] else None
    budget=approved['summary'] if approved else summarize(result(state,accounting=False)[0],start,end=period_end(state))
    known=state.get('setup',{}).get('opening_cash_known',state['draft']['opening_cash']>0)
    cash=aggregate(events,start,'Monthly',state['draft']['opening_cash'],end=period_end(state)) if known else None
    return dict(start=start,end=period_end(state),events=events,summary=summary,budget=budget,approved=approved,cash=cash,
                closing=cash[-1]['closing_cash'] if cash else None,lowest=min(r['lowest_cash'] for r in cash) if cash else None)


def category_view(state,left,right):
    approved=state['versions'][-1] if state['versions'] else None
    budget_events=dated_allocations(approved['events'] if approved else result(state,accounting=False)[0])
    budget=[e for e in budget_events if e['kind']=='expense' and left<=e['date']<right]
    forecast=[e for e in result(state)[0] if e['kind']=='expense' and left<=e['date']<right]
    transactions=[t for t in current_observations(state) if left<=date.fromisoformat(t['date'])<right and date.fromisoformat(t['date'])<=date.fromisoformat(state.get('tracking_date',state['draft']['start']))]
    covered=any(date.fromisoformat(c['start'])<=left and date.fromisoformat(c['end'])>=right for c in state.get('coverage',[]))
    names=sorted({e['category'] for e in budget+forecast}|{t.get('category') or 'Uncategorised' for t in transactions})
    rows=[]
    for name in names:
        matching=[t for t in transactions if (t.get('category') or 'Uncategorised')==name]
        amount=sum((e['amount'] for e in budget if e['category']==name),ZERO)
        actual=sum((money(t['amount']) for t in matching),ZERO) if covered or matching else None
        rows.append(dict(category=name,budget=amount,actual=actual,remaining=amount-actual if covered and actual is not None else None,
                         forecast=sum((e['amount'] for e in forecast if e['category']==name),ZERO)))
    return dict(rows=rows,budget=budget,forecast=forecast,transactions=transactions,covered=covered)

from observations import current as current_observations
