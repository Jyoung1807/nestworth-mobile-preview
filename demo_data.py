"""Deterministic synthetic fixtures. Never represent these as connected bank data."""
from datetime import date
from finance import CATEGORIES, add_months


def new_demo(start):
    expenses = []
    amounts = (2400,450,500,320,180,900,350,200)
    for category, amount in zip(CATEGORIES, amounts):
        expenses.append({'name':f'{category} plan', 'category':category, 'amount':float(amount),
                         'frequency':'Monthly','first_payment':start.isoformat()})
    transactions=[]
    for month in range(12):
        period = add_months(start, month-12)
        for i, (category, amount) in enumerate(zip(CATEGORIES, amounts)):
            transactions.append({'id':f'demo-{month}-{i}', 'date':period.replace(day=5+i).isoformat(),
                                 'description':f'Synthetic {category.lower()} expense',
                                 'category':category, 'amount':round(amount*(.88+((month+i)%5)*.04),2)})
    transactions[1]['category']=None
    transactions[10]['category']=None
    return {'start':start.isoformat(), 'expenses':expenses, 'transactions':transactions,
            'income':[{'name':'Demo salary A','amount':6500.0,'frequency':'Monthly','first_payment':start.isoformat()},
                      {'name':'Demo salary B','amount':4200.0,'frequency':'Monthly','first_payment':start.isoformat()}],
            'dependants':2,'vehicles':1,'housing':'Mortgage',
            'assets':[{'asset':'Synthetic home','value':780000.0}, {'asset':'Synthetic vehicle','value':25000.0}],
            'members':[{'name':'Demo adult A','relationship':'Adult'}, {'name':'Demo adult B','relationship':'Adult'},
                       {'name':'Demo child A','relationship':'Dependant'}, {'name':'Demo child B','relationship':'Dependant'}],
            'goal':24000.0,'committed':1200.0,'contingency':10,'adjustments':[]}


def demo_state(session, user_id, household_id, start=None):
    key = f'demo:{user_id}:{household_id}'
    active=session.get(key+':active_test')
    if active and active.startswith(key+':test:') and session.get(active,{}).get('_test_only'):return session[active],active
    if key not in session:
        session[key] = new_demo(start or date.today().replace(day=1))
    return session[key], key
