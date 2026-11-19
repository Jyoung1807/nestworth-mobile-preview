"""Context-preserving shared entry to the existing future-expense service.

Already-paid entries remain transaction review, not a second forecast expense.
The mixed actual/future command is added only with the ledger reconciliation.
"""
def shortcut(st,state,key,page):
    if state.get('_quick_expense') and state['_quick_expense']['page']==page:
        return True
    if st.button('+ Add Expense',type='primary',key=key+':quick_add'):
        state['_quick_expense']={'page':page};st.rerun()
    return False


def render(st,state,key):
    st.subheader('Add Expense')
    st.caption('Planned future spending · approved budget stays unchanged')
    if st.button('Return to previous view',key=key+':quick_return'):
        state.pop('_quick_expense',None);st.rerun()
    from outlook_workflows import unexpected
    unexpected(st,state,key+':shared_expense')
    notice=state.pop('outlook_notice',None)
    if notice:st.success(notice)
