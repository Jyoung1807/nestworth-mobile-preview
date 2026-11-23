"""Proactive financial notices backed by the shared action conditions."""
from proactive_alerts import alerts,acknowledge


def currency(value):return ('−' if value<0 else '')+f'${abs(value):,.2f}'


def render(st,state,key,actions=None):
    from actions_ui import open_source,navigate
    from notifications import decision_count
    from action_finance import collect_actions
    actions=collect_actions(state) if actions is None else actions
    rows=alerts(state,actions)
    outstanding=decision_count(actions)
    if not rows:return
    st.markdown('### Needs your attention'+(' · '+str(outstanding) if outstanding else ''))
    for alert in rows[:3]:
        with st.container(border=True,key='financial_alert_'+alert['severity']+'_'+alert['id']):
            period=''
            if alert.get('period_start') and alert.get('period_end'):
                from datetime import timedelta
                period=alert['period_start'].strftime('%d %b')+' – '+(alert['period_end']-timedelta(days=1)).strftime('%d %b %Y')
            if alert['type']=='overspend':
                st.markdown('**'+alert['category']+' · '+currency(alert['amount'])+' needs a decision**')
                if period:st.caption(period)
                st.caption('Forecast impact '+currency(-(alert.get('amount',0)+alert.get('accepted',0)))+' · already included, never deducted twice')
                if alert.get('committed'):st.caption(currency(alert['committed'])+' allocated to recovery · not yet verified savings')
                if st.button('Review & resolve '+alert['category'],type='primary',key=key+':resolve:'+alert['id'],width='stretch'):
                    open_source(st,state,alert['source'],review_first=True)
            elif alert['id']=='cash':
                st.error('Projected cash shortfall · '+currency(alert['amount']))
                st.caption(alert['reason'])
                if st.button('Review cash forecast',key=key+':cash',width='stretch'):
                    state['home_view_next']='Cash Position';st.rerun()
            elif alert['type']=='pace':
                st.info(alert['category']+' is approaching its weekly limit')
                st.caption(alert['reason']+' '+period)
                if st.button('Review '+alert['category'],key=key+':pace:'+alert['id']):
                    state['analysis_focus']=dict(week=alert['period_start'],category=alert['category']);state['home_view_next']='Spending Analysis';st.rerun()
            else:
                st.warning(alert['category']+(' · '+currency(alert['amount']) if alert['amount'] else ''))
                st.caption(alert['reason'])
                if st.button(alert['next'],key=key+':other:'+alert['id'],width='stretch'):
                    navigate(st,state,alert.get('page','Actions'))
            if alert.get('acknowledged'):st.caption('Seen · still unresolved. This remains in To Do.')
            elif alert['type']!='pace' and st.button('Mark seen · keep unresolved',key=key+':ack:'+alert['id']):
                acknowledge(state,alert);st.rerun()
    if len(rows)>3:st.caption(str(len(rows)-3)+' more conditions are available in To Do.')
