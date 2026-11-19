"""Urgent financial decisions are distinct from routine setup reminders."""
def decision_count(actions):
    return sum(a['status']=='Needs decision' and (a['type']=='overspend' or a.get('id')=='cash') for a in actions)


def financial_alerts(st,state,key,actions=None):
    from action_finance import collect_actions
    from actions_ui import open_source,navigate
    actions=collect_actions(state) if actions is None else actions
    financial=[a for a in actions if a['status']=='Needs decision' and a['type']=='overspend']
    if financial:
        st.caption(f'{len(financial)} spending decision(s) need attention. Pending commitments are separate.')
        for a in financial[:2]:
            if st.button('Resolve '+a['category']+' · $'+f"{a['remaining']:,.2f}",key=key+':'+a['id'],width='stretch'):open_source(st,state,a['source'])
    elif any(a['status']=='Needs decision' and a.get('id')=='cash' for a in actions):
        if st.button('Review projected cash shortage',key=key+':cash'):navigate(st,state,'Outlook',{'kind':'cash'})
