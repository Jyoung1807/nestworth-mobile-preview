"""Seven-step Budget Builder over the existing financial and approval services."""
from budget_period import BudgetPeriod,period_end,month_starts
from copy import deepcopy
from datetime import date
from setup_model import STEPS,setup_state,requirements,approve_setup
from setup_journey import STAGES,current_stage,set_stage,stage_completion,stage_for_internal
from planning import result,summarize,replace_draft,aggregate
from finance import money,add_months
from budget_comparison import historical_totals,historical_rows,category_comparison,mark_reviewed,edit_historical


def goto(st,state,step):
    set_stage(state,step if step in STAGES else stage_for_internal(state,step));st.rerun()


def historical(st,state,key):
    setup=setup_state(state);transactions=state.get('spending',[]);start=date.fromisoformat(state['draft']['start'])
    st.subheader('Your household budget is taking shape!')
    st.caption('Compare the previous 12 months to spot forgotten costs, subscriptions and spending assumptions. This step is optional.')
    if st.button('Upload & Compare Spending',type='primary' if not setup.get('history_open') else 'secondary',key=key+':upload_open'):
        setup['history_upload']=True;st.rerun()
    if setup.get('history_upload'):
        st.caption('CSV · UTF-8 · up to 2 MB / 10,000 rows. Columns: Date, Description, Amount; optional Category. Dates: YYYY-MM-DD or DD/MM/YYYY. Positive spending amounts only, without $ or commas; exclude income and refunds.')
        st.caption(f'Date range: {add_months(start,-12)} to {start} (end excluded). Use anonymised test data. Files stay in this household’s server session memory; nothing is saved to Supabase or a bank.')
        upload=st.file_uploader('Historical spending CSV',type=['csv'],max_upload_size=2,key=key+':csv')
        if upload:
            from history_import import preview_csv,import_csv
            try:
                preview=preview_csv(upload.getvalue(),start,state['categories'],transactions)
                counts={s:sum(r['status']==s for r in preview) for s in ('New','Possible duplicate','Already imported')}
                st.caption(f"{counts['New']} new · {counts['Possible duplicate']} possible duplicates · {counts['Already imported']} already imported")
                for item in preview[:5]:
                    row=item['record'];st.caption(row['date']+' · '+row['description']+' · $'+f"{row['amount']:,.2f}"+' · '+(row['category'] or 'Needs category')+' · '+item['status'])
                duplicates=st.checkbox('Include possible duplicates — these are separate legitimate expenses',key=key+':duplicates') if counts['Possible duplicate'] else False
                confirmed=st.checkbox('Confirm adding these historical records to this test household session',key=key+':confirm:'+__import__('hashlib').sha256(upload.getvalue()).hexdigest())
                if st.button('Import & Review',key=key+':import',disabled=not confirmed):
                    added=import_csv(state,upload.getvalue(),duplicates);setup.update(history_open=True,mode='Detailed Setup')
                    state['setup_notice']=f'{added} historical records added. Existing records and approved budgets are unchanged.';st.rerun()
            except ValueError as error:st.error(str(error))
    existing=historical_rows(transactions,start)
    if existing and not setup.get('history_open') and st.button('Review saved transactions',key=key+':open'):
        setup.update(history_open=True,mode='Detailed Setup');st.rerun()
    if setup.get('history_open'):
        totals=historical_totals(transactions,start)
        st.progress((len(existing)-totals['uncategorised'])/len(existing) if existing else 0.0,text=f"{len(existing)-totals['uncategorised']} of {len(existing)} historical records categorised")
        descriptions=sorted({r['description'] for r in existing})
        with st.expander('Assign a category to a merchant group'):
            if descriptions:
                merchant=st.selectbox('Merchant / description',descriptions,key=key+':merchant')
                category=st.selectbox('Group category',state['categories'],key=key+':category')
                if st.button('Apply category to matching records',key=key+':batch'):
                    state['history_batch_undo']=[deepcopy(r) for r in existing if r['description']==merchant]
                    for row in existing:
                        if row['description']==merchant:edit_historical(state,transactions,row['id'],category)
                    st.rerun()
            if state.get('history_batch_undo') and st.button('Undo merchant category change',key=key+':undo'):
                old={r['id']:r for r in state.pop('history_batch_undo')}
                for row in transactions:
                    previous=old.get(row['id'])
                    if previous is not None:row.clear();row.update(previous)
                st.rerun()
        from transaction_review import transaction_browser
        ordered=sorted(existing,key=lambda r:(not __import__('budget_comparison').needs_category(r),r['date']))
        transaction_browser(st,state,transactions,ordered,key+':records',True)
        outstanding=historical_totals(transactions,start)['uncategorised']
        partial=st.checkbox('Finish with outstanding categorisation',key=key+':partial',help='Unknown categories remain incomplete; approval does not certify a completed historical comparison.') if outstanding else False
        if st.button('Save & Continue',type='primary',key=key+':reviewed'):
            if outstanding and not partial:st.warning('Categorise the remaining records, explicitly retain incomplete history, or Skip for Now.')
            else:
                setup.update(history_choice='reviewed_partial' if partial else 'reviewed',history_invitation=True)
                state['history_reviewed']=not partial;goto(st,state,STAGES[6])
    if st.button('Skip for Now',key=key+':decline'):
        setup.update(history_choice='declined',history_invitation=False);goto(st,state,STAGES[6])


def assumptions(st,state,key):
    from draft_inputs import field,saved,applied,discard
    setup=setup_state(state);scope='reserve-policy'
    dirty=state.get('setup_buffers',{}).get(scope,{}).get('_dirty')
    if setup['reserve_reviewed'] and not dirty:
        from contingency_ui import label
        st.caption('Contingency · '+label(state)+' · '+('Savings goal $'+f"{state['draft']['goal']:,.2f}" if state['draft']['goal'] else 'No savings goal set'))
        if st.button('Edit budget assumptions',key=key+':edit'):setup['reserve_reviewed']=False;st.rerun()
        return True
    st.markdown('**Budget assumptions**')
    from contingency_ui import inputs,current_policy
    def reserve_field(kind,label,name,default,**kwargs):return field(st,state,scope,STEPS[4],kind,label,name,default,**kwargs)
    try:policy,legacy_percent=inputs(st,state,key+':reserve',reserve_field)
    except ValueError as error:st.info(str(error));return False
    goal=field(st,state,scope,STEPS[4],'number_input','Savings aspiration (optional $)','goal',float(state['draft']['goal']) if state['draft']['goal'] else None,min_value=0.0,step=100.0)
    known=setup.get('opening_cash_known',state['draft']['opening_cash']>0)
    cash=field(st,state,scope,STEPS[4],'number_input','Opening cash (optional $)','cash',float(state['draft']['opening_cash']) if known else None,min_value=0.0,step=100.0)
    st.caption('Opening cash is money already available. Leave unknown balances blank; contingency earmarking never creates another expense.')
    opening_savings=field(st,state,scope,STEPS[4],'number_input','Identified opening savings (optional $)','opening_savings',float(state['draft']['opening_savings']) if state['draft'].get('opening_savings') is not None else None,min_value=0.0,step=100.0)
    st.caption('Savings is an explicit planning pot, separate from general cash. Do not add it to opening cash again if cash already includes these funds. Leave unknown balances blank.')
    target_options={'No target':None,'Additional savings this period':'additional_savings','Total savings at period end':'total_savings','Closing cash at period end':'closing_cash'}
    current_target=state['draft'].get('target') or {}
    target_label=next((label for label,kind in target_options.items() if kind==current_target.get('kind')),'No target')
    target_kind=field(st,state,scope,STEPS[4],'radio','Period-end target','target_kind',target_label,options=list(target_options))
    target_amount=field(st,state,scope,STEPS[4],'number_input','Target amount ($)','target_amount',float(current_target.get('amount',0)),min_value=0.0,step=100.0) if target_options[target_kind] else None
    saved(st,state,scope);discard(st,state,scope)
    if st.button('Save & Continue',type='primary',key=key+':apply'):
        try:
            candidate=deepcopy(state['draft']);candidate.update(goal=money(goal or 0),opening_cash=money(cash or 0))
            if legacy_percent is not None:candidate['contingency_pct']=legacy_percent
            if not state['versions'] and policy is not None:candidate['contingency_policy']=policy
            if opening_savings is not None:candidate['opening_savings']=money(opening_savings)
            else:candidate.pop('opening_savings',None)
            if target_options[target_kind]:
                if target_options[target_kind]=='total_savings' and opening_savings is None:raise ValueError('Identify opening savings before setting a total-savings target.')
                if target_options[target_kind]=='closing_cash' and cash is None:raise ValueError('Enter opening cash before setting a closing-cash target.')
                candidate['target']=dict(kind=target_options[target_kind],amount=money(target_amount))
            else:candidate.pop('target',None)
            proposed=deepcopy(state);replace_draft(proposed,candidate)
            if state['versions'] and policy is not None and policy!=current_policy(state):
                from contingency_policy import save_change
                save_change(proposed,policy)
            state.update(proposed);setup=state['setup'];applied(state,scope);setup.update(reserve_reviewed=True,opening_cash_known=cash is not None);st.rerun()
        except ValueError as error:st.error(str(error))
    return False


def approval(st,state,key):
    setup=setup_state(state);transactions=state.get('spending',[]);start=date.fromisoformat(state['draft']['start'])
    events=result(state)[0];summary=summarize(events,start,end=period_end(state))
    from savings_projection import project
    savings=project(state['draft'],summary)
    if savings['total'] is not None:
        st.metric('Projected total savings at period end','$'+f"{savings['total']:,.2f}",delta='+'+f"{savings['additional']:,.2f}"+' this budget period',delta_color='off')
        st.caption('Identified opening savings $'+f"{savings['opening']:,.2f}"+' · earmarked reserve $'+f"{savings['reserve']:,.2f}"+' · unallocated total $'+f"{savings['unallocated']:,.2f}")
    planned=sum((e['amount'] for e in events if e['kind']=='expense' and e.get('project_id') and start<=e['date']<period_end(state)),money(0))
    with st.container(border=True):
        for label,value in [('Budget-period net household income',summary['income']),('Budget-period regular expenses',summary['expenses']-planned),('Planned expenses',planned),('Contingency reserve',summary['contingency']),('Additional unallocated savings (after reserve)',summary['savings'])]:st.write(label+' · **$'+f'{value:,.2f}'+'**')
    if setup.get('opening_cash_known',state['draft']['opening_cash']>0):
        cash=aggregate(events,start,'Monthly',state['draft']['opening_cash'],end=period_end(state))
        for label,value in [('Opening cash',money(state['draft']['opening_cash'])),('Projected closing cash',cash[-1]['closing_cash']),('Lowest projected cash',min(r['lowest_cash'] for r in cash))]:st.write(label+' · **$'+f'{value:,.2f}'+'**')
        st.caption('Scenario cash projection, not a verified bank balance. Cash includes opening funds; annual savings is a separate result.')
    else:st.caption('Cash position unknown · add opening cash to see cash projections. Annual savings is not your bank balance.')
    target_projection=project(state['draft'],summary,cash[-1]['closing_cash'] if setup.get('opening_cash_known',state['draft']['opening_cash']>0) else None)['target']
    if target_projection:
        labels={'additional_savings':'Additional savings','total_savings':'Total savings balance','closing_cash':'Closing cash balance'}
        st.write(labels[target_projection['kind']]+' target · **$'+f"{target_projection['amount']:,.2f}"+'**')
        if target_projection['projected'] is None:st.caption('Outcome unknown until the relevant opening balance is identified.')
        else:st.caption('Projected outcome $'+f"{target_projection['projected']:,.2f}"+' · '+('$'+f"{abs(target_projection['variance']):,.2f}"+(' surplus' if target_projection['variance']>=0 else ' shortfall'))+' · not realised savings')
    if not assumptions(st,state,key+':assumptions'):return
    if setup['history_choice']=='declined':
        def declined():
            from model_guard import household_model_lock
            with household_model_lock(state['_nav_key']):setup['history_invitation']=bool(st.session_state.get(key+':decline_history'))
        st.checkbox('I choose to approve without comparing historical spending',value=setup['history_invitation'],key=key+':decline_history',on_change=declined)
        if st.button('Review historical spending instead',key=key+':history'):goto(st,state,STAGES[5])
    if setup['history_choice']=='reviewed':
        st.subheader('Historical differences')
        for row in category_comparison(state,transactions,state.get('variance_threshold',15)):
            if row['significant'] and not row['reviewed']:
                with st.container(border=True):
                    st.write(row['name']+' · historical $'+f"{row['baseline']:,.2f}"+' · proposed $'+f"{row['proposed']:,.2f}")
                    if st.button('Mark '+row['name']+' difference reviewed',key=key+':review:'+row['id']):mark_reviewed(state,row);st.rerun()
    needs=requirements(state,transactions)
    for i,(step,message) in enumerate(needs):
        st.caption(message)
        if step!=STEPS[5]:
            from setup_journey import requirement_stage
            target=requirement_stage(state,step)
            if st.button('Review '+target,key=key+':need:'+str(i)):goto(st,state,target)
    keep=st.checkbox('Keep my aspiration as a separate stretch goal',key=key+':stretch') if state['draft']['goal'] else False
    import hashlib,json
    signature=hashlib.sha256(json.dumps([state['draft'],state['decisions'],state.get('recoveries',[]),state.get('plan_recoveries',[]),len(state['versions']),needs],sort_keys=True,default=str).encode()).hexdigest()[:16]
    agree=st.checkbox('I understand this locks the calculated budget version',key=key+':agree:'+signature)
    if st.button('Approve new version' if state['versions'] else 'Approve budget',type='primary',disabled=not agree or bool(needs),key=key+':approve'):
        try:approve_setup(state,transactions,agree,keep)
        except ValueError as error:st.error(str(error))
        else:state['budget_complete']=True;st.session_state[state['_nav_key']+':next']='Home';st.rerun()
    if state['versions']:
        with st.expander('Locked budget versions'):
            for version in state['versions']:st.caption(f"Version {version['number']} · ${version['savings_baseline']:,.2f} · immutable")


def render_setup(st,state,key):
    setup=setup_state(state);stage=current_stage(state);done=stage_completion(state);index=STAGES.index(stage)
    st.progress(sum(done.values())/7)
    st.markdown('**Step '+str(index+1)+' of 7 · '+stage+'**')
    dirty=any(b.get('_dirty') for b in state.get('setup_buffers',{}).values())
    with st.popover('Setup menu',key=key+':menu:'+str(setup.get('journey_epoch',0))):
        st.caption('Input drafts saved in this household session · not yet applied' if dirty else 'Budget draft saved in this household session')
        # This optional jump control never drives the ordinary Save & Continue path.
        options=list(STAGES);jump=st.selectbox('Jump to step',options,index=index,key=key+':jump:'+str(setup.get('journey_epoch',0)))
        if jump!=stage:goto(st,state,jump)
    message=state.pop('setup_notice',None)
    if message:st.success(message)
    if stage not in (STAGES[0],STAGES[2],STAGES[3]) and st.button('Back',key=key+':back'):goto(st,state,STAGES[index-1])
    if index==0:
        from setup_household import household
        household(st,state,key+':household')
    elif index==1:
        from income_entry import income_editor
        income_editor(st,state,key+':income')
    elif index in (2,3):
        from setup_expenses import regular
        from expense_workflow import FIXED,VARIABLE
        regular(st,state,key+':regular',FIXED if index==2 else VARIABLE)
    elif index==4:
        from setup_plans import plans
        plans(st,state,key+':plans')
    elif index==5:historical(st,state,key+':history')
    else:approval(st,state,key+':approval')
