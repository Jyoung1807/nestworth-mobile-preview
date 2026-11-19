"""Bounded CSV staging for session-only historical review; no database or network I/O."""
import csv
import hashlib
import io
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from finance import add_months,money
from category_catalog import normalized

MAX_BYTES=2*1024*1024
MAX_ROWS=10000


def fingerprint(row):
    value='|'.join((row['date'],normalized(row['description']),str(money(row['amount']))))
    return hashlib.sha256(value.encode()).hexdigest()


def csv_rows(reader):
    try:yield from reader
    except csv.Error:raise ValueError('Malformed CSV quoting. Export the file again as CSV.') from None


def preview_csv(content,start,categories,existing=()):
    if not content or len(content)>MAX_BYTES:raise ValueError('Choose a non-empty CSV up to 2 MB.')
    try:text=content.decode('utf-8-sig')
    except UnicodeDecodeError:raise ValueError('Save the CSV as UTF-8 text.') from None
    reader=csv.DictReader(io.StringIO(text,newline=''),strict=True)
    headers=reader.fieldnames or []
    names=[h.strip().casefold() for h in headers]
    if len(names)!=len(set(names)) or not {'date','description','amount'}<=set(names):raise ValueError('CSV needs unique Date, Description and Amount columns; Category is optional.')
    known={normalized(c):c for c in categories};left=add_months(start,-12)
    file_id=hashlib.sha256(content).hexdigest();seen={fingerprint(r) for r in existing};ids={r['id'] for r in existing}
    rows=[]
    for index,raw in enumerate(csv_rows(reader),2):
        if index-1>MAX_ROWS:raise ValueError('Use at most 10,000 transaction rows per file.')
        if None in raw or any(v is None for v in raw.values()):raise ValueError(f'Row {index}: columns do not match the header.')
        values={name:raw[header].strip() for header,name in zip(headers,names)}
        if not any(values.values()):continue
        try:
            token=values['date']
            when=date.fromisoformat(token) if len(token)==10 and token[4]=='-' else datetime.strptime(token,'%d/%m/%Y').date()
        except ValueError:raise ValueError(f'Row {index}: use YYYY-MM-DD or DD/MM/YYYY dates.') from None
        if not left<=when<start:raise ValueError(f'Row {index}: historical dates must be from {left} to {start} (end excluded).')
        try:
            raw_amount=Decimal(values['amount'])
            if not raw_amount.is_finite() or raw_amount<=0 or raw_amount>Decimal('999999999') or raw_amount!=raw_amount.quantize(Decimal('.01')):raise InvalidOperation
        except (InvalidOperation,ValueError):raise ValueError(f'Row {index}: Amount must be positive spending, with at most two decimal places and no currency symbols. Exclude income/refunds.') from None
        description=values['description']
        if not description or len(description)>300:raise ValueError(f'Row {index}: enter a description up to 300 characters.')
        category=known.get(normalized(values.get('category','')))
        row=dict(id='csv:'+file_id+':'+str(index),date=str(when),description=description,amount=money(raw_amount),category=category,source='csv-session',reviewed=False)
        token=fingerprint(row)
        status='Already imported' if row['id'] in ids else 'Possible duplicate' if token in seen else 'New'
        rows.append(dict(record=row,status=status));seen.add(token)
    if not rows:raise ValueError('No transaction rows were found.')
    return rows


def import_csv(state,content,include_duplicates=False):
    # Revalidate at confirmation, including dates, household category context and
    # existing IDs. Never trust a stale preview or replace an existing record.
    rows=state.setdefault('spending',[])
    preview=preview_csv(content,date.fromisoformat(state['draft']['start']),state['categories'],rows)
    added=[item['record'] for item in preview if item['status']=='New' or include_duplicates and item['status']=='Possible duplicate']
    rows.extend(added)
    if added:
        from setup_model import setup_state
        setup_state(state).update(history_choice='undecided',history_invitation=False)
        state['history_reviewed']=False
    return len(added)
