"""Dedicated Actions Centre and a three-step, resumable resolution workflow."""
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


def open_source(st,state,source,grouping=None):
    existing=state.get('action_workflow')
    if not existing or existing['source']!=source:
        action=next((a for a in collect_actions(state) if a.get('source')==source and a['type']=='overspend'),{})
        state['action_workflow']=dict(source=source,label=action.get('category',source.rsplit(':',1)[-1]),step=1,response='Offset another spending category',grouping=grouping or ('Month' if state.get('dashboard_view')=='Monthly' else 'Week'))
    navigate(st,state,'Actions Centre')


def render_actions(st,state,key):
    actions=collect_actions(state)
    message=state.pop('action_notice',None)
    if message:st.success(message)
    workflow=state.get('action_workflow')
    if workflow:
        from recovery_editor import render_editor
        render_editor(st,state,key+':flow',workflow)
        return
    st.subheader('To Do')
    need=sum(a['status']=='Needs decision' for a in actions)
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
            elif st.button(action['next'],key=key+':review:'+action['id'],width='stretch'):
                navigate(st,state,action['page'],dict(kind=action['id'],project_id=action.get('project_id'),setup_step=action.get('setup_step')))


def current_selection(wf):
    fields=('response','category','left','right','amount','custom','mode','project','plan_action','plan_amount','new_date')
    return {field:deepcopy(wf[field]) for field in fields if field in wf}


def render_category_configuration(st,state,wf,key,start,end,today,unresolved,fixed_mode=None):
    wf['configured']=False
    grouping=st.radio('Recover over',['Month','Week'],index=0 if wf.get('grouping','Week')=='Month' else 1,key=key+':grouping')
    wf['grouping']=grouping
    if grouping=='Month':
        periods=[add_months(start,n) for n in range(12) if add_months(start,n+1)>today+timedelta(days=1)]
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
    st.caption('Calendar-day distribution uses entries marked Flexible spending allowance in Build Your Budget. Scheduled bills keep their payment dates.')
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
    category=st.selectbox('Recovery category',choices,index=choices.index(wf['category']) if wf.get('category') in choices else 0,format_func=lambda c:c+' · '+dollars(caps[c])+' eligible',key=key+':category:'+str(left)+':'+mode)
    maximum=min(unresolved,caps[category])
    if maximum<=0:st.info('This source is already fully committed. Go Back or Cancel.');return
    amount=st.number_input('Recovery amount ($)',min_value=0.01,max_value=float(maximum),value=float(min(money(wf.get('amount',maximum)),maximum)) or .01,step=1.0,key=key+':amount:'+str(left)+':'+category+':'+mode+':'+str(maximum))
    wf.update(category=category,amount=amount)
    try:
        preview=distribution_preview(state,category,left,right,amount,mode=mode)
        custom=None
        if mode=='flexible':
            st.caption('Even reduction per eligible calendar day. Only days inside this period count; no four-week approximation.')
            use_custom=st.checkbox('Custom weekly amounts',value=bool(wf.get('custom')),key=key+':custom')
            if use_custom:
                old=wf.get('custom') or {}
                custom={date.fromisoformat(w['week']):money(st.number_input(w['label'],min_value=0.0,max_value=float(w['capacity']),value=float(min(money(old.get(date.fromisoformat(w['week']),w['amount'])),w['capacity'])),key=key+':custom:'+w['week']+':'+str(left)+':'+category)) for w in preview['weeks']}
                wf['custom']=custom
                preview=distribution_preview(state,category,left,right,amount,custom,mode)
        else:st.caption('Only actual scheduled payments are reduced. Payment dates stay unchanged.')
        for week in preview['weeks']:st.caption(week['label']+' · '+dollars(week['amount'])+(f" · {week['days']} eligible days" if mode=='flexible' else ''))
        wf['custom']=custom;wf['configured']=True;wf['credit']=money(amount)
        st.write('Accepted savings impact unless another source is added: **'+dollars(unresolved-money(amount))+'**')
    except ValueError as error:st.warning(str(error));wf['configured']=False


def render_plan_configuration(st,state,wf,key,start,end,today,unresolved):
    wf['configured']=False
    events=result(state,accounting=False)[0]
    ids={e.get('project_id') for e in events if e.get('project_id') and not e['paid'] and today<e['date']<end and e['amount']>0}
    plans={p['id']:p['name'] for p in state['draft']['projects'] if p['id'] in ids and not plan_category_conflict(state,[e for e in events if e.get('project_id')==p['id'] and not e['paid'] and today<e['date']<end])}
    if not plans:st.info('No eligible future unpaid plans are available. Payments already funding a recovery are excluded. Go Back to choose category recovery or accept the impact.');return
    project=st.selectbox('Planned expense',list(plans),index=list(plans).index(wf['project']) if wf.get('project') in plans else 0,format_func=plans.get,key=key+':project')
    action=st.radio('Change the plan',['Reduce','Postpone','Cancel'],index=['Reduce','Postpone','Cancel'].index(wf.get('plan_action','Reduce')),key=key+':plan_action')
    amount=0;new_date=None
    if action=='Reduce':amount=st.number_input('Plan reduction ($)',min_value=.01,value=float(wf.get('plan_amount',min(20,unresolved))) or .01,key=key+':plan_amount')
    if action=='Postpone':
        first=min(e['date'] for e in events if e.get('project_id')==project and not e['paid'] and e['date']>today)
        new_date=st.date_input('New first payment date',value=date.fromisoformat(wf['new_date']) if wf.get('new_date') else first+timedelta(days=7),min_value=first+timedelta(days=1),key=key+':plan_date')
    wf.update(project=project,plan_action=action,plan_amount=amount,new_date=str(new_date) if new_date else None)
    try:
        _,record,impact=plan_preview(state,wf['source'],project,action,amount,new_date)
        st.write('Projected annual savings change: **'+dollars(impact)+'**')
        credit=min(record['amount'],unresolved)
        st.caption('Recovery credit: '+dollars(credit)+'. Postponing inside the year does not create annual savings.')
        wf['configured']=True;wf['credit']=credit
    except ValueError as error:st.warning(str(error))
