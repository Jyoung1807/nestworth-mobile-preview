"""Deterministic fictional household factory. No clients, credentials or persistence.

First safe slice: existing outgoing/forecast models only. Incoming-ledger and new
reserve policies must be added through their approved services, never faked here.
"""
from datetime import date
from decimal import Decimal
from copy import deepcopy
from planning import new_planner,result
from setup_model import setup_state,approve_setup,requirements
from category_catalog import sync
from accountability import simulate_period

VERSION='nestworth-uat-1'
SCENARIO_DATE=date(2026,11,19)


def populated_household():
    start=date(2026,11,1)
    income=[dict(name='Nora · net salary',person='Person A',amount=6500,frequency='Monthly',first_payment='2026-11-01'),
            dict(name='Sam · net salary',person='Person B',amount=5200,frequency='Monthly',first_payment='2026-11-15')]
    specs=[('Mortgage','Mortgage / Rent',2400,'Monthly','2026-11-23',False),
           ('Groceries','Groceries',900,'Weekly','2026-11-02',True),
           ('Electricity','Utilities',180,'Quarterly','2026-11-20',False),
           ('Internet','Utilities',85,'Monthly','2026-11-26',False),
           ('Car insurance','Vehicles',980,'Annual','2026-11-24',False),
           ('Fuel','Vehicles',160,'Weekly','2026-11-02',True),
           ('Lily · school costs','Children',220,'Monthly','2026-11-01',True),
           ('Theo · childcare','Children',450,'Monthly','2026-11-01',False),
           ('Milo · food','Pets',90,'Monthly','2026-11-01',True),
           ('Dining and leisure','Leisure',200,'Weekly','2026-11-02',True),
           ('Christmas gifts','Other',800,'Annual','2026-12-10',False),
           ('Christmas food and hosting','Other',350,'Annual','2026-12-20',False),
           ('Lily birthday celebration','Other',180,'Annual','2027-03-10',False)]
    expenses=[dict(name=n,category=c,amount=a,frequency=f,first_payment=d,allowance=flex,
                   **({'allocation_method':'consistent'} if flex else {})) for n,c,a,f,d,flex in specs]
    state=new_planner(start,income,expenses)
    # Stable fixture IDs make canonical resets auditable (new_planner normally
    # generates IDs for user-created entries). No existing record is rewritten.
    for collection in ('income','expenses'):
        for n,item in enumerate(state['draft'][collection]):item['id']=f'fictional:{collection}:{n}'
    state['profile'].update(adult_names=['Nora','Sam'],ages=[8,4],
        children=[dict(id='child:0',name='Lily',age=8),dict(id='child:1',name='Theo',age=4)],
        pets=[dict(id='pet:0',name='Milo',type='Dog')],cars=1,
        vehicles=[dict(id='cars:0',name='Family car',type='Car',finance=False)],timezone='Australia/Brisbane')
    state['draft'].update(opening_cash=18000,goal=15000)
    state['draft']['projects']=[dict(id='fictional:holiday',name='Family holiday',category='Leisure',total=2400,status='Active',payments=[
        dict(id='deposit',date='2027-01-15',amount=600,description='Deposit',precision='Exact date'),
        dict(id='balance',date='2027-03-15',amount=1800,description='Balance',precision='Exact date')])]
    state['tracking_date']=str(SCENARIO_DATE)
    sync(state)
    setup_state(state).update(household_reviewed=True,regular_reviewed=True,plans_reviewed=True,
        history_choice='declined',history_invitation=True,reserve_reviewed=True,opening_cash_known=True)
    if requirements(state):raise ValueError('Fictional household does not meet approval requirements')
    approve_setup(state,[],confirmed=True)
    # Use the same approved-budget observation service as the existing simulator.
    simulate_period(state,result(state,accounting=False)[0],SCENARIO_DATE,'Weekly','Groceries',35)
    state['period_transactions']=[dict(id=f'fictional:groceries:{n}',date=d,description=merchant,
        category='Groceries',amount=Decimal(a),reviewed=True,source='fictional-demo') for n,(d,merchant,a) in enumerate([
            ('2026-11-16','Fictional Woolworths','350.00'),('2026-11-18','Fictional ALDI','280.00'),('2026-11-19','Fictional Woolworths','305.00')])]
    history=[dict(id=f'fictional:history:{month}:{n}',date=f'2026-{month:02d}-{5+n:02d}',
        description='Fictional '+item['name'],category=item['category'],amount=Decimal(str(item['amount'])),reviewed=True,source='fictional-demo')
        for month in (8,9,10) for n,item in enumerate(state['draft']['expenses'][:8])]
    state['spending']=history
    return dict(start=str(start),income=deepcopy(income),expenses=deepcopy(expenses),transactions=history,planner=state,
                _test_only=True,_fixture_version=VERSION,test_name='Nora & Sam · populated fictional household')


def demo_key(base):return base+':test:'+VERSION


def load_demo(session,base):
    key=demo_key(base)
    if key not in session:session[key]=populated_household()
    if not session[key].get('_test_only') or session[key].get('_fixture_version')!=VERSION:
        raise ValueError('Only the isolated fictional fixture can be loaded here.')
    session[base+':active_test']=key
    return key


def reset_demo(session,base,key,confirmed=False):
    if not confirmed:raise ValueError('Confirm discarding changes to the fictional demo only.')
    if key!=demo_key(base) or session.get(base+':active_test')!=key or not session.get(key,{}).get('_test_only') or session[key].get('_fixture_version')!=VERSION:
        raise ValueError('Only this active populated fictional household can be reset.')
    fresh=populated_household()  # Validate before removing any old state.
    for widget in list(session):
        if widget.startswith(key+':'):del session[widget]
    session[key]=fresh
