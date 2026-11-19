"""Forecast decisions and money movement, backed by replay rather than deltas."""
from mobile_ui import responsive_table
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
import pandas as pd
from finance import money, add_months
from planning import (uid, result, summarize, aggregate, change_decision,event_total)
from guided_ui import dollars


def frame(rows):
    return pd.DataFrame([{k:float(v) if isinstance(v,Decimal) else v for k,v in row.items()} for row in rows])


def funding(st,explanation):
    st.subheader(explanation['description']+' · '+dollars(explanation['amount']))
    sources={}
    for i,detail in enumerate(explanation['details']):
        sources[f"Offset {i+1}: {detail['label']}"]=float(detail['reduction'])
    sources['Reduction in savings']=float(max(Decimal(0),explanation['savings_impact']))
    if any(sources.values()):
        st.bar_chart(pd.DataFrame([sources],index=['Funding allocation']),horizontal=True,stack=True)
    if explanation['savings_impact']<0:
        st.success('Offsets exceed the new cost by '+dollars(-explanation['savings_impact'])+'. Forecast savings improve by this amount.')
    else: st.write('Remaining reduction in forecast savings: **'+dollars(explanation['savings_impact'])+'**')
    st.caption('This is a forecast reallocation, not a bank transfer. Percentages use the remaining unpaid allocation after earlier decisions.')
    with st.expander('See amounts, category changes and payment dates'):
        if explanation.get('category_changes'):
            st.write('What changes in each category')
            responsive_table(st,frame([{'Category':row['category'],'Original forecast':row['original'],'Revised forecast':row['revised'],
                                 'Change ($)':row['change'],'Change (%)':row['percent']} for row in explanation['category_changes']]),hide_index=True,width='stretch')
        if explanation['details']:
            responsive_table(st,frame([{'Source':d['label'],'Original remaining':d['basis'],'Revised within year':d['revised'],
                                 'Annual reduction':d['reduction'],'Change %':-d['change_percent']} for d in explanation['details']]),hide_index=True,width='stretch')
            with st.expander('See payment dates and calculation basis'):
                for detail in explanation['details']:
                    st.write(f"{detail['method']} · basis {dollars(detail['basis'])}")
                    responsive_table(st,frame(detail['changes']),hide_index=True,width='stretch')
    if explanation['timing_gap']>0 and explanation['offsets']>0:
        st.warning(dollars(explanation['timing_gap'])+' of the new cost is not released by its payment date. Later offsets may protect annual savings but cannot fund earlier cash needs. Check the cash-flow table.')


def decision_editor(st,state,key):
    existing={d['id']:d for d in state['decisions']}
    selected=st.selectbox('Add or change a decision',['new',*existing],format_func=lambda x:'New unexpected expense' if x=='new' else existing[x]['description'],key=key+':choose')
    current=existing.get(selected,{})
    scope=key+':edit:'+selected+':'+str(len(state['history']))
    start=date.fromisoformat(state['draft']['start']); end=add_months(start,12)
    st.subheader('What has changed?')
    description=st.text_input('Unexpected expense / description',value=current.get('description',''),key=scope+':desc')
    reason=st.text_input('Why are you changing the plan?',value=current.get('reason',''),key=scope+':reason')
    amount=st.number_input('New expense ($)',min_value=0.0,value=float(current.get('amount',0)),step=100.0,key=scope+':amount')
    day=st.date_input('Payment date',value=date.fromisoformat(current.get('date',str(start))),min_value=start,max_value=end,key=scope+':date')
    category=st.selectbox('Expense category',state['categories'],index=state['categories'].index(current.get('category','Other')),key=scope+':cat')
    choices=['Reduce savings','Fully offset','Partially offset']
    choice=st.radio('How would you like to fund it?',choices,index=choices.index(current.get('funding_choice','Partially offset' if current.get('offsets') else 'Reduce savings')),key=scope+':choice',horizontal=True)
    offsets=[]
    if choice!='Reduce savings':
        count=st.number_input('Number of funding changes',min_value=1,max_value=8,value=max(1,len(current.get('offsets',[]))),key=scope+':count')
        from category_catalog import category_id
        previous=state['decisions'][:list(existing).index(selected)] if selected in existing else state['decisions']
        source_events,_=result(state,decisions=previous)
        for i in range(count):
            old=current.get('offsets',[])[i] if i<len(current.get('offsets',[])) else {}
            with st.container(border=True):
                st.write(f'Funding change {i+1}')
                source_types=['A planned one-off expense','A regular expense','An entire spending category']
                old_kind=old.get('kind','')
                default_source=0 if old_kind in ('cancel_project','postpone_project','project_fixed','project_percent') else 1 if old_kind.startswith('expense_') else 2
                source_type=st.selectbox('What would you like to change?',source_types,index=default_source,key=scope+f':source{i}')
                if source_type==source_types[0]:
                    targets={p['id']:p['name'] for p in state['draft']['projects'] if p.get('status','Active')=='Active'}
                    prefix='project'
                elif source_type==source_types[1]:
                    targets={e['id']:e['name'] for e in state['draft']['expenses']}; prefix='expense'
                else:
                    targets={category_id(c):c for c in [*state['categories'],'Contingency']}; prefix='category'
                    if old.get('target')=='legacy_housing':targets['legacy_housing']='Former Housing (combined)'
                if not targets:
                    st.info('No matching expenses yet. Choose a regular expense or category, or add a plan in Build Your Budget.'); continue
                def remaining(target):
                    return sum((e['amount'] for e in source_events if not e['paid'] and start<=e['date']<end and e['kind']!='income'
                        and ((e.get('category_id')==target or (target=='legacy_housing' and e['category'] in ('Mortgage / Rent','Home & Property'))) if prefix=='category' else e.get('project_id')==target if prefix=='project' else e['item_id']==target)),Decimal(0))
                ids=list(targets); old_target=old.get('target')
                if prefix=='category' and old_target not in ids and old_target: old_target=category_id(old_target)
                target=st.selectbox('Which category?' if prefix=='category' else 'Which specific expense?',ids,
                    index=ids.index(old_target) if old_target in ids else 0,
                    format_func=lambda t:targets[t]+' — '+dollars(remaining(t))+' remaining',key=scope+f':target{i}:'+prefix)
                actions={'Reduce by a percentage':prefix+'_percent','Reduce by a dollar amount':prefix+'_fixed'}
                if prefix=='project': actions.update({'Cancel unpaid payments':'cancel_project','Postpone payments':'postpone_project'})
                action=st.radio('What would you like to do?',list(actions),
                    index=list(actions.values()).index(old_kind) if old_kind in actions.values() else 0,key=scope+f':action{i}:'+prefix,horizontal=True)
                kind=actions[action]; offset={'kind':kind,'target':target}
                st.caption('Remaining unpaid forecast before this decision: '+dollars(remaining(target))+'. The preview recalculates exact bases after each funding change.')
                if kind=='postpone_project':
                    offset['new_date']=str(st.date_input('New first unpaid payment date',value=date.fromisoformat(old.get('new_date',str(add_months(start,1)))),key=scope+f':postpone{i}'))
                    st.caption('All unpaid instalments move by the same number of days. A move within this year changes timing, not annual spending.')
                elif kind!='cancel_project':
                    offset['value']=st.number_input('Percentage reduction' if kind.endswith('_percent') else 'Reduction ($)',min_value=0.0,
                                                   max_value=100.0 if kind.endswith('_percent') else None,value=float(old.get('value',0)),key=scope+f':value{i}')
                offsets.append(offset)
    candidate={'id':current.get('id',uid()),'description':description,'reason':reason,'amount':amount,'date':str(day),'category':category,'offsets':offsets,'funding_choice':choice}
    preview=None
    if amount>0 and description.strip() and reason.strip():
        decisions=deepcopy(state['decisions'])
        ix=next((i for i,d in enumerate(decisions) if d['id']==candidate['id']),None)
        if ix is None: decisions.append(candidate)
        else: decisions[ix]=candidate
        try:
            _,explanations=result(state,decisions=decisions)
            preview=next(e for e in explanations if e['id']==candidate['id'])
            funding(st,preview)
        except ValueError as error: st.warning(str(error))
    if st.button('Save forecast decision',key=scope+':save'):
        try:
            if preview is None: raise ValueError('Complete a valid expense and funding plan first')
            if choice=='Fully offset' and preview['savings_impact']>0: raise ValueError('Add enough offsets to cover the expense, or choose Partially offset')
            change_decision(state,candidate)
        except ValueError as error: st.error(str(error))
        else: st.rerun()
    if current and st.button('Reverse this decision',key=scope+':reverse'):
        try: change_decision(state,remove_id=selected)
        except ValueError as error: st.error('Later decisions depend on this funding. Amend those decisions first. '+str(error))
        else: st.rerun()


def detailed_forecast(st,state,key,compact=False):
    start=date.fromisoformat(state['draft']['start'])
    st.caption(f'Scenario review date: {start:%d %b %Y}. The next 12 months are expectations, not observed transactions.')
    events,explanations=result(state); forecast=summarize(events,start)
    baseline=state['versions'][-1] if state['versions'] else None
    original_goal=baseline.get('savings_baseline',baseline['summary']['savings']) if baseline else money(state['draft']['goal'])
    a,b,c,d=st.columns(4)
    a.metric('Monthly income · average',dollars(forecast['income']/12))
    b.metric('Annual forecast income',dollars(forecast['income']))
    c.metric('Forecast savings',dollars(forecast['savings']),delta=dollars(forecast['savings']-original_goal))
    d.metric('Approved savings baseline' if baseline else 'Savings target · draft',dollars(original_goal))
    st.caption('Savings means income less household cash expenses and contingency reserve. It is not a bank balance, mortgage principal or an account transfer.')
    if not state['versions']:
        st.info('Your budget is still a draft. Complete Build your budget → Review & approve to lock the original plan and unlock forecast decisions.')
    selection=len(state['versions'])-1 if state['versions'] else 0
    if len(state['versions'])>1:
        selection=st.selectbox('Compare with budget version',list(range(len(state['versions']))),format_func=lambda x:f"Version {x+1}"+(' · original' if x==0 else ''),index=len(state['versions'])-1,key=key+':version')
    approved=state['versions'][selection] if state['versions'] else None
    if approved:
        summary=approved['summary']
        with st.expander('Approved budget versus latest forecast · details'):
            responsive_table(st,frame([{'Measure':'Income','Approved budget':summary['income'],'Latest forecast':forecast['income'],'Change':forecast['income']-summary['income']},
                                {'Measure':'Expenses','Approved budget':summary['expenses'],'Latest forecast':forecast['expenses'],'Change':forecast['expenses']-summary['expenses']},
                                {'Measure':'Contingency reserve','Approved budget':summary['contingency'],'Latest forecast':forecast['contingency'],'Change':forecast['contingency']-summary['contingency']},
                                {'Measure':'Savings','Approved budget':summary['savings'],'Latest forecast':forecast['savings'],'Change':forecast['savings']-summary['savings']}]),hide_index=True,width='stretch')
    period=st.radio('See your cash flow',['Annual','Monthly','Weekly'],index=1,horizontal=True,key=key+':period')
    grouping='Weekly' if period=='Weekly' else 'Monthly'
    rows=aggregate(events,start,grouping,state['draft']['opening_cash']); df=frame(rows)
    from dashboard_charts import savings_chart
    original=approved['events'] if approved else None
    savings_chart(st,events,original,start,original_goal,budget_label=f"Approved budget v{approved['number']}" if approved else 'Original budget',period=grouping)
    st.subheader('Monthly cash flow' if grouping=='Monthly' else 'Weekly cash flow')
    st.caption('Separate from cumulative savings: money arriving and payments due. No genuine actuals are connected.')
    if grouping=='Weekly':
        from household_calendar import household_timezone
        st.caption('Monday–Sunday weeks · '+household_timezone(state)+'. Financial-year totals and payment dates are unchanged.')
    from dashboard_charts import cash_flow_chart
    cash_flow_chart(st,rows)
    st.subheader('Projected available cash')
    cash_flow_chart(st,rows,cumulative=True)
    st.caption('Available cash includes your fictional starting cash. The second line also sets aside contingency. Negative cumulative savings alone does not mean you cannot pay bills; warnings use dated available cash.')
    st.metric('Forecast contingency remaining',dollars(forecast['contingency']))
    st.caption('Unallocated contingency after forecast funding reductions. No actual contingency spending has been recorded.')
    if approved:
        bud=aggregate(approved['events'],start,grouping)
        comparison=pd.merge(frame(bud)[['period','income','expenses']],df[['period','income','expenses']],on='period',suffixes=('_budget','_forecast'),how='outer').fillna(0)
        with st.expander('Budget versus forecast by period'):
            responsive_table(st,comparison,hide_index=True,width='stretch')
    with st.expander('Cash-flow detail · savings and available cash are different',expanded=False):
        responsive_table(st,df.drop(columns=['actuals']),hide_index=True,width='stretch')
        st.caption('Closing cash is opening fictional cash plus dated income less expenses. After reserve also sets aside contingency. Check weekly and minimum daily cash, not just the annual savings figure. Approximate-month plans use the first day of the month.')
    if any(r['lowest_cash']<0 for r in rows):
        st.warning('The dated scenario runs short of cash, even if annual savings look positive. Review payment dates, opening fictional cash and later offsets.')
    with st.expander('Upcoming significant expenses'):
        review_day=date.fromisoformat(state.get('tracking_date',str(start)))
        upcoming=sorted((e for e in events if e['kind']=='expense' and e['date']>=review_day and e['amount']>=500),key=lambda e:e['date'])[:12]
        if not upcoming:st.caption('No upcoming payments of $500 or more in this scenario.')
        for payment in upcoming:st.write(str(payment['date'])+' · '+payment['name']+' · **'+dollars(payment['amount'])+'**')
    if compact:
        from dashboard_charts import spending_charts
        spending_charts(st,events,start,key+':spending',drill=False)
    else:
        if not state['versions']: return
        st.divider()
        from accountability_ui import revision_editor
        revision_editor(st,state,key+':revision')
        with st.expander('Unexpected expense or planned expense funding'):
            decision_editor(st,state,key+':decision')
        if explanations:
            with st.expander('Saved funding decisions'):
                for explanation in explanations: funding(st,explanation)
        st.subheader('Your change history')
        st.caption('Session-only record of decisions and assumptions. Edits replay from source values, rather than repeatedly subtracting amounts.')
        for record in reversed(state['history']):
            previous={d['id']:d for d in record.get('before_decisions',[])}
            latest={d['id']:d for d in record.get('after_decisions',[])}
            changed=next((d for id,d in latest.items() if previous.get(id)!=d),None)
            if changed is None: changed=next((d for id,d in previous.items() if id not in latest),{})
            title=record.get('description',changed.get('description','Forecast update'))
            with st.expander(f"Change {record['sequence']} · {title}"):
                if changed.get('reason'): st.write(changed['reason'])
                before=record['before']['savings']; after=record['after']['savings']
                left,right=st.columns(2)
                left.metric('Savings before',dollars(before))
                right.metric('Savings after',dollars(after),delta=dollars(after-before))
                with st.expander('Advanced change details'):
                    st.json(json.dumps(record,default=str))


def overview(st,state,key,compact=False):
    from compact_dashboard import financial_outlook
    view=st.radio('Outlook view',['Summary','Change forecast','History'],horizontal=True,key=key+':view')
    if view=='Summary':
        financial_outlook(st,state,key+':summary')
        start=date.fromisoformat(state['draft']['start']);today=date.fromisoformat(state.get('tracking_date',str(start)))
        upcoming=sorted((e for e in result(state)[0] if e['kind']=='expense' and e['date']>=today and e['amount']>=500),key=lambda e:e['date'])[:3]
        if upcoming:
            st.write('**Upcoming significant payments**')
            for e in upcoming:st.caption(str(e['date'])+' · '+e['name']+' · '+dollars(e['amount']))
        return
    if view=='History':
        for record in reversed(state.get('forecast_history',[])):
            d=record['decision'];st.write(record['type']);st.caption(d.get('reason') or d.get('funded_category') or d.get('category') or d.get('name','Financial forecast update'))
            if d.get('amount') is not None:st.caption(str(record.get('date') or d.get('effective') or d.get('date',''))+' · '+dollars(d['amount'])+' · '+str(d.get('id',''))[:8])
        with st.expander('Earlier forecast funding and payment details'):detailed_forecast(st,state,key+':details',compact=compact)
        return
    if not state['versions']:st.info('Approve your budget in Setup before making forecast decisions.');return
    from accountability_ui import revision_editor
    revision_editor(st,state,key+':revision')
    with st.expander('Unexpected expense or planned expense funding'):
        decision_editor(st,state,key+':decision')
