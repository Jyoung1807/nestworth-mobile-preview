"""Page composition only. Existing household-scoped services remain authoritative."""
from datetime import date,timedelta
from nestworth_design import intro,empty


def transactions(st,state,key):
    st.subheader('Transactions')
    intro(st,'Your spending, organised','Every transaction has a place.')
    source=st.radio('Transactions source',['Current period','Historical'],horizontal=True,key=key+':source')
    historical=source=='Historical';rows=state.get('spending',[]) if historical else state.get('period_transactions',[])
    st.caption('Historical comparison records · original dates and amounts retained' if historical else 'Recorded transactions · no bank feed connected')
    if rows:
        from transaction_review import transaction_browser
        transaction_browser(st,state,rows,rows,key+':'+source,historical)
    else:empty(st,'No transactions yet','Add historical CSV records for comparison, or use the fictional simulator in Settings for local testing.')
    if historical and rows:
        if st.button('Open historical insights',key=key+':insights_open'):state[key+':insights']=True
        if state.get(key+':insights'):
            if st.button('Close historical insights',key=key+':insights_close'):state[key+':insights']=False;st.rerun()
            from spending_ui import review_spending
            review_spending(st,state,rows,key+':legacy_insights',setup_review=True)
    if st.button('Import historical CSV',key=key+':import'):
        from setup_journey import set_stage,STAGES
        set_stage(state,STAGES[5]);state['setup']['history_upload']=True;st.session_state[state['_nav_key']+':next']='Setup';st.rerun()


def simulator(st,state,key):
    from planning import result
    from accountability import tracker,simulate_period,window
    from calendar_ui import week_selector
    from household_calendar import weeks_in_horizon,week_start
    from finance import add_months
    start=date.fromisoformat(state['draft']['start']);end=add_months(start,12)
    today=date.fromisoformat(state.get('tracking_date',str(start)))
    notice=state.pop('simulation_notice',None)
    if notice:st.success(notice)
    with st.expander('Fictional simulator & calendar settings'):
        st.caption('Fictional, session-only observations. Existing budgets and historical records stay intact.')
        review=st.date_input('Scenario review date',value=today,min_value=start,max_value=end-timedelta(days=1),key=key+':review',format='DD/MM/YYYY')
        if review!=today:
            if any(review<date.fromisoformat(r['effective']) for r in state.get('contingency_uses',[])):st.warning('Reverse later reserve allocations before moving the review date earlier than them.')
            else:state['tracking_date']=str(review);state['plan_reviewed']=False;st.rerun()
        period=st.radio('Simulator period',['Weekly','Monthly'],horizontal=True,key=key+':period')
        if period=='Weekly':when=max(start,week_selector(st,'Simulation week',weeks_in_horizon(start,end),key+':week',week_start(today)))
        else:
            months=[add_months(start,n) for n in range(12)];when=st.selectbox('Simulation month',months,format_func=lambda d:d.strftime('%B %Y'),key=key+':month')
        left,right=window(start,when,period);events=result(state,accounting=False)[0]
        rows=tracker(events,state.get('period_transactions',[]),start,when,period)
        choices=sorted({r['category'] for r in rows})
        if choices:
            category=st.selectbox('Simulate category',choices,key=key+':category')
            variance=st.number_input('Simulated variance from allocation ($)',value=35.0,key=key+':variance')
            if st.button('Simulate this period',key=key+':apply',disabled=today<left):
                try:
                    state['dashboard_view']=period
                    simulate_period(state,events,min(today,right-timedelta(days=1)),period,category,variance)
                except ValueError as error:st.error(str(error))
                else:state['simulation_notice']='Fictional spending updated. Review Home or To Do.';st.rerun()
