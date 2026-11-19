"""Server-synchronised input drafts, separate from applied financial assumptions."""
from uuid import uuid4
from model_guard import household_model_lock


def buffer(state,scope,step):
    return state.setdefault('setup_buffers',{}).setdefault(scope,{'_step':step,'_dirty':False,'_epoch':uuid4().hex})


def field(st,state,scope,setup_step,kind,label,name,default,**kwargs):
    draft=buffer(state,scope,setup_step);draft.setdefault(name,default)
    key=state['_nav_key']+':input:'+scope+':'+draft['_epoch']+':'+name
    def changed():
        with household_model_lock(state['_nav_key']):
            current=state.get('setup_buffers',{}).get(scope)
            if current is not None and current.get('_epoch')==draft['_epoch']:current[name]=st.session_state[key];current['_dirty']=True
    value=draft[name]
    if kind=='date_input':kwargs.setdefault('format','DD/MM/YYYY')
    if kind in ('selectbox','radio'):
        options=kwargs.pop('options')
        if value not in options:value=options[0];draft[name]=value
        widget=getattr(st,kind)(label,options,index=options.index(value),key=key,on_change=changed,**kwargs)
    else:widget=getattr(st,kind)(label,value=value,key=key,on_change=changed,**kwargs)
    # Includes defaults and the final submitted widget value, without applying a
    # monetary assumption or changing an approval. The callback also runs before
    # navigation, so Streamlit's widget cleanup cannot discard a saved input.
    draft[name]=widget
    return widget


def saved(st,state,scope):
    draft=state.get('setup_buffers',{}).get(scope,{})
    st.caption('Input draft saved in this session · not applied to the forecast' if draft.get('_dirty') else 'Saved to budget draft · approved versions stay locked' if draft.get('_applied') else 'Inputs stay in this session until saved to the budget draft')


def applied(state,scope):
    state['setup_buffers'][scope]['_dirty']=False;state['setup_buffers'][scope]['_applied']=True


def discard(st,state,scope,label='Discard input draft'):
    if state.get('setup_buffers',{}).get(scope,{}).get('_dirty') and st.button(label,key=state['_nav_key']+':discard:'+scope):
        state['setup_buffers'].pop(scope,None);st.rerun()
