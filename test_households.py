"""Explicitly isolated synthetic sessions. No database/client argument or I/O."""
from datetime import date
from uuid import uuid4
from planning import new_planner


def clean_household(start,name='Fresh test household'):
    start=start.replace(day=1);planner=new_planner(start)
    planner['profile'].update(adults=2,ages=[],children=[],cars=0,housing='Rent',garden=False)
    planner['draft'].update(goal=0,opening_cash=0)
    return dict(start=str(start),income=[],expenses=[],transactions=[],planner=planner,_test_only=True,test_name=name.strip() or 'Fresh test household')


def create_test_household(session,base,start,name):
    key=base+':test:'+uuid4().hex;session[key]=clean_household(start,name);session[base+':active_test']=key
    return key


def reset_test_household(session,base,key,confirmed=False):
    if not confirmed:raise ValueError('Confirm test-only reset first.')
    if not key.startswith(base+':test:') or session.get(base+':active_test')!=key or not session.get(key,{}).get('_test_only'):raise ValueError('Only this active synthetic test household can be reset.')
    old=session[key];fresh=clean_household(date.fromisoformat(old['start']),old['test_name'])
    for widget in list(session):
        if widget.startswith(key+':'):del session[widget]
    session[key]=fresh


def controls(st,base,start):
    with st.sidebar.expander('Demo / Testing Controls',expanded=True):
        from populated_demo import load_demo,reset_demo,demo_key
        if st.button('Load Demo Household',type='primary',key=base+':load_demo'):
            load_demo(st.session_state,base);st.rerun()
        populated=st.session_state.get(base+':active_test')==demo_key(base)
        if populated:
            st.caption('DEMO MODE · Fictional · Scenario date 19 Nov 2026 · Session only')
            confirmed=st.checkbox('Discard demo changes and restore the starting fixture',key=base+':populated_reset_confirm')
            def reset_populated():
                from model_guard import household_model_lock
                with household_model_lock(demo_key(base)+':page'):
                    reset_demo(st.session_state,base,demo_key(base),st.session_state.get(base+':populated_reset_confirm',False))
                st.session_state[base+':populated_reset_confirm']=False
            st.button('Reset Demo Household',disabled=not confirmed,key=base+':reset_populated',on_click=reset_populated)
            st.caption('Early demo: outgoing spending and current surplus-based reserve. Incoming money and the revised reserve policy are not implemented in this fixture yet.')
        st.caption('Separate fictional household. Existing households, approved budgets and history stay untouched. Nothing is saved to Supabase.')
        name=st.text_input('Test household name',value='Fresh test household',key=base+':test_name')
        if st.button('Start Fresh Setup',key=base+':create_test'):
            fresh=create_test_household(st.session_state,base,start,name)
            st.session_state[fresh+':page:next']='Setup';st.rerun()
        active=st.session_state.get(base+':active_test')
        if active and not populated:
            confirm=st.checkbox('Confirm reset of this test household only',key=base+':reset_test_confirm')
            def reset():
                from model_guard import household_model_lock
                with household_model_lock(active+':page'):
                    reset_test_household(st.session_state,base,active,st.session_state.get(base+':reset_test_confirm',False))
                st.session_state[base+':reset_test_confirm']=False
            st.button('Reset test household only',disabled=not confirm,key=base+':reset_test',on_click=reset)
        if active:
            if st.button('Return to default demo',key=base+':leave_test'):
                st.session_state.pop(base+':active_test',None);st.rerun()
