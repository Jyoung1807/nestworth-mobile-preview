"""One-screen allocation editor using the existing atomic recovery preview."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4
import hashlib,json
from finance import money,add_months
from action_finance import collect_actions,recovery_decision_preview,remaining_source,source_used,remove_pending
from contingency_ledger import reserve_balance
from model_guard import household_model_lock

TYPES=['Accrued contingency','Flexible allowance','Scheduled payment','Planned expense']


def new_row(grouping='Week',kind='Flexible allowance',**values):return dict(id=uuid4().hex,type=kind,grouping=grouping,**values)


def initialise(state,wf):
    if 'rows' in wf:return
    wf.setdefault('token',uuid4().hex)
    if wf.get('old_record'):
        r=wf['old_record'];kind='Accrued contingency' if r.get('kind')=='contingency' else 'Planned expense' if r.get('project_id') else 'Flexible allowance' if r.get('mode')=='flexible' else 'Scheduled payment'
        wf['rows']=[dict(wf,id=uuid4().hex,type=kind)]
    elif wf.get('sources'):
        wf['rows']=[dict(s,id=uuid4().hex,type='Planned expense' if s['response']=='Adjust a planned one-off expense' else 'Flexible allowance' if s.get('mode')=='flexible' else 'Scheduled payment',grouping=wf.get('grouping','Week')) for s in wf['sources']]
    elif wf.get('response')=='Accept lower projected savings':wf['rows']=[]
    else:wf['rows']=[new_row(wf.get('grouping','Week'),'Accrued contingency' if reserve_balance(state)['available'] else 'Flexible allowance')]


def acknowledgement_signature(value):
    # Custom weekly allocations use date keys; JSON's default hook handles
    # values only. Canonicalise keys too so any edit invalidates acceptance.
    def canonical(item):
        if isinstance(item,dict):return {str(k):canonical(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)):return [canonical(v) for v in item]
        return item
    return hashlib.sha256(json.dumps(canonical(value),sort_keys=True,default=str).encode()).hexdigest()[:16]


def render_editor(st,state,key,wf):
    from actions_ui import render_category_configuration,render_plan_configuration,dollars,current_selection
    initialise(state,wf);key+=':'+wf['token'];source=wf['source']
    st.subheader('Resolve spending overrun')
    st.caption(wf.get('label',source)+' · allocate once, then confirm')
    if st.button('Cancel · return to To Do',key=key+':cancel'):
        state.pop('action_workflow',None);st.rerun()
    if not any(a['type']=='overspend' and a['source']==source for a in collect_actions(state)):
        st.warning('The spending behind this draft changed. Cancel and review the current decision. Existing commitments can still be reversed.');return
    original=money(state['recovery_sources'].get(source,0));selections=[];valid=True
    prior_accepted=money(state.get('accepted_overspends',{}).get(source,0))
    start=date.fromisoformat(state['draft']['start']);end=add_months(start,12);today=date.fromisoformat(state['tracking_date'])
    before_reserve=reserve_balance(state)
    st.caption('Available accumulated contingency: '+dollars(before_reserve['available'])+'. It is offered first, never consumed silently.')
    for index,row in enumerate(list(wf['rows'])):
        row['source']=source
        try:candidate,_,_=recovery_decision_preview(state,source,selections,wf.get('replace_id'),False)
        except ValueError as error:st.warning(str(error));valid=False;break
        unresolved=remaining_source(candidate,source)
        if not wf.get('replace_id'):unresolved=max(Decimal(0),unresolved-prior_accepted)
        prefix=key+':row:'+row['id']
        with st.expander('Funding source '+str(index+1)+' · '+row['type'],expanded=index==len(wf['rows'])-1,key='funding_row_'+row['id']+':'+str(len(wf['rows']))):
            st.write('**Funding source '+str(index+1)+'**')
            if st.button('Remove source '+str(index+1),key=prefix+':remove'):
                wf['rows']=[r for r in wf['rows'] if r['id']!=row['id']];st.rerun()
            def changed(identity=row['id'],widget=prefix+':type'):
                with household_model_lock(state['_nav_key']):
                    flow=state.get('action_workflow',{});current=next((r for r in flow.get('rows',[]) if r['id']==identity),None)
                    if current is not None:current['type']=st.session_state[widget]
            kind=st.selectbox('Funding type',TYPES,index=TYPES.index(row['type']),key=prefix+':type',on_change=changed);row['type']=kind
            if kind=='Accrued contingency':
                cap=min(unresolved,reserve_balance(candidate)['available']);row['response']='Use contingency';row['configured']=False
                if cap<=0:st.info('No accrued, uncommitted contingency is available. Choose a future spending source or remove this row and accept the impact.')
                else:
                    row['amount']=st.number_input('Contingency amount ($)',min_value=.01,max_value=float(cap),value=float(min(money(row.get('amount',cap)),cap)),step=1.0,key=prefix+':reserve:'+str(cap));row['configured']=True
                    st.caption('Reallocates already-accrued reserve; it is not new savings or a future promise.')
            elif kind in ('Flexible allowance','Scheduled payment'):
                row['response']='Offset another spending category'
                render_category_configuration(st,candidate,row,prefix,start,end,today,unresolved,fixed_mode='flexible' if kind=='Flexible allowance' else 'scheduled')
            else:
                row['response']='Adjust a planned one-off expense'
                render_plan_configuration(st,candidate,row,prefix,start,end,today,unresolved)
            if row.get('configured'):selections.append(current_selection(row))
            else:valid=False
    try:
        preview,records,accepted=recovery_decision_preview(state,source,selections,wf.get('replace_id'))
        after=summarize_savings(preview);before=summarize_savings(state)
        allocated=source_used(preview,source)
        signature=acknowledgement_signature([selections,wf.get('replace_id'),str(original),str(accepted)])
        ack=st.checkbox('Accept '+dollars(accepted)+' lower projected savings',value=accepted<=prior_accepted,key=key+':accept:'+signature) if accepted else True
        st.caption('Accepted impact is already included in observed spending. It is not deducted a second time.')
        accepted_now=accepted if ack else min(prior_accepted,accepted)
        with st.container(border=True):
            for record in records:
                name='Accrued contingency' if record.get('kind')=='contingency' else record.get('name',record['category'])
                period=record.get('period_start',record['effective'])
                st.caption(name+' · '+period+' · '+dollars(record['amount']))
            for label,amount in [('Original overspend',original),('Total allocated',allocated),('Accepted savings reduction',accepted_now),('Remaining unresolved',max(Decimal(0),original-allocated-accepted_now))]:st.write(label+': **'+dollars(amount)+'**')
            st.write('Latest projected annual savings: **'+dollars(after)+'** · change '+dollars(after-before))
            balance=reserve_balance(preview)
            st.caption('Accrued reserve available '+dollars(before_reserve['available'])+' → '+dollars(balance['available'])+' · committed '+dollars(balance['committed'])+'. Future recoveries remain pending, not realised savings.')
            for record in records:
                if record.get('action')=='Postpone' and not record['impact']:st.caption('Postponing inside this financial year changes timing, not annual savings.')
        if wf.get('replace_id'):st.caption('Only the selected commitment is replaced; other commitments and all locked budget versions stay intact.')
        if st.button('Add funding source',disabled=not valid or allocated+prior_accepted>=original,key=key+':add',width='stretch'):
            wf['rows'].append(new_row(wf.get('grouping','Week')));st.rerun()
        if st.button('Confirm decision',type='primary',disabled=not valid or not ack,key=key+':confirm',width='stretch'):
            state.update(preview);state.pop('action_workflow',None);state['action_notice']='Decision confirmed. Remaining impact accepted; pending recovery is not realised savings.';st.rerun()
    except ValueError as error:
        st.warning(str(error));st.caption('Edit or remove an invalid source. Nothing has been saved.')


def summarize_savings(state):
    from planning import result,summarize
    return summarize(result(state)[0],date.fromisoformat(state['draft']['start']))['savings']
