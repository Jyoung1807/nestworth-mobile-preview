"""Guided forecast changes; all previews and commits use existing replay services."""
from budget_period import BudgetPeriod,period_end,month_starts
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
from finance import money,add_months,FREQUENCIES
from planning import result,summarize,change_decision,uid
from draft_inputs import field,buffer
from setup_model import STEPS
from year_ahead_ui import funding


def audit_json(value):
    # Custom monthly recovery records have date-keyed weekly amounts.
    def safe(item):
        if isinstance(item,dict):return {str(k):safe(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)):return [safe(v) for v in item]
        return item
    return __import__('json').dumps(safe(value),default=str)


def preview_decision(state,candidate):
    decisions=[d for d in deepcopy(state['decisions']) if d['id']!=candidate['id']]+[candidate]
    return result(state,decisions=decisions)


def unexpected(st,state,key,existing_only=False):
    existing={d['id']:d for d in state['decisions']}
    selected=st.selectbox('Add or change a decision',(list(existing) if existing_only else ['new',*existing]),format_func=lambda i:'New unexpected expense' if i=='new' else existing[i]['description'],key=key+':selected')
    current=existing.get(selected,{})
    scope='outlook:unexpected:'+selected;b=buffer(state,scope,'Outlook');b.setdefault('step',1 if existing_only else 0);b.setdefault('offsets',deepcopy(current.get('offsets',[])));b.setdefault('decision_id',current.get('id',uid()))
    step=b['step'];labels=['Expense details','Funding method','Spending reductions','Review & confirm']
    st.progress((step+1)/4,text=f'Step {step+1} of 4 · '+labels[step])
    def f(kind,label,name,default,**kw):return field(st,state,scope,'Outlook',kind,label,name,default,**kw)
    start=date.fromisoformat(state['draft']['start']);end=period_end(state);today=date.fromisoformat(state.get('tracking_date',str(start)))
    if step==0:
        f('text_input','Unexpected expense / description','description',current.get('description',''))
        f('text_input','Why are you changing the plan?','reason',current.get('reason',''))
        f('number_input','New expense ($)','amount',float(current.get('amount',0)),min_value=0.0,step=100.0)
        f('date_input','Payment date','date',date.fromisoformat(current.get('date',str(today))),min_value=start,max_value=end-timedelta(days=1))
        f('selectbox','Expense category','category',current.get('category','Other'),options=state['categories'])
    elif step==1:
        f('radio','How would you like to fund it?','choice',current.get('funding_choice','Reduce savings'),options=['Reduce savings','Fully offset','Partially offset'])
        st.caption('Future reductions protect forecast savings. They do not imply cash is available before the expense payment date.')
    elif step==2:
        if b.get('choice','Reduce savings')=='Reduce savings':st.info('No reductions selected. This expense will reduce projected savings.')
        else:
            for n,offset in enumerate(list(b['offsets'])):
                identity=offset.setdefault('_ui_id',uuid4().hex);row_scope=scope+':offset:'+identity
                def g(kind,label,name,default,**kw):return field(st,state,row_scope,'Outlook',kind,label,name,default,**kw)
                with st.expander(f'Funding adjustment {n+1}',expanded=True):
                    target_type=g('selectbox','Reduction source','target_type','Regular expense' if offset.get('kind','').startswith('expense') else 'Planned expense' if 'project' in offset.get('kind','') else 'Category',options=['Regular expense','Category','Planned expense'])
                    collection='expenses' if target_type=='Regular expense' else 'projects'
                    targets={e['id']:e['name'] for e in state['draft'][collection]} if target_type!='Category' else {c:c for c in [*state['categories'],'Contingency']}
                    if not targets:st.info('No eligible source entries. Add a budget expense/plan or remove this adjustment.');continue
                    target=g('selectbox','Reduction target','target',offset.get('target',next(iter(targets))),options=list(targets),format_func=targets.get)
                    actions=['Dollar reduction','Percentage reduction']+(['Cancel unpaid payments','Postpone payments'] if target_type=='Planned expense' else [])
                    action=g('selectbox','Reduction action','action','Percentage reduction' if offset.get('kind','').endswith('percent') else 'Dollar reduction',options=actions)
                    prefix='expense' if target_type=='Regular expense' else 'project' if target_type=='Planned expense' else 'category'
                    offset['kind']=('cancel_project' if action.startswith('Cancel') else 'postpone_project' if action.startswith('Postpone') else prefix+('_percent' if action.startswith('Percentage') else '_fixed'));offset['target']=target
                    offset['from']=str(g('date_input','Reduction starts','from',date.fromisoformat(offset.get('from',str(today))),min_value=today,max_value=end-timedelta(days=1)))
                    offset['until']=str(g('date_input','Reduction ends (inclusive)','until',date.fromisoformat(offset.get('until',str(end-timedelta(days=1)))),min_value=today,max_value=end-timedelta(days=1)))
                    if action.startswith('Postpone'):offset['new_date']=str(g('date_input','New first unpaid payment date','new_date',date.fromisoformat(offset.get('new_date',str(add_months(today,1))))))
                    elif not action.startswith('Cancel'):
                        offset['value']=g('number_input','Reduction (%)' if action.startswith('Percentage') else 'Reduction amount ($)','value',float(offset.get('value') or 0),min_value=0.0,max_value=100.0 if action.startswith('Percentage') else None)
                        if action.startswith('Dollar'):
                            offset['frequency']=g('selectbox','Reduction frequency','frequency',offset.get('frequency','One-off'),options=['One-off','Weekly','Fortnightly','Monthly','Quarterly','Annual'])
                            st.caption('One-off is the total across the window. Recurring amounts multiply by scheduled reduction occurrences; exact reductions still cannot exceed unpaid expenses.')
                    if st.button('Remove adjustment',key=key+':remove:'+identity):b['offsets'].remove(offset);st.rerun()
            if st.button('Add funding adjustment',key=key+':add'):
                b['offsets'].append(dict(kind='expense_fixed',value=0));st.rerun()
    candidate=dict(id=b['decision_id'],description=b.get('description',current.get('description','')),reason=b.get('reason',current.get('reason','')),amount=b.get('amount',current.get('amount',0)),date=str(b.get('date',current.get('date',str(today)))),category=b.get('category',current.get('category','Other')),offsets=deepcopy(b['offsets']) if b.get('choice',current.get('funding_choice','Reduce savings'))!='Reduce savings' else [],funding_choice=b.get('choice',current.get('funding_choice','Reduce savings')))
    try:valid=bool(candidate['description'].strip() and candidate['reason'].strip() and money(candidate['amount'])>0)
    except ValueError:valid=False
    preview=None
    if step==3:
        try:
            if not valid:raise ValueError('Complete expense description, amount and reason first.')
            events,explanations=preview_decision(state,candidate);preview=next(e for e in explanations if e['id']==candidate['id'])
            if candidate['funding_choice']=='Fully offset' and preview['savings_impact']>0:raise ValueError('Full offset requires enough eligible reductions. Choose partial offset or add funding.')
            funding(st,preview)
            st.caption('Expense '+candidate['description']+' · payment '+candidate['date']+' · '+str(len(candidate['offsets']))+' funding adjustments')
            confirmed=st.checkbox('Confirm this forecast change; approved budgets stay locked',key=key+':ack:'+str(candidate))
            if st.button('Save forecast decision',type='primary',disabled=not confirmed,key=key+':save'):
                change_decision(state,candidate);state['setup_buffers'].pop(scope,None);state['outlook_notice']='Forecast decision saved. Overview now uses the updated projection.';st.rerun()
        except ValueError as error:st.warning(str(error))
    a,c=st.columns(2)
    if a.button('Back',disabled=step==0,key=key+':back'):b['step']-=1;st.rerun()
    if c.button('Next',disabled=step==3 or step==0 and not valid,key=key+':next'):b['step']+=1;st.rerun()
    if current and st.button('Reverse this decision',key=key+':reverse'):
        try:change_decision(state,remove_id=selected)
        except ValueError as error:st.error('Later funding depends on this decision. '+str(error))
        else:state['setup_buffers'].pop(scope,None);st.rerun()


def regular_change(st,state,key):
    from accountability_ui import revision_editor
    st.caption('Current net income / expense amounts and frequencies remain the source. Amount-only changes retain the existing dated schedule.')
    revision_editor(st,state,key)


def outlook(st,state,key):
    st.subheader('Adjust Forecast')
    notice=state.pop('outlook_notice',None)
    if notice:st.success(notice)
    st.caption('Financial analysis is on Overview. Changes here update its latest forecast without changing locked budgets.')
    if not state['versions']:st.info('Approve your budget in Build Your Budget before making forecast decisions.');return
    choices=['Change Regular Expense','Change Income','Add unexpected expense','Change a planned expense','Review expense funding','Change contingency','Amendment history']
    requested=state.pop('forecast_action_next',None)
    if requested in choices:st.session_state[key+':action']=requested
    saved_action=key+':saved_action'
    if key+':action' not in st.session_state and st.session_state.get(saved_action) in choices:
        st.session_state[key+':action']=st.session_state[saved_action]
    view=st.selectbox('Forecast action',choices,key=key+':action');st.session_state[saved_action]=view
    if view in ('Change Regular Expense','Change Income'):
        revision_workflow(st,state,key+':revision:'+view,collection_hint='income' if view=='Change Income' else 'expenses')
        with st.expander('Advanced category / percentage revisions'):
            regular_change(st,state,key+':advanced')
    elif view=='Add unexpected expense':unexpected(st,state,key+':decision')
    elif view=='Change a planned expense':revision_workflow(st,state,key+':plan_revision',True)
    elif view=='Change contingency':
        from contingency_ui import forecast
        forecast(st,state,key+':reserve')
    elif view=='Review expense funding':
        st.caption('Amend existing unexpected-expense funding below, or manage overspend commitments in To Do.')
        if st.button('Manage recovery commitments',key=key+':actions'):
            state['_actions_focus_view']='Commitments';st.session_state[state['_nav_key']+':next']='Actions';st.rerun()
        existing=state.get('decisions',[])
        if not existing:st.info('No unexpected expenses to amend. Add an unexpected expense first.')
        else:unexpected(st,state,key+':decision',existing_only=True)
    else:
        if state.get('revisions'):
            from accountability import reverse_latest_revision
            try:
                candidate=deepcopy(state);reverse_latest_revision(candidate)
                start=date.fromisoformat(state['draft']['start'])
                st.caption('Latest pending amendment can be reversed. Forecast savings after reversal: '+f"${summarize(result(candidate)[0],start,end=period_end(state))['savings']:,.2f}")
                ack=st.checkbox('Confirm reversal of the latest pending amendment',key=key+':reverse_ack:'+str(len(state['revisions'])))
                if st.button('Reverse latest forecast amendment',disabled=not ack,key=key+':reverse_revision'):
                    state.update(candidate);state['outlook_notice']='Amendment reversed; audit history and approved versions are retained.';st.rerun()
            except ValueError as error:st.caption(str(error))
        for record in reversed([*state.get('forecast_history',[]),*state.get('history',[])]):
            title=record.get('type',f"Funding decision {record.get('sequence','')}")
            with st.expander(title):st.json(audit_json(record))


def revision_workflow(st,state,key,plans=False,collection_hint=None):
    """Select → edit → confirm, with input buffers surviving page navigation."""
    from accountability import save_revision,revision_entry
    scope='outlook:revision:'+str(plans)+':'+str(collection_hint);b=buffer(state,scope,'Outlook');b.setdefault('step',0)
    stage=b['step'];st.progress((stage+1)/3,text=f'Change step {stage+1} of 3 · '+['Choose entry','Edit proposal','Review impact'][stage])
    def f(kind,label,name,default,**kw):return field(st,state,scope,'Outlook',kind,label,name,default,**kw)
    if stage==0:
        collection='projects' if plans else collection_hint or f('selectbox','Entry type','collection','expenses',options=['expenses','income'],format_func=lambda x:'Regular expenses' if x=='expenses' else 'Net household income')
        b['collection']=collection
        targets={e['id']:e['name'] for e in state['draft'][collection]}
        if not targets:st.info('No entries available. Add them in Build Your Budget first.');return
        target=f('selectbox','Entry to change','target',next(iter(targets)),options=list(targets),format_func=targets.get)
    collection=b.get('collection','projects' if plans else 'expenses');target=b.get('target')
    old=next((e for e in state['draft'][collection] if e['id']==target),{})
    if not old:st.warning('Select an entry first.');b['step']=0;return
    start=date.fromisoformat(state['draft']['start']);today=date.fromisoformat(state.get('tracking_date',str(start)));end=period_end(state)
    old=revision_entry(state,collection,target,today)
    if stage==1:
        st.write('Current '+old['name']+' · '+(f"${old['total']:,.2f} planned" if plans else f"${old['amount']:,.2f} {old['frequency'].lower()}"))
        if plans:
            f('radio','Plan change','action','Reduce',options=['Reduce','Postpone','Cancel'])
            if b['action']=='Reduce':f('number_input','Plan reduction ($)','value',0.0,min_value=0.0)
            if b['action']=='Postpone':f('date_input','New first payment date','new_date',add_months(today,1))
        else:
            f('number_input','New amount per payment ($)','value',float(old['amount']),min_value=0.0)
            f('selectbox','New frequency','frequency',old['frequency'],options=list(FREQUENCIES[:-1]))
            st.caption('Income amendments are net (after tax). Use Build Your Budget income estimates if converting gross pay.')
        f('date_input','Effective from','effective',today,min_value=today,max_value=end-timedelta(days=1))
        f('text_input','Reason for revision','reason','')
    if stage==2:
        effective=b.get('effective',today)
        proposal=dict(scope='item',target=target,kind='income' if collection=='income' else 'expense',mode='plan_schedule' if plans else 'schedule' if b.get('frequency',old.get('frequency'))!=revision_entry(state,collection,target,effective).get('frequency') else 'amount',value=b.get('value',0),old_amount=old.get('_revision_basis',old.get('amount',0)),effective=str(effective),reason=b.get('reason',''),label=old['name'],new_frequency=b.get('frequency'),plan_action=b.get('action'),new_date=str(b.get('new_date',today)))
        try:
            if not proposal['reason'].strip():raise ValueError('Add a reason before confirming.')
            candidate=deepcopy(state);save_revision(candidate,proposal)
            before=summarize(result(state)[0],start,end=period_end(state));after=summarize(result(candidate)[0],start,end=period_end(state))
            a,c=st.columns(2);a.metric('Spending change',f"${after['expenses']-before['expenses']:,.2f}");c.metric('Savings change',f"${after['savings']-before['savings']:,.2f}")
            from payment_rescheduling import financial_position
            before_cash=financial_position(state);after_cash=financial_position(candidate)
            st.caption('Closing cash: '+str(before_cash['closing'])+' → '+str(after_cash['closing'])+' · Lowest cash: '+str(before_cash['lowest'])+' → '+str(after_cash['lowest']))
            st.caption(old['name']+' · effective '+str(effective)+'. Approved versions and historical actuals stay unchanged.')
            ack=st.checkbox('Confirm revision; keep the approved baseline unchanged',key=key+':ack:'+str(proposal))
            if st.button('Confirm forecast revision',disabled=not ack,type='primary',key=key+':confirm'):
                state.update(candidate);state['setup_buffers'].pop(scope,None);state['outlook_notice']='Revision saved. Overview reflects the latest forecast.';st.rerun()
        except ValueError as error:st.warning(str(error))
    a,c=st.columns(2)
    if a.button('Back',disabled=stage==0,key=key+':back'):b['step']-=1;st.rerun()
    if c.button('Next',disabled=stage==2,key=key+':next'):b['step']+=1;st.rerun()
    if st.button('Discard amendment draft',key=key+':discard'):state['setup_buffers'].pop(scope,None);st.rerun()
