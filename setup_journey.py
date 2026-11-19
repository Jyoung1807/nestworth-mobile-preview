"""Seven presentation stages mapped onto the existing approval requirements."""
from setup_model import STEPS,setup_state,requirements,considered
from expense_workflow import FIXED,VARIABLE,workflow_for,status

STAGES=('Your Household','Your Income','Fixed & Scheduled Expenses',
        'Variable & Lifestyle Spending','Planned Expenses','Review Past Spending — Optional','Review & Approve')
INTERNAL=(STEPS[0],STEPS[0],STEPS[1],STEPS[1],STEPS[2],STEPS[3],STEPS[5])


def stage_for_internal(state,step):
    if step==STEPS[0]:
        topic=setup_state(state).get('household_section')
        return STAGES[1] if topic=='Income' else STAGES[6] if topic=='Goals' else STAGES[0]
    if step==STEPS[1]:return STAGES[3] if state.get('expense_workflow',{}).get('workflow')==VARIABLE else STAGES[2]
    return STAGES[{STEPS[2]:4,STEPS[3]:5,STEPS[4]:6,STEPS[5]:6}.get(step,0)]


def set_stage(state,stage):
    if stage not in STAGES:raise ValueError('Choose a budget setup step.')
    setup=setup_state(state);setup.update(journey_stage=stage,step=INTERNAL[STAGES.index(stage)],step_next=False)
    setup['journey_epoch']=setup.get('journey_epoch',0)+1
    if stage in STAGES[2:4]:
        from expense_workflow import metadata
        data=metadata(state);data['workflow']=FIXED if stage==STAGES[2] else VARIABLE
        data.pop('next_workflow',None)


def migrate_input_drafts(state):
    setup=setup_state(state)
    if setup.get('journey_migrated'):return
    buffers=state.get('setup_buffers',{})
    for person in ('Person A','Person B','Other income'):
        old='income:'+person;new='income:new:'+person
        if buffers.get(old,{}).get('_dirty'):
            if new not in buffers:buffers[new]=buffers.pop(old)
    goals=buffers.get('household:Goals',{})
    if goals.get('_dirty') and 'reserve-policy' not in buffers:
        goals=buffers.pop('household:Goals');goals['_step']=STEPS[4]
        if not goals.get('cash'):goals['cash']=None
        buffers['reserve-policy']=goals;setup['reserve_reviewed']=False
    selection=list(state.get('income_selection',{}).values())
    if selection and 'income_ui' not in state:
        previous=selection[-1];person=previous.get('person','Person A');source=previous.get('source','new')
        dirty=[scope for scope,b in buffers.items() if scope.startswith('income:') and b.get('_dirty')]
        if dirty and source=='new':
            source=next((scope[len('income:'):] for scope in dirty if not scope.startswith('income:new:')),'new')
        state['income_ui']=dict(person=person,selected=source,open=bool(dirty))
    setup['journey_migrated']=True


def current_stage(state):
    migrate_input_drafts(state)
    setup=setup_state(state);stage=setup.get('journey_stage')
    if setup.pop('step_next',False) or stage not in STAGES or setup['step']!=INTERNAL[STAGES.index(stage)]:
        stage=stage_for_internal(state,setup['step']);set_stage(state,stage)
    return stage


def workflow_ready(state,workflow):
    rows,matched,_=considered(state)
    relevant=[r for r in rows if workflow_for(r,matched)==workflow]
    def belongs(scope,b):
        owner=b.get('_workflow')
        if owner:return owner==workflow
        if scope.startswith('expenses:custom:'):return workflow in scope
        suggestion=next((r for r in rows if r['id']==b.get('_suggestion_id') or scope=='expenses:'+r['id']),None)
        if suggestion:return workflow_for(suggestion,matched)==workflow
        entry=next((e for e in state['draft']['expenses'] if scope=='expenses:'+e['id']),None)
        if entry:return (VARIABLE if entry.get('allowance') else FIXED)==workflow
        return scope.startswith('expenses:') or scope=='category:new'
    dirty=any(b.get('_dirty') and belongs(scope,b) for scope,b in state.get('setup_buffers',{}).items())
    return not dirty and all(status(state,r,matched) in ('Added','Skipped') for r in relevant)


def stage_completion(state):
    setup=setup_state(state);buffers=state.get('setup_buffers',{})
    dirty=lambda prefix:any(b.get('_dirty') for scope,b in buffers.items() if scope.startswith(prefix))
    needs=requirements(state,state.get('spending',[]))
    return dict(zip(STAGES,(setup['household_reviewed'] and not dirty('household:'),
        bool(state['draft']['income']) and not dirty('income:'),
        workflow_ready(state,FIXED),workflow_ready(state,VARIABLE),
        setup['plans_reviewed'] and not dirty('plan:'),
        setup['history_choice']!='undecided',
        not needs and bool(state['versions']) and state['versions'][-1]['plan']==state['draft'])))


def requirement_stage(state,internal):
    """Point a legacy approval guard to the actual unfinished presentation step."""
    setup=setup_state(state)
    if internal==STEPS[0]:
        household_dirty=any(b.get('_dirty') for scope,b in state.get('setup_buffers',{}).items() if scope.startswith('household:'))
        return STAGES[0] if not setup['household_reviewed'] or household_dirty else STAGES[1]
    if internal==STEPS[1]:return STAGES[2] if not workflow_ready(state,FIXED) else STAGES[3]
    return stage_for_internal(state,internal)
