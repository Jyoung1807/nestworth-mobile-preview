"""Reusable category charts and cumulative projections; no changes to cash maths."""
from mobile_ui import responsive_table
from datetime import date
from decimal import Decimal
import altair as alt
import pandas as pd
from category_catalog import category_id,color_for
from finance import add_months
from planning import aggregate


def category_frame(events,start):
    end=add_months(start,12)
    values={}
    for e in events:
        if e['kind']!='expense' or not start<=e['date']<end: continue
        key=(e['date'].replace(day=1).isoformat(),category_id(e['category']),e['category'])
        values[key]=values.get(key,Decimal(0))+e['amount']
    for category in {key[2] for key in list(values)}:
        for n in range(12): values.setdefault((add_months(start,n).isoformat(),category_id(category),category),Decimal(0))
    return pd.DataFrame([{'month':m,'category_id':id,'category':c,'amount':float(v)} for (m,id,c),v in values.items()],columns=['month','category_id','category','amount'])


def category_scale(names):
    names=sorted(set(names))
    return alt.Scale(domain=names,range=[color_for(name) for name in names])


def spending_charts(st,events,start,key,drill=True):
    df=category_frame(events,start)
    if df.empty:
        st.info('Your category charts will appear when you add expenses or plans.'); return
    st.subheader('Where your money goes each month')
    chart=alt.Chart(df).mark_bar(cornerRadiusTopLeft=3,cornerRadiusTopRight=3).encode(
        x=alt.X('month:O',title=None,axis=alt.Axis(labelAngle=0,labelExpr="slice(datum.label,5,7)")), y=alt.Y('sum(amount):Q',title='Expenses ($)'),
        color=alt.Color('category:N',scale=category_scale(df.category),title=None),
        tooltip=[alt.Tooltip('month:O',title='Month'),alt.Tooltip('category:N',title='Category'),alt.Tooltip('amount:Q',title='Amount',format='$,.2f')])
    st.altair_chart(chart,width='stretch')
    monthly=df.groupby('month').amount.sum()
    peak=monthly.idxmax(); average=monthly.mean()
    st.caption(f'Highest spending: {peak} · ${monthly.max():,.2f}'+(f' · {monthly.max()/average:.1f}× the monthly average' if average else '')+'. Contingency is shown separately.')
    peaks=monthly[monthly>average*1.25]
    if not peaks.empty: st.warning('Plan ahead for higher-cost months: '+', '.join(f'{month}: ${amount:,.0f}' for month,amount in peaks.items()))
    totals=df.groupby('category',as_index=False).amount.sum()
    totals['percent']=totals.amount/totals.amount.sum() if totals.amount.sum() else 0
    st.subheader('Your annual spending mix')
    donut=alt.Chart(totals).mark_arc(innerRadius=80,outerRadius=130).encode(
        theta=alt.Theta('amount:Q'), color=alt.Color('category:N',scale=category_scale(totals.category),title=None),
        tooltip=[alt.Tooltip('category:N',title='Category'),alt.Tooltip('amount:Q',title='Annual spending',format='$,.2f'),alt.Tooltip('percent:Q',title='Share',format='.1%')])
    left,right=st.columns([1,1])
    left.altair_chart(donut,width='stretch')
    with right:
        for row in totals.itertuples():
            st.write(f'**{row.category}** · ${row.amount:,.0f} · {row.percent:.0%}')
    if drill:
        with st.expander('Explore a month or individual expense'):
            selected=st.selectbox('Month to explore',list(monthly.index),index=list(monthly.index).index(peak),key=key+':month')
            names=sorted(df.category.unique())
            category=st.selectbox('Category to explore',['All categories',*names],key=key+':category')
            rows=[{'Payment':e['name'],'Date':e['date'],'Category':e['category'],'Amount ($)':float(e['amount'])} for e in events
                  if e['kind']=='expense' and e['date'].strftime('%Y-%m')==selected[:7] and (category=='All categories' or e['category']==category)]
            responsive_table(st,pd.DataFrame(rows),hide_index=True,width='stretch')


def cumulative_rows(forecast,budget,start,goal,budget_label="Original budget",period="Monthly"):
    forecast_rows=aggregate(forecast,start,period)
    budget_rows=aggregate(budget,start,period) if budget is not None else None
    total_f=Decimal(0); total_b=Decimal(0); result=[]
    for i,row in enumerate(forecast_rows):
        total_f+=row['savings']
        result.append({'month':row['period'],'period':row.get('period_label',row['period']),'series':'Latest forecast','savings':float(total_f)})
        if budget_rows is not None:
            total_b+=budget_rows[i]['savings']
            result.append({'month':row['period'],'period':row.get('period_label',row['period']),'series':budget_label,'savings':float(total_b)})

    return result


def savings_chart(st,events,original,start,goal,budget_label="Original budget",height=280,period="Monthly"):
    st.subheader('Watch your savings build')
    rows=cumulative_rows(events,original,start,goal,budget_label,period)
    chart=alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
        x=alt.X('month:T',title=None,axis=alt.Axis(format='%b' if period=='Monthly' else '%d %b',tickCount=6,labelOverlap='greedy')),y=alt.Y('savings:Q',title='Savings ($)'),
        color=alt.Color('series:N',scale=alt.Scale(domain=['Latest forecast',budget_label],range=['#258C80','#6676D6']),title=None,legend=alt.Legend(orient='bottom',direction='vertical',labelLimit=260)),
        strokeDash=alt.StrokeDash('series:N',scale=alt.Scale(domain=['Latest forecast',budget_label],range=[[1,0],[6,3]]),legend=None),
        tooltip=['period:N','series:N',alt.Tooltip('savings:Q',format='$,.2f')])
    st.altair_chart(chart.properties(height=height),width='stretch')
    st.caption('Savings accumulate from income less expenses and reserved contingency. This starts at zero savings for the year; existing cash is shown separately below. Genuine actuals are not connected, so no actual savings line is shown.')


def cash_flow_chart(st,rows,cumulative=False):
    measures={'closing_cash':'Available cash','after_reserve':'After contingency reserve'} if cumulative else {'income':'Income','expenses':'Expenses','cash_flow':'Net cash flow'}
    data=[{'period':r['period'],'range':r.get('period_label',r['period']),'measure':name,'amount':float(r[field])} for r in rows for field,name in measures.items()]
    base=alt.Chart(pd.DataFrame(data)).encode(
        x=alt.X('period:O',sort=[r['period'] for r in rows],title=None,axis=alt.Axis(labelExpr="slice(datum.label,5,10)",labelOverlap='greedy',labelAngle=-35)),
        y=alt.Y('amount:Q',title='Dollars ($)'),
        color=alt.Color('measure:N',title=None,legend=alt.Legend(orient='bottom',columns=1)),
        tooltip=[alt.Tooltip('range:N',title='Period'),'measure:N',alt.Tooltip('amount:Q',format='$,.2f')])
    chart=base.mark_line() if cumulative else base.mark_bar().encode(xOffset='measure:N')
    st.altair_chart(chart.properties(height=260),width='stretch')
