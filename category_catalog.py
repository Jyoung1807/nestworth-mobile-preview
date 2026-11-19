"""Shared session taxonomy with deterministic IDs and colours, not database rows."""
import hashlib
import unicodedata
from uuid import uuid5, NAMESPACE_URL
from finance import CATEGORIES

DEFAULTS = ('Mortgage / Rent','Home & Property',*CATEGORIES[1:-1], 'Pets', 'Other')
COLORS = {'Mortgage / Rent':'#5268CF','Home & Property':'#8A9BE0','Housing':'#8A9BE0','Uncategorised':'#A0A7B3','Utilities':'#39A5B8','Vehicles':'#E5A23B','Children':'#B57AD1',
          'Pets':'#D97C9B','Health':'#42A889','Groceries':'#799749','Leisure':'#E17962','Other':'#7C8DA1',
          'Contingency':'#B1BCC9','Income':'#248D79'}


def normalized(name):
    return ' '.join(unicodedata.normalize('NFKC',str(name)).split()).casefold()


def category_id(name):
    token=normalized(name)
    token={'mortgage/rent':'mortgage / rent','home and property':'home & property','home&property':'home & property'}.get(token,token)
    if token=='home & property':token='housing'  # Retain legacy property category identity.
    return 'cat_'+uuid5(NAMESPACE_URL,'young-budget/category/'+token).hex


def subcategory_id(parent,name):
    return 'sub_'+uuid5(NAMESPACE_URL,parent+'/'+normalized(name)).hex if str(name).strip() else None


def color_for(name):
    name=next((n for n in COLORS if normalized(n)==normalized(name)),name)
    if name in COLORS: return COLORS[name]
    palette=['#9680BA','#4B9CB0','#B88056','#5B9B83','#A36D8E','#838C4F']
    return palette[int(hashlib.sha256(normalized(name).encode()).hexdigest()[:8],16)%len(palette)]


def register(state,name,sub=''):
    label=' '.join(str(name).split())
    aliases={'housing':'Home & Property','home and property':'Home & Property','home&property':'Home & Property','mortgage/rent':'Mortgage / Rent'}
    label=aliases.get(normalized(label),label)
    if not label: raise ValueError('Enter a category name')
    registry=state.setdefault('category_catalog',{})
    key=category_id(label)
    if key not in registry:
        registry[key]={'id':key,'name':label,'color':color_for(label),'subcategories':{}}
    record=registry[key]
    if str(sub).strip():
        child=subcategory_id(key,sub)
        record['subcategories'].setdefault(child,{'id':child,'name':' '.join(str(sub).split())})
    state['categories']=[r['name'] for r in registry.values() if normalized(r['name']) not in ('income','contingency','uncategorised','uncategorized')]
    return record


def tag(state,row):
    child=row.get('subcategory') or ''
    name=row.get('category')
    if not name or normalized(name) in ('uncategorised','uncategorized'):name='Uncategorised';child=''
    item=register(state,name,child)
    row['category']=item['name']; row['category_id']=item['id']
    row['subcategory_id']=subcategory_id(item['id'],child)
    row['subcategory']=item['subcategories'][row['subcategory_id']]['name'] if row['subcategory_id'] else ''
    return row


def sync(state,transactions=()):
    migrate_housing(state,transactions)
    for name in [*DEFAULTS,*state.get('categories',[])]: register(state,name)
    for collection in ('expenses','projects'):
        for row in state['draft'][collection]: tag(state,row)
    for row in transactions: tag(state,row)
    # Approved versions are deliberately never rewritten during session upgrades.


def remap_housing(row):
    if normalized(row.get('category') or '')=='housing':
        label=normalized(row.get('name',row.get('description','')))
        primary=('mortgage' in label or label=='rent' or label.startswith('rent ') or label in ('housing plan','synthetic housing expense') or row.get('source_id')=='home:primary')
        row['category']='Mortgage / Rent' if primary else 'Home & Property'
    return row


def migrate_housing(state,transactions):
    # Re-label rows in place; never duplicate entries or rewrite approved snapshots.
    for key in ('expenses','projects'):
        for row in state['draft'][key]:remap_housing(row)
    for row in transactions:remap_housing(row)
    for decision in state.get('decisions',[]):
        remap_housing(decision)
        for offset in decision.get('offsets',[]):
            if offset['kind'].startswith('category_') and offset['target'] in ('Housing',category_id('Housing')) and not state.get('housing_split'):
                offset['target']='legacy_housing'
    old=state.get('category_catalog',{}).get(category_id('Housing'))
    if old and old['name']=='Housing':old.update(name='Home & Property',color=color_for('Home & Property'))
    state['categories']=['Home & Property' if normalized(n)=='housing' else n for n in state.get('categories',[])]
    state['housing_split']=True
