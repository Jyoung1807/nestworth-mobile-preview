"""Bounded session/household-local memoisation, never a shared financial store.

Only active inside a renderer scope. Domain callers retain uncached behaviour.
Keys include every current financial input to the engine; snapshots,
observations, dates and commands invalidate automatically. Copies on both sides
prevent callers or candidate previews mutating a previously calculated result.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from hashlib import sha256
import pickle
import marshal

_active=ContextVar('nestworth_projection_cache',default=None)

def _copy_output(value):
    # Only internally generated projection DTOs are round-tripped. Never read
    # pickle bytes from a file, upload, network or caller. The C-level codec
    # preserves Decimal/date values, aliasing and independent mutable results.
    return pickle.loads(pickle.dumps(value,protocol=5))

@contextmanager
def projection_scope(cache):
    token=_active.set(cache)
    try:yield
    finally:_active.reset(token)

# Exclude UI state by selecting engine inputs, rather than caching widget drafts.
# Non-result functions use their complete arguments.
ENGINE_FIELDS=('categories','profile','draft','versions','decisions','actuals','revisions','payment_reschedules',
 'reserve_changes','recoveries','plan_recoveries','contingency_uses','tracking_date',
 'coverage','period_transactions','spending','frozen_until','frozen_schedule',
 'recovery_sources','accepted_overspends','observation_history','observation_exclusions')

def memo_projection(fn):
    code_version=sha256(marshal.dumps(fn.__code__)).digest()
    @wraps(fn)
    def run(*args,**kwargs):
        cache=_active.get()
        if cache is None:return fn(*args,**kwargs)
        values=args
        if fn.__name__=='result':values=({k:args[0][k] for k in ENGINE_FIELDS if k in args[0]},*args[1:])
        slot=(fn.__module__,fn.__name__)
        bucket=cache.setdefault(slot,{})
        if bucket.get('__code__')!=code_version:
            bucket={'__code__':code_version};cache[slot]=bucket
        key=sha256(pickle.dumps((values,kwargs),protocol=5)).digest()
        if key in bucket:
            value=bucket.pop(key);bucket[key]=value
            return _copy_output(value)
        value=fn(*args,**kwargs)
        if len(bucket)>=9:bucket.pop(next(k for k in bucket if k!='__code__'))
        bucket[key]=_copy_output(value)
        return value
    return run
