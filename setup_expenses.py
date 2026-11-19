"""One prompted expense at a time, plus direct maintenance of existing entries."""
from copy import deepcopy
from datetime import date
from draft_inputs import field,saved,applied,discard,buffer
from setup_model import STEPS,setup_state,considered
from planning import replace_draft,uid
from finance import FREQUENCIES,money
from guided_ui import smart_frequency
from category_catalog import tag


def remove_expense(state,existing):
    from expense_workflow import invalidate,restore
    candidate=deepcopy(state['draft']);candidate['expenses']=[e for e in candidate['expenses'] if e['id']!=existing['id']]
    replace_draft(state,candidate);state['removed_expense']=deepcopy(existing)
    state.get('setup_buffers',{}).pop('expenses:'+existing['id'],None);invalidate(state)
    for row in considered(state)[0]:
        if row['id']==existing.get('source_id') or state.get('expense_workflow',{}).get('links',{}).get(row['id'])==existing['id']:restore(state,row)


def undo_expense_removal(state):
    from expense_workflow import invalidate
    removed=state['removed_expense'];candidate=deepcopy(state['draft'])
    if any(e['id']==removed['id'] for e in candidate['expenses']):raise ValueError('That expense has already been restored.')
    candidate['expenses'].append(deepcopy(removed));replace_draft(state,candidate);state.pop('removed_expense');invalidate(state)


def expense_editor(st,state,key,existing=None,suggestion=None,kind='expenses',advance=None,draft_scope=None,save_label=None):
    defaults=existing or suggestion or {};identity=(existing or suggestion or {}).get('id','new')
    scope=draft_scope or kind+':'+identity;step=STEPS[0] if kind=='income' else STEPS[1]
    if kind=='expenses':
        associated=(suggestion or {}).get('id') or (existing or {}).get('source_id')
        if existing and not associated:
            associated=next((sid for sid,e in considered(state)[1].items() if e['id']==existing['id']),None)
        buffer(state,scope,step)['_suggestion_id']=associated
        buffer(state,scope,step)['_workflow']=state.get('expense_workflow',{}).get('workflow')
    def f(widget,label,name,value,**kw):return field(st,state,scope,step,widget,label,name,value,**kw)
    name=f('text_input','Income name' if kind=='income' else 'Expense name','name',defaults.get('name',''))
    category=defaults.get('category','Other') if kind=='expenses' else 'Income';sub=defaults.get('subcategory','')
    if kind=='expenses':category=f('selectbox','Category','category',category,options=state['categories'])
    amount=f('number_input','Amount per payment ($)','amount',float(defaults.get('amount',0)),min_value=0.0,step=10.0)
    frequency=f('selectbox','Frequency','frequency',defaults.get('frequency','Weekly' if defaults.get('allowance') else smart_frequency(name)),options=list(FREQUENCIES[:-1]))
    allowance=False;method=None
    if kind=='expenses':
        title=defaults.get('name','').casefold()
        suggested=defaults.get('allowance',False) or ('allowance' not in defaults and not existing and any(word in title for word in ('grocer','dining','food','personal spending','shopping')) and not any(word in title for word in ('insurance','subscription','finance')))
        expense_type=f('radio','Expense type','type','Flexible allowance' if suggested else 'Scheduled bill',options=['Flexible allowance','Scheduled bill'],horizontal=True,help='An allowance funds day-to-day spending; a bill stays on its due date.')
        allowance=expense_type=='Flexible allowance'
    first=f('date_input','First income date' if kind=='income' else 'First payment date' if not allowance else 'Allowance start date','first',date.fromisoformat(defaults.get('first_payment') or state['draft']['start']))
    account='';member='Household'
    with st.expander('Advanced details'):
        if allowance:
            method=f('selectbox','Weekly allocation','allocation_method',defaults.get('allocation_method','calendar' if existing and defaults.get('allowance') else 'consistent'),options=['consistent','calendar'],format_func=lambda x:'Consistent weekly allowance' if x=='consistent' else 'Calendar-day allocation',help='Consistent: annual budget ÷ 52 for regular weeks; the final period receives the remaining annual allocation. Calendar-day: monthly amounts spread over actual days.')
        if kind=='expenses':
            account=f('text_input','Payment account (optional)','account',defaults.get('account','')) if not allowance else ''
            member=f('selectbox','Household member (optional)','member',defaults.get('member','Household'),options=['Household','Person A','Person B']) if allowance else 'Household'
            sub=f('text_input','Subcategory (optional)','sub',sub)
        estimated=f('checkbox','Payment date is approximate','estimated',bool(defaults.get('estimated',True)),help='Estimated dates are forecast placeholders, not confirmed due dates.')
        ends=f('checkbox','Has an end date','ends',bool(defaults.get('end_date')))
        end=f('date_input','Last payment date','end',date.fromisoformat(defaults.get('end_date') or state['draft']['start'])) if ends else None
    saved(st,state,scope);discard(st,state,scope)
    label=save_label or ('Save income' if kind=='income' else 'Save & Continue' if advance else 'Apply expense')
    if st.button(label,type='primary',key=key+':apply'):
        try:
            if not name.strip() or amount<=0:raise ValueError('Enter a name and a positive payment amount.')
            entry=dict(existing or {},id=(existing or {}).get('id',uid()),name=name.strip(),amount=money(amount),frequency=frequency,first_payment=str(first),end_date=str(end) if end else None,category=category,subcategory=sub,estimated=estimated,allowance=allowance,account=account,member=member,source_id=(existing or {}).get('source_id') or (suggestion or {}).get('id'))
            if allowance:entry['allocation_method']=method
            if kind=='expenses':tag(state,entry)
            candidate=deepcopy(state['draft']);candidate[kind]=[e for e in candidate[kind] if e['id']!=entry['id']]+[entry]
            replace_draft(state,candidate);applied(state,scope)
            if kind=='expenses':
                from expense_workflow import invalidate
                invalidate(state)
            if not existing:state['setup_buffers'].pop(scope,None)
            if advance:advance()
            else:state['setup_notice']='Applied to the draft forecast. Approved versions are unchanged.'
            st.rerun()
        except ValueError as error:st.error(str(error))
    if existing and st.button('Remove income' if kind=='income' else 'Remove expense',key=key+':remove'):
        candidate=deepcopy(state['draft']);candidate[kind]=[e for e in candidate[kind] if e['id']!=existing['id']]
        if kind=='expenses':state['removed_expense']=deepcopy(existing)
        try:
            replace_draft(state,candidate);state.get('setup_buffers',{}).pop(scope,None)
            if kind=='expenses':
                from expense_workflow import invalidate,restore
                invalidate(state)
                for row in considered(state)[0]:
                    if row['id']==existing.get('source_id') or state.get('expense_workflow',{}).get('links',{}).get(row['id'])==existing['id']:restore(state,row)
            st.rerun()
        except ValueError as error:st.error(str(error))


def income_editor(st,state,key):
    names={r['id']:r['name'] for r in state['draft']['income']}
    selected=st.selectbox('Income source',['new',*names],format_func=lambda x:'Add income' if x=='new' else names[x],key=key+':selected')
    expense_editor(st,state,key,existing=next((e for e in state['draft']['income'] if e['id']==selected),None),kind='income')


def finish_regular(st,state,key,rows,workflow):
    from setup_journey import set_stage,STAGES,workflow_ready
    from expense_workflow import FIXED
    if st.button('Save & Continue',type='primary',key=key+':finish'):
        if not workflow_ready(state,workflow):st.warning('Save or discard input drafts and add or skip outstanding suggestions in this step.')
        elif workflow==FIXED:set_stage(state,STAGES[3]);state['expense_workflow']['summary']=False;st.rerun()
        elif any(b.get('_dirty') and b['_step']==STEPS[1] for b in state.get('setup_buffers',{}).values()):st.warning('Save or discard all expense input drafts before continuing.')
        elif len(considered(state)[2])<len(rows):st.warning('Add or skip remaining suggestions in Fixed Expenses before continuing.')
        else:
            setup=setup_state(state);setup['regular_reviewed']=True;state['budget_ready']=True;state['expense_workflow']['summary']=False;set_stage(state,STAGES[4]);st.rerun()


def regular(st,state,key,workflow):
    """One editor, one primary action; no suggestion-card wall or shared selector."""
    from expense_workflow import (FIXED,VARIABLE,metadata,status,workflow_for,
        categories,skip,restore,legacy_candidates,link_existing)
    from setup_journey import STAGES,set_stage,workflow_ready
    from nestworth_design import line,empty
    setup=setup_state(state);data=metadata(state);data['workflow']=workflow
    rows,matched,_=considered(state)
    scoped=[r for r in rows if workflow_for(r,matched)==workflow]
    cursors=data.setdefault('guided_cursors',{});trail=data.setdefault('guided_trail',[])
    pending=lambda:[r for r in scoped if status(state,r) in ('Not Reviewed','Draft')]
    def open_item(identity,category=None,target=workflow,remember=True):
        if remember and cursors.get(workflow):trail.append((workflow,cursors[workflow],data.get('category',{}).get(workflow)))
        cursors[target]=identity
        if category:data['category'][target]=category
        data['nav_epoch']+=1
        if target!=workflow:set_stage(state,STAGES[2] if target==FIXED else STAGES[3])
    def advance():
        data['nav_epoch']+=1
        # Saving a changed type respects the actual saved record; no reclassification.
        remaining=pending()
        if remaining:
            following=remaining[0];open_item(following['id'],considered(state)[1].get(following['id'],following)['category'])
        elif workflow_ready(state,workflow):
            if workflow==FIXED:
                if cursors.get(workflow):trail.append((workflow,cursors[workflow],data['category'].get(workflow)))
                set_stage(state,STAGES[3]);cursors.pop(VARIABLE,None)
            elif len(considered(state)[2])==len(rows) and not any(b.get('_dirty') and b.get('_step')==STEPS[1] for b in state.get('setup_buffers',{}).values()):
                setup['regular_reviewed']=True;state['budget_ready']=True;set_stage(state,STAGES[4])
            else:cursors[workflow]='review'
        else:cursors[workflow]='review'
    selected=cursors.get(workflow)
    valid={r['id'] for r in rows}|{'entry:'+e['id'] for e in state['draft']['expenses']}|{'review'}
    if selected not in valid and not str(selected).startswith('custom:'):selected=None
    if selected is None:
        selected=pending()[0]['id'] if pending() else 'review';cursors[workflow]=selected
    suggestion=next((r for r in rows if r['id']==selected),None)
    existing=matched.get(selected) or next((e for e in state['draft']['expenses'] if 'entry:'+e['id']==selected),None)
    category=(existing or suggestion or {}).get('category',data['category'].get(workflow,categories(state,workflow)[0]))
    if str(selected).startswith('custom:'):category=str(selected)[len('custom:'):]
    data['category'][workflow]=category
    counts={label:sum(status(state,r)==label for r in scoped) for label in ('Added','Skipped','Draft','Not Reviewed')}
    st.progress((counts['Added']+counts['Skipped'])/max(1,len(scoped)),text=f"{counts['Added']} added · {counts['Skipped']} skipped · {counts['Draft']+counts['Not Reviewed']} remaining")
    st.subheader(category if selected!='review' else 'Expenses reviewed')
    if suggestion:st.caption('Expense '+str(scoped.index(suggestion)+1 if suggestion in scoped else 1)+' of '+str(len(scoped))+' · '+status(state,suggestion))
    if selected=='review':
        empty(st,'You’re up to date' if workflow_ready(state,workflow) else 'A few items need attention','Review saved expenses or resume a draft below.')
        if st.button('Continue to Variable Spending' if workflow==FIXED else 'Continue to Planned Expenses',type='primary',key=key+':complete'):
            if not workflow_ready(state,workflow):st.warning('Resume or discard your saved expense drafts in Review expenses before continuing.')
            elif workflow==VARIABLE and len(considered(state)[2])<len(rows):st.warning('Fixed expenses still need review. Use Setup menu to return to that step.')
            else:advance();st.rerun()
    else:
        ambiguous=suggestion and sum(e.get('source_id')==suggestion['id'] for e in state['draft']['expenses'])>1
        if ambiguous:st.warning('More than one saved expense references this suggestion. Open a specific record in Review expenses; none has been selected automatically.')
        else:
            if suggestion and not existing:
                for candidate in legacy_candidates(state,suggestion):
                    if st.button('Use existing '+candidate['name']+' · '+candidate['category']+' · $'+f"{candidate['amount']:,.2f}",key=key+':link:'+candidate['id']):
                        try:
                            link_existing(state,suggestion,candidate['id']);target=VARIABLE if candidate.get('allowance') else FIXED
                            open_item('entry:'+candidate['id'],candidate['category'],target);st.rerun()
                        except ValueError as error:st.warning(str(error))
            defaults=dict(suggestion or {},allowance=workflow==VARIABLE) if not existing else suggestion
            if not suggestion and not existing:defaults=dict(category=category,allowance=workflow==VARIABLE)
            scope=None if existing or suggestion else 'expenses:custom:'+workflow+':'+category
            with st.container(key='nw_editor_expense'):
                expense_editor(st,state,key+':single:'+str(selected),existing=existing,suggestion=defaults,advance=advance,draft_scope=scope,save_label='Save & Next')
            if suggestion and not existing and st.button('Skip',key=key+':skip'):
                try:skip(state,[suggestion],workflow);advance();st.rerun()
                except ValueError as error:st.warning(str(error))
    if st.button('Back',key=key+':back'):
        if trail:
            target,identity,prior=trail.pop();open_item(identity,prior,target,remember=False)
        else:set_stage(state,STAGES[1] if workflow==FIXED else STAGES[2])
        st.rerun()
    if st.button('Add another expense in '+category,key=key+':custom'):
        open_item('custom:'+category,category);st.rerun()
    with st.popover('Review expenses',key=key+':review:'+str(data['nav_epoch'])):
        st.caption('Saved records and explicit skips · draft amounts are not applied')
        for entry in state['draft']['expenses']:
            line(st,entry['name'],'$'+f"{entry['amount']:,.2f}",entry['category']+' · '+entry['frequency']+' · '+('Allowance' if entry.get('allowance') else 'Scheduled'))
            if st.button('Edit expense · '+entry['name'],key=key+':edit:'+entry['id']):
                target=VARIABLE if entry.get('allowance') else FIXED;open_item('entry:'+entry['id'],entry['category'],target);st.rerun()
            if st.button('Remove expense · '+entry['name'],key=key+':remove:'+entry['id']):remove_expense(state,entry);cursors[workflow]=None;st.rerun()
        for row in rows:
            current=status(state,row)
            if current in ('Skipped','Not Reviewed','Draft'):
                target=workflow_for(row,considered(state)[1])
                if st.button(('Restore skipped · ' if current=='Skipped' else 'Resume · ')+row['name'],key=key+':restore:'+row['id']):
                    if current=='Skipped':restore(state,row)
                    open_item(row['id'],row['category'],target);st.rerun()
        for scope,b in state.get('setup_buffers',{}).items():
            if scope.startswith('expenses:custom:') and b.get('_dirty'):
                if st.button('Resume expense draft · '+b.get('name','Custom expense'),key=key+':draft:'+scope):
                    target=b.get('_workflow',workflow);category_name=scope.split(target+':',1)[-1];open_item('custom:'+category_name,category_name,target);st.rerun()
        if state.get('removed_expense') and st.button('Undo expense removal',key=key+':undo'):
            undo_expense_removal(state);cursors[workflow]=None;st.rerun()
        if st.button('Skip remaining suggestions in this category',key=key+':skip_category'):
            try:skip(state,[r for r in scoped if r['category']==category],workflow);advance();st.rerun()
            except ValueError as error:st.warning(str(error))
        if st.button('Mark remaining suggestions not applicable',key=key+':skip_all'):
            try:skip(state,scoped,workflow);advance();st.rerun()
            except ValueError as error:st.warning(str(error))
    with st.popover('Custom category',key=key+':category'):
        from category_catalog import register
        scope='category:new';name=field(st,state,scope,STEPS[1],'text_input','Category name','name','')
        if st.button('Add category',key=key+':add_category'):
            try:
                if name.strip().casefold() in ('income','contingency'):raise ValueError('Choose a spending category name.')
                category_name=register(state,name)['name'];state['setup_buffers'].pop(scope,None);open_item('custom:'+category_name,category_name);st.rerun()
            except ValueError as error:st.warning(str(error))
        discard(st,state,scope,'Discard category draft')
