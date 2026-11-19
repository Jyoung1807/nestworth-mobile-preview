"""Serialize nested model access across overlapping Streamlit rerun threads.

SafeSessionState protects its outer mapping, not mutable dictionaries retrieved
from it. A fast rerun can start while the previous script is still calculating.
Locks hold no financial data and are isolated by session plus household namespace.
Weak references discard idle scopes; rerun/stop exceptions always release the lock.
"""
from contextlib import contextmanager
from threading import Lock,RLock,get_ident
from weakref import WeakValueDictionary

_registry_guard=Lock()
_locks=WeakValueDictionary()


@contextmanager
def household_model_lock(scope,*,session_id=None):
    if session_id is None:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        context=get_script_run_ctx(suppress_warning=True)
        session_id=context.session_id if context else ('local',get_ident())
    identity=(session_id,scope)
    with _registry_guard:
        lock=_locks.get(identity)
        if lock is None:
            lock=RLock();_locks[identity]=lock
    with lock:
        yield
