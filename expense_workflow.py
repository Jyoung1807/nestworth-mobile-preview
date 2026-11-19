"""Expense setup metadata. Never changes monetary assumptions or saved records."""
from category_catalog import normalized
from planning import suggestions

FIXED='Fixed and Scheduled Expenses'
VARIABLE='Variable and Lifestyle Spending'
WORKFLOWS=(FIXED,VARIABLE)


def suggested_workflow(row):
    identity=row['id']
    return VARIABLE if identity in ('shared:Groceries','shared:Dining out') or identity.endswith((':Fuel',':Food')) else FIXED


def metadata(state):
    return state.setdefault('expense_workflow',{'skipped':{},'links':{},'category':{},'nav_epoch':0})


def matches(state,rows=None):
    rows=suggestions(state['profile']) if rows is None else rows
    entries=state['draft']['expenses'];links=state.get('expense_workflow',{}).get('links',{})
    result={};claimed=set()
    for row in rows:
        explicit=[e for e in entries if e.get('source_id')==row['id']]
        linked=[e for e in entries if e['id']==links.get(row['id']) and not e.get('source_id')]
        candidates=explicit or linked
        if len(candidates)==1 and candidates[0]['id'] not in claimed:
            result[row['id']]=candidates[0];claimed.add(candidates[0]['id'])
    return result


def workflow_for(row,matched):
    entry=matched.get(row['id'])
    return (VARIABLE if entry.get('allowance') else FIXED) if entry else suggested_workflow(row)


def status(state,row,matched=None):
    matched=matches(state) if matched is None else matched
    # A parked input draft is not an applied expense or a review decision.
    if any(b.get('_dirty') and (b.get('_suggestion_id')==row['id'] or scope=='expenses:'+row['id']) for scope,b in state.get('setup_buffers',{}).items()):return 'Draft'
    if row['id'] in matched:return 'Added'
    workflow=workflow_for(row,matched)
    scoped=state.get('expense_workflow',{}).get('skipped',{}).get(workflow,[])
    # Old global skips are ambiguous for variable suggestions: reopen them there.
    legacy=state.get('skipped',[]) if workflow==FIXED else []
    return 'Skipped' if row['id'] in scoped or row['id'] in legacy or row['name'] in legacy else 'Not Reviewed'


def skip(state,rows,workflow):
    matched=matches(state)
    pending=[r for r in rows if workflow_for(r,matched)==workflow and r['id'] not in matched]
    if any(status(state,r,matched)=='Draft' for r in pending):raise ValueError('Apply or discard the saved input draft before skipping it.')
    data=metadata(state);data['skipped'][workflow]=sorted(set(data['skipped'].get(workflow,[]))|{r['id'] for r in pending})


def restore(state,row):
    data=metadata(state)
    for workflow in WORKFLOWS:data['skipped'][workflow]=[s for s in data['skipped'].get(workflow,[]) if s!=row['id']]
    state['skipped']=[s for s in state.get('skipped',[]) if s not in (row['id'],row['name'])]
    invalidate(state)


def invalidate(state):
    if 'setup' in state:state['setup']['regular_reviewed']=False
    state['budget_ready']=False


def link_existing(state,row,entry_id):
    entries=state['draft']['expenses'];matched=matches(state)
    entry=next((e for e in entries if e['id']==entry_id),None)
    if entry is None or entry.get('source_id') or entry_id in {e['id'] for e in matched.values()}:raise ValueError('This expense is unavailable or already linked.')
    if row['id'] in matched:raise ValueError('This suggestion already has an expense.')
    if status(state,row,matched)=='Draft':raise ValueError('Apply or discard the input draft before linking an existing expense.')
    metadata(state)['links'][row['id']]=entry_id;invalidate(state)


def legacy_candidates(state,row):
    claimed={e['id'] for e in matches(state).values()}
    return [e for e in state['draft']['expenses'] if not e.get('source_id') and e['id'] not in claimed and normalized(e['name'])==normalized(row['name'])]


def categories(state,workflow,rows=None,matched=None):
    rows=suggestions(state['profile']) if rows is None else rows
    matched=matches(state,rows) if matched is None else matched
    names=[matched.get(r['id'],r)['category'] for r in rows if workflow_for(r,matched)==workflow]
    names += [e['category'] for e in state['draft']['expenses'] if (VARIABLE if e.get('allowance') else FIXED)==workflow]
    return list(dict.fromkeys(names)) or ['Other']


def move_category(state,workflow,category,direction=1):
    data=metadata(state);names=categories(state,workflow);index=names.index(category)
    if 0<=index+direction<len(names):target=workflow;destination=names[index+direction]
    elif workflow==FIXED and direction>0:target=VARIABLE;destination=categories(state,target)[0]
    elif workflow==VARIABLE and direction<0:target=FIXED;destination=categories(state,target)[-1]
    else:return workflow,category
    data['category'][target]=destination;data['nav_epoch']+=1
    return target,destination
