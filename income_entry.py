"""Discoverable household income; only confirmed net payment values enter maths."""
from copy import deepcopy
from datetime import date
from draft_inputs import field,saved,discard,applied
from income_tax import estimate_net,tax_year,FIRST_RATE,PER_YEAR
from finance import money
from planning import replace_draft,uid
from setup_model import STEPS


def income_editor(st,state,key):
    from setup_journey import set_stage,STAGES
    from setup_model import setup_state
    ui=state.setdefault('income_ui',{})
    people=['Person A','Person B','Other income']
    entries=state['draft']['income']
    st.caption(str(len(entries))+' income source'+('s' if len(entries)!=1 else '')+' saved · after-tax pay funds your budget')
    st.caption('Paid monthly? Enter monthly pay, not an annual salary.')
    for entry in entries:
        with st.container(border=True):
            st.markdown('**'+entry['name']+'**')
            st.caption(entry.get('person','Household')+' · $'+f"{entry['amount']:,.2f}"+' net · '+entry['frequency']+' · from '+entry.get('first_payment',state['draft']['start']))
            if st.button('Edit income · '+entry['name'],key=key+':edit:'+entry['id']):
                ui.update(selected=entry['id'],open=True,person_next=entry.get('person','Other income'));st.rerun()
            if st.button('Remove income · '+entry['name'],key=key+':remove:'+entry['id']):
                candidate=deepcopy(state['draft']);candidate['income']=[e for e in entries if e['id']!=entry['id']]
                try:
                    replace_draft(state,candidate);state.get('setup_buffers',{}).pop('income:'+entry['id'],None)
                    ui.update(selected='new',open=False,new_scope='income:new');st.rerun()
                except ValueError as error:st.error(str(error))
    opened=ui.get('open',False)
    if not opened and st.button('Add Income',key=key+':add'):
        ui.update(selected='new',open=True,new_scope='income:new',person_next=None);st.rerun()
    if not opened:
        pending=[b for scope,b in state.get('setup_buffers',{}).items() if scope.startswith('income:') and b.get('_dirty')]
        if pending:
            st.caption('Save or discard the pending income drafts before continuing.')
            for scope,draft in state.get('setup_buffers',{}).items():
                if not scope.startswith('income:') or not draft.get('_dirty'):continue
                identity=scope[len('income:'):];entry=next((e for e in entries if e['id']==identity),None)
                person=identity[len('new:'):] if identity.startswith('new:') else (entry or {}).get('person',ui.get('person','Person A'))
                if st.button('Resume income draft · '+draft.get('name',person),key=key+':resume:'+scope):
                    ui.update(selected=entry['id'] if entry else 'new',open=True,new_scope=scope,person_next=person);st.rerun()
        if st.button('Save & Continue',type='primary',key=key+':continue'):
            if not entries or pending:st.warning('Save at least one income source and save or discard pending income drafts.')
            else:set_stage(state,STAGES[2]);st.rerun()
        return
    selected=ui.get('selected','new')
    old=next((r for r in entries if r['id']==selected),None)
    # Recipient is part of the source draft, not the key of the form. Changing
    # ownership must never swap the entered amount/name into another draft.
    if old:scope='income:'+old['id']
    else:
        scope=ui.get('new_scope')
        if not scope:
            parked=next((scope for scope,b in state.get('setup_buffers',{}).items() if scope.startswith('income:new:') and b.get('_dirty')),None)
            scope=parked or 'income:new';ui['new_scope']=scope
    def f(kind,label,name,default,**kwargs):return field(st,state,scope,STEPS[0],kind,label,name,default,**kwargs)
    defaults=old or {};metadata=defaults.get('income_entry',{})
    income_type=f('selectbox','Income type','income_type',defaults.get('income_type','Salary / Wages'),options=['Salary / Wages','Business','Rental Property','Dividends / Investments','Other Income'])
    name=f('text_input','Income name','name',defaults.get('name',''))
    method=f('radio','Income amount is','method',metadata.get('method','Net (after tax)'),options=['Net (after tax)','Gross (before tax)'])
    frequency=f('selectbox','Pay frequency','frequency',defaults.get('frequency','Monthly'),options=list(PER_YEAR),help='The amount must cover one payment at this frequency. Annual salary with monthly pay needs a manual per-payment amount; separate salary-basis conversion is deferred.')
    amount=f('number_input','Net amount per payment ($)' if method.startswith('Net') else 'Gross amount per payment ($)','gross_entered' if method.startswith('Gross') else 'net_entered',float(metadata.get('entered',defaults.get('amount',0)) if metadata.get('method',method)==method else defaults.get('amount',0)),min_value=0.0,step=100.0)
    first=f('date_input','First income date','first',date.fromisoformat(defaults.get('first_payment') or state['draft']['start']))
    recipient_default=defaults.get('person') or (scope[len('income:new:'):] if scope.startswith('income:new:') else 'Choose recipient')
    if recipient_default=='Other income':recipient_default='Household / Other income'
    recipients=['Choose recipient','Person A','Person B','Household / Other income']
    recipient_names=dict(zip(('Person A','Person B'),state['profile'].get('adult_names',[])))
    recipient=f('selectbox','Recipient','recipient',recipient_default,options=recipients,format_func=lambda value:recipient_names.get(value) or value,help='Current supported labels are Person A, Person B or household/other income. No adult/child allocation or shared-funds rules are applied.')
    person='Other income' if recipient=='Household / Other income' else recipient
    st.caption('Choose the recipient explicitly. Income type and recipient are labels; they do not add tax or shared-funds rules.')

    net=money(amount);details={}
    if method.startswith('Gross'):
        default_year=tax_year(first)
        year=f('selectbox','Australian tax year','tax_year',metadata.get('tax_year',default_year if default_year in FIRST_RATE else '2026–27'),options=list(FIRST_RATE))
        levy=f('checkbox','Include estimated Medicare levy (flat 2%)','medicare',metadata.get('medicare',True))
        estimate=estimate_net(amount,frequency,year,levy);net=estimate['net_per_payment']
        st.info(f"Estimated net pay: ${net:,.2f} {frequency.lower()} · annual net ${estimate['annual_net']:,.2f}".replace('$',r'\$'))
        with st.expander('Tax estimate assumptions'):
            st.caption('Australian resident, full tax-free threshold and LITO. Excludes HELP, surcharge, deductions, super and other offsets. Flat Medicare estimate excludes low-income/family reductions. Estimate assumes this is the person’s total taxable income; use payslip net for multiple jobs or personal circumstances.')
        override=f('checkbox','Override estimated net income','override',metadata.get('override',False))
        if override:net=money(f('number_input','Net override per payment ($)','net_override',float(metadata.get('net_override',net)),min_value=0.0,step=100.0))
        details=dict(tax_year=year,medicare=levy,override=override,net_override=net,estimate=estimate)
        if tax_year(first)!=year:st.caption('Selected tax-year estimate differs from the payment start year. Later-year rates are not automatically applied; review or override net pay.')
    st.write(f'Budget uses **${net:,.2f} net per payment**. Gross amounts never enter the forecast as spendable income.')
    saved(st,state,scope);discard(st,state,scope)
    if st.button('Save income source',type='primary',key=key+':save:'+scope):
        try:
            if not name.strip() or net<=0:raise ValueError('Enter a name and positive net income.')
            if recipient=='Choose recipient':raise ValueError('Choose Person A, Person B or Household / Other income before saving.')
            entry=dict(defaults,id=defaults.get('id',uid()),name=name.strip(),amount=net,frequency=frequency,first_payment=str(first),category='Income',estimated=method.startswith('Gross'),person=person,income_type=income_type,income_entry=dict(method=method,entered=money(amount),**details))
            candidate=deepcopy(state['draft']);candidate['income']=[e for e in candidate['income'] if e['id']!=entry['id']]+[entry]
            replace_draft(state,candidate);applied(state,scope)
            if not old:state['setup_buffers'].pop(scope,None)
            ui.update(selected='new',open=False,new_scope='income:new')
            state['setup_notice']='Net income saved. Approved versions stay locked.';st.rerun()
        except ValueError as error:st.error(str(error))
    if st.button('Return to saved income',key=key+':close'):
        ui['open']=False;st.rerun()
