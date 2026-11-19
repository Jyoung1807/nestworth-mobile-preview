"""Presentation data from the shared dated engine; no second allocation formula."""
from datetime import date
from decimal import Decimal
from accountability import tracker,window
from finance import add_months,money
from category_catalog import category_id

ZERO=Decimal('0.00')


def spending_view(state,events,when,period='Weekly'):
    start=date.fromisoformat(state['draft']['start']);end=add_months(start,12)
    left,right=window(start,when,period);today=date.fromisoformat(state['tracking_date'])
    covered=any(date.fromisoformat(c['start'])<=max(start,left) and date.fromisoformat(c['end'])>=min(end,right) for c in state.get('coverage',[]))
    transactions=[t for t in state.get('period_transactions',[]) if max(start,left)<=date.fromisoformat(t['date'])<min(end,right) and date.fromisoformat(t['date'])<=today]
    expenses=[e for e in events if e['kind']=='expense' and max(start,left)<=e['date']<min(end,right)]
    bills=sorted((e for e in expenses if not e.get('allowance')),key=lambda e:(e['date'],e['id']))
    flexible=[e for e in events if e.get('allowance') and e['kind']=='expense']
    rows=tracker(flexible,transactions,start,when,period,True,as_of=today)
    flexible_categories={category_id(e['category']) for e in flexible if left<=e['date']<right}
    rows=[r for r in rows if category_id(r['category']) in flexible_categories]
    for row in rows:
        matching=[t for t in transactions if category_id(t['category'])==category_id(row['category'])]
        mixed=any(category_id(e['category'])==category_id(row['category']) for e in bills)
        # An aggregate observation for a mixed category cannot prove which part
        # was an allowance. Explicit links permit an honest allowance subtotal.
        ambiguous=mixed and any(not t.get('allowance_id') for t in matching)
        known=covered or bool(matching)
        if mixed and not ambiguous:
            row['spent']=sum((money(t['amount']) for t in matching if t.get('allowance_id')),ZERO)
            row['remaining']=row['allocation']-row['spent']
        if ambiguous or not known:row.update(spent=None,remaining=None)
        row['coverage']='Mixed payments · link transactions to an allowance' if ambiguous else 'Complete coverage' if covered else 'Recorded so far · incomplete coverage' if matching else 'Spending unknown · no coverage'
    total=sum((e['amount'] for e in expenses),ZERO)
    # Matched paid events are already in expenses. Observations are not another
    # scheduled payment. Coverage remains the sole proof of a complete statement.
    recorded=sum((money(t['amount']) for t in transactions),ZERO) if covered or transactions else None
    return dict(left=left,right=right,covered=covered,transactions=transactions,allowances=rows,bills=bills,budget=total,recorded=recorded,remaining=total-recorded if covered else None)
