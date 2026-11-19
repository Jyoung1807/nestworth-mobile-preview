"""Five focused Nestworth views over shared, unchanged financial services."""
from datetime import date,timedelta
from decimal import Decimal
import altair as alt
import pandas as pd
from finance import money,add_months
from planning import aggregate
from home_view_model import annual_view,category_view
from nestworth_design import intro,line,empty,chart_style,FOREST,GOLD,NEGATIVE,MUTED,PALETTE

VIEWS=('Overview','Spending Analysis','Cash Flow','Cash Position','Upcoming Payments')


def dollars(value):return 'Unknown' if value is None else f'${value:,.2f}'


def navigate(st,state,page):
    st.session_state[state['_nav_key']+':next']=page;st.rerun()


def category_chart(st,rows,key,selected=None):
    records=[]
    for row in rows:
        records.append(dict(category=row['category'],series='Budget',amount=float(row['budget'])))
        if row['actual'] is not None:records.append(dict(category=row['category'],series='Recorded',amount=float(row['actual'])))
    if not records:empty(st,'Nothing to compare yet','Category budgets appear after you build your budget.');return None
    pick=alt.selection_point(name='category_pick',fields=['category'])
    chart=alt.Chart(pd.DataFrame(records)).mark_bar(cornerRadiusEnd=4,size=10).encode(
        y=alt.Y('category:N',title=None,sort=alt.EncodingSortField(field='amount',op='sum',order='descending'),axis=alt.Axis(labelLimit=115)),
        x=alt.X('amount:Q',title=None,axis=alt.Axis(format='$~s',tickCount=4)),yOffset='series:N',
        color=alt.Color('series:N',scale=alt.Scale(domain=['Budget','Recorded'],range=['#789A85',FOREST]),legend=alt.Legend(orient='bottom',title=None),title=None),
        opacity=alt.condition(alt.datum.category==selected,alt.value(1),alt.value(.7)) if selected else alt.value(1),
        tooltip=['category:N','series:N',alt.Tooltip('amount:Q',format='$,.2f')]).add_params(pick).properties(height=max(230,len(rows)*52+80))
    event=st.altair_chart(chart_style(chart),width='stretch',key=key,on_select='rerun',selection_mode='category_pick')
    selection=event.selection.get('category_pick',[]) if event and hasattr(event,'selection') else []
    return selection[0].get('category') if selection else None


def period_selection(st,state,key):
    from calendar_ui import week_selector
    from household_calendar import weeks_in_horizon,week_start
    start=date.fromisoformat(state['draft']['start']);end=add_months(start,12)
    today=date.fromisoformat(state.get('tracking_date',str(start)))
    period=st.radio('Analysis period',['Week','Month','Year'],horizontal=True,key=key+':period')
    if period!='Year':state['dashboard_view']='Monthly' if period=='Month' else 'Weekly'
    if period=='Year':return start,end
    if period=='Week':
        selected=week_selector(st,'Analysis week',weeks_in_horizon(start,end),key+':week',week_start(today))
        return max(start,selected),min(end,selected+timedelta(days=7))
    months=[add_months(start,n) for n in range(12)]
    selected=st.selectbox('Analysis month',months,index=months.index(today.replace(day=1)) if today.replace(day=1) in months else 0,format_func=lambda d:d.strftime('%B %Y'),key=key+':month')
    n=months.index(selected)
    def move(offset):st.session_state[key+':month']=months[n+offset]
    a,b=st.columns(2);a.button('Previous month',key=key+':previous',disabled=n==0,on_click=move,args=(-1,));b.button('Next month',key=key+':next',disabled=n==11,on_click=move,args=(1,))
    return selected,add_months(selected,1)


def spending_analysis(st,state,key,events=None):
    focus=state.pop('analysis_focus',None)
    if focus:state.pop('_category_detail',None)
    detail=state.get('_category_detail')
    if detail:
        if st.button('Back to Spending Analysis',key=key+':detail_back'):
            state.pop('_category_detail',None)
            state.pop(key+':chart_click:'+detail['left']+':'+detail['right'],None)
            state['_analysis_chart_epoch']=state.get('_analysis_chart_epoch',0)+1
            st.session_state[key+':category:'+detail['left']+':'+detail['right']]=None
            st.rerun()
        left=date.fromisoformat(detail['left']);right=date.fromisoformat(detail['right'])
        st.caption(left.strftime('%a %d %b')+' – '+(right-timedelta(days=1)).strftime('%a %d %b %Y'))
        category_details(st,state,key,left,right,detail['category']);return
    if focus:
        st.session_state[key+':period']='Week';st.session_state[key+':week']=focus['week']
    left,right=period_selection(st,state,key)
    data=category_view(state,left,right);context=f'{left}:{right}';selection_key=key+':category:'+context
    selected=st.session_state.get(selection_key)
    if focus and focus.get('category'):st.session_state[selection_key]=focus['category'];selected=focus['category']
    clicked=category_chart(st,data['rows'],key+':chart:'+context+':'+str(state.get('_analysis_chart_epoch',0)),selected)
    marker=key+':chart_click:'+context
    if clicked and clicked!=state.get(marker):
        state[marker]=clicked;st.session_state[selection_key]=clicked;state['_category_detail']=dict(left=str(left),right=str(right),category=clicked);st.rerun()
    st.caption('Tap a category to explore · '+('Complete transaction coverage' if data['covered'] else 'Recorded amounts are partial; missing spending is unknown'))
    names=[r['category'] for r in data['rows']]
    if names:
        with st.popover('Choose category',key=key+':choose:'+str(selected)):
            selected=st.pills('Category',names,selection_mode='single',key=selection_key)
    if selected not in names:return
    state['_category_detail']=dict(left=str(left),right=str(right),category=selected)
    st.rerun()


def category_details(st,state,key,left,right,selected):
    data=category_view(state,left,right);context=f'{left}:{right}'
    row=next(r for r in data['rows'] if r['category']==selected)
    st.subheader(selected)
    with st.container(key='nw_hero_category'):
        a,b,c=st.columns(3);a.metric('Category budget',dollars(row['budget']));b.metric('Actual spending',dollars(row['actual']));c.metric('Remaining / overspend',dollars(row['remaining']))
    if row['forecast']!=row['budget']:line(st,'Forecast allocation',dollars(row['forecast']),'Current adjustments · not realised savings')
    components={}
    for e in data['budget']:
        if e['category']==selected:
            identity=(e.get('item_id'),e['name'],bool(e.get('allowance')));components[identity]=components.get(identity,money(0))+e['amount']
    with st.expander('What makes up this budget',expanded=True):
        for (_,name,allowance),amount in components.items():line(st,name,dollars(amount),'Flexible allowance' if allowance else 'Scheduled commitment')
    matching=[t for t in data['transactions'] if (t.get('category') or 'Uncategorised')==selected]
    transaction_key=key+':transactions:'+context
    if matching or transaction_key+':undo' in state:
        from spending_ui import inline_transactions
        st.markdown('**Transactions**');inline_transactions(st,state,state.get('period_transactions',[]),matching,transaction_key,False,page_size=8)
    else:empty(st,'No recorded transactions','This is a budget allocation, not evidence of actual spending.')


def cash_flow(st,state,key,data):
    rows=aggregate(data['events'],data['start'],'Monthly',state['draft']['opening_cash'])
    with st.container(key='nw_hero_flow'):
        a,b,c=st.columns(3);a.metric('Annual income',dollars(data['summary']['income']));b.metric('Annual expenses',dollars(data['summary']['expenses']));c.metric('Net cash flow',dollars(data['summary']['income']-data['summary']['expenses']))
    records=[dict(month_id=r['period'],month=r['period'],series=label,amount=float(r[field])) for r in rows for label,field in [('Income','income'),('Expenses','expenses'),('Net cash flow','cash_flow')]]
    selection=alt.selection_point(name='cash_month',fields=['month_id'])
    chart=alt.Chart(pd.DataFrame(records)).mark_bar(cornerRadiusTopLeft=3,cornerRadiusTopRight=3).encode(
        x=alt.X('month_id:N',title=None,sort='ascending',axis=alt.Axis(labelExpr="timeFormat(toDate(datum.label), '%b')",labelAngle=0)),
        xOffset=alt.XOffset('series:N',sort=['Income','Expenses','Net cash flow']),
        y=alt.Y('amount:Q',title=None,axis=alt.Axis(format='$~s')),
        color=alt.condition("datum.series === 'Net cash flow' && datum.amount < 0",alt.value(NEGATIVE),alt.Color('series:N',scale=alt.Scale(domain=['Income','Expenses','Net cash flow'],range=[FOREST,'#8FAE91',GOLD]),legend=alt.Legend(orient='bottom',title=None))),
        tooltip=[alt.Tooltip('month:T',format='%B %Y'),'series:N',alt.Tooltip('amount:Q',format='$,.2f')]).add_params(selection).properties(height=280)
    event=st.altair_chart(chart_style(chart),width='stretch',key=key+':monthly_chart',on_select='rerun',selection_mode='cash_month')
    picked=event.selection.get('cash_month',[]) if event and hasattr(event,'selection') else []
    if picked and picked[0].get('month_id')!=state.get(key+':month_click'):
        month=picked[0]['month_id']
        if month in [r['period'] for r in rows]:
            st.session_state[key+':month']=month;state[key+':month_click']=month
    st.caption('Tap a month to explore · net cash flow excludes contingency earmarking')
    selected=st.selectbox('Cash-flow month',[r['period'] for r in rows],format_func=lambda d:date.fromisoformat(d).strftime('%B %Y'),key=key+':month')
    row=next(r for r in rows if r['period']==selected)
    line(st,'Income',dollars(row['income']));line(st,'Expenses',dollars(row['expenses']));line(st,'Contingency transfer',dollars(row['reserve']))
    left=date.fromisoformat(selected);right=add_months(left,1)
    with st.expander('Month commitments'):
        for e in data['events']:
            if e['kind']=='expense' and left<=e['date']<right and not e.get('allowance'):line(st,e['name'],dollars(e['amount']),str(e['date']))


def cash_position(st,state,key,data):
    if not data['cash']:
        empty(st,'Your cash position is unknown','Add opening cash in Build Your Budget → Review & Approve to see a projection. No bank balance is connected.')
        if st.button('Add opening cash',key=key+':opening'):
            from setup_journey import set_stage,STAGES
            set_stage(state,STAGES[6]);state['setup']['reserve_reviewed']=False;navigate(st,state,'Setup')
        return
    with st.container(key='nw_hero_position'):
        a,b,c=st.columns(3);a.metric('Opening cash',dollars(state['draft']['opening_cash']));b.metric('Projected closing cash',dollars(data['closing']));c.metric('Lowest projected cash',dollars(data['lowest']))
    frame=pd.DataFrame([dict(month=str(data['start']),balance=float(state['draft']['opening_cash']),point='Opening cash')]+[dict(month=str(add_months(date.fromisoformat(r['period']),1)-timedelta(days=1)),balance=float(r['closing_cash']),point='Month-end forecast') for r in data['cash']])
    chart=alt.Chart(frame).mark_line(color=FOREST,strokeWidth=3,point=alt.OverlayMarkDef(size=35)).encode(x=alt.X('month:T',title=None,axis=alt.Axis(format='%b',tickCount=6)),y=alt.Y('balance:Q',title='Projected cash',scale=alt.Scale(zero=False)),tooltip=[alt.Tooltip('month:T',format='%d %b %Y'),'point:N',alt.Tooltip('balance:Q',format='$,.2f')]).properties(height=300)
    st.altair_chart(chart_style(chart),width='stretch')
    if data['lowest']<0:st.warning('Projected cash drops below zero. Review dated commitments in Adjust Forecast.')
    st.caption('Month-end scenario projection · includes earmarked contingency · not verified bank balances. Lowest cash uses the engine’s dated-payment calculation.')


def upcoming(st,state,key,data):
    today=date.fromisoformat(state.get('tracking_date',str(data['start'])))
    window=st.radio('Upcoming window',['Next 7 days','Next 30 days'],horizontal=True,key=key+':window');right=today+timedelta(days=7 if window=='Next 7 days' else 30)
    rows=sorted([e for e in data['events'] if e['kind']=='expense' and not e.get('allowance') and not e['paid'] and today<=e['date']<right],key=lambda e:(e['date'],e['name']))
    st.metric('Upcoming scheduled total',dollars(sum((e['amount'] for e in rows),money(0))))
    st.caption(today.strftime('%d %b')+' – '+(right-timedelta(days=1)).strftime('%d %b %Y')+' · includes scenario date · '+str(len(rows))+' scheduled commitments · recorded payments excluded')
    if not rows:empty(st,'Nothing scheduled in this window','Flexible spending allowances are separate from bills and scheduled payments.')
    for e in rows[:6]:line(st,e['name'],dollars(e['amount']),e['date'].strftime('%a %d %b')+' · '+e['category']+(' · estimated' if e.get('estimated') else ''))
    if len(rows)>6:
        with st.expander('All scheduled payments'):
            for e in rows[6:]:line(st,e['name'],dollars(e['amount']),str(e['date']))
    allowances=sum((e['amount'] for e in data['events'] if e['kind']=='expense' and e.get('allowance') and today<=e['date']<right),money(0))
    st.caption('Flexible allowances: '+dollars(allowances)+' · forecast spending capacity, not bills due or recorded transactions')


def render_home(st,state,key):
    st.subheader('Home')
    if not state['versions']:
        intro(st,'Your household. Your future.','A clearer picture starts here.')
        empty(st,'Let’s build your household budget','Income, everyday spending and future plans — one guided step at a time.')
        if st.button('Start or resume budget setup',type='primary',key=key+':setup'):navigate(st,state,'Setup')
        with st.expander('Preview your draft'):
            data=annual_view(state);st.metric('Annual net income',dollars(data['summary']['income']));st.metric('Projected spending',dollars(data['summary']['expenses']))
        return
    data=annual_view(state)
    requested=state.pop('home_view_next',None)
    if requested in VIEWS:st.session_state[key+':home_view']=requested
    view=st.radio('Home view',VIEWS,key=key+':home_view',horizontal=True)
    if view=='Overview':
        intro(st,data['start'].strftime('%b %Y')+' — '+(data['end']-timedelta(days=1)).strftime('%b %Y'),'Your year, at a glance.')
        compare=st.toggle('Compare to Budget',value=True,key=key+':compare')
        baseline=data['budget'];forecast=data['summary'];approved=data['approved']
        known_baseline=approved['plan']['opening_cash']>0 or approved.get('opening_cash_known',False)
        baseline_cash=aggregate(approved['events'],data['start'],'Monthly',approved['plan']['opening_cash'])[-1]['closing_cash'] if known_baseline else None
        def figure(column,label,budget,current,expense=False):
            primary=budget if compare else current
            delta=None;color='off'
            if compare:
                difference=None if budget is None or current is None else current-budget
                if difference is not None and difference!=0:
                    favourable=difference<0 if expense else difference>0
                    color='normal' if favourable else 'inverse'
                delta='Forecast '+dollars(current)+(' · no change' if difference==0 else ' · '+('+' if difference>0 else '−')+dollars(abs(difference)) if difference is not None else ' · baseline unknown')
            tone='favourable' if color=='normal' else 'unfavourable' if color=='inverse' else 'neutral'
            with column.container(key='nw_comparison_'+label.replace(' ','_')+'_'+tone):
                st.metric(label,dollars(primary),delta=delta,delta_color=color,border=False)
        with st.container(key='nw_hero_annual'):
            a,b,c,d=st.columns(4)
            figure(a,'Annual net income',baseline['income'],forecast['income'])
            figure(b,'Annual spending budget' if compare else 'Forecast spending',baseline['expenses'],forecast['expenses'],True)
            figure(c,'Unallocated annual savings',baseline['savings'],forecast['savings'])
            figure(d,'Closing cash',baseline_cash,data['closing'])
        st.caption('Approved budget is primary' if compare else 'Latest forecast · approved budget preserved')
        with st.popover('Budget & forecast details',key=key+':annual_details'):
            from planning import approved_savings
            from contingency_ledger import reserve_balance
            from action_finance import collect_actions,recovery_totals
            line(st,'Approved annual savings',dollars(approved_savings(state)))
            line(st,'Forecast annual savings',dollars(data['summary']['savings']))
            line(st,'Change from approval',dollars(data['summary']['savings']-approved_savings(state)))
            reserve=reserve_balance(state)
            for label,field in [('Reserve accrued','accumulated'),('Reserve committed','committed'),('Reserve available now','available')]:line(st,label,dollars(reserve[field]))
            recovery=recovery_totals(collect_actions(state));line(st,'Pending recovery',dollars(recovery['pending']));line(st,'Verified recovery',dollars(recovery['verified']))
            st.caption('Pending recovery is a forecast commitment, not realised savings.')
            if data['approved'].get('stretch_goal') is not None:line(st,'Separate stretch goal',dollars(data['approved']['stretch_goal']))
        from household_calendar import week_start,week_label
        today=date.fromisoformat(state.get('tracking_date',str(data['start'])))
        from calendar_ui import week_selector
        from household_calendar import weeks_in_horizon
        st.subheader('This week')
        week=week_selector(st,'Overview week',weeks_in_horizon(data['start'],data['end']),key+':week',week_start(today))
        context=category_view(state,max(data['start'],week),min(data['end'],week+timedelta(days=7)))
        budget=sum((r['budget'] for r in context['rows']),money(0));recorded=sum((money(t['amount']) for t in context['transactions']),money(0)) if context['covered'] or context['transactions'] else None
        remaining=budget-recorded if context['covered'] else None
        with st.container(key='nw_hero_week'):
            a,b,c=st.columns(3);a.metric('Weekly spending budget',dollars(budget));b.metric('Actual spending to date',dollars(recorded));c.metric('Remaining / overspend',dollars(remaining))
        if recorded is not None:st.progress(min(1.0,max(0.0,float(recorded/budget))) if budget else (1.0 if recorded>0 else 0.0))
        else:st.caption('No transaction coverage yet · actual spending and remaining budget are unknown')
        if remaining is not None and remaining<0:st.warning('This week is '+dollars(-remaining)+' over budget. Review To Do for recovery choices.')
        clicked=category_chart(st,context['rows'],key+':week-chart')
        if clicked and state.get('overview_click')!=(str(week),clicked):
            state['overview_click']=(str(week),clicked);state['analysis_focus']=dict(week=week,category=clicked);state['home_view_next']='Spending Analysis';st.rerun()
        a,b,c=st.columns(3)
        if a.button("View this week's spending",key=key+':explore'):state.pop('_category_detail',None);state['analysis_focus']=dict(week=week,category=None);state['home_view_next']='Spending Analysis';st.rerun()
        if b.button('Review transactions',key=key+':transactions'):navigate(st,state,'Spending')
        from notifications import decision_count
        from action_finance import collect_actions
        count=decision_count(collect_actions(state))
        if c.button('To Do'+(' · '+str(count) if count else ''),key=key+':todo'):navigate(st,state,'Actions')
        st.subheader('Where your money goes')
        spending={}
        for event in data['events']:
            if event['kind']=='expense':spending[event['category']]=spending.get(event['category'],money(0))+event['amount']
        ranked=sorted(spending.items(),key=lambda pair:pair[1],reverse=True)
        if ranked:
            records=[dict(category=name,amount=float(value)) for name,value in ranked[:4]]
            if len(ranked)>4:records.append(dict(category='Other categories',amount=float(sum((v for _,v in ranked[4:]),money(0)))))
            mix=alt.Chart(pd.DataFrame(records)).mark_bar(cornerRadiusEnd=5,size=18).encode(
                y=alt.Y('category:N',sort='-x',title=None,axis=alt.Axis(labelFontSize=13,labelLimit=130)),
                x=alt.X('amount:Q',title=None,axis=alt.Axis(format='$~s',tickCount=3)),
                color=alt.Color('category:N',scale=alt.Scale(range=PALETTE),legend=None),
                tooltip=['category:N',alt.Tooltip('amount:Q',format='$,.2f')]).properties(height=220)
            st.altair_chart(chart_style(mix),width='stretch')
            st.caption('Latest forecast spending · '+dollars(data['summary']['expenses']))
        if data['cash']:
            st.subheader('Your cash outlook')
            line(st,'Projected closing cash',dollars(data['closing']),'Lowest projected '+dollars(data['lowest']))
            curve=pd.DataFrame([dict(date=str(data['start']),cash=float(state['draft']['opening_cash']))]+[dict(date=str(add_months(date.fromisoformat(r['period']),1)-timedelta(days=1)),cash=float(r['closing_cash'])) for r in data['cash']])
            trajectory=alt.Chart(curve).mark_line(color=FOREST,strokeWidth=3).encode(x=alt.X('date:T',title=None,axis=alt.Axis(format='%b',tickCount=4)),y=alt.Y('cash:Q',title=None,axis=alt.Axis(format='$~s',tickCount=3)),tooltip=[alt.Tooltip('date:T',format='%d %b %Y'),alt.Tooltip('cash:Q',format='$,.2f')]).properties(height=160)
            st.altair_chart(chart_style(trajectory),width='stretch')
            st.caption('Household forecast · not a verified bank balance')
        else:empty(st,'Cash outlook needs opening cash','Your income and spending forecast remains available.')
        st.subheader('Coming up')
        upcoming_left=date.fromisoformat(state.get('tracking_date',str(data['start'])))
        upcoming_right=upcoming_left+timedelta(days=7)
        due=sorted([e for e in data['events'] if e['kind']=='expense' and not e.get('allowance') and not e['paid'] and upcoming_left<=e['date']<upcoming_right],key=lambda e:(e['date'],e['name']))
        st.caption(upcoming_left.strftime('%d %b')+' – '+(upcoming_right-timedelta(days=1)).strftime('%d %b %Y')+' · includes scenario date')
        for event in due[:3]:line(st,event['name'],dollars(event['amount']),event['date'].strftime('%a %d %b'))
        if not due:st.caption('No unpaid scheduled payments in this scenario window.')
        if st.button('Manage upcoming payments',key=key+':upcoming_link'):
            state['home_view_next']='Upcoming Payments';st.rerun()
    elif view=='Spending Analysis':spending_analysis(st,state,key+':analysis')
    elif view=='Cash Flow':cash_flow(st,state,key+':cash',data)
    elif view=='Cash Position':cash_position(st,state,key+':position',data)
    else:upcoming(st,state,key+':upcoming',data)
