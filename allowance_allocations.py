"""Explicit annualised weekly policy; legacy calendar allocations are untouched."""
from datetime import date,timedelta
from decimal import Decimal
from finance import money
from household_calendar import week_start

FACTORS={'Weekly':52,'Fortnightly':26,'Monthly':12,'Quarterly':4,'Six-monthly':2,'Annual':1}


def consistent_events(item,start,end):
    from accountability import dated_allocations
    annual=money(item['amount'])*FACTORS[item['frequency']]
    original_first=date.fromisoformat(item.get('first_payment') or str(start))
    if item.get('end_date') and date.fromisoformat(item['end_date'])<original_first:raise ValueError('End date must not precede the allowance start')
    first=max(start,original_first)
    last=min(end,date.fromisoformat(item['end_date'])+timedelta(days=1)) if item.get('end_date') else end
    if last<=first:return []
    total=money(annual*Decimal((last-first).days)/Decimal((end-start).days))
    rate=money(annual/52);cursor=first;remaining=total;rows=[]
    while cursor<last:
        boundary=min(last,week_start(cursor)+timedelta(days=7))
        amount=remaining if boundary==last else min(remaining,money(rate*Decimal((boundary-cursor).days)/7))
        remaining-=amount
        rows.append(dict(id=item['id']+':weekly:'+str(cursor),item_id=item['id'],project_id=None,name=item['name'],category=item['category'],subcategory=item.get('subcategory',''),kind='expense',date=cursor,amount=amount,paid=False,allowance=True,allocation_method='consistent',allocation_end=boundary,estimated=item.get('estimated',True)))
        cursor=boundary
    return dated_allocations(rows)


def calendar_events(item,start,end):
    """New explicit calendar policy: monthly shares follow calendar months.

    Legacy entries without a policy keep their original rolling periods. Weekly
    and fortnightly entries also retain their dated allowance periods.
    """
    from finance import add_months
    annual=money(item['amount'])*FACTORS[item['frequency']];monthly=annual/12
    original_first=date.fromisoformat(item.get('first_payment') or str(start))
    if item.get('end_date') and date.fromisoformat(item['end_date'])<original_first:raise ValueError('End date must not precede the allowance start')
    first=max(start,original_first)
    last=min(end,date.fromisoformat(item['end_date'])+timedelta(days=1)) if item.get('end_date') else end
    if last<=first:return []
    periods=[];cursor=first.replace(day=1)
    while cursor<last:
        boundary=add_months(cursor,1);left=max(cursor,first);right=min(last,boundary)
        periods.append((left,right,monthly*Decimal((right-left).days)/Decimal((boundary-cursor).days)))
        cursor=boundary
    remaining=money(sum((amount for _,_,amount in periods),Decimal(0)));rows=[]
    for index,(left,right,amount) in enumerate(periods):
        value=remaining if index==len(periods)-1 else min(remaining,money(amount));remaining-=value
        rows.append(dict(id=f"{item['id']}:{index}",item_id=item['id'],project_id=None,name=item['name'],category=item['category'],subcategory=item.get('subcategory',''),kind='expense',date=left,amount=value,paid=False,allowance=True,allocation_method='calendar',allocation_end=right,estimated=item.get('estimated',True)))
    return rows


def period_events(item,start,end):
    """New-budget policy: prorate actual days in the original allowance cycle.

    Each cycle is rounded once and distributed cent-exactly across its covered
    days. Scheduled bills are deliberately excluded from this adapter.
    """
    from finance import add_months
    from accountability import dated_allocations
    frequency=item['frequency']
    if frequency not in FACTORS:raise ValueError('Choose a supported allowance frequency')
    anchor=date.fromisoformat(str(item.get('first_payment') or start))
    until=date.fromisoformat(item['end_date'])+timedelta(days=1) if item.get('end_date') else end
    if until<=anchor:raise ValueError('End date must not precede allowance start')
    last=min(end,until);rows=[];index=0
    def boundary(n):
        return anchor+timedelta(days=n*(7 if frequency=='Weekly' else 14)) if frequency in ('Weekly','Fortnightly') else add_months(anchor,n*{'Monthly':1,'Quarterly':3,'Six-monthly':6,'Annual':12}[frequency])
    while boundary(index+1)<=start:index+=1
    while boundary(index)<last:
        cycle=boundary(index);following=boundary(index+1);left=max(start,cycle);right=min(last,following)
        if left<right:
            amount=money(money(item['amount'])*Decimal((right-left).days)/Decimal((following-cycle).days))
            rows.append(dict(id=f"{item['id']}:cycle:{index}",item_id=item['id'],project_id=None,name=item['name'],category=item['category'],subcategory=item.get('subcategory',''),kind='expense',date=left,amount=amount,paid=False,allowance=True,allocation_method='cycle_days_v1',allocation_end=right,estimated=item.get('estimated',True)))
        index+=1
    return dated_allocations(rows)
