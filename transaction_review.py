"""Search/filter before rendering a bounded page; explicit review and reversible batches."""
from copy import deepcopy
from collections import Counter
from datetime import date
from finance import money
from budget_comparison import needs_category,UNKNOWN,edit_historical


def filter_transactions(rows,query='',category='All categories',merchant='All merchants',left=None,right=None,status='All statuses'):
    query=query.strip().casefold()
    return [r for r in rows if (not query or query in (r['description']+' '+r['date']+' '+str(r['amount'])).casefold())
        and (category=='All categories' or (UNKNOWN if needs_category(r) else r['category'])==category)
        and (merchant=='All merchants' or r['description']==merchant)
        and (left is None or date.fromisoformat(r['date'])>=left) and (right is None or date.fromisoformat(r['date'])<=right)
        and (status=='All statuses' or status=='Needs review' and not r.get('reviewed') or status=='Reviewed' and r.get('reviewed') or status=='Excluded one-offs' and r.get('exclude_baseline'))]


def bulk_review(state,transactions,ids,category=None,approve=False):
    selected=[r for r in transactions if r['id'] in set(ids)]
    if not selected:raise ValueError('Select at least one transaction.')
    if category is None and approve and any(needs_category(r) for r in selected):raise ValueError('Assign categories before approving these transactions.')
    if category is not None and category not in state['categories']:raise ValueError('Choose a known category.')
    old=deepcopy(selected)
    for r in selected:
        if category is not None:edit_historical(state,transactions,r['id'],category)
        if approve:r['reviewed']=True
    return old


def transaction_browser(st,state,transactions,rows,key,allow_baseline=True):
    from spending_ui import inline_transactions
    if not rows:st.caption('No transactions in this selection.');return
    saved_key=key+':saved_filters'
    saved=st.session_state.get(saved_key,{})
    choices={'category':['All categories',UNKNOWN,*state['categories']],'merchant':['All merchants',*sorted({r['description'] for r in rows})],'status':['All statuses','Needs review','Reviewed','Excluded one-offs'],'queue':['Needs review','Confirmed','All']}
    for name,value in saved.items():
        if key+':'+name not in st.session_state and (name not in choices or value in choices[name]):st.session_state[key+':'+name]=value
    st.caption(f'{len(rows):,} records · {sum(not r.get("reviewed") for r in rows):,} awaiting explicit review · {sum(needs_category(r) for r in rows):,} uncategorised')
    queue=st.radio('Review queue',['Needs review','Confirmed','All'],horizontal=True,key=key+':queue')
    query=st.text_input('Search transactions',key=key+':search',placeholder='Search description, amount or date')
    with st.popover('Filters',key=key+':filters'):
        category=st.selectbox('Review category',['All categories',UNKNOWN,*[c for c in state['categories'] if c!=UNKNOWN]],key=key+':category')
        merchant=st.selectbox('Review merchant',['All merchants',*sorted({r['description'] for r in rows})],key=key+':merchant')
        status=st.selectbox('Review status',['All statuses','Needs review','Reviewed','Excluded one-offs'],key=key+':status')
        with st.container():
            first=min(date.fromisoformat(r['date']) for r in rows);last=max(date.fromisoformat(r['date']) for r in rows)
            left=st.date_input('Transactions from',value=first,key=key+':from');right=st.date_input('Transactions through',value=last,key=key+':through')
    selected=filter_transactions(rows,query,category,merchant,left,right,status)
    selected=[r for r in selected if queue=='All' or bool(r.get('reviewed'))==(queue=='Confirmed') and not (queue=='Needs review' and r.get('excluded_duplicate'))]
    st.session_state[saved_key]=dict(search=query,category=category,merchant=merchant,status=status,queue=queue,**{'from':left,'through':right})
    signature=str((query,category,merchant,left,right,status,len(selected)))
    if state.setdefault('review_filters',{}).get(key)!=signature:
        st.session_state[key+':page']=1;state['review_filters'][key]=signature
    page=st.number_input('Review page',min_value=1,max_value=max(1,(len(selected)+7)//8),value=1,key=key+':page')
    shown=selected[(page-1)*8:page*8]
    st.caption(f'{len(selected):,} matching · showing {len(shown)}')
    # Eight records maximum, with the shared inline category/exclusion callback.
    focused=state.get(key+':focused')
    if focused:
        row=next((r for r in rows if r['id']==focused),None)
        if row:
            if st.button('Back to transactions',key=key+':back'):state.pop(key+':focused',None);st.rerun()
            inline_transactions(st,state,transactions,[row],key+':inline',allow_baseline,page_size=8)
            if not allow_baseline:
                from observations import set_duplicate
                with st.expander('Duplicate review'):
                    duplicate=bool(row.get('excluded_duplicate'))
                    matches={r['id']:r for r in transactions if r['id']!=row['id'] and not r.get('excluded_duplicate') and r['date']==row['date'] and r['amount']==row['amount']}
                    original=st.selectbox('Original transaction to keep',list(matches),format_func=lambda i:matches[i]['description']+' · '+matches[i]['date']+' · $'+str(matches[i]['amount']),key=key+':original:'+row['id']) if matches and not duplicate else None
                    if not matches and not duplicate:st.caption('No matching date and amount. These records cannot be treated as duplicates.')
                    confirmed=st.checkbox('I have verified this is a duplicate',key=key+':duplicate_ack:'+row['id']+':'+str(original)) if not duplicate else True
                    if st.button('Restore duplicate' if duplicate else 'Exclude confirmed duplicate',disabled=not confirmed or not duplicate and not matches,key=key+':duplicate:'+row['id']):
                        try:set_duplicate(state,row['id'],not duplicate,duplicate_of=original)
                        except ValueError as error:st.warning(str(error))
                        else:state.pop(key+':focused',None);st.rerun()
            if st.button('Confirm transaction',key=key+':confirm',type='primary',disabled=needs_category(row)):
                before=deepcopy(row);bulk_review(state,transactions,[row['id']],approve=True)
                state.setdefault('transaction_audit',[]).append(dict(type='Review confirmed',transaction_id=row['id'],before=before,after=deepcopy(row)))
                state.pop(key+':focused',None);st.rerun()
            return
    if not shown:st.caption('Nothing in this queue. Choose Confirmed or All to see reviewed records.')
    for row in shown:
        label=row['description']+' · $'+f"{money(row['amount']):,.2f}"+' · '+row['date']+' · '+(row.get('category') or 'Needs a category')+(' · Duplicate excluded' if row.get('excluded_duplicate') else '')
        if st.button(label,key=key+':open:'+row['id'],width='stretch'):
            state[key+':focused']=row['id'];st.rerun()

    ids=[r['id'] for r in shown];names={r['id']:r['date']+' · '+r['description'] for r in shown}
    with st.expander('Review selected records / bulk actions'):
        all_page=st.checkbox('Select this page',key=key+':all:'+signature)
        picked=ids if all_page else st.multiselect('Selected transactions',ids,format_func=names.get,key=key+':picked:'+signature)
        destination=st.selectbox('Bulk category',state['categories'],key=key+':bulkcategory')
        def apply(category=None,approve=False):
            try:state[key+':bulkundo']=bulk_review(state,transactions,picked,category,approve)
            except ValueError as error:st.error(str(error))
            else:st.rerun()
        if st.button('Apply category to selected',key=key+':apply',disabled=not picked):apply(destination)
        if st.button('Approve selected transactions',key=key+':approve',disabled=not picked):apply(approve=True)
        if state.get(key+':bulkundo') and st.button('Undo bulk review',key=key+':undo'):
            previous={r['id']:r for r in state.pop(key+':bulkundo')}
            for row in transactions:
                if row['id'] in previous:old=previous[row['id']];row.clear();row.update(old)
            st.rerun()
    if merchant!='All merchants':
        known=Counter(r['category'] for r in transactions if r['description']==merchant and not needs_category(r))
        if known:
            suggestion=known.most_common(1)[0][0]
            st.caption('Merchant suggestion from existing categorisation: '+suggestion+'. Review before applying; no amount or date changes.')
            targets=[r['id'] for r in selected if r['description']==merchant]
            if st.button('Apply merchant suggestion to matching records',disabled=not targets,key=key+':suggest'):
                try:state[key+':bulkundo']=bulk_review(state,transactions,targets,suggestion)
                except ValueError as error:st.error(str(error))
                else:st.rerun()
