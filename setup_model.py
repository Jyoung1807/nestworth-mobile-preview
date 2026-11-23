"""One session-only setup state and explicit approval requirements."""
from copy import deepcopy
from datetime import date
from finance import money
from planning import suggestions,project_payments

STEPS=('Your Household','Build Your Regular Budget','Your Plans','Review Historical Spending','Contingency & Savings','Compare & Approve')
ROUTES=('Home','BudgetSpending','Payments','Spending','Outlook','Actions','Setup','Settings','More')
LEGACY={'Dashboard':('Home',None),'Review Your Spending':('Spending',None),'Actions Centre':('Actions',None),'Your Year Ahead':('Outlook',None),'Your Household':('Setup',STEPS[0]),'Build Your Budget':('Setup',STEPS[1]),'Compare & Finalise':('Setup',STEPS[5])}


def setup_state(state):
    if 'setup' not in state:
        approved=bool(state['versions'])
        state['setup']=dict(step=STEPS[0],mode='Quick Setup',household_reviewed=approved,regular_reviewed=approved,
            plans_reviewed=approved,history_choice='reviewed' if approved and state.get('history_reviewed') else 'declined' if approved else 'undecided',
            history_invitation=approved,reserve_reviewed=approved)
    return state['setup']


def route(state,requested):
    target,step=LEGACY.get(requested,(requested,None))
    if step:
        setup_state(state).update(step=step,step_next=True)
    return target if target in ROUTES else ('Home' if state['versions'] else 'Setup')


def considered(state):
    from expense_workflow import matches,status
    rows=suggestions(state['profile']);matched=matches(state,rows)
    done={r['id'] for r in rows if status(state,r,matched) in ('Added','Skipped')}
    return rows,matched,done


def requirements(state,transactions=()):
    from budget_comparison import historical_totals,category_comparison
    setup=setup_state(state);needs=[]
    if not setup['household_reviewed'] or not state['draft']['income']:needs.append((STEPS[0],'Review your household and add an income source.'))
    if not setup['regular_reviewed']:needs.append((STEPS[1],'Review regular expenses and allowances.'))
    if not setup['plans_reviewed']:needs.append((STEPS[2],'Review known plans, or confirm there are none.'))
    for project in state['draft']['projects']:
        try:project_payments(project)
        except ValueError as error:needs.append((STEPS[2],project['name']+': '+str(error)))
    dirty={b.get('_step') for b in state.get('setup_buffers',{}).values() if b.get('_dirty')}
    for step in dirty.intersection(STEPS):needs.append((step,'Apply or discard the saved input draft in '+step+'.'))
    if setup['history_choice']=='undecided':needs.append((STEPS[3],'Choose Quick Setup or review historical spending.'))
    if setup['history_choice']=='reviewed':
        totals=historical_totals(transactions,date.fromisoformat(state['draft']['start']))
        if totals['uncategorised']:needs.append((STEPS[3],f"Categorise {totals['uncategorised']} historical transactions."))
        for row in category_comparison(state,transactions,state.get('variance_threshold',15)):
            if row['significant'] and not row['reviewed']:needs.append((STEPS[5],'Review historical difference: '+row['name']+'.'))
    elif not setup['history_invitation']:needs.append((STEPS[5],'Respond to the invitation to compare history before approving.'))
    if not setup['reserve_reviewed']:needs.append((STEPS[4],'Review contingency policy and savings assumptions.'))
    return needs


def completion(state,transactions=()):
    pending={step for step,_ in requirements(state,transactions)}
    return {step:step not in pending and (bool(state['versions']) and state['versions'][-1]['plan']==state['draft'] and not pending if step==STEPS[5] else True) for step in STEPS}


def approve_setup(state,transactions,confirmed=False,keep_stretch=False):
    from budget_comparison import finalise
    from planning import approve
    if not confirmed:raise ValueError('Acknowledge the proposed budget before approval.')
    needs=requirements(state,transactions)
    if needs:raise ValueError(needs[0][1])
    if setup_state(state)['history_choice']=='reviewed':return finalise(state,transactions,True,keep_stretch)
    version=approve(state,stretch_goal=money(state['draft']['goal']) if keep_stretch else None)
    partial=setup_state(state)['history_choice']=='reviewed_partial'
    state['versions'][-1]['historical_review']='Explicitly incomplete historical comparison; outstanding categories retained' if partial else 'Deliberately declined; no historical comparison asserted'
    if partial:
        from budget_comparison import historical_totals
        state['versions'][-1]['historical_totals']=historical_totals(transactions,date.fromisoformat(state['draft']['start']))
    return deepcopy(state['versions'][-1])


def apply_profile(state,values):
    before={r['id'] for r in suggestions(state['profile'])}
    state['profile'].update(deepcopy(values))
    if before!={r['id'] for r in suggestions(state['profile'])}:
        setup_state(state)['regular_reviewed']=False;state['budget_ready']=False
