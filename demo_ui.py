"""Session-local synthetic dashboard. Financial calculations live in finance.py."""
from datetime import date
from decimal import Decimal
import pandas as pd
from finance import CATEGORIES, FREQUENCIES, forecast, scheduled_totals, money
from demo_data import demo_state

PAGES = ('Dashboard','Review Your Spending','Your Household','Build Your Budget','Your Year Ahead','Compare & Finalise','Actions Centre')
NAV_PAGES = ('Your Household','Build Your Budget','Review Your Spending','Compare & Finalise','Your Year Ahead','Dashboard','Actions Centre')


def dollars(value):
    return f'${value:,.2f}'


def table(rows):
    return pd.DataFrame([{k:float(v) if isinstance(v,Decimal) else v for k,v in row.items()} for row in rows])


def schedule_editor(st, items, key, category=False):
    config = {'frequency':st.column_config.SelectboxColumn('Frequency',options=FREQUENCIES,required=True),
              'amount':st.column_config.NumberColumn('Amount ($)',min_value=0.0,required=True),
              'first_payment':st.column_config.DateColumn('First payment / one-off date',required=True)}
    if category:
        config['category']=st.column_config.SelectboxColumn('Category', options=CATEGORIES,required=True)
    columns=["name", "category", "amount", "frequency", "first_payment"] if category else ["name", "amount", "frequency", "first_payment"]
    frame=pd.DataFrame(items,columns=columns)
    frame["amount"]=pd.to_numeric(frame["amount"])
    frame['first_payment']=pd.to_datetime(frame['first_payment']).dt.date
    edited=st.data_editor(frame,num_rows='dynamic',hide_index=True,column_config=config,key=key,width='stretch')
    return edited


def validate_schedule(frame, category=False):
    rows=frame.to_dict('records')
    for row in rows:
        if not isinstance(row['name'],str) or not row['name'].strip():
            raise ValueError('Every item needs a name')
        row['amount']=float(money(row['amount']))
        if row['frequency'] not in FREQUENCIES:
            raise ValueError('Choose a valid frequency')
        row['first_payment']=date.fromisoformat(str(row['first_payment'])).isoformat()
        if category and row['category'] not in CATEGORIES:
            raise ValueError('Choose a category')
    return rows


def render_history(st,data,key,categories,state=None):
    from spending_ui import review_spending
    review_spending(st,state,data['transactions'],key)


def render_demo(st,client,household_id,household_name,account_renderer=None):
    from app_integrity import require_compatible
    require_compatible(st)
    from mobile_ui import mobile_styles
    mobile_styles(st)
    user_id=client.auth.get_user().user.id
    from model_guard import household_model_lock
    # Auth is verified before entering the model transaction. The same namespace
    # is used by inline financial callbacks, which run before the next render.
    scope=demo_state(st.session_state,user_id,household_id)[1]
    from projection_cache import projection_scope
    cache_key=scope+':projection_cache'
    if cache_key not in st.session_state:st.session_state[cache_key]={}
    with household_model_lock(scope+':page'),projection_scope(st.session_state[cache_key]):
        _render_household_model(st,user_id,household_id,household_name,account_renderer)


def _render_household_model(st,user_id,household_id,household_name,account_renderer=None):
    from planning import new_planner
    from setup_model import ROUTES,STEPS,setup_state,route
    from action_finance import collect_actions
    from notifications import decision_count
    base=f'demo:{user_id}:{household_id}'
    from test_households import controls
    controls(st,base,date.today().replace(day=1))
    data,key=demo_state(st.session_state,user_id,household_id)
    if 'planner' not in data:data['planner']=new_planner(date.fromisoformat(data['start']),data['income'],data['expenses'])
    if data.get('_fixture_version'):
        st.markdown('<div class="nw-demo-banner">DEMO MODE · Fictional · Scenario date 19 Nov 2026</div>',unsafe_allow_html=True)
    state=data['planner'];state.setdefault('tracking_date',state['draft']['start'])
    from category_catalog import sync
    sync(state,data['transactions']);state['spending']=data['transactions'];setup=setup_state(state)
    nav_key=key+':page';state['_nav_key']=nav_key
    request=st.session_state.pop(nav_key+':next',None)
    current=route(state,request or st.session_state.get(nav_key,'Home'))
    st.session_state[nav_key]=current
    if current=='Home' and (state.get('_last_route')!='Home' or state.pop('_home_next_weekly',False)):
        state['dashboard_view']='Weekly';st.session_state[key+':overview:view']='Weekly'
    previous_route=state.get('_last_route');state['_last_route']=current
    if current in ('Home','BudgetSpending','Payments') and (request or previous_route!=current) and not state.pop('_restore_context',False):
        state['_home_screen']={'Home':'Overview','BudgetSpending':'Spending','Payments':'Upcoming Payments'}[current]
        state.pop('_category_detail',None)
    actions=collect_actions(state);count=decision_count(actions)
    action_focus=state.pop('_actions_focus_view',None) if current=='Actions' else None
    if action_focus:
        state['action_list_view']=action_focus;st.session_state[key+':actions:list']=action_focus
    elif current=='Actions' and previous_route!='Actions' and count and not state.get('action_workflow'):
        state['action_list_view']='Needs attention';st.session_state[key+':actions:list']='Needs attention'
    labels={'BudgetSpending':'Spending','Payments':'Upcoming Payments','More':'More','Home':'Overview','Setup':'Build Your Budget','Spending':'Transactions','Outlook':'Adjust Forecast','Actions':('To Do · '+str(count) if count else 'To Do'),'Settings':'Settings'}
    st.sidebar.caption('YOUR HOUSEHOLD')
    page=current
    from consumer_navigation import go,request
    for destination in ROUTES:
        if destination=='More':continue
        st.sidebar.button(labels[destination],key=key+':navigation:'+destination,type='primary' if current==destination else 'secondary',width='stretch',on_click=request,args=(state,st.session_state,destination))
    with st.sidebar.expander('Demo / testing controls'):
        new_start=st.date_input('Scenario start month',value=date.fromisoformat(data['start']),key=key+':scenario_date')
        reset_ok=st.checkbox('Create a separate seeded demo household',key=key+':reset_confirm')
        if st.button('Start fresh scenario',key=key+':reset',disabled=not reset_ok or data.get('_test_only',False)):
            from demo_data import new_demo
            from test_households import create_test_household
            target=create_test_household(st.session_state,base,new_start.replace(day=1),'Seeded synthetic demo')
            st.session_state[target]=dict(new_demo(new_start.replace(day=1)),_test_only=True,test_name='Seeded synthetic demo')
            st.rerun()
        st.caption('Creates a separate fictional scenario; existing approved budgets and history remain untouched. Use Clean setup testing for an empty household.')
    from navigation_layout import navigation_layout
    active_step=setup['step'] if setup.get('step_next') else st.session_state.get(key+':setup:step',setup['step'])
    active_topic=setup.get('household_section','People') if setup.get('household_next') else st.session_state.get(key+':setup:household:section',setup.get('household_section','People'))
    navigation_layout(st,page+(':'+active_step+':'+active_topic+':'+str(state.get('expense_workflow',{}).get('nav_epoch',0))+':'+str(setup.get('journey_epoch',0)) if page=='Setup' else ''))
    if not data.get('_fixture_version'):st.caption('SYNTHETIC DEMO · Fictional · Session only')
    focus=state.pop('page_focus',None)
    if focus:
        if page=='Setup':
            setup['step']=focus['setup_step'] if focus.get('setup_step') in STEPS else STEPS[2] if focus.get('kind')=='plans' or focus.get('project_id') else STEPS[0] if focus.get('kind')=='profile' else STEPS[5];setup['step_next']=True
            if focus.get('project_id'):state['plan_focus']=focus['project_id']
        elif page=='Spending':state['spending_focus']=focus
        elif page=='Outlook':state['outlook_focus']=focus;st.session_state[key+':year:view']='Summary'
    if data.get('_test_only') and not data.get('_fixture_version'):st.caption(data['test_name']+(' · populated fictional test household' if data.get('_fixture_version') else ' · empty-start fictional test household')+' · session only')
    from consumer_navigation import header,more
    notification_view=header(st,state,key,actions)
    from quick_actions import shortcut,render as render_quick_expense
    quick=bool(state.get('_quick_expense') and state['_quick_expense']['page']==page and not state['_quick_expense'].get('suspended'))
    if state['versions'] and page=='Spending' and not quick:quick=shortcut(st,state,key,page)
    if notification_view:pass
    elif quick:
        render_quick_expense(st,state,key)
    elif page in ('Home','BudgetSpending','Payments'):
        from home_dashboard import render_home
        render_home(st,state,key+':overview')
    elif page=='Spending':
        from nestworth_pages import transactions
        transactions(st,state,key+':transactions')
    elif page=='Actions':
        from actions_ui import render_actions
        render_actions(st,state,key+':actions')
    elif page=='Outlook':
        from outlook_workflows import outlook
        outlook(st,state,key+':year')
    elif page=='More':more(st,state,key)
    elif page=='Setup':
        from setup_ui import render_setup
        render_setup(st,state,key+':setup')
    else:
        st.subheader('Settings')
        st.write(household_name)
        st.caption('Switch households and sign out in the household menu. Financial drafts remain isolated to each authenticated household session.')
        from household_calendar import AUSTRALIAN_TIMEZONES,household_timezone
        state['profile']['timezone']=st.selectbox('Household timezone',AUSTRALIAN_TIMEZONES,index=AUSTRALIAN_TIMEZONES.index(household_timezone(state)),key=key+':settings_zone')
        from nestworth_pages import simulator
        simulator(st,state,key+':simulator')
        if account_renderer:account_renderer()
    # The same real Streamlit buttons provide accessible bottom navigation on
    # phones; CSS hides this second representation on desktop. No iframe/router
    # workaround or persistent financial store is involved.
    with st.container(key='daily_nav'):
        cols=st.columns(4)
        for col,(target,icon) in zip(cols,[('Home',':material/home:'),('BudgetSpending',':material/bar_chart:'),('Payments',':material/calendar_month:'),('More',':material/menu:')]):
            col.button(labels[target],icon=icon,key=key+':daily:'+target,type='primary' if page==target else 'secondary',width='stretch',on_click=request,args=(state,st.session_state,target))
