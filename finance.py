"""Pure calendar-aware demonstration calculations. All money is Decimal dollars."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

FREQUENCIES = ('Weekly', 'Fortnightly', 'Monthly', 'Quarterly', 'Six-monthly', 'Annual', 'One-off')
CATEGORIES = ('Housing', 'Vehicles', 'Children', 'Utilities', 'Health', 'Groceries', 'Leisure', 'Other')


def money(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid monetary amount") from None
    if not result.is_finite() or result < 0:
        raise ValueError('Amounts must be finite and non-negative')
    try:
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError('Monetary amount is too large') from None


def add_months(day, count):
    year, month = divmod(day.year * 12 + day.month - 1 + count, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def months(start, count=12):
    first = start.replace(day=1)
    return [add_months(first, i) for i in range(count)]


def payment_dates(first, frequency, start, end):
    """Inclusive start, exclusive end. Month-end schedules retain original day."""
    if frequency not in FREQUENCIES:
        raise ValueError('Unsupported frequency')
    if frequency == 'One-off':
        return [first] if start <= first < end else []
    result, n = [], 0
    while True:
        if frequency in ('Weekly', 'Fortnightly'):
            occurrence = first + timedelta(days=n * (7 if frequency == 'Weekly' else 14))
        else:
            occurrence = add_months(first, n * {'Monthly':1, 'Quarterly':3, 'Six-monthly':6, 'Annual':12}[frequency])
        if occurrence >= end:
            break
        if occurrence >= start:
            result.append(occurrence)
        n += 1
    return result


def scheduled_totals(items, start, count=12):
    periods = months(start, count)
    end = add_months(periods[0], count)
    totals = {d.isoformat(): Decimal('0.00') for d in periods}
    for item in items:
        amount = money(item['amount'])
        first = date.fromisoformat(str(item['first_payment']))
        until = date.fromisoformat(str(item['end_date'])) + timedelta(days=1) if item.get('end_date') else end
        for day in payment_dates(first, item['frequency'], periods[0], min(end, until)):
            totals[day.replace(day=1).isoformat()] += amount
    return totals


def forecast(income, expenses, start, adjustments=(), contingency_percent=0, closed_actual=None):
    """Frozen budget vs actual/forward scenario. Offsets move, never invent money."""
    incoming = scheduled_totals(income, start)
    base = scheduled_totals(expenses, start)
    categories = {cat: scheduled_totals([e for e in expenses if e['category']==cat], start) for cat in CATEGORIES}
    revised = dict(base)
    available = {cat: dict(values) for cat, values in categories.items()}
    for adj in adjustments:
        period = adj['month']
        if period not in revised or period in (closed_actual or {}):
            raise ValueError('Adjustments require an open forecast month')
        amount = money(adj['amount'])
        offset = adj.get('offset', 'Reduce savings')
        if offset != 'Reduce savings':
            if offset not in available or available[offset][period] < amount:
                raise ValueError('Offset exceeds the remaining category budget')
            available[offset][period] -= amount
        else:
            revised[period] += amount
    percent = Decimal(str(contingency_percent))
    if not percent.is_finite() or not 0 <= percent <= 100:
        raise ValueError('Contingency percentage must be 0–100')
    rows = []
    for period in incoming:
        contingency = (max(incoming[period]-revised[period], Decimal(0))*percent/100).quantize(Decimal('.01'))
        actual = (closed_actual or {}).get(period)
        spending = money(actual) if actual is not None else revised[period]+contingency
        rows.append({'month':period, 'income':incoming[period], 'budget':base[period],
                     'actual':money(actual) if actual is not None else None,
                     'forecast':spending, 'contingency':contingency if actual is None else Decimal(0),
                     'savings':incoming[period]-spending})
    return rows
