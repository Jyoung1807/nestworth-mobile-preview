"""Explicit, reversible future payment timing decisions, no amount edits."""
from datetime import date
from payment_rescheduling import preview,save,reverse
from finance import money

def render(st,state,key,events,selected_id=None):
    with st.expander('Reschedule payment',expanded=selected_id is not None):
        today=date.fromisoformat(state['tracking_date'])
        rows={e['id']:e for e in events if e['kind']=='expense' and not e.get('allowance') and not e['paid'] and e['date']>=today and e['amount']>0}
        if not rows:st.caption('No unpaid future payments are eligible. Recorded and historical payments stay unchanged.');return
        if selected_id is not None:rows={i:e for i,e in rows.items() if i==selected_id}
        if not rows:st.caption('This payment cannot be rescheduled.');return
        identity=st.selectbox('Payment to reschedule',list(rows),format_func=lambda i:rows[i]['name']+' · '+str(rows[i]['date'])+' · $'+f"{rows[i]['amount']:,.2f}",key=key+':payment')
        from budget_period import period_end
        from datetime import timedelta
        new_date=st.date_input('Revised payment date',value=rows[identity]['date'],min_value=today,max_value=period_end(state)-timedelta(days=1),key=key+':date:'+identity)
        scope=st.radio('Apply date change to',['This occurrence','This and future occurrences'],key=key+':scope',horizontal=True)
        try:
            p=preview(state,identity,new_date,'occurrence' if scope=='This occurrence' else 'future_series')
            st.caption(str(len(p['command']['moves']))+' payment(s) · amounts unchanged')
            for label,field in [('Additional period savings','additional_savings'),('Projected closing cash','closing'),('Lowest projected cash','lowest')]:
                before=p['before'][field];after=p['after'][field]
                st.write(label+': '+('Unknown' if before is None else '$'+f'{before:,.2f}'+' → $'+f'{after:,.2f}'))
            st.caption('Forecast only. No bank payment is moved and the approved budget is unchanged.')
            if st.button('Confirm reschedule',type='primary',key=key+':confirm'):
                save(state,identity,new_date,p['command']['scope']);st.rerun()
        except ValueError as error:st.caption(str(error))
        for command in state.get('payment_reschedules',[]):
            if selected_id is not None and not any(m['event_id']==selected_id for m in command['moves']):continue
            st.caption(command['name']+' · '+command['scope']+' · '+command['moves'][0]['old_date']+' → '+command['moves'][0]['new_date'])
            if st.button('Reverse reschedule',key=key+':reverse:'+command['id']):
                try:reverse(state,command['id'])
                except ValueError as error:st.warning(str(error))
                else:st.rerun()
