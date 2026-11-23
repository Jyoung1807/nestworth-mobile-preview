"""Session-only budget versions and replayable, dated forecast decisions.

No Streamlit, database or bank calls. Monetary values are Decimal dollars.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4
from finance import money, payment_dates, add_months, CATEGORIES

from projection_cache import memo_projection

ZERO = Decimal('0.00')


def uid():
    return uuid4().hex


def new_planner(start, income=(), expenses=(), end_exclusive=None):
    start=start.replace(day=1) if end_exclusive is None else start
    def entries(rows):
        return [dict(deepcopy(row), id=uid(), estimated=True, subcategory='') for row in rows]
    # Rename only known fictional fixture labels; never infer new amounts.
    seed_names={'Housing':'Mortgage','Vehicles':'Car 1 · Fuel','Children':'Child 1 · School costs',
                'Utilities':'Electricity','Health':'Medical and dental','Groceries':'Groceries','Leisure':'Dining out','Other':'Other household costs'}
    expenses=deepcopy(expenses)
    for row in expenses:
        if row.get('name')==row.get('category','')+' plan': row['name']=seed_names.get(row['category'],row['name'])
    state={'draft':{'start':str(start), 'income':entries(income), 'expenses':entries(expenses),
                     'projects':[], 'goal':24000.0, 'contingency_pct':10, 'opening_cash':0.0},
            'profile':{'adults':2,'ages':[5,9],'housing':'Mortgage','pool':False,'garden':True,
                       'cars':1,'boats':0,'caravans':0,'other_assets':'','notes':''},
            'categories':list(CATEGORIES), 'subcategories':{}, 'skipped':[],
            'versions':[], 'decisions':[], 'history':[]}
    if end_exclusive is not None:
        from budget_period import BudgetPeriod
        period=BudgetPeriod(start,end_exclusive);state['draft']['end_exclusive']=str(period.end);state['draft']['goal']=0
        from contingency_policy import default_policy
        state['draft']['contingency_policy']=default_policy()
    return state


def suggestions(profile):
    """Per-item suggestions in customer order; shared bills occur only once."""
    from category_catalog import category_id
    rows=[]
    def add(name,category,group,identity):
        rows.append({'id':identity,'name':name,'category':category,'category_id':category_id(category),'group':group})
    home=profile['housing']
    if home in ('Mortgage','Rent'): add(home,'Mortgage / Rent','Mortgage / Rent','home:primary')
    costs=['Contents insurance'] if home=='Rent' else ['Rates','Home insurance','Home maintenance']
    if profile.get('pool'): costs.append('Pool maintenance')
    if profile.get('garden'): costs.append('Garden care')
    for name in costs: add(name,'Home & Property','Home & Property','home:'+name)
    for name in ('Electricity','Water','Internet','Mobile phones'): add(name,'Utilities','Utilities','shared:'+name)
    assets=profile.get('vehicles',[])
    if not assets:
        assets=[{'id':f'{key}:{n}','name':f'{label} {n+1}','type':label,'finance':False} for key,label in [('cars','Car'),('boats','Boat'),('caravans','Caravan')] for n in range(profile.get(key,0))]
    for asset in assets:
        label=asset['name'] or asset['type']
        costs=['Registration','Insurance','Servicing','Storage' if asset['type']=='Caravan' else 'Fuel']
        if asset.get('finance'): costs.append('Finance')
        for name in costs: add(label+' · '+name,'Vehicles','Vehicles · '+label,asset['id']+':'+name)
    children=profile.get('children') or [{'id':f'child:{i}','name':f'Child {i+1}','age':age} for i,age in enumerate(profile['ages'])]
    for child in children:
        costs=['Activities']
        if child['age'] is None or child['age']<6: costs.insert(0,'Childcare')
        if child['age'] is None or child['age']>=5: costs.insert(0,'School costs')
        label=child.get('name') or 'Child'
        for name in costs: add(label+' · '+name,'Children','Children · '+label,child['id']+':'+name)
    for pet in profile.get('pets',[]):
        label=pet.get('name') or pet['type']
        costs=['Food','Tank maintenance'] if pet['type']=='Fish' else ['Food','Vet care','Boarding']
        if pet['type'] in ('Dog','Cat'): costs+=['Insurance','Grooming']
        for name in costs:
            add(label+' · '+name,'Pets','Pets · '+label,pet['id']+':'+name)
    for name in ('Health insurance','Medical and dental'): add(name,'Health','Health','shared:'+name)
    add('Groceries','Groceries','Everyday essentials','shared:Groceries')
    for name in ('Dining out','Subscriptions'): add(name,'Leisure','Lifestyle','shared:'+name)
    return rows


def project_payments(project):
    if not project.get('name','').strip(): raise ValueError('Give the plan a name')
    if project.get('status','Active') not in ('Active','Cancelled'): raise ValueError('Invalid plan status')
    payments=project.get('payments',[])
    if not payments or sum((money(p['amount']) for p in payments),ZERO)!=money(project['total']):
        raise ValueError('Payment amounts must add up to the project total')
    ids=[p['id'] for p in payments]
    if len(ids)!=len(set(ids)): raise ValueError('Payment IDs must be unique')
    for p in payments: date.fromisoformat(str(p['date']))
    if project.get('status')=='Cancelled': return []
    return payments


def event_total(events, kind=None, start=None, end=None):
    return sum((money(e['amount']) for e in events if (kind is None or e['kind']==kind)
                and (start is None or e['date']>=start) and (end is None or e['date']<end)),ZERO)


def scheduled_events(plan):
    from category_catalog import category_id,subcategory_id
    start=date.fromisoformat(plan['start']); end=period_end(plan)
    result=[]
    ids=[]
    for kind,key in [('income','income'),('expense','expenses')]:
        for item in plan[key]:
            ids.append(item['id'])
            if plan.get('end_exclusive') and item.get('allowance'):
                from allowance_allocations import period_events
                if not item['name'].strip():raise ValueError('Every allowance needs a name')
                result.extend(period_events(item,start,end));continue
            if item.get('allowance') and item.get('allocation_method')=='consistent':
                from allowance_allocations import consistent_events
                if item['frequency'] not in ('Weekly','Fortnightly','Monthly','Quarterly','Six-monthly','Annual'):raise ValueError('Choose a supported allowance frequency')
                if not item['name'].strip():raise ValueError('Every allowance needs a name')
                result.extend(consistent_events(item,start,end));continue
            if item.get('allowance') and item.get('allocation_method')=='calendar' and item['frequency'] in ('Monthly','Quarterly','Six-monthly','Annual'):
                from allowance_allocations import calendar_events
                if not item['name'].strip():raise ValueError('Every allowance needs a name')
                result.extend(calendar_events(item,start,end));continue
            if item.get('allowance') and item['frequency'] not in ('Weekly','Fortnightly','Monthly','Quarterly','Six-monthly','Annual'):raise ValueError('Choose a supported allowance frequency')
            if not item['name'].strip(): raise ValueError('Every payment needs a name')
            first=date.fromisoformat(str(item.get('first_payment') or plan['start']))
            until=date.fromisoformat(str(item['end_date']))+timedelta(days=1) if item.get('end_date') else end
            if item.get('end_date') and date.fromisoformat(str(item['end_date']))<first:
                raise ValueError('End date must not precede first payment')
            for day in payment_dates(first,item['frequency'],start,min(end,until)):
                # Stable occurrence identity even when a future amount changes.
                if item['frequency'] in ('Weekly','Fortnightly'):
                    index=(day-first).days//(7 if item['frequency']=='Weekly' else 14)
                elif item['frequency']=='One-off': index=0
                else:
                    step={'Monthly':1,'Quarterly':3,'Six-monthly':6,'Annual':12}[item['frequency']]
                    index=((day.year-first.year)*12+day.month-first.month)//step
                result.append({'id':f"{item['id']}:{index}",'item_id':item['id'], 'project_id':None,
                               'name':item['name'],'category':item.get('category','Income'),
                               'subcategory':item.get('subcategory',''), 'kind':kind,
                               'date':day,'amount':allowance_amount(item,day,min(end,until)) if item.get('allowance') else money(item['amount']),'paid':False,
                               'allowance':bool(item.get('allowance')),
                               'estimated':item.get('estimated',True),'allocation_method':item.get('allocation_method','calendar'),
                               'allocation_end':min(end,until,day+timedelta(days=7 if item['frequency']=='Weekly' else 14) if item['frequency'] in ('Weekly','Fortnightly') else add_months(day,{'Monthly':1,'Quarterly':3,'Six-monthly':6,'Annual':12}[item['frequency']])) if item.get('allowance') else None})
    for project in plan['projects']:
        ids.append(project['id'])
        for payment in project_payments(project):
            day=date.fromisoformat(str(payment['date']))
            if start<=day<end:
                result.append({'id':f"project:{project['id']}:{payment['id']}", 'item_id':project['id'],
                               'project_id':project['id'],'name':project['name']+' · '+payment.get('description','Payment'),
                               'category':project['category'],'subcategory':project.get('subcategory',''),
                               'kind':'expense','date':day,'amount':money(payment['amount']),'paid':False,'estimated':payment.get('precision','Exact date')!='Exact date'})
    if len(ids)!=len(set(ids)): raise ValueError('Item IDs must be unique')
    if plan.get('contingency_policy'):
        from contingency_policy import monthly_events,eligible
        definitions={item['id']:item for item in plan['expenses']}
        for event in result:
            if event['kind']=='expense':event['contingency_eligible']=eligible(definitions[event['item_id']]) if event['item_id'] in definitions and not event.get('project_id') else False
        result.extend(monthly_events(plan,result))
    else:
        percent=Decimal(str(plan['contingency_pct']))
        if not percent.is_finite() or not 0<=percent<=100: raise ValueError('Invalid contingency percentage')
        spans=BudgetPeriod.from_plan(plan).months() if plan.get('end_exclusive') else [(add_months(start,n),add_months(start,n+1)) for n in range(12)]
        for n,(day,boundary) in enumerate(spans):
            surplus=event_total(result,'income',day,boundary)-event_total(result,'expense',day,boundary)
            reserve=(max(ZERO,surplus)*percent/100).quantize(Decimal('.01'))
            result.append({'id':f'reserve:{n}','item_id':'reserve','project_id':None,'name':'Contingency reserve',
                           'category':'Contingency','subcategory':'','kind':'reserve','date':day,'amount':reserve,'paid':False})
    for event in result:
        event['category_id']=category_id(event['category'])
        event['subcategory_id']=subcategory_id(event['category_id'],event['subcategory'])
    return result


def apply_actuals(events, originals, actuals, as_of):
    """Replace a matched payment exactly once; preserve removed paid payments."""
    original_map={e['id']:e for e in originals}
    result={e['id']:deepcopy(e) for e in events}
    for event in originals:
        if event['date']<as_of:
            result[event['id']]=deepcopy(event)
    seen=set()
    for actual in actuals:
        key=actual['payment_id']
        if key in seen or key not in original_map: raise ValueError('Actual must match a unique known payment')
        seen.add(key)
        if original_map[key]['kind']=='reserve': raise ValueError('A reserve is not a completed transaction')
        entry=deepcopy(original_map[key])
        entry.update(date=date.fromisoformat(str(actual['date'])),amount=money(actual['amount']),paid=True)
        result[key]=entry
    return list(result.values())


def reduce_events(candidates, amount):
    """Cent-exact proportional reduction; deterministic remainder, no negatives."""
    total=event_total(candidates)
    amount=money(amount)
    if amount>total: raise ValueError('Reduction exceeds remaining unpaid expenses')
    remaining=amount
    for i,event in enumerate(sorted(candidates,key=lambda e:(e['date'],e['id']))):
        share=remaining if i==len(candidates)-1 else (amount*event['amount']/total).quantize(Decimal('.01'),rounding=ROUND_DOWN) if total else ZERO
        share=min(share,event['amount'])
        event['amount']-=share
        remaining-=share
    # Cent remainder can exceed the last tiny payment; distribute safely.
    for event in candidates:
        take=min(remaining,event['amount']); event['amount']-=take; remaining-=take
    if remaining: raise ValueError('Unable to allocate reduction')


def replay(plan, decisions, as_of=None, actuals=(), originals=None, source_events=None):
    from category_catalog import category_id
    start=date.fromisoformat(plan['start']); end=period_end(plan)
    as_of=as_of or start
    raw=scheduled_events(plan) if source_events is None else deepcopy(source_events)
    events=apply_actuals(raw,originals or raw,actuals,as_of)
    explanations=[]
    for decision in decisions:
        if not decision.get('active',True): continue
        day=date.fromisoformat(str(decision['date']))
        if not as_of<=day<end: raise ValueError('New spending must be in the remaining forecast year')
        amount=money(decision['amount'])
        if amount<=0 or not decision['description'].strip() or not decision.get('reason','').strip():
            raise ValueError('Add an expense amount, description and reason')
        before=deepcopy(events); details=[]
        for offset in decision.get('offsets',[]):
            kind=offset['kind']
            candidates=[e for e in events if e['kind'] in ('expense','reserve') and not e['paid'] and as_of<=e['date']<end]
            if kind.startswith('category_'):
                candidates=[e for e in candidates if (offset['target']=='legacy_housing' and e['category'] in ('Housing','Home & Property','Mortgage / Rent')) or e['category']==offset['target'] or e.get('category_id') in (offset['target'],category_id(offset['target']))]
            elif kind in ('expense_fixed','expense_percent'):
                candidates=[e for e in candidates if e['item_id']==offset['target']]
            elif kind in ('cancel_project','postpone_project','project_fixed','project_percent'):
                candidates=[e for e in candidates if e['project_id']==offset['target']]
            else: raise ValueError('Invalid offset type')
            if offset.get('from'):
                left=date.fromisoformat(offset['from']);right=date.fromisoformat(offset.get('until',str(end-timedelta(days=1))))+timedelta(days=1)
                if left<as_of or right<=left or right>end:raise ValueError('Reduction dates must form an eligible forecast window')
                candidates=[e for e in candidates if left<=e['date']<right]
            basis=event_total(candidates)
            if not candidates or basis==0: raise ValueError('No unpaid amount remains for this offset')
            original=deepcopy(candidates)
            if kind=='postpone_project':
                new_date=date.fromisoformat(str(offset['new_date']))
                first=min(e['date'] for e in candidates)
                if new_date<=first: raise ValueError('Postponed date must be later than the first unpaid payment')
                shift=new_date-first
                for event in candidates: event['date']+=shift
            else:
                if kind=='cancel_project': reduction=basis
                elif kind in ('category_percent','expense_percent','project_percent'):
                    percent=Decimal(str(offset['value']))
                    if not percent.is_finite() or not 0<=percent<=100: raise ValueError('Percentage must be between 0 and 100')
                    reduction=(basis*percent/100).quantize(Decimal('.01'))
                else:
                    reduction=money(offset['value'])
                    if offset.get('frequency','One-off')!='One-off':
                        left=date.fromisoformat(offset.get('from',str(as_of)));right=date.fromisoformat(offset.get('until',str(end-timedelta(days=1))))+timedelta(days=1)
                        reduction*=len(payment_dates(left,offset['frequency'],left,right))
                reduce_events(candidates,reduction)
            revised=event_total(candidates,start=start,end=end)
            details.append({'method':kind,'target':offset['target'],'label':'Former Housing (combined)' if offset['target']=='legacy_housing' else original[0]['category'] if kind.startswith('category_') else original[0]['name'],'basis':basis,'revised':revised,
                            'reduction':basis-revised,'change_percent':((basis-revised)/basis*100).quantize(Decimal('.01')),
                            'changes':[{'payment':old['name'],'old_date':old['date'],'new_date':new['date'],
                                        'original':old['amount'],'revised':new['amount']} for old,new in zip(original,candidates)]})
        offsets=event_total(before,start=start,end=end)-event_total(events,start=start,end=end)
        by_due=event_total(before,start=start,end=day+timedelta(days=1))-event_total(events,start=start,end=day+timedelta(days=1))
        paid_decision=next((e for e in events if e['id']==f"decision:{decision['id']}" and e['paid']),None)
        if paid_decision:
            original=next(e for e in (originals or []) if e['id']==paid_decision['id'])
            if day!=original['date'] or amount!=original['amount']:
                raise ValueError('An incurred expense cannot be changed')
            amount=paid_decision['amount']
        else:
            events.append({'id':f"decision:{decision['id']}",'item_id':decision['id'],'project_id':None,
                       'name':decision['description'],'category':decision['category'],'subcategory':'',
                       'kind':'expense','date':day,'amount':amount,'paid':False})
        category_changes=[]
        for category in sorted({e['category'] for e in before+events if e['kind']!='income'}):
            original_value=event_total([e for e in before if e['category']==category],start=start,end=end)
            revised_value=event_total([e for e in events if e['category']==category],start=start,end=end)
            if original_value!=revised_value:
                category_changes.append({'category':category,'original':original_value,'revised':revised_value,
                                         'change':revised_value-original_value,
                                         'percent':((revised_value-original_value)/original_value*100).quantize(Decimal('.01')) if original_value else None})
        explanations.append({'id':decision['id'],'description':decision['description'],'amount':amount,
                             'offsets':offsets,'savings_impact':amount-offsets,'released_by_due_date':by_due,
                             'timing_gap':max(ZERO,amount-by_due),'details':details,'category_changes':category_changes})
    from category_catalog import category_id,subcategory_id
    for event in events:
        event['category_id']=category_id(event['category'])
        event['subcategory_id']=subcategory_id(event['category_id'],event.get('subcategory',''))
    return sorted(events,key=lambda e:(e['date'],e['id'])),explanations


def summarize(events,start,end=None):
    end=end or add_months(start,12)
    income=event_total(events,'income',start,end)
    expense=event_total(events,'expense',start,end)
    from contingency_policy import dated_earmarks
    reserve=sum((e['amount'] for e in dated_earmarks(events) if e['kind']=='reserve' and start<=e['date']<end),ZERO)
    return {'income':income,'expenses':expense,'contingency':reserve,'savings':income-expense-reserve}


@memo_projection
def aggregate(events,start,period='Monthly',opening_cash=0,end=None):
    if period not in ('Monthly','Weekly'): raise ValueError('Choose monthly or weekly aggregation')
    from household_calendar import week_start,week_label
    from contingency_policy import dated_earmarks
    events=dated_earmarks(events)
    legacy_end=end is None
    end=end or add_months(start,12); opening=money(opening_cash); rows={}
    for event in events:
        if not start<=event['date']<end: continue
        day=event['date']
        group=day.replace(day=1) if period=='Monthly' else week_start(day)
        key=group.isoformat()
        row=rows.setdefault(key,{'period':key,'income':ZERO,'expenses':ZERO,'reserve':ZERO,'actuals':ZERO})
        field={'income':'income','expense':'expenses','reserve':'reserve'}[event['kind']]
        row[field]+=event['amount']
        if event['paid']:
            row['actuals']+=event['amount'] if event['kind']=='income' else -event['amount']
    # Include zero-payment weeks/months, not just populated periods.
    cursor=(start if legacy_end else start.replace(day=1)) if period=='Monthly' else week_start(start)
    while cursor<end:
        key=cursor.isoformat()
        rows.setdefault(key,{'period':key,'income':ZERO,'expenses':ZERO,'reserve':ZERO,'actuals':ZERO})
        cursor=add_months(cursor,1) if period=='Monthly' else cursor+timedelta(days=7)
    cash=opening; spendable=opening
    result=[]
    for key in sorted(rows):
        row=rows[key]
        row['cash_flow']=row['income']-row['expenses']
        row['savings']=row['cash_flow']-row['reserve']
        daily={}
        for event in events:
            if not start<=event['date']<end or event['kind']=='reserve': continue
            group=event['date'].replace(day=1) if period=='Monthly' else week_start(event['date'])
            if group.isoformat()==key:
                daily[event['date']]=daily.get(event['date'],ZERO)+(event['amount'] if event['kind']=='income' else -event['amount'])
        running=cash; low=cash
        for day in sorted(daily):
            running+=daily[day]; low=min(low,running)
        cash+=row['cash_flow']; spendable+=row['savings']
        row['lowest_cash']=low
        row['closing_cash']=cash; row['after_reserve']=spendable
        if period=='Weekly':row['period_label']=week_label(date.fromisoformat(key))
        result.append(row)
    return result


@memo_projection
def result(state, decisions=None, plan=None, accounting=True):
    draft=plan or state['draft']
    original=state['versions'][-1]['events'] if state['versions'] else None
    from accountability import revise_events,apply_recoveries,observed_events
    raw=scheduled_events(draft)
    if state.get('frozen_until'):
        from accountability import dated_allocations
        raw=dated_allocations(raw)
        cutoff=date.fromisoformat(state['frozen_until'])
        raw=[e for e in raw if e['date']>=cutoff and not (e['kind']=='reserve' and e['date']==cutoff)]+[e for e in dated_allocations(state['frozen_schedule']) if e['date']<cutoff or (e['kind']=='reserve' and e['date']==cutoff)]
    source=revise_events(raw,state.get('revisions',[]))
    from payment_rescheduling import apply_reschedules
    source=apply_reschedules(source,state.get('payment_reschedules',[]))
    from contingency_policy import forecast_events
    source=forecast_events(state,source,draft)
    events,explanations=replay(draft,state['decisions'] if decisions is None else decisions,
                  as_of=date.fromisoformat(draft['start']),actuals=state.get('actuals',[]), originals=original,source_events=source)
    from action_finance import apply_plan_recoveries
    events=apply_plan_recoveries(events,state.get('plan_recoveries',[]))
    if state.get('tracking_date'):
        from accountability import dated_allocations
        events=dated_allocations(events)
    events=apply_recoveries(events,state.get('recoveries',[]))
    from contingency_policy import forecast_events
    events=forecast_events(state,events,draft,source)
    from contingency_ledger import apply_reserve_uses
    events=apply_reserve_uses(events,state.get('contingency_uses',[]))
    events=observed_events(events,state) if accounting else events
    if draft.get('end_exclusive'):
        bounds=BudgetPeriod.from_plan(draft);events=[e for e in events if bounds.contains(e['date'])]
    return events,explanations


def approve(state,stretch_goal=None):
    events,explanations=result(state)
    plan=state['draft']
    if not plan['income']: raise ValueError('Add at least one income source before approval')
    money(plan['goal'])
    version={'number':len(state['versions'])+1,'plan':deepcopy(plan),'events':deepcopy(events),
             'decisions':deepcopy(state['decisions']),'summary':summarize(events,date.fromisoformat(plan['start']),period_end(plan))}
    if state.get('reserve_changes') or plan.get('contingency_policy'):
        from contingency_policy import sequence
        version['reserve_sequence']=sequence(state)
        version['reserve_changes']=deepcopy(state.get('reserve_changes',[]))
    if state.get('payment_reschedules'):version['payment_reschedules']=deepcopy(state['payment_reschedules'])
    version['savings_baseline']=version['summary']['savings']
    expected=summarize(result(state,accounting=False)[0],date.fromisoformat(plan['start']),period_end(plan))
    version['approval_context']={'review_date':state.get('tracking_date'),
        'observed_savings_impact':expected['savings']-version['summary']['savings'],
        'recovery_forecast_reduction':sum((money(r['amount']) for r in [*state.get('recoveries',[]),*state.get('plan_recoveries',[])]),ZERO)}
    review=date.fromisoformat(state.get('tracking_date') or plan['start'])
    version['approval_context']['reserve_policy_effective']=str(max(date.fromisoformat(plan['start']),review) if not state['versions'] else add_months(review.replace(day=1),1))
    version['approval_context']['contingency_uses']={}
    for use in state.get('contingency_uses',[]):
        for allocation in use['allocations']:
            values=version['approval_context']['contingency_uses'];identity=allocation['event_id'];values[identity]=values.get(identity,ZERO)+allocation['amount']
    version['draft_aspiration']=money(plan['goal'])
    version['stretch_goal']=money(stretch_goal) if stretch_goal is not None else None
    version['monthly_allocations']=deepcopy(aggregate(events,date.fromisoformat(plan['start']),end=period_end(plan)))
    version['category_allocations']={}
    for event in events:
        if event['kind']=='expense':
            key=event.get('category_id')
            version['category_allocations'][key]=version['category_allocations'].get(key,ZERO)+event['amount']
    state['versions'].append(version)
    return deepcopy(version)


def change_decision(state,decision=None,remove_id=None):
    if not state['versions']: raise ValueError('Approve a budget before making forecast decisions')
    old=deepcopy(state['decisions']); candidate=deepcopy(old)
    if remove_id: candidate=[d for d in candidate if d['id']!=remove_id]
    elif decision:
        index=next((i for i,d in enumerate(candidate) if d['id']==decision['id']),None)
        if index is None: candidate.append(deepcopy(decision))
        else: candidate[index]=deepcopy(decision)
    before,_=result(state); after,explanations=result(state,decisions=candidate)
    state['decisions']=candidate
    state['history'].append({'sequence':len(state['history'])+1,'before_decisions':old,'after_decisions':deepcopy(candidate),
                             'before':summarize(before,date.fromisoformat(state['draft']['start']),period_end(state)),
                             'after':summarize(after,date.fromisoformat(state['draft']['start']),period_end(state)),
                             'explanations':deepcopy(explanations)})


def replace_draft(state,candidate):
    if state['versions'] and candidate.get('contingency_policy')!=state['draft'].get('contingency_policy'):
        raise ValueError('Change forecast contingency prospectively; the approved policy cannot be rewritten through budget editing.')
    if state['versions'] and BudgetPeriod.from_plan(candidate)!=BudgetPeriod.from_plan(state['draft']):
        raise ValueError('The approved budget period is locked. Create a separate budget for different dates.')
    before,_=result(state)
    proposed=deepcopy(state)
    if state['versions']:
        cutoff=date.fromisoformat(state.get('tracking_date',candidate['start']))
        from accountability import dated_allocations
        prior=dated_allocations(scheduled_events(state['draft']))
        if state.get('frozen_until'):
            previous=date.fromisoformat(state['frozen_until'])
            prior=[e for e in prior if e['date']>=previous and not (e['kind']=='reserve' and e['date']==previous)]+[e for e in dated_allocations(state['frozen_schedule']) if e['date']<previous or (e['kind']=='reserve' and e['date']==previous)]
        proposed['frozen_schedule']=[e for e in prior if e['date']<cutoff or (e['kind']=='reserve' and e['date']==cutoff)]
        proposed['frozen_until']=str(cutoff)
    after,_=result(proposed,plan=candidate)
    if state['versions']:
        state['frozen_schedule']=proposed['frozen_schedule']
        state['frozen_until']=proposed['frozen_until']
        state['history'].append({'sequence':len(state['history'])+1,'description':'Updated forecast assumptions',
                                 'before_plan':deepcopy(state['draft']),'after_plan':deepcopy(candidate),
                                 'before':summarize(before,date.fromisoformat(candidate['start']),period_end(candidate)),
                                 'after':summarize(after,date.fromisoformat(candidate['start']),period_end(candidate))})
    state['draft']=deepcopy(candidate)


def allowance_amount(item,day,end):
    """Period allocation, not a payment promise; partial final windows are prorated."""
    frequency=item['frequency']
    if frequency not in ('Weekly','Fortnightly','Monthly','Quarterly','Six-monthly','Annual'):raise ValueError('Choose a supported allowance frequency')
    boundary=day+timedelta(days=7 if frequency=='Weekly' else 14) if frequency in ('Weekly','Fortnightly') else add_months(day,{'Monthly':1,'Quarterly':3,'Six-monthly':6,'Annual':12}[frequency])
    days=(min(boundary,end)-day).days
    return (money(item['amount'])*Decimal(days)/Decimal((boundary-day).days)).quantize(Decimal('.01'))


def approved_savings(state):
    if not state['versions']:return None
    version=state['versions'][-1]
    return version.get('savings_baseline',version['summary']['savings'])


from budget_period import BudgetPeriod,period_end


@memo_projection
def dated_cash(events,start,end,opening_cash=0):
    """Daily cash path over the same income/expense events used by aggregate.

    Reserve/provision earmarks are not cash outflows. Same-day events are netted;
    this does not claim to model intraday bank settlement order.
    """
    days={}
    for event in events:
        if start<=event['date']<end and event['kind'] in ('income','expense'):
            days[event['date']]=days.get(event['date'],ZERO)+(event['amount'] if event['kind']=='income' else -event['amount'])
    balance=money(opening_cash);rows=[]
    for day in sorted(days):
        before=balance;balance+=days[day]
        rows.append(dict(date=day,opening=before,movement=days[day],closing=balance))
    return rows
