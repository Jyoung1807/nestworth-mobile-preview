"""Short household questions; optional details stay behind disclosure controls."""
from copy import deepcopy
from datetime import date
from draft_inputs import field,saved,applied,discard
from setup_model import STEPS,setup_state,apply_profile
from finance import FREQUENCIES,money
from planning import uid,replace_draft

TOPICS=('People','Home','Vehicles')


def household(st,state,key):
    setup=setup_state(state)
    topic=setup.get('household_section','People')
    if topic not in TOPICS:topic='People'
    st.caption('Household details · '+str(TOPICS.index(topic)+1)+' of 3 · '+topic)
    for section in TOPICS:
        if section!=topic and st.button('Edit '+section,key=key+':section:'+section):
            setup['household_section']=section;setup['journey_epoch']=setup.get('journey_epoch',0)+1;st.rerun()
    setup['household_section']=topic;scope='household:'+topic;step=STEPS[0];p=state['profile']
    def f(kind,label,name,default,**kw):return field(st,state,scope,step,kind,label,name,default,**kw)
    values={};candidate=deepcopy(state['draft'])
    if topic!='Income':st.subheader(topic)
    if topic=='People':
        from budget_period import BudgetPeriod
        bounds=BudgetPeriod.from_plan(state)
        if state['versions']:
            st.caption('Approved budget period · '+bounds.start.strftime('%d %b %Y')+' – '+bounds.inclusive_end.strftime('%d %b %Y')+' · locked')
        else:
            st.markdown('**Your budget period**')
            period_start=f('date_input','Budget start date','period_start',bounds.start,format='DD/MM/YYYY')
            duration=f('radio','Budget duration','duration',setup.get('period_preset','12 months'),options=['3 months','6 months','12 months','Custom dates'],horizontal=True)
            if duration=='Custom dates':
                period_end=f('date_input','Budget end date (inclusive)','period_end',bounds.inclusive_end,format='DD/MM/YYYY')
                selected=BudgetPeriod.selected(period_start,period_end) if period_end>=period_start else None
            else:selected=BudgetPeriod.preset(period_start,int(duration.split()[0]))
            if selected:
                st.caption('Through '+selected.inclusive_end.strftime('%d %b %Y')+' · allowances follow their actual cycle days; bills and pay keep their due dates.')
                candidate.update(start=str(selected.start),end_exclusive=str(selected.end))
                if not candidate.get('contingency_policy'):
                    from contingency_policy import default_policy
                    candidate['contingency_policy']=default_policy()
            else:st.warning('End date must be on or after the start date.')
        adults=f('number_input','Adults','adults',p['adults'],min_value=1,max_value=10)
        names=[]
        for i in range(adults):
            previous=p.get('adult_names',[])
            names.append(f('text_input',f'Adult {i+1} name (optional)',f'adult_name:{i}',previous[i] if i<len(previous) else ''))
        count=f('number_input','Children','count',len(p['ages']),min_value=0,max_value=20)
        children=[];animals=[]
        if count:
            st.markdown('**Children**')
            for i in range(count):
                old=p.get('children',[])[i] if i<len(p.get('children',[])) else {'age':p['ages'][i] if i<len(p['ages']) else None}
                name=f('text_input',f'Child {i+1} name (optional)',f'child_name:{i}',old.get('name',''))
                age=f('number_input',f'Child {i+1} age (optional)',f'child_age:{i}',old.get('age'),min_value=0,max_value=25)
                children.append(dict(id=old.get('id',f'child:{i}'),name=name or f'Child {i+1}',age=age))
        pets=f('number_input','Pets','pet_count',len(p.get('pets',[])),min_value=0,max_value=20)
        if pets:
            st.markdown('**Pets**')
            for i in range(pets):
                old=p.get('pets',[])[i] if i<len(p.get('pets',[])) else {}
                kind=f('selectbox',f'Pet {i+1} type',f'pet_kind:{i}',old.get('type','Dog'),options=['Dog','Cat','Bird','Fish','Other'])
                name=f('text_input',f'Pet {i+1} name (optional)',f'pet_name:{i}',old.get('name',''))
                animals.append(dict(id=old.get('id',f'pet:{i}'),type=kind,name=name or f'Pet {i+1}'))
        values=dict(adults=adults,adult_names=names,ages=[c['age'] if c['age'] is not None else 0 for c in children],children=children,pets=animals)
    elif topic=='Home':
        values['housing']=f('radio','Your home','housing',p['housing'],options=['Mortgage','Rent','Owned outright'])
        for label,name in [('Pool','pool'),('Garden','garden'),('Solar panels','solar'),('Battery','battery')]:values[name]=f('checkbox',label,name,bool(p.get(name)))
        with st.expander('Optional property details'):
            values['property_type']=f('selectbox','Property type','property_type',p.get('property_type','Not specified'),options=['Not specified','House','Apartment','Townhouse','Other'])
            values['bedrooms']=f('number_input','Bedrooms (0 if unspecified)','bedrooms',int(p.get('bedrooms',0)),min_value=0,max_value=20)
            values['bathrooms']=f('number_input','Bathrooms (0 if unspecified)','bathrooms',float(p.get('bathrooms',0)),min_value=0.0,max_value=20.0,step=.5)
            values['suburb']=f('text_input','Suburb (optional, fictional)','suburb',p.get('suburb',''))
            values['postcode']=f('text_input','Postcode (optional, fictional)','postcode',p.get('postcode',''))
            values['notes']=f('text_area','Other household needs (optional)','notes',p.get('notes',''))
            st.caption('Notes are for reference; they do not automatically create expense suggestions.')
    elif topic=='Vehicles':
        vehicles=[]
        for label,name,kind in [('Cars','cars','Car'),('Boats','boats','Boat'),('Caravans','caravans','Caravan')]:
            count=f('number_input',label,name,int(p.get(name,0)),min_value=0,max_value=20);values[name]=count
            for i in range(count):
                identity=f'{name}:{i}';old=next((v for v in p.get('vehicles',[]) if v['id']==identity),{})
                st.markdown('**'+old.get('name',f'{kind} {i+1}')+'**')
                title=f('text_input','Vehicle name (optional)','name:'+identity,old.get('name',f'{kind} {i+1}'))
                finance=f('checkbox','Finance repayments','finance:'+identity,bool(old.get('finance')))
                vehicles.append(dict(id=identity,type=kind,name=title or f'{kind} {i+1}',finance=finance))
        values['vehicles']=vehicles
        with st.expander('Other assets'):
            values['other_assets']=f('text_input','Other assets (optional)','other_assets',p.get('other_assets',''))
            st.caption('Asset notes do not automatically generate expense suggestions.')
    saved(st,state,scope);discard(st,state,scope)
    index=TOPICS.index(topic)
    if st.button('Back',disabled=index==0,key=key+':previous'):
        setup['household_section']=TOPICS[index-1];setup['journey_epoch']=setup.get('journey_epoch',0)+1;st.rerun()
    if st.button('Save & Continue',type='primary',key=key+':continue'):
        try:
            if topic=='People' and not state['versions']:
                if selected is None:raise ValueError('Choose a valid budget period before continuing.')
                replace_draft(state,candidate)
                setup['period_preset']=duration
                state['tracking_date']=str(max(selected.start,min(date.fromisoformat(state.get('tracking_date',str(selected.start))),selected.inclusive_end)))
            apply_profile(state,values);applied(state,scope)
            if index<2:
                setup['household_section']=TOPICS[index+1];setup['journey_epoch']=setup.get('journey_epoch',0)+1
            else:
                if any(b.get('_dirty') for scope,b in state.get('setup_buffers',{}).items() if scope.startswith('household:')):raise ValueError('Save or discard the other household input drafts first.')
                setup['household_reviewed']=True;state['profile_complete']=True
                from setup_journey import set_stage,STAGES
                set_stage(state,STAGES[1])
            st.rerun()
        except ValueError as error:st.error(str(error))
