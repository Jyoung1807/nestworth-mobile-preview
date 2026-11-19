"""Compact full-week selections; navigating a view never changes the review date."""
from household_calendar import week_label


def week_selector(st,label,weeks,key,initial):
    if not weeks:return None
    if key in st.session_state and st.session_state[key] not in weeks:del st.session_state[key]
    selected=st.selectbox(label,weeks,index=weeks.index(initial) if initial in weeks else 0,
                          format_func=week_label,key=key)
    index=weeks.index(selected)
    def move(offset):st.session_state[key]=weeks[index+offset]
    with st.container(key='period_nav_'+key.replace(':','_')):
        left,right=st.columns(2)
        left.button('Previous week',key=key+':previous',disabled=index==0,on_click=move,args=(-1,),width='stretch')
        right.button('Next week',key=key+':next',disabled=index==len(weeks)-1,on_click=move,args=(1,),width='stretch')
    return selected
