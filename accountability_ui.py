"""Touch-friendly fictional weekly accountability and guided dated revisions."""
from budget_period import BudgetPeriod,period_end,month_starts
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal
from finance import money,add_months
from planning import result,summarize,uid
from category_catalog import color_for,category_id
from calendar_ui import week_selector
from household_calendar import (week_start,week_label,weeks_in_horizon,household_timezone,AUSTRALIAN_TIMEZONES)
from accountability import window,tracker,save_revision,commit_recovery,recovery_status,simulate_period,recovery_eligibility,recovery_source


def dollars(n):return f'${n:,.2f}'


def category_icon(name):
    return {'Groceries':'🛒','Leisure':'☕','Mortgage / Rent':'🏠','Home & Property':'🔧','Vehicles':'🚗','Utilities':'💡','Health':'💚','Children':'🧒','Pets':'🐾','Alcohol':'🍷'}.get(name,'•')


def tracker_ui(st,state,key):
    start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    st.subheader('This week & month')
    st.caption('Fictional transactions only · latest revised forecast is the default benchmark. No bank connection or Extra Savings balance.')
    period=st.radio('Tracker period',['Weekly','Monthly'],horizontal=True,key=key+':period')
    review_date=date.fromisoformat(state.get('tracking_date',str(start)))
    zone=household_timezone(state)
    if period=='Weekly':
        with st.expander('Household calendar & review date'):
            zone=st.selectbox('Household timezone',AUSTRALIAN_TIMEZONES,index=AUSTRALIAN_TIMEZONES.index(zone),key=key+':timezone')
            state['profile']['timezone']=zone
            review_date=st.date_input('Scenario review date',value=review_date,min_value=start,max_value=end-timedelta(days=1),key=key+':scenario_date',format='DD/MM/YYYY')
        selected_week=week_selector(st,'Spending week',weeks_in_horizon(start,end),key+':week',week_start(review_date))
        when=max(start,selected_week)
        st.caption(week_label(selected_week)+' · '+zone+' · Monday 00:00 through Sunday 23:59:59. Navigation changes the view, not the scenario review date.')
    else:
        review_date=st.date_input('Review date',value=review_date,min_value=start,max_value=end-timedelta(days=1),key=key+':date',format='DD/MM/YYYY')
        when=review_date
    if state.get('tracking_date')!=str(review_date):
        state['tracking_date']=str(review_date);st.rerun()
    original=st.checkbox('Compare with original approved budget',key=key+':original')
    events=result(state,accounting=False)[0]
    benchmark=state['versions'][0]['events'] if original and state['versions'] else events
    left,right=window(start,when,period,end=period_end(state))
    covered=any(date.fromisoformat(c['start'])<=max(start,left) and date.fromisoformat(c['end'])>=min(end,right) for c in state.get('coverage',[]))
    with st.expander('Fictional transaction simulator'):
        st.caption('Creates synthetic transactions and explicit period coverage, retaining earlier nonoverlapping simulations. Never use real records here.')
        categories=sorted({e['category'] for e in events if e['kind']=='expense' and left<=e['date']<right})
        if categories:
            category=st.selectbox('Simulate category',categories,key=key+':simcat')
            excess=st.number_input('Simulated variance from allocation ($)',min_value=-100000.0,value=35.0,key=key+':excess')
            simulation_day=min(review_date,right-timedelta(days=1))
            future=review_date<left
            if future:st.info('This week is in the future. Advance the scenario review date before simulating observed spending.')
            if st.button('Simulate this period',key=key+':simulate',disabled=future):
                try:simulate_period(state,events,simulation_day,period,category,excess)
                except ValueError as error:st.error(str(error))
                else:st.rerun()
    rows=tracker(benchmark,state.get('period_transactions',[]),start,when,period,covered,as_of=review_date,end=period_end(state))
    attention=st.checkbox('Only categories needing attention',key=key+':attention')
    for row in rows:
        if attention and row['status'] in ('On track','Period completed with underspending','No statement coverage'):continue
        category=row['category']
        with st.container(border=True):
            st.badge(category_icon(category)+' '+category,color='primary')
            st.markdown('<div style="height:3px;background:'+color_for(category)+';border-radius:3px"></div>',unsafe_allow_html=True)
            st.caption(('Original approved' if original else 'Latest forecast')+' · '+dollars(row['allocation']))
            if row['spent'] is None:st.caption('Actual spending: no fictional coverage for this period')
            else:
                st.write(('Fictional spent **'+dollars(row['spent'])+'** · '+('overspend ' if row['remaining']<0 else 'remaining ')+dollars(abs(row['remaining']))).replace('$',r'\$'))
                st.progress(min(1.0,float(row['spent']/row['allocation'])) if row['allocation'] else 1.0 if row['spent'] else 0.0,text=row['status'])
                if row['remaining']<0 and not original:
                    with st.expander('Respond to overspend · '+category):
                        source,excess=recovery_source(state,category,left,right)
                        state.setdefault('recovery_sources',{})[source]=excess
                        st.caption('The observed excess is already included once in projected annual spending. Accepting it does not add it again.')
                        if excess<=0:st.info('The full covered forecast still covers this spending. There is no additional annual cost to recover from this observation.')
                        elif not state['versions']:st.info('Approve a budget before saving recovery decisions.')
                        else:recovery_editor(st,state,key+':recover:'+category,source,review_date,right)
    commitments=state.get('recoveries',[])
    if commitments:
        with st.expander('Recovery commitments · Actions Centre',expanded=True):
            baseline=deepcopy(state);baseline['recoveries']=[]
            base=result(baseline,accounting=False)[0]
            for r in commitments:
                status=recovery_status(state,r,base)
                period_left=date.fromisoformat(r.get('period_start',r['effective']));period_right=date.fromisoformat(r.get('period_end',r['end']))
                period_name=week_label(period_left) if (period_right-period_left).days==7 and period_left.weekday()==0 else str(period_left)+' – '+str(period_right-timedelta(days=1))
                st.write(f"**{r['category']} · {period_name}** · {dollars(r['amount'])}")
                if date.fromisoformat(r['effective'])>review_date and st.button('Reverse pending commitment',key=key+':reverse:'+str(commitments.index(r))):
                    state['recoveries'].remove(r)
                    state.setdefault('forecast_history',[]).append(dict(type='Reversed commitment',decision=deepcopy(r)))
                    st.rerun()
                st.caption((f"Source: {r['source']} · {status['status']} · recovered {dollars(status['recovered'])} · unresolved {dollars(status['remaining'])}").replace('$',r'\$'))
    st.caption('Promised reductions affect the forecast, not confirmed savings. Completion requires explicit destination-period coverage. Extra Savings is unavailable until a ledger exists.')


def recovery_editor(st,state,key,source,when,boundary):
    choice=st.selectbox('Recovery choice',['Accept reduced savings','Offset another category','Offset a future week or month','Partially offset'],key=key+':choice')
    st.button('Extra Savings · coming later',disabled=True,key=key+':extra')
    if choice=='Accept reduced savings':
        if st.button('Acknowledge savings reduction',key=key+':accept'):
            state.setdefault('accepted_overspends',{})[source]=state['recovery_sources'][source]
            st.success('Acknowledged. The forecast includes this excess once.')
        return
    events=result(state,accounting=False)[0];start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    grouping=st.radio('Recovery period',['Weekly','Monthly'],horizontal=True,key=key+':group')
    future_only=choice=='Offset a future week or month'
    categories=sorted({e['category'] for e in events if e['kind']=='expense'})
    if choice=='Offset another category':categories=[c for c in categories if category_id(c)!=category_id(source.rsplit(':',1)[-1])]
    if grouping=='Weekly':
        periods=[w for w in weeks_in_horizon(start,end) if w+timedelta(days=7)>when+timedelta(days=1) and (not future_only or w>when)]
    else:
        periods=[d for d in month_starts(state) if add_months(d,1)>when+timedelta(days=1) and (not future_only or d>when)]
    if not periods:st.info('No eligible current or future periods remain in this budget year. Accept the savings reduction instead.');return
    def boundary_for(left):return left+timedelta(days=7) if grouping=='Weekly' else add_months(left,1)
    initial=next((p for p in periods if any(recovery_eligibility(state,events,c,p,boundary_for(p))['amount']>0 for c in categories)),periods[0])
    if grouping=='Weekly':
        left=week_selector(st,'Recovery week',periods,key+':week',initial)
        st.caption(week_label(left)+' · '+household_timezone(state))
    else:
        left=st.selectbox('Recovery month',periods,index=periods.index(initial),format_func=lambda d:d.strftime('%B %Y'),key=key+':month')
    right=boundary_for(left)
    eligible={c:recovery_eligibility(state,events,c,left,right) for c in categories}
    choices=[c for c in categories if eligible[c]['amount']>0]
    with st.expander('Eligible spending by category',expanded=not bool(choices)):
        for c in categories:
            st.caption(c+' · '+dollars(eligible[c]['amount'])+' eligible')
            if eligible[c]['amount']==0:st.caption(eligible[c]['reason'])
    if not choices:
        st.selectbox('Recovery category',['No eligible categories in this period'],disabled=True,key=key+':empty:'+grouping)
        st.info('No eligible future spending is available in this period. Scheduled bills remain on their payment dates; monthly bills are not divided into imaginary weekly payments. Choose another week or month, or accept reduced savings.')
        next_dates=sorted({v['next_date'] for v in eligible.values() if v['next_date'] and v['next_date']>=right})
        if next_dates:st.caption('Next unpaid scheduled spending: '+next_dates[0].strftime('%d %b %Y')+' · '+week_label(next_dates[0]))
        st.button('Confirm recovery commitment',disabled=True,key=key+':save')
        return
    category=st.selectbox('Recovery category',choices,format_func=lambda c:c+' · '+dollars(eligible[c]['amount'])+' eligible',key=key+':cat:'+grouping+':'+str(left))
    available=eligible[category]['amount']
    st.metric('Eligible recovery spending',dollars(available))
    used=sum((money(r['amount']) for r in state.get('recoveries',[]) if r['source']==source),Decimal(0))
    unresolved=max(Decimal(0),money(state['recovery_sources'][source])-used)
    maximum=min(available,unresolved)
    amount_key=key+':amount:'+category+':'+grouping+':'+str(left)+':'+str(maximum)
    amount=st.number_input('Amount to recover ($)',min_value=0.0,max_value=float(maximum) if maximum else None,value=float(maximum),disabled=maximum<=0,key=amount_key)
    st.caption('Only unpaid spending after '+when.strftime('%d %b %Y')+' is eligible. '+dollars(unresolved-money(amount))+' of this overspend remains unoffset. This is a forecast commitment, not realised savings.')
    st.caption('Effective allocation window: '+str(eligible[category]['effective'])+' to '+str(eligible[category]['end'])+' (end excluded). Historical transactions and approved budgets stay unchanged.')
    if st.button('Confirm recovery commitment',key=key+':save',disabled=maximum<=0 or amount<=0):
        try:commit_recovery(state,source,category,left,right,amount)
        except ValueError as error:st.error(str(error))
        else:st.rerun()


def revision_editor(st,state,key):
    # Store server-synchronised forecast draft inputs outside widget lifecycle cleanup.
    drafts=state.setdefault('revision_ui_drafts',{})
    for widget_key,value in drafts.get(key,{}).items():
        if widget_key not in st.session_state:st.session_state[widget_key]=value
    st.subheader('Revise your forecast')
    flow=st.selectbox('What changed?',['Regular expense changed','Income changed','Category allocation changed','Planned expense changed'],key=key+':flow')
    kind='income' if flow=='Income changed' else 'expense'
    category_mode=flow=='Category allocation changed'
    collection='income' if kind=='income' else 'projects' if flow=='Planned expense changed' else 'expenses'
    targets={c:c for c in state['categories']} if category_mode else {e['id']:e['name'] for e in state['draft'][collection]}
    if not targets:st.info('Add an entry in Build Your Budget first.');return
    target=st.selectbox('Choose what to revise',list(targets),format_func=targets.get,key=key+':target:'+flow)
    percentage=category_mode or st.checkbox('Change by a percentage',key=key+':pct:'+flow)
    old=next((e for e in state['draft'][collection] if e['id']==target),{}) if not category_mode else {}
    if collection=='projects' and not percentage:
        percentage=True;st.caption('Planned payment amounts are revised by percentage. Existing dated instalments retain their schedule.')
    value=st.number_input('Change (%)' if percentage else 'New amount per payment ($)',min_value=-100.0 if percentage else 0.0,value=0.0 if percentage else float(old.get('amount',0)),key=key+':value:'+flow+':'+target+':'+str(percentage))
    start=date.fromisoformat(state['draft']['start']);end=period_end(state)
    effective=st.date_input('Effective from',value=date.fromisoformat(state.get('tracking_date',str(start))),min_value=start,max_value=end-timedelta(days=1),key=key+':effective')
    note=st.text_input('Reason for revision',key=key+':reason')
    revision=dict(scope='category' if category_mode else 'item',target=target,kind=kind,mode='percentage' if percentage else 'amount',value=value,old_amount=old.get('amount',0),effective=str(effective),reason=note,label=targets[target])
    # Project events use the project ID as item_id.
    candidate=deepcopy(state)
    try:
        before=summarize(result(state)[0],start,end=period_end(state))
        save_revision(candidate,revision)
        after=summarize(result(candidate)[0],start,end=period_end(state))
        change=before['savings']-after['savings']
        st.write(('Annual spending change: **'+dollars(after['expenses']-before['expenses'])+'** · savings impact: **'+dollars(-change)+'**').replace('$',r'\$'))
        st.caption('Earlier dated events, historical transactions and approved versions remain unchanged. No category is silently reduced.')
        offset_choice=st.radio('Offset this revision',['No offset','Full offset','Partial offset'],horizontal=True,key=key+':offset')
        if change>0 and offset_choice!='No offset':
            category=st.selectbox('Offset category',state['categories'],key=key+':offsetcat')
            amount=st.number_input('Revision offset ($)',min_value=0.0,value=float(change),max_value=float(change),key=key+':offsetamount')
            if offset_choice=='Full offset' and money(amount)!=change:raise ValueError('Full offset must cover the complete savings impact')
            source='revision:'+str(len(state.get('revisions',[])))
            candidate.setdefault('recovery_sources',{})[source]=change
            commit_recovery(candidate,source,category,max(effective,date.fromisoformat(state.get('tracking_date',str(start))))+timedelta(days=1),end,amount)
            st.caption('Savings after proposed offset: '+dollars(summarize(result(candidate)[0],start,end=period_end(state))['savings']))
        if st.button('Confirm forecast revision',key=key+':save',disabled=not note.strip()):
            state.update(candidate);st.rerun()
    except ValueError as error:st.warning(str(error))
    drafts[key]={k:deepcopy(st.session_state[k]) for k in st.session_state if k.startswith(key+':') and not k.endswith(':save')}
    with st.expander('Forecast revision & recovery history'):
        for record in reversed(state.get('forecast_history',[])):
            d=record['decision']
            names={e['id']:e['name'] for collection in ('income','expenses','projects') for e in state['draft'][collection]}
            label=d.get('category') or d.get('label') or names.get(d.get('target'),d.get('target','Budget') if d.get('scope')=='category' else 'Removed entry')
            st.write(record['type']+' · '+label)
            amount=(str(d['value'])+'%' if d.get('mode')=='percentage' else dollars(money(d.get('value',d.get('amount',0)))))
            st.caption('Effective '+d['effective']+(' to '+d['end'] if d.get('end') else '')+' · '+amount)
            if d.get('reason'):st.caption(d['reason'])
