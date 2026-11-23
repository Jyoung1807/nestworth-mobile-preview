"""Fail closed on an old loaded financial module after a partial app refresh."""
from inspect import signature

def compatible():
    from planning import summarize
    return 'end' in signature(summarize).parameters

def require_compatible(st):
    if not compatible():
        st.error('This app update has not finished loading. Restart the app, then reopen it. Financial actions are unavailable until it reloads.')
        st.stop()
