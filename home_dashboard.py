"""Five focused Nestworth views over shared, unchanged financial services."""
from budget_period import BudgetPeriod,period_end,month_starts
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
        budget=float(row['budget']);actual=None if row['actual'] is None else float(row['actual'])
        records.append(dict(category=row['category'],series='Budget',part='Budget',amount=budget,total=budget))
        if actual is not None:
            pending=row['category']=='Uncategorised'
            records.append(dict(category=row['category'],series='Recorded',part='Needs review' if pending else 'Recorded',amount=actual if pending else min(actual,budget),total=actual))
            if not pending and actual>budget:records.append(dict(category=row['category'],series='Recorded',part='Overspend',amount=actual-budget,total=actual))
    if not records:empty(st,'Nothing to compare yet','Category budgets appear after you build your budget.');return None
    pick=alt.selection_point(name='category_pick',fields=['category'])
    chart=alt.Chart(pd.DataFrame(records)).mark_bar(cornerRadiusEnd=4,size=14).encode(
        y=alt.Y('category:N',title=None,sort=alt.EncodingSortField(field='total',op='max',order='descending'),axis=alt.Axis(labelLimit=115)),
        x=alt.X('amount:Q',title=None,stack='zero',axis=alt.Axis(format='$~s',tickCount=4)),yOffset=alt.YOffset('series:N',sort=['Budget','Recorded']),
        color=alt.Color('part:N',scale=alt.Scale(domain=['Budget','Recorded','Overspend','Needs review'],range=['#789A85',FOREST,NEGATIVE,GOLD]),legend=alt.Legend(orient='bottom',title=None,columns=2),title=None),
        order=alt.Order('part:N',sort='descending'),
        tooltip=['category:N','series:N','part:N',alt.Tooltip('amount:Q',title='This segment',format='$,.2f'),alt.Tooltip('total:Q',title='Total',format='$,.2f')]).add_params(pick).properties(height=max(260,len(rows)*48+70))
    event=st.altair_chart(chart_style(chart),width='stretch',key=key,on_select='rerun',selection_mode='category_pick')
    selection=event.selection.get('category_pick',[]) if event and hasattr(event,'selection') else []
    return selection[0].get('category') if selection else None


def period_selection(st,state,key):
    from calendar_ui import week_selector
    from household_calendar import weeks_in_horizon,week_start
    start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    today=date.fromisoformat(state.get('tracking_date',str(start)))
    saved=state.setdefault('spending_filters',{})
    if key+':period' not in st.session_state and saved.get('period'):st.session_state[key+':period']=saved['period']
    period=st.radio('Analysis period',['Week','Month','Budget period' if state['draft'].get('end_exclusive') else 'Year'],horizontal=True,key=key+':period')
    saved['period']=period
    if period!='Year':state['dashboard_view']='Monthly' if period=='Month' else 'Weekly'
    if period in ('Year','Budget period'):return start,end
    if period=='Week':
        selected=week_selector(st,'Analysis week',weeks_in_horizon(start,end),key+':week',date.fromisoformat(saved['week']) if saved.get('week') else week_start(today));saved['week']=str(selected)
        return max(start,selected),min(end,selected+timedelta(days=7))
    months=month_starts(state)
    if key+':month' not in st.session_state and saved.get('month') and date.fromisoformat(saved['month']) in months:st.session_state[key+':month']=date.fromisoformat(saved['month'])
    selected=st.selectbox('Analysis month',months,index=months.index(today.replace(day=1)) if today.replace(day=1) in months else 0,format_func=lambda d:d.strftime('%B %Y'),key=key+':month')
    saved['month']=str(selected)
    n=months.index(selected)
    def move(offset):st.session_state[key+':month']=months[n+offset]
    a,b=st.columns(2);a.button('Previous month',key=key+':previous',disabled=n==0,on_click=move,args=(-1,));b.button('Next month',key=key+':next',disabled=n==len(months)-1,on_click=move,args=(1,))
    return max(start,selected),min(end,add_months(selected,1))


def spending_analysis(st,state,key,events=None):
    focus=state.pop('analysis_focus',None)
    if focus:state.pop('_category_detail',None)
    detail=state.get('_category_detail')
    if detail:
        if st.button('Back to Overview' if detail.get('parent')=='Overview' else 'Back to Spending',key=key+':detail_back'):
            if detail.get('parent')=='Overview':state['_home_screen']='Overview';state['_mix_epoch']=state.get('_mix_epoch',0)+1
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
    budget=sum((r['budget'] for r in data['rows']),money(0));actual=sum((money(t['amount']) for t in data['transactions']),money(0)) if data['covered'] or data['transactions'] else None
    with st.container(key='nw_hero_week'):
        a,b,c=st.columns(3);a.metric('Spending budget',dollars(budget));b.metric('Actual spending',dollars(actual));c.metric('Remaining / overspend',dollars(budget-actual if data['covered'] and actual is not None else None))
    from proactive_alerts import period_for
    from action_finance import collect_actions
    for issue in collect_actions(state):
        first,last=period_for(state,issue)
        if issue['type']=='overspend' and issue['status']=='Needs decision' and first and first<right and last>left:
            a,b=st.columns([3,1]);a.warning(issue['category']+' · '+dollars(issue['remaining'])+' over')
            if b.button('Review & Fix '+issue['category'],key=key+':fix:'+issue['id']):
                from actions_ui import open_source
                open_source(st,state,issue['source'],review_first=True)
    if st.button('Resume expense' if state.get('_quick_expense') else '+ Add Expense',key=key+':add_expense'):
        state['_quick_expense']={'page':state['_last_route']};st.rerun()
    if state.pop('_spending_landing',False):st.session_state[selection_key]=None
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
    row=next((r for r in data['rows'] if r['category']==selected),None)
    if row is None:st.info('There are no remaining records in this category for this period.');return
    st.subheader(selected)
    from action_finance import collect_actions
    from proactive_alerts import period_for
    def overlaps(action):
        first,last=period_for(state,action)
        return first is not None and first<right and last>left
    relevant=next((a for a in collect_actions(state) if a['type']=='overspend' and a['category']==selected and a['status']=='Needs decision' and overlaps(a)),None)
    if relevant:
        st.warning(dollars(relevant['remaining'])+' needs a recovery decision')
        if st.button('Review & resolve '+selected,type='primary',key=key+':resolve:'+context):
            from actions_ui import open_source
            open_source(st,state,relevant['source'],review_first=True)
    with st.container(key='nw_hero_category'):
        a,b,c=st.columns(3);a.metric('Category budget',dollars(row['budget']));b.metric('Actual spending',dollars(row['actual']));c.metric('Remaining / overspend',dollars(row['remaining']))
    if row['forecast']!=row['budget']:line(st,'Forecast allocation',dollars(row['forecast']),'Current adjustments · not realised savings')
    components={}
    for e in data['budget']:
        if e['category']==selected:
            identity=(e.get('item_id'),e['name'],bool(e.get('allowance')));components[identity]=components.get(identity,money(0))+e['amount']
    with st.expander('What makes up this budget',expanded=True):
        for (_,name,allowance),amount in components.items():line(st,name,dollars(amount),'Flexible allowance' if allowance else 'Scheduled commitment')
    trend_key=key+':trend:'+context+':'+selected
    if st.button('Hide trend' if state.get(trend_key) else 'View trend',key=trend_key+':toggle'):
        state[trend_key]=not state.get(trend_key);st.rerun()
    if state.get(trend_key):
        days=sorted({e['date'] for e in data['budget'] if e['category']==selected}|{date.fromisoformat(t['date']) for t in data['transactions'] if (t.get('category') or 'Uncategorised')==selected})
        budget_running=money(0);actual_running=money(0);records=[];today=date.fromisoformat(state['tracking_date'])
        for day in days:
            budget_running+=sum((e['amount'] for e in data['budget'] if e['category']==selected and e['date']==day),money(0))
            observed=[t for t in data['transactions'] if (t.get('category') or 'Uncategorised')==selected and date.fromisoformat(t['date'])==day]
            actual_running+=sum((money(t['amount']) for t in observed),money(0));records.append(dict(day=str(day),series='Budget',amount=float(budget_running)))
            if day<=today and (data['covered'] or observed):records.append(dict(day=str(day),series='Recorded',amount=float(actual_running)))
        if records:
            chart=alt.Chart(pd.DataFrame(records)).mark_line(point=True).encode(x=alt.X('day:T',title=None,axis=alt.Axis(format='%d %b',tickCount=4)),y=alt.Y('amount:Q',title=None,axis=alt.Axis(format='$~s')),color=alt.Color('series:N',scale=alt.Scale(domain=['Budget','Recorded'],range=['#789A85',FOREST]),legend=alt.Legend(orient='bottom',title=None)),tooltip=[alt.Tooltip('day:T',format='%d %b %Y'),'series:N',alt.Tooltip('amount:Q',format='$,.2f')]).properties(height=180)
            st.altair_chart(chart_style(chart),width='stretch');st.caption('Cumulative within this period · '+('covered transactions to date' if data['covered'] else 'partial records only'))
    matching=[t for t in data['transactions'] if (t.get('category') or 'Uncategorised')==selected]
    transaction_key=key+':transactions:'+context
    if matching or transaction_key+':undo' in state:
        from spending_ui import inline_transactions
        st.markdown('**Transactions**');inline_transactions(st,state,state.get('period_transactions',[]),matching,transaction_key,False,page_size=8)
    else:empty(st,'No recorded transactions','This is a budget allocation, not evidence of actual spending.')


def cash_flow(st,state,key,data):
    rows=aggregate(data['events'],data['start'],'Monthly',state['draft']['opening_cash'],end=period_end(state))
    with st.container(key='nw_hero_flow'):
        a,b,c=st.columns(3);a.metric('Budget-period income' if state['draft'].get('end_exclusive') else 'Annual income',dollars(data['summary']['income']));b.metric('Budget-period expenses' if state['draft'].get('end_exclusive') else 'Annual expenses',dollars(data['summary']['expenses']));c.metric('Net cash flow',dollars(data['summary']['income']-data['summary']['expenses']))
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
    line(st,'Income',dollars(row['income']));line(st,'Expenses',dollars(row['expenses']));line(st,'Contingency earmark',dollars(row['reserve']))
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
    frame=pd.DataFrame([dict(month=str(data['start']),balance=float(state['draft']['opening_cash']),point='Opening cash')]+[dict(month=str(min(data['end']-timedelta(days=1),add_months(date.fromisoformat(r['period']),1)-timedelta(days=1))),balance=float(r['closing_cash']),point='Month-end forecast') for r in data['cash']])
    chart=alt.Chart(frame).mark_line(color=FOREST,strokeWidth=3,point=alt.OverlayMarkDef(size=35)).encode(x=alt.X('month:T',title=None,axis=alt.Axis(format='%b',tickCount=6)),y=alt.Y('balance:Q',title='Projected cash',scale=alt.Scale(zero=False)),tooltip=[alt.Tooltip('month:T',format='%d %b %Y'),'point:N',alt.Tooltip('balance:Q',format='$,.2f')]).properties(height=300)
    st.altair_chart(chart_style(chart),width='stretch')
    if data['lowest']<0:st.warning('Projected cash drops below zero. Review dated commitments in Adjust Forecast.')
    st.caption('Month-end scenario projection · includes earmarked contingency · not verified bank balances. Lowest cash uses the engine’s dated-payment calculation.')


def upcoming(st,state,key,data):
    today=date.fromisoformat(state.get('tracking_date',str(data['start'])))
    window=st.radio('Upcoming window',['Next 7 days','Next 30 days'],index=1 if state.get('_payment_window')=='Next 30 days' else 0,horizontal=True,key=key+':window');state['_payment_window']=window;right=min(data['end'],today+timedelta(days=7 if window=='Next 7 days' else 30))
    rows=sorted([e for e in data['events'] if e['kind']=='expense' and not e.get('allowance') and not e['paid'] and today<=e['date']<right],key=lambda e:(e['date'],e['name']))
    st.metric('Upcoming scheduled total',dollars(sum((e['amount'] for e in rows),money(0))))
    st.caption(today.strftime('%d %b')+' – '+(right-timedelta(days=1)).strftime('%d %b %Y')+' · includes scenario date · '+str(len(rows))+' scheduled commitments · recorded payments excluded')
    if not rows:empty(st,'Nothing scheduled in this window','Flexible spending allowances are separate from bills and scheduled payments.')
    focused=state.get('_payment_detail')
    if focused:
        event=next((e for e in data['events'] if e['id']==focused),None)
        if st.button('Back to payments',key=key+':payment_back'):state.pop('_payment_detail',None);st.rerun()
        if event:
            st.subheader(event['name']);line(st,event['date'].strftime('%a %d %b'),dollars(event['amount']),event['category'])
            from payment_rescheduling_ui import render as reschedule_payments
            reschedule_payments(st,state,key+':reschedule',data['events'],selected_id=focused)
        else:st.info('This payment is outside the current window. Return to the schedule.')
        return
    def payment_button(e):
        if st.button(e['date'].strftime('%a %d %b')+' · '+e['name']+' · '+dollars(e['amount']),key=key+':payment:'+e['id'],width='stretch'):
            state['_payment_detail']=e['id'];st.rerun()
    for e in rows[:6]:payment_button(e)
    if len(rows)>6:
        with st.expander('All scheduled payments'):
            for e in rows[6:]:payment_button(e)
    if state.get('payment_reschedules'):
        with st.expander('Changed payment dates'):
            for command in state['payment_reschedules']:
                move=command['moves'][0]
                if st.button(command['name']+' · '+move['old_date']+' → '+move['new_date'],key=key+':changed:'+command['id']):
                    state['_payment_detail']=move['event_id'];st.rerun()
    allowances=sum((e['amount'] for e in data['events'] if e['kind']=='expense' and e.get('allowance') and today<=e['date']<right),money(0))
    st.caption('Flexible allowances: '+dollars(allowances)+' · forecast spending capacity, not bills due or recorded transactions')


def render_home(st,state,key):
    from consumer_navigation import open_detail,go,detail_request
    if not state['versions']:
        st.subheader('Your household. Your future.')
        if st.button('Start or resume budget setup',type='primary',key=key+':setup'):go(st,state,'Setup')
        return
    requested=state.pop('home_view_next',None)
    if requested:state['_home_screen']='Spending' if requested=='Spending Analysis' else requested
    screen=state.get('_home_screen','Overview')
    if screen=='Spending':
        st.subheader('Spending');spending_analysis(st,state,key+':analysis');return
    data=annual_view(state)
    if screen=='Upcoming Payments':
        st.subheader('Upcoming Payments');upcoming(st,state,key+':upcoming',data);return
    if screen!='Overview':
        st.button('Back to Overview',key=key+':back_overview',on_click=detail_request,args=(state,'Overview'))
        st.subheader(screen)
        if screen=='Cash Flow':cash_flow(st,state,key+':cash',data)
        elif screen=='Cash Position':cash_position(st,state,key+':position',data)
        else:savings_details(st,state,key,data)
        return
    st.subheader('Overview')
    from proactive_alerts import alerts
    conditions=alerts(state)
    urgent=next((a for a in conditions if a['type']=='overspend' or a.get('severity')=='critical'),None)
    if urgent:
        with st.container(key='nw_attention_strip'):
            a,b=st.columns([3,1])
        a.warning(urgent['category']+' · '+dollars(urgent['amount'])+(' over budget' if urgent['type']=='overspend' else ' needs attention'))
        if b.button('Review & Fix',key=key+':urgent',type='primary'):
            from actions_ui import open_source
            if urgent['type']=='overspend':open_source(st,state,urgent['source'],review_first=True)
            else:open_detail(st,state,'Cash Position')
    st.caption(data['start'].strftime('%d %b %Y')+' – '+(data['end']-timedelta(days=1)).strftime('%d %b %Y'))
    compare=st.toggle('Compare to Budget',value=st.session_state.get(key+':compare_preference',True),key=key+':compare');st.session_state[key+':compare_preference']=compare
    from savings_projection import project
    baseline=data['budget'];forecast=data['summary'];approved=data['approved']
    known=approved.get('opening_cash_known',approved['plan']['opening_cash']>0)
    baseline_cash=aggregate(approved['events'],data['start'],'Monthly',approved['plan']['opening_cash'],end=period_end(approved['plan']))[-1]['closing_cash'] if known else None
    current=project(state['draft'],forecast,data['closing']);budget=project(approved['plan'],baseline,baseline_cash)
    primary=budget if compare else current
    with st.container(key='nw_hero_annual'):
        a,b,c,d=st.columns(4)
        for col,label,old,new in [(a,'Projected total savings',budget['total'],current['total']),(b,'Spending',baseline['expenses'],forecast['expenses']),(c,'Net income',baseline['income'],forecast['income']),(d,'Closing cash',baseline_cash,data['closing'])]:
            with col.container(border=True,key='nw_balance_card_'+label.replace(' ','_')):
                st.metric(label,dollars(old if compare else new))
                if compare:
                    difference=None if old is None or new is None else new-old
                    tone='neutral' if difference is None or difference==0 else 'good' if (difference<0 if label=='Spending' else difference>0) else 'adverse'
                    variance='' if difference is None else 'No change' if difference==0 else ('+' if difference>0 else '−')+dollars(abs(difference))
                    st.html('<div class="nw-forecast '+tone+'"><span>Forecast '+dollars(new)+'</span><small>'+variance+'</small></div>')
                if label=='Projected total savings':
                    st.caption(('+' if primary['additional']>=0 else '−')+dollars(abs(primary['additional']))+' this period')
                    if primary['opening'] is None:st.caption('Opening savings not provided')
    st.caption('Budget with forecast comparison' if compare else 'Latest forecast · approved budget preserved')
    target=current.get('target')
    if target:
        with st.container(border=True):
            line(st,'Your target',dollars(target['amount']),{'total_savings':'Total savings at period end','additional_savings':'Additional savings this period','closing_cash':'Closing cash at period end'}[target['kind']])
            if target['projected'] is not None:
                st.progress(float(max(0,min(1,target['projected']/target['amount']))) if target['amount'] else 0)
                st.caption('Projected '+dollars(target['projected'])+' · '+dollars(abs(target['variance']))+(' above target' if target['variance']>=0 else ' shortfall'))
            else:st.caption('Identify the opening balance to see your projection')
    st.button('Savings & budget details',key=key+':savings_details',on_click=detail_request,args=(state,'Savings & Budget'))
    left,right=st.columns(2)
    with left:
        st.markdown('#### Where your money goes')
        spending={}
        for e in data['events']:
            if e['kind']=='expense':spending[e['category']]=spending.get(e['category'],money(0))+e['amount']
        if spending:
            total=sum(spending.values(),money(0))
            records=[dict(category=n,amount=float(v),share=float(v/total)) for n,v in spending.items() if v>0]
            pick=alt.selection_point(name='mix_category',fields=['category'])
            chart=alt.Chart(pd.DataFrame(records)).mark_arc(innerRadius=65,outerRadius=105).encode(theta='amount:Q',color=alt.Color('category:N',scale=alt.Scale(range=PALETTE),legend=alt.Legend(orient='bottom',columns=2,title=None,labelLimit=130)),tooltip=['category:N',alt.Tooltip('amount:Q',format='$,.2f'),alt.Tooltip('share:Q',format='.1%',title='Share of spending')]).add_params(pick).properties(height=230)
            ev=st.altair_chart(chart_style(chart),width='stretch',key=key+':mix:'+str(state.get('_mix_epoch',0)),on_select='rerun',selection_mode='mix_category')
            chosen=ev.selection.get('mix_category',[]) if ev and hasattr(ev,'selection') else []
            if chosen:
                category=chosen[0]['category']
                state['_home_screen']='Spending';state['_category_detail']=dict(category=category,left=str(data['start']),right=str(data['end']),parent='Overview');st.rerun()
    with right:
        st.markdown('#### Cash outlook')
        if data['cash']:
            line(st,'Projected closing cash',dollars(data['closing']),'Lowest '+dollars(data['lowest']))
            rows=[dict(month=str(data['start']),cash=float(state['draft']['opening_cash']))]+[dict(month=str(min(data['end']-timedelta(days=1),add_months(date.fromisoformat(r['period']),1)-timedelta(days=1))),cash=float(r['closing_cash'])) for r in data['cash']]
            curve=alt.Chart(pd.DataFrame(rows)).mark_area(color=FOREST,opacity=.2,line=alt.OverlayMarkDef(color=FOREST)).encode(x=alt.X('month:T',title=None,axis=alt.Axis(format='%b',tickCount=4)),y=alt.Y('cash:Q',title=None,axis=alt.Axis(format='$~s',tickCount=3)),tooltip=[alt.Tooltip('cash:Q',format='$,.2f')]).properties(height=120)
            st.altair_chart(chart_style(curve),width='stretch')
            st.caption('Projected · not a verified bank balance')
        else:st.caption('Add opening cash to see its projected path')
        a,b=st.columns(2)
        a.button('Cash position',key=key+':cash_detail',on_click=detail_request,args=(state,'Cash Position'))
        b.button('Cash flow',key=key+':flow_detail',on_click=detail_request,args=(state,'Cash Flow'))
        line(st,'Contingency reserved',dollars(current['reserve']),'Unallocated savings '+dollars(current['unallocated']))
    st.markdown('#### Coming up')
    today=date.fromisoformat(state['tracking_date'])
    due=sorted([e for e in data['events'] if e['kind']=='expense' and not e.get('allowance') and not e['paid'] and today<=e['date']<today+timedelta(days=7)],key=lambda e:(e['date'],e['name']))
    for e in due[:3]:line(st,e['name'],dollars(e['amount']),e['date'].strftime('%a %d %b'))
    if not due:st.caption('No scheduled payments in the next seven days')
    if st.button('All upcoming payments',key=key+':payments'):go(st,state,'Payments')


def savings_details(st,state,key,data):
    from savings_projection import project
    from contingency_ledger import reserve_balance
    p=project(state['draft'],data['summary'],data['closing'])
    for label,field in [('Opening savings','opening'),('Additional savings this period','additional'),('Projected total savings','total'),('Contingency reserved','reserve'),('Unallocated projected savings','unallocated')]:line(st,label,dollars(p[field]))
    balance=reserve_balance(state)
    with st.expander('Available contingency and recovery'):
        line(st,'Available to use now',dollars(balance['available']))
        line(st,'Already committed',dollars(balance['committed']))
        st.caption('Future savings and recovery promises are not money available today.')
    if st.button('Adjust contingency',key=key+':contingency'):
        state['forecast_action_next']='Change contingency';navigate(st,state,'Outlook')
    with st.expander('Approved budget comparison'):
        for name,value in data['budget'].items():line(st,name.title(),dollars(value))
