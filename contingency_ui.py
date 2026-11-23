"""Shared setup/forecast policy controls over one validated reserve projection."""
from copy import deepcopy
from datetime import date,timedelta
from finance import money,add_months
from contingency_policy import default_policy,validate,preview_change,save_change,FREQUENCIES,eligible
from budget_period import period_end


def current_policy(state):
    return deepcopy(state.get('reserve_changes',[])[-1]['policy'] if state.get('reserve_changes') else state['draft'].get('contingency_policy'))


def label(state):
    p=current_policy(state)
    if not p:return 'Legacy surplus policy · '+str(state['draft']['contingency_pct'])+'%'
    return str(p['percentage'])+'% of normal recurring spending' if p['method']=='percentage' else '$'+f"{money(p['amount']):,.2f}"+' · '+p['frequency']


def inputs(st,state,key,field=None,forecast=False):
    p=current_policy(state)
    def f(kind,title,name,default,**kw):
        if field:return field(kind,title,'reserve_'+name,default,**kw)
        if kind in ('radio','selectbox'):
            options=kw.pop('options');return getattr(st,kind)(title,options,index=options.index(default),key=key+':'+name,**kw)
        return getattr(st,kind)(title,value=default,key=key+':'+name,**kw)
    choices=['Percentage of normal spending','Fixed amount']
    legacy=bool(state['versions'] and p is None and not forecast)
    if legacy:choices=['Keep existing approved surplus policy',*choices]
    selected=f('radio','Contingency method','method',choices[0] if p is None or p['method']=='percentage' else 'Fixed amount',options=choices)
    if selected=='Keep existing approved surplus policy':
        percent=f('number_input','Contingency reserve (%)','legacy_percent',int(state['draft']['contingency_pct']),min_value=0,max_value=100)
        st.caption('Your existing policy stays unchanged. Select another method to change the forecast prospectively.')
        return None,percent
    first=max(date.fromisoformat(state['draft']['start']),add_months(date.fromisoformat(state['tracking_date']).replace(day=1),1)) if forecast or state['versions'] else date.fromisoformat(state['draft']['start'])
    if selected==choices[-1]:
        amount=f('number_input','Fixed contingency amount ($)','amount',float(p.get('amount',0)) if p else 0.0,min_value=0.0,step=10.0)
        frequency=f('selectbox','Contribution frequency','frequency',p.get('frequency','Weekly') if p else 'Weekly',options=list(FREQUENCIES))
        anchor=date.fromisoformat(str(p.get('first_contribution',first))) if p else first
        anchor=f('date_input','First contribution date','first',anchor,format='DD/MM/YYYY')
        policy=dict(version=2,method='fixed',amount=money(amount),frequency=frequency,first_contribution=str(anchor))
        st.caption('The first date anchors the schedule; only dates inside your budget/effective period count. Earlier anchors do not rewrite history. A 12-month period can contain 53 weekly dates; 52 weeks contains 52.')
    else:
        percent=f('number_input','Contingency reserve (%)','percentage',float(p.get('percentage',10)) if p else float(state['draft'].get('contingency_pct',10)),min_value=0.0,max_value=100.0,step=1.0)
        policy=dict(version=2,method='percentage',percentage=percent)
        st.caption('Based on dated ordinary recurring bills and flexible allowances. Excludes one-offs, projects, holidays, renovations, major purchases, transfers, savings contributions and contingency.')
        with st.expander('Review eligible household spending'):
            for item in state['draft']['expenses']:
                st.caption(item['name']+' · '+item['frequency']+' · '+('Included' if eligible(item) else 'Excluded'))
            st.caption('Spending purpose can be changed in the expense editor. Standalone plans are always excluded.')
    st.caption('Earmarked savings, not an expense or extra cash outflow. Availability still accrues progressively, capped by dated income and net resources after planned outgoings; future fixed contributions are unavailable before their scheduled date.')
    policy=validate(policy)
    if not forecast:
        from planning import scheduled_events,summarize
        if state['versions']:
            try:
                _,_,details=preview_change(state,policy)
                st.metric('Calculated forecast contingency', '$'+f"{details['after']['contingency']:,.2f}")
                st.caption('Changes take effect '+str(details['effective'])+'; accrued history stays unchanged.')
            except ValueError as error:st.caption(str(error))
        else:
            plan=deepcopy(state['draft']);plan['contingency_policy']=policy
            events=scheduled_events(plan);totals=summarize(events,date.fromisoformat(plan['start']),period_end(plan))
            if policy['method']=='percentage':st.caption('Eligible normal spending · $'+f"{sum((e.get('eligible_spending',0) for e in events if e['kind']=='reserve'),money(0)):,.2f}")
            st.metric('Calculated contingency for this budget','$'+f"{totals['contingency']:,.2f}")
            if policy['method']=='fixed':st.caption(str(sum(len(e.get('contributions',[])) for e in events if e['kind']=='reserve'))+' scheduled contributions inside the selected dates')
            if totals['contingency']>totals['income']-totals['expenses']:st.warning('Reserve target exceeds additional period savings. Earmarking does not make cash available.')
    return policy,None


def forecast(st,state,key):
    from planning import result,summarize
    from savings_projection import project
    st.subheader('Forecast contingency')
    st.caption('Latest forecast policy · '+label(state))
    today=date.fromisoformat(state['tracking_date']);effective=add_months(today.replace(day=1),1)
    if effective>=period_end(state):st.info('No future month remains. Accrued and committed contingency stay protected.');return
    policy,_=inputs(st,state,key,forecast=True)
    try:
        candidate,command,impact=preview_change(state,policy)
        before=project(state['draft'],impact['before']);after=project(state['draft'],impact['after'])
        def dollars(v):return 'Unknown' if v is None else '$'+f'{v:,.2f}'
        if policy['method']=='percentage':st.caption('Eligible normal spending from effective date · $'+f"{sum((e.get('eligible_spending',0) for e in command['snapshot_events'] if e['kind']=='reserve' and e['date']>=impact['effective']),money(0)):,.2f}")
        if policy['method']=='fixed':st.caption(str(sum(len(e.get('contributions',[])) for e in command['snapshot_events'] if e['kind']=='reserve' and e['date']>=impact['effective']))+' scheduled contributions from the effective date')
        st.caption('Effective '+str(impact['effective'])+' · current and earlier earned tranches unchanged')
        for title,old,new in [('Projected total savings',before['total'],after['total']),('Contingency allocation',before['reserve'],after['reserve']),('Unallocated total savings',before['unallocated'],after['unallocated'])]:
            st.write(title+': **'+dollars(old)+' → '+dollars(new)+'**')
        st.write('Unallocated additional savings: **'+dollars(impact['after']['savings'])+'**')
        st.write('Additional savings this period: **'+dollars(after['additional'])+'** · cash position unchanged by earmarking')
        if after['reserve']>after['additional']:st.warning('The reserve allocation exceeds additional savings generated this period. This is an earmark target, not proof of available funds.')
        st.caption('Approved budgets, historical actuals and existing reserve commitments stay intact.')
        if st.button('Confirm contingency change',type='primary',key=key+':confirm'):
            save_change(state,policy);state['outlook_notice']='Contingency forecast updated prospectively. Approved budget and cash flows are unchanged.';st.rerun()
    except ValueError as error:st.warning(str(error))
