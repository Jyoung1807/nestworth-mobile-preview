"""One-screen allocation editor using the existing atomic recovery preview."""
from budget_period import BudgetPeriod,period_end,month_starts
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
import hashlib,json
from finance import money,add_months
from action_finance import collect_actions,recovery_decision_preview,remaining_source,source_used,remove_pending
from contingency_ledger import reserve_balance
from model_guard import household_model_lock

TYPES=['Accrued contingency','Flexible allowance','Custom weekly reduction','Scheduled payment','Planned expense','Accept lower projected savings']


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
    from action_finance import available_events,plan_category_conflict
    from planning import result,summarize
    initialise(state,wf);key+=':'+wf['token'];source=wf['source']
    st.subheader(wf.get('label','Spending')+' is over budget')
    st.write('How would you like to cover the extra '+f"${state['recovery_sources'].get(source,0):,.2f}"+'?')
    if st.button('Back',key=key+':cancel'):
        if wf.get('had_review'):wf['review_stage']=True;st.rerun()
        from consumer_navigation import return_to_context
        return_to_context(st,state)
    if not any(a['type']=='overspend' and a['source']==source for a in collect_actions(state)):
        st.warning('The spending behind this draft changed. Cancel and review the current decision. Existing commitments can still be reversed.');return
    original=money(state['recovery_sources'].get(source,0));selections=[];valid=True
    prior_accepted=money(state.get('accepted_overspends',{}).get(source,0))
    start=date.fromisoformat(state['draft']['start']);end=period_end(state);today=date.fromisoformat(state['tracking_date'])
    before_reserve=reserve_balance(state)
    st.caption('Contingency available today: '+dollars(before_reserve['available'])+'. Future contributions cannot be used yet.')
    if before_reserve.get('unfunded_accrual',0):
        with st.expander('Why can’t I use more contingency?'):
            st.caption(dollars(before_reserve['unfunded_accrual'])+' is not available yet. Future contributions and unverified recoveries cannot be spent.')
    for index,row in enumerate(list(wf['rows'])):
        row['source']=source
        try:candidate,_,_=recovery_decision_preview(state,source,selections,wf.get('replace_id'),False)
        except ValueError as error:st.warning(str(error));valid=False;break
        unresolved=remaining_source(candidate,source)
        if not wf.get('replace_id'):unresolved=max(Decimal(0),unresolved-prior_accepted)
        prefix=key+':row:'+row['id']
        with st.container(border=True,key='funding_row_'+row['id']+':'+str(len(wf['rows']))):
            if len(wf['rows'])>1:st.caption('Part '+str(index+1)+' of '+str(len(wf['rows'])))
            if len(wf['rows'])>1 and st.button('Remove part '+str(index+1),key=prefix+':remove'):
                wf['rows']=[r for r in wf['rows'] if r['id']!=row['id']];st.rerun()
            def changed(identity=row['id'],widget=prefix+':type'):
                with household_model_lock(state['_nav_key']):
                    flow=state.get('action_workflow',{});current=next((r for r in flow.get('rows',[]) if r['id']==identity),None)
                    if current is not None:current.setdefault('method_amounts',{})[current['type']]=current.get('amount')
                    if current is not None:
                        current['type']=st.session_state[widget];current['chosen']=True;current.pop('amount',None);current.pop('custom',None)
                        previous=current.get('method_amounts',{}).get(current['type'])
                        if previous is not None:current['amount']=previous
            options=[]
            if reserve_balance(candidate)['available']>0:options.append('Accrued contingency')
            if any(available_events(candidate,c,today+timedelta(days=1),end,'flexible') for c in candidate['categories']):options+=['Flexible allowance','Custom weekly reduction']
            if any(available_events(candidate,c,today+timedelta(days=1),end,'scheduled') for c in candidate['categories']):options.append('Scheduled payment')
            future=[e for e in result(candidate,accounting=False)[0] if e.get('project_id') and not e['paid'] and today<e['date']<end and e['amount']>0]
            if any(not plan_category_conflict(candidate,[e for e in future if e['project_id']==identity]) for identity in {e['project_id'] for e in future}):options.append('Planned expense')
            options.append('Accept lower projected savings')
            if row['type'] not in options:row['type']=options[0]
            if row.get('chosen') or wf.get('old_record'):
                with st.popover('Change method',key=prefix+':change_method'):
                    kind=st.radio('How to cover it',options,index=options.index(row['type']) if row.get('chosen') or wf.get('old_record') else None,format_func=lambda t:{'Accrued contingency':'Use available contingency','Flexible allowance':'Reduce another category','Scheduled payment':'Reduce a scheduled payment','Planned expense':'Adjust a planned expense','Custom weekly reduction':'Set a custom weekly reduction','Accept lower projected savings':'Accept lower projected savings'}[t],key=prefix+':type',on_change=changed)
            else:
                kind=st.radio('How to cover it',options,index=options.index(row['type']) if row.get('chosen') or wf.get('old_record') else None,format_func=lambda t:{'Accrued contingency':'Use available contingency','Flexible allowance':'Reduce another category','Scheduled payment':'Reduce a scheduled payment','Planned expense':'Adjust a planned expense','Custom weekly reduction':'Set a custom weekly reduction','Accept lower projected savings':'Accept lower projected savings'}[t],key=prefix+':type',on_change=changed)
            if kind is None:st.caption('Choose how you want to cover this overspend. Nothing is changed until you confirm.');return
            row['type']=kind
            if kind=='Accept lower projected savings':
                wf['rows']=[r for r in wf['rows'] if r['id']!=row['id']];st.rerun()
            if kind=='Accrued contingency':
                cap=min(unresolved,reserve_balance(candidate)['available']);row['response']='Use contingency';row['configured']=False
                if cap<=0:st.info('No accrued, uncommitted contingency is available. Choose a future spending source or remove this row and accept the impact.')
                else:
                    row['amount']=st.number_input('Contingency amount ($)',min_value=.01,max_value=float(cap),value=float(min(money(row.get('amount') if row.get('amount') is not None else cap),cap)),step=1.0,key=prefix+':reserve:'+str(cap));row['configured']=True
                    if row['amount'] is None:st.info('Enter the amount you want to use.');row['configured']=False;valid=False;continue
                    from actions_ui import funding_amounts
                    funding_amounts(st,reserve_balance(candidate)['available'],money(row['amount']),unresolved,today,end,'Contingency available today')
                    st.caption('Reallocates already-accrued reserve; it is not new savings or a future promise.')
            elif kind in ('Flexible allowance','Custom weekly reduction','Scheduled payment'):
                row['response']='Offset another spending category'
                render_category_configuration(st,candidate,row,prefix+':method:'+kind,start,end,today,unresolved,fixed_mode='flexible' if kind!='Scheduled payment' else 'scheduled',force_custom=kind=='Custom weekly reduction')
            else:
                row['response']='Adjust a planned one-off expense'
                render_plan_configuration(st,candidate,row,prefix,start,end,today,unresolved)
            if row.get('configured'):selections.append(current_selection(row))
            else:valid=False
    try:
        preview,records,accepted=recovery_decision_preview(state,source,selections,wf.get('replace_id'))
        after=summarize_savings(preview);before=summarize_savings(state)
        from payment_rescheduling import financial_position
        cash_before=financial_position(state);cash_after=financial_position(preview)
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
            for label,amount in [('Original overspend',original),('Covered by this plan',allocated),('Lower savings accepted',accepted_now),('Still needs a decision',max(Decimal(0),original-allocated-accepted_now))]:st.write(label+': **'+dollars(amount)+'**')
            from savings_projection import project
            projection=project(preview['draft'],summarize(result(preview)[0],start,end),cash_after['closing'])
            st.metric('Projected total savings','Unknown' if projection['total'] is None else dollars(projection['total']))
            st.write('Savings this period after reserve: **'+dollars(after)+'** · change '+dollars(after-before))
            if cash_before['closing'] is None:st.caption('Cash-position impact unavailable: opening cash has not been provided. No bank balance is assumed.')
            else:
                st.write('Projected closing cash: **'+dollars(cash_before['closing'])+' → '+dollars(cash_after['closing'])+'**')
                st.caption('Lowest projected cash: '+dollars(cash_before['lowest'])+' → '+dollars(cash_after['lowest'])+'. Forecast only; not verified bank balances.')
            balance=reserve_balance(preview)
            st.caption('Contingency remaining '+dollars(before_reserve['available'])+' → '+dollars(balance['available'])+' · committed '+dollars(balance['committed'])+'. Planned reductions are not verified savings.')
            for record in records:
                if record.get('action')=='Postpone' and not record['impact']:st.caption('Postponing inside this financial year changes timing, not annual savings.')
        if wf.get('replace_id'):st.caption('Only the selected commitment is replaced; other commitments and all locked budget versions stay intact.')
        if st.button('Split across another option',disabled=not valid or allocated+prior_accepted>=original,key=key+':add',width='stretch'):
            wf['rows'].append(new_row(wf.get('grouping','Week')));st.rerun()
        if st.button('Confirm decision',type='primary',disabled=not valid or not ack,key=key+':confirm',width='stretch'):
            state.update(preview);state.pop('action_workflow',None);state['action_notice']='Decision confirmed. Remaining impact accepted; pending recovery is not realised savings.';st.rerun()
    except ValueError as error:
        st.warning(str(error));st.caption('Edit or remove an invalid source. Nothing has been saved.')


def summarize_savings(state):
    from planning import result,summarize
    return summarize(result(state)[0],date.fromisoformat(state['draft']['start']),end=period_end(state))['savings']
