"""Presentation navigation only; financial drafts live independently of routes."""
def request(state,session,page,screen=None):
    from model_guard import household_model_lock
    with household_model_lock(state['_nav_key']):
        if state.get('_quick_expense'):state['_quick_expense']['suspended']=True
        if page in ('Home','BudgetSpending','Payments'):
            state['_spending_landing']=True;state['_mix_epoch']=state.get('_mix_epoch',0)+1
            state.pop('_payment_detail',None);state.pop('_category_detail',None);state['_analysis_chart_epoch']=state.get('_analysis_chart_epoch',0)+1
            state['_home_screen']=screen or {'Home':'Overview','BudgetSpending':'Spending','Payments':'Upcoming Payments'}[page]
        if page=='Spending':
            for key in list(state):
                if key.endswith(':focused'):state.pop(key,None)
        state['_notifications_open']=False
        session[state['_nav_key']+':next']=page

def go(st,state,page,screen=None):
    request(state,st.session_state,page,screen);st.rerun()

def detail_request(state,screen):
    from model_guard import household_model_lock
    with household_model_lock(state['_nav_key']):
        state['_detail_parent']=state.get('_home_screen','Overview');state['_home_screen']=screen

def open_detail(st,state,screen):
    detail_request(state,screen);st.rerun()

def toggle_notifications(state):
    from model_guard import household_model_lock
    with household_model_lock(state['_nav_key']):state['_notifications_open']=not state.get('_notifications_open')

def header(st,state,key,actions):
    from notifications import decision_count
    count=decision_count(actions)
    with st.container(key='nw_notification_toolbar'):
        a,b=st.columns([7,1])
        a.caption('YOUR HOUSEHOLD · '+{'Home':'Overview','BudgetSpending':'Spending','Payments':'Upcoming payments','Spending':'Transactions','Outlook':'Adjust forecast','Actions':'To do','Setup':'Budget setup','More':'More','Settings':'Settings'}.get(state.get('_last_route'),'Nestworth'))
        badge=str(count) if count else ''
        st.html('<style>[class*="st-key-nw_notification_toolbar"] button p::after{content:"'+badge+'";'+('background:#AD4941;padding:1px 5px;' if count else '')+'}</style>')
        b.button('Notifications',icon=':material/notifications:',key=key+':bell',width='stretch',on_click=toggle_notifications,args=(state,))
    if not state.get('_notifications_open'):
        if state.get('_last_route') not in ('Home','BudgetSpending','Payments','More','Setup') and not state.get('action_workflow') and not any(k.endswith(':focused') and v for k,v in state.items()):
            if st.button('Back to More',key=key+':workspace_back'):go(st,state,'More')
        return False
    st.button('Back',key=key+':notification_back',on_click=toggle_notifications,args=(state,))
    st.subheader('Notifications')
    from proactive_alerts import alerts,acknowledge
    from actions_ui import open_source,navigate
    notices=alerts(state,actions)
    if not notices:st.success('You’re all caught up.')
    for alert in notices:
        with st.container(border=True):
            st.write('**'+alert['category']+'**'+(f" · ${alert['amount']:,.2f}" if alert.get('amount') else ''))
            st.caption(alert.get('reason','A decision is needed'))
            if alert.get('period_start') and alert.get('period_end'):
                from datetime import timedelta
                st.caption(alert['period_start'].strftime('%d %b')+' – '+(alert['period_end']-timedelta(days=1)).strftime('%d %b %Y'))
            if alert.get('acknowledged'):st.caption('Seen · still unresolved')
            elif st.button('Mark seen',key=key+':seen:'+alert['id']):acknowledge(state,alert);st.rerun()
            if st.button('Review & Fix' if alert['type']=='overspend' else 'Review',key=key+':notification:'+alert['id']):
                state['_notifications_open']=False
                if alert['type']=='overspend':open_source(st,state,alert['source'],review_first=True)
                else:navigate(st,state,alert.get('page','Actions'))
    return True

def more(st,state,key):
    st.subheader('More')
    for page,label in [('Spending','Transactions'),('Outlook','Adjust Forecast'),('Actions','To Do'),('Setup','Build Your Budget'),('Settings','Settings')]:
        if st.button(label,key=key+':more:'+page,width='stretch'):go(st,state,page)


def return_to_context(st,state):
    context=state.pop('_action_return',None);state.pop('action_workflow',None)
    if context:
        state['_home_screen']=context['screen']
        if context.get('detail'):state['_category_detail']=context['detail']
        else:state.pop('_category_detail',None)
        state['_restore_context']=True;st.session_state[state['_nav_key']+':next']=context['page']
    st.rerun()
