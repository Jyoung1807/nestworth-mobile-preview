"""Categorise, exclude and compare without duplicating the draft budget."""
from mobile_ui import responsive_table
from datetime import date
import hashlib
import json
from decimal import Decimal
import altair as alt
import pandas as pd
from category_catalog import category_id,color_for
from finance import add_months,money
from planning import result,summarize
from budget_comparison import (UNKNOWN,needs_category,historical_rows,historical_totals,category_comparison,
                               mark_reviewed,edit_historical,finalise)


def dollars(value):return f'${value:,.2f}'


def transaction_editor(st,state,transactions,rows,key):
    if not rows:st.caption('No transactions in this selection.');return
    from transaction_review import transaction_browser
    transaction_browser(st,state,transactions,rows,key+':browser')
    with st.expander('Detailed transaction review',key=key+':advanced'):
        names={r['id']:f"{r['date']} · {r['description']} · {dollars(r['amount'])}" for r in rows}
        selected=st.selectbox('Transaction to review',list(names),format_func=names.get,key=key+':tx')
        row=next(r for r in rows if r['id']==selected)
        scope=key+':edit:'+selected
        with st.form(scope):
            choices=[UNKNOWN,*state['categories']]
            category=st.selectbox('Assign category',choices,index=choices.index(UNKNOWN if needs_category(row) else row['category']))
            sub=st.text_input('Subcategory (optional)',value=row.get('subcategory',''))
            allowances={e['id']:e['name'] for e in state['draft']['expenses'] if e.get('allowance')}
            allocation=st.selectbox('Link to a matching allowance (optional)',[None,*allowances],index=([None,*allowances].index(row.get('allowance_id')) if row.get('allowance_id') in allowances else 0),format_func=lambda id:allowances.get(id,'No allowance link')) if allowances else None
            excluded=st.checkbox('Exclude from normal spending baseline',value=row.get('exclude_baseline',False))
            reason=st.text_input('Reason for exclusion (optional)',value=row.get('exclusion_reason',''))
            save=st.form_submit_button('Save transaction review')
        if save:
            try:edit_historical(state,transactions,selected,category,sub,excluded,reason,allocation)
            except ValueError as error:st.error(str(error))
            else:st.rerun()
        with st.expander('All transactions in this selection'):
            responsive_table(st,pd.DataFrame(rows).drop(columns=['category_id','subcategory_id'],errors='ignore'),hide_index=True,width='stretch')


def review_spending(st,state,transactions,key,setup_review=False):
    start=date.fromisoformat(state['draft']['start']); rows=historical_rows(transactions,start)
    totals=historical_totals(transactions,start)
    focus=state.pop('spending_focus',None)
    options=['Current spending','Historical review',"Last Year's One-Offs"]
    if focus:
        st.session_state[key+':view']='Current spending' if focus.get('kind')=='transactions' else 'Historical review'
        if focus.get('category'):st.session_state[key+':filter']=focus['category']
        if focus.get('kind')=='categorisation':st.session_state[key+':filter']=UNKNOWN
    view=st.radio('Spending view',options,index=1 if setup_review else 0,key=key+':view')
    if view=='Current spending':
        current=state.get('period_transactions',[])
        st.caption('Fictional observed transactions. Amounts and dates are retained when you recategorise.')
        categories=sorted(set(state['categories'])|{r['category'] for r in current})
        selected=st.selectbox('Filter current category',['All categories',*categories],index=([None,*categories].index(focus['category']) if focus and focus.get('category') in categories else 0),key=key+':currentfilter')
        from transaction_review import transaction_browser
        transaction_browser(st,state,current,[r for r in current if selected=='All categories' or r['category']==selected],key+':current',False)
        return
    if view=="Last Year's One-Offs":
        st.metric('Explicitly excluded historical one-offs',dollars(totals['excluded']))
        st.caption('Review large purchases; exclusions require confirmation. Irregular bills still need future allowances.')
        inline_transactions(st,state,transactions,[r for r in rows if money(r['amount'])>=1000 or r.get('exclude_baseline')],key+':oneoffs')
        return
    st.subheader('Needs Categorising')
    st.write(f"**{totals['uncategorised']} transactions need a category** before you can approve your budget.")
    pending=[r for r in rows if needs_category(r)]
    if pending:transaction_editor(st,state,transactions,pending,key+':unknown')
    else:st.success('All historical example transactions have a category.')
    st.caption('Historical spending '+dollars(totals['full'])+' · adjusted baseline '+dollars(totals['adjusted'])+' · excluded '+dollars(totals['excluded']))
    frame=pd.DataFrame([{'month':r['date'][:7],'category':UNKNOWN if needs_category(r) else r['category'],'amount':float(r['amount'])} for r in rows],columns=['month','category','amount'])
    from dashboard_charts import category_scale
    # Accessible category buttons give deterministic toggle behaviour on desktop/mobile.
    selected=st.session_state.get(key+':filter')
    categories=sorted(frame.category.unique()) if not frame.empty else []
    if selected and selected not in categories:
        selected=None;st.session_state[key+':filter']=None
    with st.container(key='category_filters'):
        for n in range(0,len(categories),3):
            columns=st.columns(3)
            for col,name in zip(columns,categories[n:n+3]):
                if col.button(name,key=key+':filter:'+name,type='primary' if selected==name else 'secondary',width='stretch'):
                    st.session_state[key+':filter']=None if selected==name else name;st.rerun()
    if st.button('Clear category selection',key=key+':clear'):
        st.session_state[key+':filter']=None;st.rerun()
    st.caption('Tap a category to filter the list. Tap it again to show everything. The highlighted category is selected.')
    chart=alt.Chart(frame).mark_bar().encode(x=alt.X('month:O',title=None),y=alt.Y('sum(amount):Q',title='Full example spending ($)'),
        color=alt.Color('category:N',scale=category_scale(categories),title=None),
        opacity=alt.condition(alt.datum.category==selected,alt.value(1),alt.value(.25)) if selected else alt.value(1),
        tooltip=['month:O','category:N',alt.Tooltip('sum(amount):Q',format='$,.2f')])
    with st.expander('Historical category chart'):
        st.altair_chart(chart,width='stretch')
    filtered=[r for r in rows if not selected or (UNKNOWN if needs_category(r) else r['category'])==selected]
    st.subheader('Selected transactions' if selected else 'Historical transactions')
    transaction_editor(st,state,transactions,filtered,key+':records')
    with st.expander('Savings opportunities'):
        leisure=sum((money(r['amount']) for r in rows if r.get('category')=='Leisure' and not r.get('exclude_baseline')),Decimal(0))
        st.caption('A hypothetical 15% Leisure reduction is '+dollars(leisure*Decimal('.15'))+'. It is not automatically applied.')
        state['committed_savings']=st.number_input('Committed annual savings opportunity target ($)',min_value=0.0,value=float(state.get('committed_savings',1200)),key=key+':commitment')
    if not setup_review and st.button('Continue to Compare & Finalise',type='primary',key=key+':next'):
        state['history_reviewed']=True;st.session_state[state['_nav_key']+':next']='Compare & Finalise';st.rerun()


def compare_and_finalise(st,state,transactions,key):
    start=date.fromisoformat(state['draft']['start']);events,_=result(state);summary=summarize(events,start)
    totals=historical_totals(transactions,start)
    st.metric('Projected annual savings',dollars(summary['savings']))
    st.caption('Excluded historical one-offs: '+dollars(totals['excluded']))
    st.subheader('Does your budget reflect the way you spend?')
    if state['versions']:st.info('Edits change the latest forecast only. Approve a new version to formally replace the current baseline; earlier approved versions stay locked.')
    if not historical_rows(transactions,start):st.warning('No fictional history is available for this period. A zero baseline is missing evidence, not proof of zero spending.')
    st.caption(f"Fictional history: {add_months(start,-12):%b %Y}–{add_months(start,-1):%b %Y}. Proposed year: {start:%b %Y}–{add_months(start,11):%b %Y}. These are separate, consecutive 12-month periods; past spending is a guide, not a promise about the future.")
    a,b,c=st.columns(3)
    a.metric("Last 12 months' spending",dollars(totals['full']))
    b.metric('Adjusted historical baseline',dollars(totals['adjusted']))
    c.metric('Proposed annual expenses',dollars(summary['expenses']))
    difference=summary['expenses']-totals['adjusted']
    pct=difference/totals['adjusted']*100 if totals['adjusted'] else None
    st.write(f"Your proposed expenses are **{dollars(abs(difference))} {'lower' if difference<0 else 'higher'}** than the adjusted baseline"+(f' ({abs(pct):.1f}%).' if pct is not None else ' (no non-zero baseline for a percentage).'))
    with st.expander('Review threshold and contingency'):
        state['variance_threshold']=st.slider('Highlight category changes of at least (%)',5,50,int(state.get('variance_threshold',15)),key=key+':threshold')
        reserve=st.slider('Contingency (% of positive monthly surplus)',0,50,int(state['draft']['contingency_pct']),key=key+':reserve')
        if reserve!=state['draft']['contingency_pct']:
            from copy import deepcopy
            from guided_ui import update_plan
            candidate=deepcopy(state['draft']);candidate['contingency_pct']=reserve
            if update_plan(st,state,candidate):st.rerun()
    comparisons=category_comparison(state,transactions,state.get('variance_threshold',15))
    chart_rows=[{'category':r['name'],'view':view,'amount':float(r[field])} for r in comparisons for view,field in [('Full history','historical'),('Adjusted baseline','baseline'),('Proposed budget','proposed')]]
    chart=alt.Chart(pd.DataFrame(chart_rows,columns=['category','view','amount'])).mark_bar().encode(
        y=alt.Y('category:N',title=None),x=alt.X('amount:Q',title='Annual expenses ($)'),yOffset='view:N',
        color=alt.Color('view:N',scale=alt.Scale(domain=['Full history','Adjusted baseline','Proposed budget'],range=['#B6BECF','#8A9BE0','#258C80']),title=None),
        tooltip=['category:N','view:N',alt.Tooltip('amount:Q',format='$,.2f')]).properties(height=max(200,len(comparisons)*60))
    with st.expander('Annual category comparison chart'):
        st.altair_chart(chart,width='stretch')
    major=[r for r in comparisons if r['significant']]
    completed=sum(r['reviewed'] for r in major)
    st.progress(completed/max(1,len(major)) if major else 1.0,text=f'{completed} of {len(major)} highlighted category differences reviewed')
    for row in comparisons:
        note=' · review needed' if row['significant'] and not row['reviewed'] else ' · reviewed' if row['reviewed'] else ''
        change='No previous baseline' if row['percent'] is None else f"{abs(row['percent']):.1f}% {'less' if row['variance']<0 else 'more'} than before"
        with st.expander(row['name']+' · '+change+note,key=key+':panel:'+row['id']):
            a,b,c=st.columns(3);a.metric('Full history',dollars(row['historical']));b.metric('Adjusted baseline',dollars(row['baseline']));c.metric('Proposed budget',dollars(row['proposed']))
            st.caption('A reduction is a choice, not automatically a mistake. Review whether it fits your household.')
            selected=[r for r in historical_rows(transactions,start) if category_id(UNKNOWN if needs_category(r) else r['category'])==row['id']]
            transaction_editor(st,state,transactions,selected,key+':category:'+row['id'])
            from guided_ui import entry_form
            entries=[e for e in state['draft']['expenses'] if category_id(e['category'])==row['id']]
            if entries:
                names={e['id']:e['name'] for e in entries}
                chosen=st.selectbox('Budget expense to adjust',list(names),format_func=names.get,key=key+':expense:'+row['id'])
                st.caption('Edit the payment amount and frequency below. This is the same entry used in Build Your Budget; we never divide an annual total by 52 or 12 to guess its schedule.')
                entry_form(st,state,key+':editbudget:'+chosen,explicit=chosen)
            else:st.caption('No recurring expense in this category. Plans can be edited below.')
            if st.button('Mark difference reviewed',key=key+':review:'+row['id']+':'+row['fingerprint']):
                mark_reviewed(state,row,st.session_state.get(key+':note:'+row['id'],''));st.rerun()
            st.text_input('Optional explanation',value=row['note'],key=key+':note:'+row['id'])
    with st.expander('Edit planned expenses without leaving this page'):
        from guided_ui import plans
        plans(st,state,key+':plans')
    st.subheader('Approve your annual financial position')
    a,b,c=st.columns(3);a.metric('Annual income',dollars(summary['income']));b.metric('Contingency reserve',dollars(summary['contingency']));c.metric('Proposed approved savings baseline',dollars(summary['savings']))
    if summary['savings']<0:st.warning('This plan draws on savings over the year. Existing starting cash may cover it; check dated cash flow before approving.')
    aspiration=money(state['draft']['goal'])
    st.write(f"Your approved baseline will be **{dollars(summary['savings'])}**, calculated from this plan. Your earlier savings aspiration was **{dollars(aspiration)}**. Approval does not silently turn that aspiration into the baseline.")
    keep=st.checkbox('Retain my earlier aspiration as a separate stretch goal',value=False,key=key+':stretch')
    signature=hashlib.sha256(json.dumps([state['draft'],state['decisions'],[(r['id'],r['fingerprint']) for r in comparisons]],default=str,sort_keys=True).encode()).hexdigest()[:12]
    agree=st.checkbox('I have reviewed this fictional plan and want to lock a budget version',key=key+':agree:'+str(len(state['versions']))+':'+signature)
    outstanding=totals['uncategorised']+sum(not r['reviewed'] for r in major)
    if totals['uncategorised']:st.warning(f"Categorise {totals['uncategorised']} remaining transactions before approving. None are silently treated as Other.")
    if outstanding:st.caption(f'{outstanding} review actions remain. Approval is disabled until they are resolved.')
    label='Approve and lock budget' if not state['versions'] else 'Approve a new budget version'
    if st.button(label,type='primary',disabled=not agree or bool(outstanding),key=key+':approve'):
        try:finalise(state,transactions,confirmed=agree,keep_stretch=keep)
        except ValueError as error:st.error(str(error))
        else:state['budget_complete']=True;st.session_state[state['_nav_key']+':next']='Dashboard';st.rerun()
    with st.expander('Monthly category charts, payment calendar and locked budget history'):
        from dashboard_charts import spending_charts
        spending_charts(st,events,start,key+':details')
        responsive_table(st,pd.DataFrame(events).drop(columns=['id','item_id','project_id'],errors='ignore'),hide_index=True,width='stretch')
        for version in state['versions']:
            st.write(f"Version {version['number']} · approved savings {dollars(version.get('savings_baseline',version['summary']['savings']))} · original snapshot retained")


def inline_transactions(st,state,transactions,rows,key,allow_baseline=True,page_size=4):
    from copy import deepcopy
    if key+':undo' in state:
        if st.button('Undo last transaction change',key=key+':undo'):
            previous=state.pop(key+':undo')
            row=next(r for r in transactions if r['id']==previous['id']);row.clear();row.update(previous);st.rerun()
    if not rows:st.caption('No transactions in this selection.');return
    pages=max(1,(len(rows)+page_size-1)//page_size)
    page=st.number_input('Transaction page',min_value=1,max_value=pages,value=1,key=key+':page') if pages>1 else 1
    for row in rows[(page-1)*page_size:page*page_size]:
        scope=key+':'+row['id']
        with st.container(border=True):
            st.write(f"**{row['description']}** · {dollars(row['amount'])}")
            st.caption(row['date'])
            choices=[UNKNOWN,*state['categories']]
            current=UNKNOWN if needs_category(row) else row['category']
            def changed(row=row,scope=scope):
                from model_guard import household_model_lock
                with household_model_lock(state['_nav_key']):
                    state[key+':undo']=deepcopy(row)
                    edit_historical(state,transactions,row['id'],st.session_state[scope+':category'])
            st.selectbox('Category · '+row['description'],choices,index=choices.index(current),key=scope+':category',on_change=changed)
            if not allow_baseline:
                with st.expander('Transaction details',key=scope+':details'):
                    st.caption('Fictional observed spending · date and amount remain unchanged on recategorisation.')
                continue
            with st.expander('One-off / advanced details',key=scope+':details'):
                with st.form(scope+':form'):
                    nonrecurring=st.checkbox('Not expected to repeat',value=row.get('nonrecurring',False))
                    excluded=st.checkbox('Confirm exclusion from normal baseline',value=row.get('exclude_baseline',False),help='Changes the regular-budget comparison only. The transaction remains in historical spending with its original date and amount.')
                    reason=st.text_input('Explanation',value=row.get('exclusion_reason',''))
                    if st.form_submit_button('Save one-off review'):
                        state[key+':undo']=deepcopy(row)
                        row['nonrecurring']=nonrecurring
                        edit_historical(state,transactions,row['id'],row['category'],row.get('subcategory',''),excluded,reason,row.get('allowance_id'))
                        st.rerun()
