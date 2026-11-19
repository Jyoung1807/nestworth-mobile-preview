"""Consumer-facing setup forms; all state remains in the household demo session."""
from copy import deepcopy
from datetime import date
import pandas as pd
from finance import money, FREQUENCIES, add_months
from category_catalog import register,tag,normalized
from planning import uid, suggestions, replace_draft, project_payments, approve, result, summarize, aggregate


def dollars(value):
    return f'${value:,.2f}'


def update_plan(st,state,candidate):
    try:
        for collection in ('expenses','projects'):
            for row in candidate[collection]: tag(state,row)
        plans_changed=candidate['projects']!=state['draft']['projects']
        replace_draft(state,candidate)
        if plans_changed:state['plan_reviewed']=False
    except (ValueError,TypeError,KeyError) as error:
        st.error(str(error))
        return False
    return True


def categories(st,state,key):
    with st.expander('Add a custom category or subcategory'):
        with st.form(key+':category',clear_on_submit=True):
            parent=st.text_input('Category name')
            child=st.text_input('Subcategory (optional)')
            save=st.form_submit_button('Add category')
        if save:
            parent=parent.strip(); child=child.strip()
            if not parent or normalized(parent) in ('income','contingency'):
                st.error('Choose a category name other than Income or Contingency.')
            else:
                parent=register(state,parent,child)['name']
                if child and child not in state['subcategories'].setdefault(parent,[]): state['subcategories'][parent].append(child)
                st.rerun()


def entry_form(st,state,key,kind='expenses',suggestion=None,explicit=None,active_key=None):
    entries=state['draft'][kind]
    names={e['id']:e['name'] for e in entries}
    if explicit is None:
        selected=st.selectbox('Choose an income source to edit', ['new',*names],format_func=lambda x:'Add new' if x=='new' else names[x],key=key+':entry_select')
        existing=next((e for e in entries if e['id']==selected),{})
    else:
        existing=next((e for e in entries if e['id']==explicit),{})
        selected=existing.get('id','new')
    defaults=existing or suggestion or {}
    form_key=key+':entry:'+selected+':'+str(defaults.get('name','new'))
    start=date.fromisoformat(state['draft']['start'])
    allowance=False
    if kind=='expenses':
        payment_type=st.radio('What kind of expense?', ['Bill','Flexible spending allowance'],index=1 if defaults.get('allowance') else 0,key=form_key+':type',horizontal=True)
        allowance=payment_type=='Flexible spending allowance'
        st.caption('Allowances fund everyday spending across calendar days; bills appear in their payment week. For Groceries, select Flexible spending allowance and Monthly to spread a monthly budget over actual days.')
    timing=st.checkbox('Set a specific payment date',value=bool(defaults.get('first_payment')) and not allowance,key=form_key+':timing') if not allowance else False
    with st.form(form_key,clear_on_submit=True):
        name=st.text_input('What is it?',value=defaults.get('name',''))
        amount=st.number_input('Amount per payment ($)',min_value=0.0,value=float(defaults.get('amount',0)),step=10.0,key=form_key+':amount')
        options=['Weekly','Fortnightly','Monthly'] if allowance else [f for f in FREQUENCIES if f!='One-off']
        frequency=st.selectbox('How often?',options,index=options.index(defaults.get('frequency',smart_frequency(defaults.get('name','')))) if defaults.get('frequency',smart_frequency(defaults.get('name',''))) in options else 2)
        first=st.date_input('First payment date',value=date.fromisoformat(defaults.get('first_payment') or str(start))) if timing else start
        if allowance: st.caption('A spending limit, not a bill. Periods start with your budget; partial final periods are prorated. Unspent amounts do not roll over. Transactions are compared with this allocation, never added to it.')
        elif not timing: st.caption('Timing not set: payments are placed from the budget start for this draft. Add a specific date when known.')
        category=defaults.get('category','Other') if kind=='expenses' else 'Income'
        sub=defaults.get('subcategory','')
        with st.expander('Optional details · category, certainty and end date'):
            if kind=='expenses':
                category=st.selectbox('Category',state['categories'],index=state['categories'].index(category))
                sub=st.text_input('Subcategory (optional)',value=sub)
            estimated=st.radio('How certain is the amount?',['Estimated','Confirmed'],index=0 if defaults.get('estimated',True) else 1,horizontal=True)
            has_end=st.checkbox('Payments have an end date',value=bool(defaults.get('end_date')))
            last=st.date_input('Last payment date (only used when checked)',value=date.fromisoformat(defaults.get('end_date') or str(add_months(start,12))))
        save=st.form_submit_button('Save expense' if kind=='expenses' else 'Save income source',key=form_key+':save')
    if amount>0:
        from planning import scheduled_events
        preview=deepcopy(state['draft']);preview[kind]=[dict(id='preview',name=name or 'Expense',amount=amount,frequency=frequency,first_payment=str(first),category=category,allowance=allowance)]
        dates=[e for e in scheduled_events(preview) if e['item_id']=='preview']
        st.caption('Annual equivalent: '+dollars(sum((e['amount'] for e in dates),money(0))))
        if timing:st.caption('Expected payments: '+', '.join(str(e['date'])+' '+dollars(e['amount']) for e in dates[:3]))
    if save:
        if not name.strip() or amount<=0:
            st.error('Give this payment a name and an amount greater than zero.')
        else:
            item={'id':existing.get('id',uid()),'name':name.strip(),'amount':amount,'frequency':frequency,
                  'first_payment':str(first),'end_date':str(last) if has_end else None,'category':category,
                  'subcategory':sub.strip(),'estimated':estimated=='Estimated','allowance':allowance,
                  'source_id':existing.get('source_id') or (suggestion or {}).get('id')}
            candidate=deepcopy(state['draft'])
            candidate[kind]=[e for e in entries if e['id']!=item['id']]+[item]
            if update_plan(st,state,candidate):
                if sub.strip() and sub.strip() not in state['subcategories'].setdefault(category,[]): state['subcategories'][category].append(sub.strip())
                if suggestion: state['skipped']=[x for x in state['skipped'] if x not in (suggestion['id'],suggestion['name'])]
                if active_key: st.session_state[active_key]=item['id']
                st.rerun()
    if existing and st.button('Remove this expense' if kind=='expenses' else 'Remove this income source',key=form_key+':remove'):
        candidate=deepcopy(state['draft']); candidate[kind]=[e for e in entries if e['id']!=selected]
        if kind=='expenses':quick_remove(state,selected);st.rerun()
        elif update_plan(st,state,candidate):st.rerun()


def profile(st,state,key):
    steps=['People','Your home','Getting around','Income','Goals & review']
    choice=st.radio('Setup step',steps,horizontal=True,key=key+':profile_step')
    index=steps.index(choice)
    st.progress((index+1)/len(steps),text=f'Step {index+1} of {len(steps)} · revisit any step to make changes')
    p=state['profile']
    if index==0:
        st.subheader('Who lives with you?')
        adults=st.number_input('Adults',min_value=1,max_value=10,value=p['adults'],key=key+':adults')
        children=st.number_input('Children',min_value=0,max_value=10,value=len(p['ages']),key=key+':children')
        ages=[st.number_input(f'Child {i+1} age',min_value=0,max_value=25,value=p['ages'][i] if i<len(p['ages']) else 0,key=key+f':age{i}') for i in range(children)]
        child_rows=[]
        for i,age in enumerate(ages):
            old=p.get('children',[])[i] if i<len(p.get('children',[])) else {}
            name=st.text_input(f'Child {i+1} name (optional, fictional)',value=old.get('name',f'Child {i+1}'),key=key+f':childname{i}')
            child_rows.append({'id':old.get('id',f'child:{i}'),'name':name or f'Child {i+1}','age':age})
        st.subheader('Pets are family too')
        count=st.number_input('Number of pets',min_value=0,max_value=20,value=len(p.get('pets',[])),key=key+':petcount')
        pets=[]
        for i in range(count):
            old=p.get('pets',[])[i] if i<len(p.get('pets',[])) else {}
            types=['Dog','Cat','Bird','Fish','Other']
            kind=st.selectbox(f'Pet {i+1} type',types,index=types.index(old.get('type','Dog')),key=key+f':pettype{i}')
            name=st.text_input(f'Pet {i+1} name (optional)',value=old.get('name',''),key=key+f':petname{i}')
            pets.append({'id':old.get('id',f'pet:{i}'),'type':kind,'name':name or f'Pet {i+1} ({kind})'})
        if st.button('Save people',key=key+':people_save'):
            p.update(adults=adults,ages=ages,children=child_rows,pets=pets); st.success('Saved. Choose the next step above.')
    elif index==1:
        st.subheader('Tell us about your home')
        housing=st.radio('Your home',['Mortgage','Rent','Owned outright'],index=['Mortgage','Rent','Owned outright'].index(p['housing']),key=key+':housing')
        pool=st.checkbox('We have a pool',value=p['pool'],key=key+':pool')
        garden=st.checkbox('We have a garden',value=p['garden'],key=key+':garden')
        solar=st.checkbox('We have solar panels',value=p.get('solar',False),key=key+':solar')
        if pool: st.caption('We will suggest pool maintenance, without assuming its cost.')
        if garden: st.caption('We will suggest garden care.')
        if st.button('Save home',key=key+':home_save'):
            p.update(housing=housing,pool=pool,garden=garden,solar=solar); st.success('Home preferences saved.')
    elif index==2:
        st.subheader('Vehicles & other things you own')
        values={}
        for label,field in [('Cars','cars'),('Boats','boats'),('Caravans','caravans')]:
            values[field]=st.number_input(label,min_value=0,max_value=20,value=p[field],key=key+':'+field)
        vehicles=[]
        for field,kind in [('cars','Car'),('boats','Boat'),('caravans','Caravan')]:
            for i in range(values[field]):
                identity=f'{field}:{i}'
                old=next((v for v in p.get('vehicles',[]) if v['id']==identity),{})
                with st.expander(old.get('name',f'{kind} {i+1}')):
                    name=st.text_input('Vehicle name (optional)',value=old.get('name',f'{kind} {i+1}'),key=key+':vehname:'+identity)
                    financed=st.checkbox('We make finance repayments for this vehicle',value=old.get('finance',False),key=key+':vehfinance:'+identity)
                vehicles.append({'id':identity,'type':kind,'name':name or f'{kind} {i+1}','finance':financed})
        values['vehicles']=vehicles
        values['other_assets']=st.text_input('Other assets (fictional examples only)',value=p['other_assets'],key=key+':other_assets')
        values['notes']=st.text_area('Other household needs (optional, fictional only)',value=p['notes'],key=key+':notes')
        if st.button('Save vehicles and needs',key=key+':assets_save'):
            p.update(values); st.success('Saved. Relevant vehicle costs will be suggested.')
    elif index==3:
        st.subheader('When does money come in?')
        st.caption('Use after-tax income. Enter the amount of each payment and its first expected date.')
        entry_form(st,state,key+':income','income')
        for source in state['draft']['income']:
            st.write(f"**{source['name']}** · {dollars(source['amount'])} · {source['frequency'].lower()}")
    else:
        st.subheader('What would you like to save?')
        if state['versions']:
            from planning import approved_savings
            st.caption('Approved savings baseline: '+dollars(approved_savings(state))+'. This aspiration is separate and cannot change the locked baseline.')
        with st.form(key+':goals'):
            goal=st.number_input('Savings aspiration ($)' if state['versions'] else 'Annual savings goal ($)',min_value=0.0,value=float(state['draft']['goal']),step=500.0)
            cash=st.number_input('Starting available cash ($, fictional)',min_value=0.0,value=float(state['draft']['opening_cash']),step=500.0)
            if st.form_submit_button('Save goals'):
                candidate=deepcopy(state['draft']); candidate.update(goal=goal,opening_cash=cash)
                if update_plan(st,state,candidate): st.success('Goals saved. Approved budget targets, if any, have not changed.')
        st.subheader('Your profile at a glance')
        st.write(f"{p['adults']} adults · {len(p['ages'])} children · {p['housing']}")
        if p['ages']: st.write('Children’s ages: '+', '.join(str(age) for age in p['ages']))
        st.write(f"{p['cars']} cars · {p['boats']} boats · {p['caravans']} caravans")
        st.caption('These are setup preferences, not actual Auth member records. No personal information is needed for this demo.')
        if p.get('vehicles'): st.write('Vehicles: '+', '.join(v['name'] for v in p['vehicles']))
        if p.get('pets'): st.write('Pets: '+', '.join(v['name']+' · '+v['type'] for v in p['pets']))
        if p.get('other_assets'): st.write('Other assets: '+p['other_assets'])
        features=[label for label,field in [('Pool','pool'),('Garden','garden'),('Solar','solar')] if p.get(field)]
        if features: st.write('Home features: '+', '.join(features))
        for source in state['draft']['income']: st.write(f"{source['name']} · {dollars(source['amount'])} {source['frequency'].lower()}")
        st.caption('We have prepared relevant expense cards for you. Add the amounts you know, estimate others, or skip what does not apply.')
        if st.button('Build My Budget',type='primary',key=key+':continue'):
            state['profile_complete']=True
            st.session_state[state['_nav_key']+':next']='Build Your Budget'
            st.rerun()


def plans(st,state,key):
    if st.button('Mark plans reviewed',key=key+':reviewed'):
        state['plan_reviewed']=True;st.success('Upcoming plans reviewed.')
    st.subheader('Your Plans')
    st.write('A holiday, a birthday or a renovation? Put known one-off costs on the calendar.')
    projects=state['draft']['projects']; names={p['id']:p['name'] for p in projects}
    focus=state.pop('plan_focus',None)
    if focus and names:st.session_state[key+':plan_select']=focus if focus in names else next(iter(names))
    selected=st.selectbox('Choose a plan',['new',*names],format_func=lambda x:'Add a plan' if x=='new' else names[x],key=key+':plan_select')
    existing=next((p for p in projects if p['id']==selected),{})
    commitment=next((r for r in state.get('plan_recoveries',[]) if r['project_id']==selected),None)
    if commitment:
        st.info('This plan has a '+commitment['action'].lower()+' decision in Actions. The latest forecast is shown below; its original source entries stay intact.')
        for event in sorted((e for e in result(state)[0] if e.get('project_id')==selected),key=lambda e:e['date']):
            st.write(str(event['date'])+' · '+dollars(event['amount'])+' · '+event['name'])
        if st.button('Manage plan decision in Actions',key=key+':manage'):
            state['action_list_view']='Commitments';st.session_state[state['_nav_key']+':next']='Actions Centre';st.rerun()
        return
    scope=key+':project:'+selected
    with st.expander('Optional: split this plan into multiple payments',expanded=len(existing.get('payments',[]))>1):
        mode=st.radio('How will you pay?',['One payment','Multiple payments'],index=1 if len(existing.get('payments',[]))>1 else 0,key=scope+':mode',horizontal=True)
        count=st.number_input('Number of payments',min_value=2,max_value=12,value=max(2,len(existing.get('payments',[]))),key=scope+':count') if mode=='Multiple payments' else 1
    precision=st.radio('When?',['Exact date','Approximate month'],horizontal=True,key=scope+':precision') if mode=='One payment' else 'Exact date'
    start=date.fromisoformat(state['draft']['start'])
    with st.form(scope+f':form:{mode}:{count}:{precision}'):
        name=st.text_input('What is the expense?',value=existing.get('name',''))
        total=st.number_input('Total project cost ($)',min_value=0.0,value=float(existing.get('total',0)),step=100.0)
        category=st.selectbox('Which category?',state['categories'],index=state['categories'].index(existing.get('category','Other')))
        with st.expander('Optional details'):
            subcategory=st.text_input('Subcategory (optional)',value=existing.get('subcategory',''))
        payments=[]
        for i in range(count):
            old=existing.get('payments',[])[i] if i<len(existing.get('payments',[])) else {}
            if mode=='Multiple payments':
                st.write(f'Payment {i+1}')
                description=st.text_input('Payment description',value=old.get('description',f'Payment {i+1}'),key=scope+f':desc{i}')
                amount=st.number_input('Payment amount ($)',min_value=0.0,value=float(old.get('amount',0)),key=scope+f':amount{i}')
            else: description='Payment'; amount=total
            if precision=='Approximate month':
                dates=[str(add_months(start,n)) for n in range(24)]
                olddate=old.get('date',str(start))[:7]+'-01'
                chosen=st.selectbox('Payment month',dates,index=dates.index(olddate) if olddate in dates else 0,key=scope+':month')
                day=date.fromisoformat(chosen)
                st.caption('For cash-flow calculations this is placed on the first of the month. Exact within-month liquidity is uncertain.')
            else:
                day=st.date_input('When will it be paid?',value=date.fromisoformat(old.get('date',str(start))),key=scope+f':date{i}')
            payments.append({'id':old.get('id',uid()),'description':description,'amount':amount,'date':str(day),'precision':precision})
        status=st.selectbox('Plan status',['Active','Cancelled'],index=1 if existing.get('status')=='Cancelled' else 0)
        save=st.form_submit_button('Save plan')
    if save:
        project={'id':existing.get('id',uid()),'name':name.strip(),'total':total,'category':category,'subcategory':subcategory,'payments':payments,'status':status}
        try:
            if total<=0: raise ValueError('Enter a total greater than zero')
            project_payments(project)
            candidate=deepcopy(state['draft']); candidate['projects']=[p for p in projects if p['id']!=project['id']]+[project]
            if update_plan(st,state,candidate): st.rerun()
        except ValueError as error: st.error(str(error))
    if existing and st.button('Remove plan',key=scope+':remove'):
        candidate=deepcopy(state['draft']); candidate['projects']=[p for p in projects if p['id']!=selected]
        if update_plan(st,state,candidate): st.rerun()
    if projects:
        with st.expander('All your plans'):
            for project in projects:
                st.write(f"**{project['name']}** · {dollars(project['total'])} · {len(project['payments'])} payment(s) · {project.get('status','Active')}")
        st.caption('Edit payment dates to postpone a plan. After approval, these edits affect only the forecast; the locked budget stays unchanged.')


def regular(st,state,key):
    st.subheader('Your regular expenses')
    st.caption('Work through each group. Add an amount or skip a cost that does not apply. Shared bills appear once; vehicles, children and pets have their own cards.')
    prepared=suggestions(state['profile'])
    existing=state['draft']['expenses']
    matched={}; claimed=set()
    for suggestion in prepared:
        item=next((e for e in existing if e.get('source_id')==suggestion['id']),None)
        if item is None:
            item=next((e for e in existing if e['id'] not in claimed and not e.get('source_id') and normalized(e['name'])==normalized(suggestion['name'])),None)
        if item: matched[suggestion['id']]=item; claimed.add(item['id'])
    def match(s): return matched.get(s['id'])
    complete=sum(bool(match(s)) or s['id'] in state['skipped'] or s['name'] in state['skipped'] for s in prepared)
    st.progress(complete/max(1,len(prepared)),text=f'{complete} of {len(prepared)} suggested costs considered')
    if st.button('Add a missing expense',key=key+':custom'):
        st.session_state[key+':active']='new'
    categories(st,state,key)
    if st.session_state.get(key+':active')=='new':
        st.subheader('Add a missing expense')
        entry_form(st,state,key+':custom_entry',explicit='new',active_key=key+':active')
    from category_catalog import DEFAULTS
    from accountability_ui import category_icon
    if state.get('removed_expense') and st.button('Undo expense removal',key=key+':undo'):
        candidate=deepcopy(state['draft']);candidate['expenses'].append(state.pop('removed_expense'))
        if update_plan(st,state,candidate):st.rerun()
    yearly=result(state)[0]
    ordering={category:i for i,category in enumerate(DEFAULTS)}
    groups=sorted(state['categories'],key=lambda c:(ordering.get(c,100),c))
    used=set()
    for ix,group in enumerate(groups):
        group_rows=[s for s in prepared if s['category']==group and (not match(s) or match(s)['category']==group)]
        total=sum((e['amount'] for e in yearly if e['kind']=='expense' and e['category']==group),money(0))
        with st.expander(category_icon(group)+' '+group+' · '+dollars(total)+'/year',expanded=ix==0):
            from category_catalog import color_for
            st.markdown('<div style="height:3px;background:'+color_for(group)+';border-radius:3px"></div>',unsafe_allow_html=True)
            if st.button('+ Add Expense',key=key+':addcategory:'+group):
                st.session_state[key+':active']='custom:'+group
            if st.session_state.get(key+':active')=='custom:'+group:
                entry_form(st,state,key+':customgroup:'+group,suggestion={'name':'','category':group},explicit='new',active_key=key+':active')
            last_entity=None
            dismissed=[s for s in group_rows if s['id'] in state.get('dismissed',[])]
            for s in dismissed:
                if st.button('Restore '+s['name'],key=key+':restore:'+s['id']):state['dismissed'].remove(s['id']);st.rerun()
            for s in [s for s in group_rows if s not in dismissed]:
                if s['group']!=last_entity and group in ('Vehicles','Children','Pets'):
                    st.write('**'+s['group']+'**'); last_entity=s['group']
                item=match(s)
                if item: used.add(item['id'])
                skipped=s['id'] in state['skipped'] or s['name'] in state['skipped']
                with st.container(border=True):
                    with st.container(key='expense_header_'+s['id'].replace(':','_')):
                        top,remove=st.columns([5,1])
                        top.write('**'+s['name']+'**')
                        removed=remove.button('×',key=key+':quick:'+s['id'],help='Remove expense' if item else 'Dismiss suggestion')
                    if removed:
                        if item:quick_remove(state,item['id'])
                        else:state.setdefault('dismissed',[]).append(s['id'])
                        st.rerun()
                    if item and normalized(item['name'])!=normalized(s['name']): st.caption('Saved as '+item['name']+'. Review this cost after your profile changes.')
                    st.caption(f"{dollars(item['amount'])} · {item['frequency'].lower()} · {'allowance' if item.get('allowance') else 'bill'}" if item else 'Skipped for now' if skipped else 'Incomplete · amount not entered')
                    left,right=st.columns(2)
                    if left.button('Edit' if item else 'Add amount',key=key+':edit:'+s['id']):st.session_state[key+':active']=item['id'] if item else s['id']
                    if not item and right.button('Revisit' if skipped else 'Skip',key=key+':skip:'+s['id']):
                        if skipped:state['skipped']=[x for x in state['skipped'] if x not in (s['id'],s['name'])]
                        else:state['skipped'].append(s['id'])
                        st.rerun()
                    if st.session_state.get(key+':active') in (s['id'],item['id'] if item else s['id']):
                        entry_form(st,state,key+':card:'+s['id'],suggestion=s,explicit=item['id'] if item else s['id'],active_key=key+':active')
            for item in [e for e in existing if e['category']==group and e['id'] not in used]:
                used.add(item['id'])
                with st.container(key='expense_header_'+item['id']):
                    title,remove=st.columns([5,1])
                    title.write(f"**{item['name']}** · {dollars(item['amount'])} · {item['frequency'].lower()}")
                    if remove.button('×',key=key+':quickextra:'+item['id'],help='Remove '+item['name']):quick_remove(state,item['id']);st.rerun()
                if st.button('Edit expense',key=key+':extra:'+item['id']):st.session_state[key+':active']=item['id']
                if st.session_state.get(key+':active')==item['id']:
                    entry_form(st,state,key+':extraform:'+item['id'],explicit=item['id'],active_key=key+':active')
    with st.expander('Advanced: edit recurring expenses as a table'):
        if existing:
            frame=pd.DataFrame(existing)
            frame['end_date']=frame['end_date'].fillna('') if 'end_date' in frame else ''
            edited=st.data_editor(frame,disabled=['id','source_id','category_id','subcategory_id'],hide_index=True,key=key+':advanced',width='stretch',
                column_config={'category':st.column_config.SelectboxColumn(options=state['categories'],required=True),
                               'frequency':st.column_config.SelectboxColumn(options=[f for f in FREQUENCIES if f!='One-off'],required=True),
                               'amount':st.column_config.NumberColumn(min_value=0.01,required=True),
                               'category_id':None,'subcategory_id':None,'source_id':None,'id':None})
            if st.button('Save table changes',key=key+':table_save'):
                candidate=deepcopy(state['draft']); candidate['expenses']=edited.to_dict('records')
                if update_plan(st,state,candidate): st.rerun()
        else: st.info('Add your first expense using a card above.')


def review(st,state,key):
    from spending_ui import compare_and_finalise
    compare_and_finalise(st,state,state.get('spending',[]),key)


def builder(st,state,key):
    if state['versions']: st.info('A budget is locked. Changes here update your forecast only. For an unexpected expense needing funding choices, use Your Year Ahead instead of entering it twice. Use Review & approve to formally save another budget version.')
    choice=st.radio('Build your budget',['Regular Expenses','Your Plans','Review & approve'],horizontal=True,key=key+':build_step')
    if choice=='Regular Expenses': regular(st,state,key+':regular')
    elif choice=='Your Plans': plans(st,state,key+':plans')
    else: review(st,state,key+':review')
    if st.button('Review My Spending',type='primary',key=key+':next_history'):
        state['budget_ready']=True
        st.session_state[state['_nav_key']+':next']='Review Your Spending'; st.rerun()


def smart_frequency(name):
    name=name.casefold()
    if 'rates' in name:return 'Quarterly'
    if 'registration' in name or 'insurance' in name:return 'Annual'
    if 'grocer' in name:return 'Weekly'
    return 'Monthly'


def quick_remove(state,item_id):
    candidate=deepcopy(state['draft'])
    item=next(e for e in candidate['expenses'] if e['id']==item_id)
    state['removed_expense']=deepcopy(item)
    candidate['expenses']=[e for e in candidate['expenses'] if e['id']!=item_id]
    replace_draft(state,candidate)
