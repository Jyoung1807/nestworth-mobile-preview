"""Confirmed duplicate corrections preserve source rows and audit history."""
from copy import deepcopy
from datetime import date


def effective(rows):return [row for row in rows if not row.get('excluded_duplicate')]


def current(state):return effective(state.get('period_transactions',[]))


def set_duplicate(state,transaction_id,excluded=True,duplicate_of=None):
    rows=state.get('period_transactions',[])
    row=next((t for t in rows if t['id']==transaction_id),None)
    if row is None:raise ValueError('Choose an existing recorded transaction.')
    if excluded:
        original=next((t for t in rows if t['id']==duplicate_of and not t.get('excluded_duplicate')),None)
        if original is None or original['id']==row['id']:raise ValueError('Select the original transaction to retain.')
        if original['date']!=row['date'] or original['amount']!=row['amount']:
            raise ValueError('Duplicate candidates must have the same date and amount. Review different payments separately.')
    before=deepcopy(row)
    row['excluded_duplicate']=bool(excluded)
    if excluded:row['duplicate_of']=duplicate_of
    else:row.pop('duplicate_of',None)
    state.setdefault('transaction_audit',[]).append(dict(type='Duplicate excluded' if excluded else 'Duplicate restored',transaction_id=transaction_id,before=before,after=deepcopy(row),review_date=state.get('tracking_date')))
