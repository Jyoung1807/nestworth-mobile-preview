"""Dedicated Actions Centre and a three-step, resumable resolution workflow."""
from budget_period import BudgetPeriod,period_end,month_starts
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
from finance import money,add_months
from household_calendar import weeks_in_horizon,week_label
from calendar_ui import week_selector
from planning import result,summarize
from action_finance import (collect_actions,remaining_source,source_used,pending,record_id,
    remove_pending,accept_impact,distribution_preview,available_events,record_category_recovery,
    plan_preview,save_plan_recovery,recovery_decision_preview,plan_category_conflict)


def dollars(n):return f'${n:,.2f}'


def navigate(st,state,page,focus=None):
    if focus:state['page_focus']=focus
    st.session_state[state['_nav_key']+':next']=page;st.rerun()


def open_source(st,state,source,grouping=None,review_first=False):
    if state.get('_last_route')!='Actions':state['_action_return']=dict(page=state.get('_last_route','Home'),screen=state.get('_home_screen','Overview'),detail=deepcopy(state.get('_category_detail')))
    existing=state.get('action_workflow')
    if not existing or existing['source']!=source:
        action=next((a for a in collect_actions(state) if a.get('source')==source and a['type']=='overspend'),{})
        state['action_workflow']=dict(source=source,label=action.get('category',source.rsplit(':',1)[-1]),step=1,response='Offset another spending category',grouping=grouping or ('Month' if state.get('dashboard_view')=='Monthly' else 'Week'))
    if review_first:state['action_workflow'].update(review_stage=True,had_review=True)
    navigate(st,state,'Actions Centre')


def render_actions(st,state,key):
    actions=collect_actions(state)
    message=state.pop('action_notice',None)
    if message:st.success(message)
    workflow=state.get('action_workflow')
    if workflow and workflow.get('review_stage'):
        render_source_review(st,state,key+':review',workflow);return
    if workflow:
        from recovery_editor import render_editor
        render_editor(st,state,key+':flow',workflow)
        return
    st.subheader('To Do')
    from notifications import decision_count
    need=decision_count(actions)
    waiting=sum(a['type'] in ('commitment','plan_commitment','reserve_commitment') and a['status'] in ('Recovery committed','Awaiting verification') for a in actions)
    st.caption(f'{need} need a decision · {waiting} commitments waiting · pending commitments are not realised savings.')
    choices=['Needs attention','Commitments','Setup reminders','All actions']
    view=st.radio('Action list',choices,index=choices.index(state.get('action_list_view',choices[0])),horizontal=True,key=key+':list')
    state['action_list_view']=view
    shown=[a for a in actions if view=='All actions' or (view=='Needs attention' and a['status']=='Needs decision') or (view=='Commitments' and a['type'] in ('commitment','plan_commitment','reserve_commitment')) or (view=='Setup reminders' and a['status']=='Setup reminder')]
    if not shown:st.success('Nothing needs a new decision here.');return
    for action in shown:
        with st.container(border=True):
            display_amount=action.get('remaining') or action.get('accepted') or action.get('committed') or action['amount']
            st.write('**'+action['category']+'**'+(' · '+dollars(display_amount) if action['amount'] else ''))
            st.caption(action['status']+' · '+action['reason'])
            st.caption(action['next'])
            if action['type']=='overspend':
                if action['status']=='Needs decision' and st.button('Resolve '+action['category'],key=key+':resolve:'+action['id'],width='stretch'):
                    open_source(st,state,action['source'])
            elif action['type'] in ('commitment','plan_commitment','reserve_commitment'):
                r=action['record'];st.caption('Accrued reserve allocated '+dollars(r['amount'])+' · not extra savings' if action['type']=='reserve_commitment' else 'Planned recovery '+dollars(r['amount'])+' · realised '+dollars(action['recovered']))
                if pending(state,r) or action['type']=='reserve_commitment':
                    a,b=st.columns(2)
                    if a.button('Amend',key=key+':amend:'+action['id'],width='stretch'):
                        state['action_workflow']=dict(source=r['source'],label=action['category'],step=1,response='Adjust a planned one-off expense' if action['type']=='plan_commitment' else 'Offset another spending category',replace_id=action['id'],old_record=deepcopy(r),category=r['category'],amount=float(r['amount']),left=r.get('period_start',r['effective']),right=r.get('period_end',r['end']),mode=r.get('mode','scheduled'),grouping='Week' if (date.fromisoformat(r.get('period_end',r['end']))-date.fromisoformat(r.get('period_start',r['effective']))).days<=7 else 'Month',custom=r.get('custom'),project=r.get('project_id'),plan_action=r.get('action','Reduce'),plan_amount=float(r.get('impact',r['amount'])),new_date=min((c['date'] for c in r.get('changes',[])),default=None) if r.get('action')=='Postpone' else None)
                        st.rerun()
                    if b.button('Reverse',key=key+':reverse:'+action['id'],width='stretch'):
                        if action['type']=='reserve_commitment':state['reserve_reversal']=action['id'];st.rerun()
                        try:remove_pending(state,action['id'])
                        except ValueError as error:st.error(str(error))
                        else:state['action_notice']='Pending commitment reversed. Your forecast is current.';st.rerun()
                    if state.get('reserve_reversal')==action['id']:
                        from contingency_ledger import reserve_balance
                        candidate=deepcopy(state);remove_pending(candidate,action['id'],record_history=False)
                        st.warning('Reverse this reserve allocation? Available reserve '+dollars(reserve_balance(state)['available'])+' → '+dollars(reserve_balance(candidate)['available'])+'. Projected savings decrease by '+dollars(r['amount'])+'. The observed expense remains.')
                        if st.button('Confirm reserve reversal',key=key+':confirm_reverse:'+action['id']):
                            remove_pending(state,action['id']);state.pop('reserve_reversal',None);state['action_notice']='Reserve funding reversed; observed transactions are unchanged.';st.rerun()
                elif st.button('Review spending',key=key+':verify:'+action['id']):navigate(st,state,'Review Your Spending',dict(kind='transactions',category=r['category']))
            elif action['id'].startswith('reminder:'):
                reminder=next(r for r in state.get('reminders',[]) if r['id']==action['id'][len('reminder:'):])
                new_due=st.date_input('New reminder date',value=max(date.fromisoformat(state['tracking_date']),date.fromisoformat(reminder['due_date'])),min_value=date.fromisoformat(state['tracking_date']),key=key+':due:'+action['id'])
                if st.button('Reschedule reminder',key=key+':move:'+action['id']):
                    state.setdefault('reminder_history',[]).append(deepcopy(reminder));reminder['due_date']=str(new_due);st.rerun()
                if st.button('Mark reminder complete',key=key+':complete:'+action['id']):
                    state.setdefault('reminder_history',[]).append(deepcopy(reminder));reminder['completed']=True;st.rerun()
            elif st.button(action['next'],key=key+':review:'+action['id'],width='stretch'):
                navigate(st,state,action['page'],dict(kind=action['id'],project_id=action.get('project_id'),setup_step=action.get('setup_step')))


def current_selection(wf):
    fields=('response','category','left','right','amount','custom','mode','project','plan_action','plan_amount','new_date')
    return {field:deepcopy(wf[field]) for field in fields if field in wf}


def render_category_configuration(st,state,wf,key,start,end,today,unresolved,fixed_mode=None,force_custom=False):
    wf['configured']=False
    grouping=st.radio('Recover over',['Month','Week'],index=0 if wf.get('grouping','Week')=='Month' else 1,key=key+':grouping')
    wf['grouping']=grouping
    if grouping=='Month':
        periods=[d for d in month_starts(state) if add_months(d,1)>today+timedelta(days=1)]
        left=st.selectbox('Recovery month',periods,index=periods.index(date.fromisoformat(wf['left'])) if wf.get('left') and date.fromisoformat(wf['left']) in periods else min(1,len(periods)-1),format_func=lambda d:d.strftime('%B %Y'),key=key+':month') if periods else None
        right=add_months(left,1) if left else None
    else:
        periods=[w for w in weeks_in_horizon(start,end) if w+timedelta(days=7)>today+timedelta(days=1)]
        left=week_selector(st,'Recovery week',periods,key+':week',date.fromisoformat(wf['left']) if wf.get('left') else periods[0]) if periods else None
        right=left+timedelta(days=7) if left else None
    if left is None:st.info('No future periods remain. Go Back to accept the savings impact.');return
    wf.update(left=str(left),right=str(right))
    modes=['Flexible allowances','Scheduled payments']
    default_mode=wf.get('mode') or ('flexible' if any(available_events(state,c,left,right,'flexible') for c in state['categories']) else 'scheduled')
    mode_label=('Flexible allowances' if fixed_mode=='flexible' else 'Scheduled payments') if fixed_mode else st.radio('Spending to reduce',modes,index=0 if default_mode=='flexible' else 1,key=key+':mode')
    mode='flexible' if mode_label==modes[0] else 'scheduled';wf['mode']=mode
    st.caption('Choose a future period and the spending you want to reduce.')
    events=result(state,accounting=False)[0]
    categories=sorted({e['category'] for e in events if e['kind']=='expense'})
    caps={c:sum((e['capacity'] for e in available_events(state,c,left,right,mode)),Decimal(0)) for c in categories}
    choices=[c for c in categories if caps[c]>0]
    if mode=='scheduled':
        dates=sorted({e['date'] for e in events if e['kind']=='expense' and not e.get('allowance') and not e['paid'] and today<e['date']<end and e['amount']>0})
        next_day=next((day for day in dates if any(available_events(state,c,day-timedelta(days=day.weekday()) if grouping=='Week' else day.replace(day=1),day-timedelta(days=day.weekday())+timedelta(days=7) if grouping=='Week' else add_months(day.replace(day=1),1),mode) for c in categories)),None)
        if next_day:
            st.caption('Next eligible scheduled payment: '+next_day.strftime('%d %b %Y'))
            def jump():
                st.session_state[key+(':week' if grouping=='Week' else ':month')]=next_day-timedelta(days=next_day.weekday()) if grouping=='Week' else next_day.replace(day=1)
            st.button('Next eligible payment',key=key+':next_payment',on_click=jump,disabled=left<=next_day<right,width='stretch')
    if not choices:
        st.info('No eligible '+mode_label.lower()+' in this period. Choose another period or spending type. Paid, elapsed and consumed spending is excluded.');return
    category=st.selectbox('Recovery category',choices,index=choices.index(wf['category']) if wf.get('category') in choices else 0,format_func=lambda c:c+' · '+dollars(caps[c])+' available',key=key+':category:'+str(left)+':'+mode)
    current=sum((e['amount'] for e in events if e['kind']=='expense' and e['category']==category and left<=e['date']<right and bool(e.get('allowance'))==(mode=='flexible')),Decimal(0))
    frequencies=sorted({str(item.get('frequency','Dated payments')) for item in state['draft']['expenses'] if item['category']==category and bool(item.get('allowance'))==(mode=='flexible')})
    st.caption('Current period allocation '+dollars(current)+' · '+', '.join(frequencies)+' · '+dollars(caps[category])+' eligible to reduce')
    maximum=min(unresolved,caps[category])
    if maximum<=0:st.info('This source is already fully committed. Go Back or Cancel.');return
    amount=st.number_input('Recovery amount ($)',min_value=0.01,max_value=float(maximum),value=float(min(money(wf.get('amount') if wf.get('amount') is not None else maximum),maximum)) or .01,step=1.0,key=key+':amount:'+str(left)+':'+category+':'+mode+':'+str(maximum))
    if amount is None:st.info('Enter the amount you want to cover.');return
    wf.update(category=category,amount=amount)
    try:
        preview=distribution_preview(state,category,left,right,amount,mode=mode)
        custom=None
        if mode=='flexible':
            st.caption('Your reduction is spread across the remaining days in this period.')
            use_custom=force_custom or st.checkbox('Custom weekly amounts',value=bool(wf.get('custom')),key=key+':custom')
            if use_custom:
                old=wf.get('custom') or {}
                custom={date.fromisoformat(w['week']):money(st.number_input(w['label'],min_value=0.0,max_value=float(w['capacity']),value=float(min(money(old.get(date.fromisoformat(w['week']),w['amount'])),w['capacity'])),key=key+':custom:'+w['week']+':'+str(left)+':'+category)) for w in preview['weeks']}
                wf['custom']=custom
                preview=distribution_preview(state,category,left,right,amount,custom,mode)
        else:st.caption('Only actual scheduled payments are reduced. Payment dates stay unchanged.')
        for week in preview['weeks']:st.caption(week['label']+' · '+dollars(week['amount'])+(f" · {week['days']} eligible days" if mode=='flexible' else ''))
        wf['custom']=custom;wf['configured']=True;wf['credit']=money(amount)
        funding_amounts(st,caps[category],money(amount),unresolved,left,right,mode_label)
    except ValueError as error:st.warning(str(error));wf['configured']=False


def render_plan_configuration(st,state,wf,key,start,end,today,unresolved):
    wf['configured']=False
    events=result(state,accounting=False)[0]
    ids={e.get('project_id') for e in events if e.get('project_id') and not e['paid'] and today<e['date']<end and e['amount']>0}
    plans={p['id']:p['name'] for p in state['draft']['projects'] if p['id'] in ids and not plan_category_conflict(state,[e for e in events if e.get('project_id')==p['id'] and not e['paid'] and today<e['date']<end])}
    if not plans:st.info('No eligible future unpaid plans are available. Payments already funding a recovery are excluded. Go Back to choose category recovery or accept the impact.');return
    project=st.selectbox('Planned expense',list(plans),index=list(plans).index(wf['project']) if wf.get('project') in plans else 0,format_func=lambda identity:plans[identity]+' · '+dollars(sum((e['amount'] for e in events if e.get('project_id')==identity and not e['paid'] and today<e['date']<end),Decimal(0)))+' unpaid',key=key+':project')
    action=st.radio('Change the plan',['Reduce','Postpone','Cancel'],index=['Reduce','Postpone','Cancel'].index(wf.get('plan_action','Reduce')),key=key+':plan_action')
    amount=0;new_date=None
    if action=='Reduce':amount=st.number_input('Plan reduction ($)',min_value=.01,value=float(wf.get('plan_amount') or min(20,unresolved)) or .01,key=key+':plan_amount')
    if action=='Postpone':
        first=min(e['date'] for e in events if e.get('project_id')==project and not e['paid'] and e['date']>today)
        new_date=st.date_input('New first payment date',value=date.fromisoformat(wf['new_date']) if wf.get('new_date') else first+timedelta(days=7),min_value=first+timedelta(days=1),key=key+':plan_date')
    wf.update(project=project,plan_action=action,plan_amount=amount,new_date=str(new_date) if new_date else None)
    try:
        _,record,impact=plan_preview(state,wf['source'],project,action,amount,new_date)
        revised=sum((money(c['amount']) for c in record['changes']),Decimal(0))
        funding_amounts(st,record['total'],record['total']-revised,unresolved,date.fromisoformat(record['effective']),end,'Future unpaid planned payments',credit=record['amount'])
        st.write('Projected budget-period savings change: **'+dollars(impact)+'**')
        credit=min(record['amount'],unresolved)
        st.caption('Recovery credit: '+dollars(credit)+'. Moving a payment within the budget period changes timing, not savings.')
        wf['configured']=True;wf['credit']=credit
    except ValueError as error:st.warning(str(error))


def render_source_review(st,state,key,workflow):
    from proactive_alerts import period_for
    from observations import current
    from spending_ui import inline_transactions
    action=next((a for a in collect_actions(state) if a.get('source')==workflow['source'] and a['type']=='overspend'),None)
    if not action:
        st.success('This overrun no longer needs a new decision.')
        if st.button('Return to To Do',key=key+':done'):state.pop('action_workflow',None);st.rerun()
        return
    left,right=period_for(state,action)
    if st.button('Back',key=key+':source_back'):
        from consumer_navigation import return_to_context
        return_to_context(st,state)
    st.subheader('Review '+action['category']+' overspend')
    if left and right:st.caption(left.strftime('%d %b')+' – '+(right-timedelta(days=1)).strftime('%d %b %Y'))
    st.warning(dollars(action['remaining'])+' still needs a decision. Its spending impact is already in the forecast.')
    rows=[t for t in current(state) if t.get('category')==action['category'] and (not left or left<=date.fromisoformat(t['date'])<right)]
    inline_transactions(st,state,state.get('period_transactions',[]),rows,key+':transactions',False,page_size=6)
    duplicate_review(st,state,key+':duplicates',rows)
    if st.button('Choose recovery action',type='primary',key=key+':continue',width='stretch'):
        workflow['review_stage']=False;st.rerun()


def duplicate_review(st,state,key,rows):
    from observations import set_duplicate
    candidates=[]
    for row in rows:
        for other in state.get('period_transactions',[]):
            if other['id']!=row['id'] and not other.get('excluded_duplicate') and other['date']==row['date'] and other['amount']==row['amount']:
                candidates.append((row,other))
    excluded=[t for t in state.get('period_transactions',[]) if t.get('excluded_duplicate')]
    if excluded:
        with st.expander('Excluded duplicates'):
            for row in excluded:
                if st.button('Restore '+row['description'],key=key+':restore:'+row['id']):set_duplicate(state,row['id'],False);st.rerun()
    if not candidates:return
    with st.expander('Review possible duplicate payments'):
        labels={str(i):row['description']+' · '+row['date']+' · '+dollars(row['amount'])+' / original '+other['description'] for i,(row,other) in enumerate(candidates)}
        choice=st.selectbox('Payment to exclude as duplicate',list(labels),format_func=labels.get,key=key+':choice')
        row,other=candidates[int(choice)]
        st.caption('Both source records are retained. Only the explicitly excluded duplicate stops contributing to spending.')
        confirm=st.checkbox('I checked that these are the same payment',key=key+':confirmed:'+choice)
        if st.button('Confirm duplicate exclusion',disabled=not confirm,key=key+':exclude'):
            set_duplicate(state,row['id'],True,other['id']);st.rerun()


def funding_amounts(st,current,reduction,unresolved,left,right,label,credit=None):
    """Display the eligible unpaid portion, never imply paid spending can be cut."""
    from datetime import timedelta
    st.caption(label+' · '+left.strftime('%d %b %Y')+' – '+(right-timedelta(days=1)).strftime('%d %b %Y'))
    st.write('Available to adjust: **'+dollars(current)+'**')
    st.write('Use / reduce by: **'+dollars(reduction)+'** → Leaves: **'+dollars(current-reduction)+'**')
    st.write('Still to cover: **'+dollars(max(Decimal(0),unresolved-(reduction if credit is None else credit)))+'**')
    st.caption('Past spending and paid bills stay unchanged.')
