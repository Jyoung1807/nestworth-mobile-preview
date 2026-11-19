"""One-off plan drafts and independently editable instalments."""
from copy import deepcopy
from datetime import date
from draft_inputs import buffer,field,saved,applied,discard
from setup_model import STEPS,setup_state
from planning import uid,project_payments,replace_draft,result
from finance import money


def plans(st,state,key):
    from setup_journey import set_stage,STAGES
    setup=setup_state(state);projects=state['draft']['projects'];names={p['id']:p['name'] for p in projects}
    ui=state.setdefault('plans_ui',{})
    st.caption('Add larger costs expected in the next 12 months, or continue without a plan.')
    for project in projects:
        with st.container(border=True):
            days=[p['date'] for p in project.get('payments',[])]
            timing=(min(days)+' – '+max(days)) if days and len(set(days))>1 else days[0] if days else 'Timing not set'
            st.markdown('**'+project['name']+'** · $'+f"{project['total']:,.2f}")
            st.caption(timing+' · '+str(len(days))+' payment'+('s' if len(days)!=1 else ''))
            if st.button('Edit plan · '+project['name'],key=key+':edit:'+project['id']):ui.update(selected=project['id'],open=True);st.rerun()
            if not any(r['project_id']==project['id'] for r in state.get('plan_recoveries',[])) and st.button('Remove plan · '+project['name'],key=key+':remove_saved:'+project['id']):
                candidate=deepcopy(state['draft']);candidate['projects']=[p for p in projects if p['id']!=project['id']]
                try:
                    replace_draft(state,candidate);state.get('setup_buffers',{}).pop('plan:'+project['id'],None);setup['plans_reviewed']=False
                    ui.update(open=False,selected='new');st.rerun()
                except ValueError as error:st.error(str(error))
    if st.button('Add Another Plan' if projects else 'Add Plan',key=key+':new'):
        ui.update(selected='new',open=True);st.rerun()
    focus=state.pop('plan_focus',None)
    if focus:ui.update(selected=focus,open=True)
    opened=ui.get('open',False)
    selected=ui.get('selected','new') if opened else None
    if selected not in names and selected!='new':selected='new'
    old=next((p for p in projects if p['id']==selected),{})
    commitment=next((r for r in state.get('plan_recoveries',[]) if r['project_id']==selected),None)
    if commitment:
        st.info('The latest forecast for this plan is managed in To Do. Its original source entries stay intact.')
        for event in result(state)[0]:
            if event.get('project_id')==selected:st.caption(str(event['date'])+' · $'+f"{event['amount']:,.2f}"+' · '+event['name'])
        if st.button('Manage plan decision in To Do',key=key+':manage'):
            state['_actions_focus_view']='Commitments';state['action_list_view']='Commitments';st.session_state[state['_nav_key']+':next']='Actions';st.rerun()
    elif opened:
        scope='plan:'+selected;b=buffer(state,scope,STEPS[2]);b.setdefault('payments',[p['id'] for p in old.get('payments',[])] or [uid()])
        def f(widget,label,name,value,**kw):return field(st,state,scope,STEPS[2],widget,label,name,value,**kw)
        name=f('text_input','Plan name','name',old.get('name',''))
        total=f('number_input','Total estimated cost ($)','total',float(old.get('total',0)),min_value=0.0,step=50.0)
        category=f('selectbox','Plan category','category',old.get('category','Leisure'),options=state['categories'])
        expected=f('date_input','Expected timing','expected',date.fromisoformat(old.get('payments',[{'date':state['draft']['start']}])[0]['date']))
        mode=f('radio','Payment schedule','mode','Multiple payments' if len(old.get('payments',[]))>1 else 'One payment',options=['One payment','Multiple payments'],horizontal=True)
        rows=[];ids=b['payments'] if mode=='Multiple payments' else b['payments'][:1]
        for i,identity in enumerate(ids):
            prior=next((p for p in old.get('payments',[]) if p['id']==identity),{})
            shown_amount=b.get(identity+':amount',prior.get('amount',0)) if mode=='Multiple payments' else total
            shown_date=b.get(identity+':date',prior.get('date',str(expected)))
            st.caption(f'Payment {i+1} · ${shown_amount:,.2f} · {shown_date}'+(' · estimated' if b.get(identity+':estimated',prior.get('precision','Exact date' if prior else 'Approximate date')!='Exact date') else ''))
            with st.container(border=True):
                desc=f('text_input','Payment description',identity+':description',prior.get('description',f'Payment {i+1}'))
                amount=f('number_input','Instalment amount ($)',identity+':amount',float(prior.get('amount',0)),min_value=0.0,step=10.0) if mode=='Multiple payments' else total
                day=f('date_input','Expected payment date',identity+':date',date.fromisoformat(prior['date']) if prior else expected) if mode=='Multiple payments' else expected
                estimated=f('checkbox','Estimated date',identity+':estimated',prior.get('precision','Exact date' if prior else 'Approximate date')!='Exact date',help='This date is a forecast estimate, not a confirmed bill date.')
                if mode=='Multiple payments' and st.button('Remove instalment',key=key+':remove:'+identity):b['payments'].remove(identity);b['_dirty']=True;st.rerun()
            rows.append(dict(id=identity,description=desc,amount=money(amount),date=str(day),precision='Approximate date' if estimated else 'Exact date'))
        if mode=='Multiple payments' and st.button('Add instalment',key=key+':add'):
            b['payments'].append(uid());b['_dirty']=True;st.rerun()
        allocated=sum((p['amount'] for p in rows),money(0));remaining=money(total)-allocated
        st.progress(min(1.0,float(allocated/money(total))) if total else 0.0,text=f'Payment schedule · ${allocated:,.2f} of ${total:,.2f} allocated')
        with st.container(key='plan_totals'):
            a,c,d=st.columns(3);a.metric('Plan total',f'${total:,.2f}');c.metric('Instalments',f'${allocated:,.2f}');d.metric('Unallocated',f'${remaining:,.2f}')
        if remaining:st.warning('Instalments must add up to the total before this plan can enter the budget. Your incomplete input draft is retained.')
        saved(st,state,scope);discard(st,state,scope,'Discard plan input draft')
        if st.button('Save incomplete plan draft',key=key+':draft'):
            b['_dirty']=bool(name.strip() or total or allocated);st.success('Input draft saved in this session. It is not in the forecast or approved budget.')
        if st.button('Apply plan',type='primary',key=key+':apply'):
            try:
                if total<=0:raise ValueError('Enter a positive total cost.')
                project=dict(old,id=old.get('id',uid()),name=name.strip(),total=money(total),category=category,subcategory=old.get('subcategory',''),payments=rows,status=old.get('status','Active'))
                project_payments(project);candidate=deepcopy(state['draft']);candidate['projects']=[p for p in projects if p['id']!=project['id']]+[project]
                replace_draft(state,candidate);applied(state,scope)
                if not old:state['setup_buffers'].pop(scope,None)
                setup['plans_reviewed']=False;state['plan_reviewed']=False;ui.update(open=False,selected='new');state['setup_notice']='Plan saved. Approved versions stay locked.';st.rerun()
            except ValueError as error:st.error(str(error))
        if st.button('Return to saved plans',key=key+':close'):
            ui['open']=False;st.rerun()
    dirty=any(b.get('_dirty') for b in state.get('setup_buffers',{}).values() if b.get('_step')==STEPS[2])
    if not opened and st.button('Save & Continue',type='primary',key=key+':review',disabled=dirty):
        setup['plans_reviewed']=True;state['plan_reviewed']=True;set_stage(state,STAGES[5]);st.rerun()
    if dirty:st.caption('Apply or discard incomplete plan drafts before finishing this review.')
