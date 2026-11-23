"""Daily spending views are compact; charts and yearly decisions live in Outlook."""
from budget_period import BudgetPeriod,period_end,month_starts
from datetime import date,timedelta
from decimal import Decimal
from html import escape
from finance import money,add_months
from planning import result,summarize,aggregate,approved_savings
from accountability import tracker,window,simulate_period,recovery_source
from household_calendar import week_start,week_label,weeks_in_horizon,household_timezone,AUSTRALIAN_TIMEZONES
from calendar_ui import week_selector
from action_finance import collect_actions,recovery_status,approval_observed_impact
from dashboard_charts import savings_chart,cash_flow_chart


def dollars(n):return f'${n:,.2f}'


def financial_outlook(st,state,key):
    start=date.fromisoformat(state['draft']['start']);events,_=result(state);summary=summarize(events,start,end=period_end(state))
    approved=state['versions'][-1] if state['versions'] else None
    baseline=approved_savings(state) if approved else money(state['draft']['goal'])
    a,b,c=st.columns(3)
    a.metric('Approved annual savings baseline' if approved else 'Savings goal · draft',dollars(baseline))
    b.metric('Forecast year-end savings',dollars(summary['savings']),help='An up-to-date projection, not verified savings in a bank account.')
    c.metric('Above / below approved baseline' if approved else 'Above / below draft goal',dollars(summary['savings']-baseline))
    if approved and approved.get('stretch_goal') is not None:st.caption('Optional stretch goal: '+dollars(approved['stretch_goal'])+' · separate from the baseline.')
    impact=approval_observed_impact(approved) if approved else Decimal(0)
    if impact:
        st.info('The approved baseline already includes '+dollars(impact)+' of observed spending impact. Future recovery changes the forecast relative to that baseline; the overspend is not deducted a second time.')
    included=approved.get('approval_context',{}).get('recovery_forecast_reduction',0) if approved else 0
    if included:st.caption('Recorded recovery reductions already included at approval: '+dollars(included)+'. Reversals change the latest forecast, not the locked baseline.')
    actions=collect_actions(state)
    from notifications import financial_alerts
    financial_alerts(st,state,key+':alerts',actions)
    from contingency_ledger import reserve_balance
    reserve=reserve_balance(state)
    with st.expander('Contingency reserve'):
        for label,field in [('Approved period target','annual_target'),('Model accrued','accumulated'),('Committed','committed'),('Available now','available')]:st.write(label+' · '+dollars(reserve[field]))
        if 'forecast_target' in reserve:st.write('Forecast period target · '+dollars(reserve['forecast_target']))
        if reserve.get('unfunded_accrual'):st.caption('Unfunded accrued target · '+dollars(reserve['unfunded_accrual'])+' · unavailable for recovery')
        if reserve['shortfall']:st.warning('Matched income evidence no longer supports '+dollars(reserve['shortfall'])+' of earlier reserve funding. Review or reverse that funding in Actions.')
        st.caption('Fictional scheduled receipts are assumed received on their date unless matched actuals override them. Future contributions are unavailable. Funding history appears in Outlook History.')
    commitments=[a for a in actions if a['type'] in ('commitment','plan_commitment')]
    from action_finance import recovery_totals
    totals=recovery_totals(actions);pending=totals['pending'];realised=totals['verified']
    st.write(('Pending recovery **'+dollars(pending)+'** · verified recovery **'+dollars(realised)+'**').replace('$',r'\$'))
    st.caption('Pending reductions are forecast assumptions, not earned Extra Savings. No bank feed or actual savings line is connected.')
    savings_chart(st,events,approved['events'] if approved else None,start,baseline,budget_label=f"Approved budget v{approved['number']}" if approved else 'Original budget',height=260,end=period_end(state))
    with st.expander('Cash flow and available cash',expanded=bool(state.pop('outlook_focus',None))):
        grouping=st.radio('Outlook cash-flow period',['Monthly','Weekly'],horizontal=True,key=key+':cashperiod')
        rows=aggregate(events,start,grouping,state['draft']['opening_cash'],end=period_end(state))
        cash_flow_chart(st,rows);cash_flow_chart(st,rows,cumulative=True)
        if any(r['lowest_cash']<0 for r in rows):st.warning('Projected available cash cannot cover a dated payment. Review Cash Flow on Home.')
    with st.expander('Approved history'):
        for v in state['versions']:st.caption(f"Version {v['number']} · {dollars(v['summary']['savings'])} · locked")


def render_dashboard(st,state,key):
    views=['Weekly','Monthly','Financial Outlook']
    view=st.radio('Dashboard view',views,index=views.index(state.get('dashboard_view','Weekly')),horizontal=True,key=key+':view',label_visibility='collapsed')
    state['dashboard_view']=view
    if view=='Financial Outlook':financial_outlook(st,state,key+':outlook');return
    start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    today=date.fromisoformat(state.get('tracking_date',str(start)));state.setdefault('tracking_date',str(today))
    if view=='Weekly':
        selected=week_selector(st,'Spending week',weeks_in_horizon(start,end),key+':week',week_start(today));when=max(start,selected)
    else:
        months=month_starts(state)
        month=st.selectbox('Spending month',months,index=months.index(today.replace(day=1)),format_func=lambda d:d.strftime('%B %Y'),key=key+':month')
        index=months.index(month)
        def move(offset):st.session_state[key+':month']=months[index+offset]
        with st.container(key='period_nav_month'):
            left,right=st.columns(2)
            left.button('Previous month',on_click=move,args=(-1,),disabled=index==0,key=key+':prevmonth',width='stretch')
            right.button('Next month',on_click=move,args=(1,),disabled=index==11,key=key+':nextmonth',width='stretch')
        when=month
    from weekly_view import spending_view
    events=result(state,accounting=False)[0]
    original=st.session_state.get(key+':original',False)
    attention=st.session_state.get(key+':attention',False)
    benchmark=state['versions'][0]['events'] if original and state['versions'] else events
    # Older approval snapshots may hold undivided allowances; use the same daily
    # splitter as result(), which is idempotent for already-dated events.
    from accountability import dated_allocations
    data=spending_view(state,dated_allocations(benchmark),when,view)
    left,right=data['left'],data['right']
    st.markdown('### '+('Weekly budget' if view=='Weekly' else 'Monthly budget'))
    with st.container(key='weekly_summary'):
        a,b,c=st.columns(3)
        a.metric('Budget',dollars(data['budget']),help='Allowances allocated to this week plus bills due in it. Monthly and annual totals use these same dated events.')
        b.metric('Recorded',dollars(data['recorded']) if data['recorded'] is not None else 'Unknown',help='Recorded fictional spending is evidence. A budget allocation is not a transaction.')
        c.metric('Remaining',dollars(data['remaining']) if data['remaining'] is not None else 'Unknown',help='Incomplete statement coverage leaves remaining capacity unknown, rather than assuming missing spending was zero.')
    st.caption('Complete fictional coverage' if data['covered'] else 'Incomplete coverage · remaining spending capacity is not yet known.')
    if original:st.caption('Original approved comparison · decisions use the latest forecast.')
    actions=collect_actions(state);need=sum(a['status']=='Needs decision' for a in actions)
    if not state['versions']:st.caption('Approve your budget in Setup before committing recovery decisions.')
    with st.popover('About spending allowances ℹ'):
        st.caption('Consistent weekly: annual budget ÷ 52 in full weeks, with partial-year adjustments. Calendar-day: actual monthly days form each week. A bill stays on its due date. Unknown spending is never zero.')
    st.subheader('Flexible spending')
    if not data['allowances']:st.caption('No flexible allowances this period. In Build Your Budget, choose Flexible spending allowance for day-to-day spending such as Groceries.')
    for row in data['allowances']:
        category=row['category'];spent=row['spent'];remaining=row['remaining']
        if attention and remaining is not None and remaining>=0:continue
        ratio=spent/row['allocation'] if spent is not None and row['allocation'] else Decimal(1) if spent else Decimal(0)
        color='#aab5c1' if spent is None else '#ba4235' if remaining<0 else '#b77a16' if ratio>=Decimal('.8') else '#258568'
        status='Unknown' if spent is None else 'Overspent' if remaining<0 else 'Approaching budget' if ratio>=Decimal('.8') else 'Within budget'
        fraction=100 if spent is None else min(100,float(ratio*100))
        amount_text=(dollars(spent) if spent is not None else 'Unknown')+' / '+dollars(row['allocation'])
        st.markdown('<div class="category-strip"><div class="category-line"><strong>'+escape(category)+'</strong><span>'+escape(amount_text)+'</span></div><div class="spending-progress" role="progressbar" aria-label="'+escape(category,quote=True)+' spending" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+str(round(fraction))+'"><div style="width:'+str(fraction)+'%;background:'+color+'"></div></div><div class="category-balance">'+escape('Remaining unknown' if remaining is None else dollars(-remaining)+' over budget' if remaining<0 else dollars(remaining)+' remaining')+' · '+status+'</div></div>',unsafe_allow_html=True)
        st.caption(row['coverage'])
        category_details(st,state,key,category,data,actions,view,original)
    if st.button(f'Actions · {need} need a decision',key=key+':actions',width='stretch'):
        from actions_ui import navigate
        navigate(st,state,'Actions Centre')
    st.subheader('Scheduled payments')
    with st.popover('About payment dates ℹ'):
        st.caption('Approximate dates are estimates for cash flow. Confirm dates before relying on within-week liquidity.')
    upcoming=sum((e['amount'] for e in data['bills'] if not e['paid']),Decimal(0))
    paid=sum((e['amount'] for e in data['bills'] if e['paid']),Decimal(0))
    st.caption((dollars(upcoming)+' scheduled · '+dollars(paid)+' recorded payments').replace('$',r'\$'))
    if not data['bills']:st.caption('No scheduled payments in this period.')
    from home_dashboard import payment_list
    payment_list(st,data['bills'],key+':scheduled',today)
    for category in sorted({e['category'] for e in data['bills']}):
        if category not in {r['category'] for r in data['allowances']}:category_details(st,state,key,category,data,actions,view,original)
    represented={r['category'] for r in data['allowances']}|{e['category'] for e in data['bills']}
    extra=sorted({t['category'] for t in data['transactions']}-represented)
    if extra:st.subheader('Other recorded spending')
    for category in extra:
        recorded=sum((money(t['amount']) for t in data['transactions'] if t['category']==category),Decimal(0))
        st.write('**'+category+' · '+dollars(recorded)+'**')
        st.caption('No allocation in this period.')
        category_details(st,state,key,category,data,actions,view,original)
    rows=tracker(events,state.get('period_transactions',[]),start,when,view,data['covered'],as_of=today,end=period_end(state))
    with st.expander('View options'):
        st.checkbox('Compare original approved budget',key=key+':original')
        st.checkbox('Only categories needing attention',key=key+':attention')
        st.caption('Household calendar: '+household_timezone(state))
    with st.expander('Fictional simulator & calendar settings'):
        st.caption('Fictional transactions only. No connected bank data. Simulations retain nonoverlapping earlier coverage.')
        review=st.date_input('Scenario review date',value=today,min_value=start,max_value=end-timedelta(days=1),key=key+':reviewdate',format='DD/MM/YYYY')
        zone=household_timezone(state)
        state['profile']['timezone']=st.selectbox('Household timezone',AUSTRALIAN_TIMEZONES,index=AUSTRALIAN_TIMEZONES.index(zone),key=key+':zone')
        if review!=today:
            if any(review<date.fromisoformat(r['effective']) for r in state.get('contingency_uses',[])):st.warning('Reverse later reserve allocations before moving the review date earlier than them.')
            else:state['tracking_date']=str(review);state['plan_reviewed']=False;st.rerun()
        choices=sorted({r['category'] for r in rows})
        if choices:
            category=st.selectbox('Simulate category',choices,key=key+':simcat')
            difference=st.number_input('Simulated variance from allocation ($)',value=35.0,key=key+':simamount')
            if st.button('Simulate this period',disabled=today<left,key=key+':simulate'):
                try:simulate_period(state,events,min(today,right-timedelta(days=1)),view,category,difference)
                except ValueError as error:st.error(str(error))
                else:st.rerun()


def payment_line(st,payment,today):
    status='Recorded payment' if payment['paid'] else 'Upcoming' if payment['date']>today else 'Due · not recorded'
    st.write(payment['name']+' · **'+dollars(payment['amount'])+'**')
    st.caption(payment['date'].strftime('%a %d %b %Y')+' · '+status+(' · estimated date' if payment.get('estimated') else ''))


def category_details(st,state,key,category,data,actions,view,original):
    relevant=[a for a in actions if a['type'] in ('overspend','commitment','plan_commitment') and (a.get('category')==category or a.get('record',{}).get('category')==category)]
    action=next((a for a in relevant if a['type']=='overspend' and a['status']=='Needs decision'),None)
    if action and not original and st.button('Review '+category+' action',key=key+':action:'+category,width='stretch'):
        from actions_ui import open_source
        open_source(st,state,action['source'],'Week' if view=='Weekly' else 'Month')
    selected=state.get('dashboard_category')==category
    if st.button(('Close ' if selected else 'Open ')+category+' details',key=key+':details:'+category,width='stretch'):
        state['dashboard_category']=None if selected else category;st.rerun()
    if not selected:return
    with st.container(border=True):
        st.write('**'+category+' · transactions and actions**')
        transactions=[t for t in data['transactions'] if t['category']==category]
        if transactions:
            from spending_ui import inline_transactions
            inline_transactions(st,state,state['period_transactions'],transactions,key+':selected:'+category,allow_baseline=False)
        else:st.caption('No recorded transactions in this period. Missing coverage is not zero spending.')
        for action in relevant:st.caption(action['status']+' · '+dollars(action['amount']))
        if not relevant:st.caption('No spending recovery decision for this category.')
        for payment in data['bills']:
            if payment['category']==category:payment_line(st,payment,date.fromisoformat(state['tracking_date']))
