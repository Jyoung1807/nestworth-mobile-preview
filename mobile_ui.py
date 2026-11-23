"""Responsive presentation shared by every financial screen."""
def mobile_styles(st):
    st.html('''<style>
    .stMainBlockContainer{max-width:1180px;}
    .category-strip{margin-top:20px;margin-bottom:8px;}
    .category-line{display:flex;justify-content:space-between;gap:8px;font-size:16px;font-weight:600;flex-wrap:wrap;}
    .spending-progress{height:24px;border-radius:10px;background:#e4eaf0;margin-top:8px;overflow:hidden;}
    .spending-progress>div{height:24px;border-radius:10px;}
    .category-balance{font-size:15px;margin-top:7px;font-weight:600;}
    [class*="st-key-weekly_summary"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:4px!important;}
    [class*="st-key-weekly_summary"] [data-testid="stColumn"]{min-width:0!important;flex:1 1 0%!important;}
    [class*="st-key-weekly_summary"] [data-testid="stMetric"]{padding:6px!important;border-radius:8px;}
    [class*="st-key-weekly_summary"] [data-testid="stMetricValue"]{font-size:clamp(.95rem,2vw,1.6rem)!important;}
    .category-line>*{min-width:0;max-width:100%;overflow-wrap:anywhere;}
    .thin-progress{height:6px;border-radius:6px;background:#e4eaf0;margin-top:5px;}
    .thin-progress>div{height:6px;border-radius:6px;}
    [class*="st-key-daily_nav"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:4px!important;}
    [class*="st-key-daily_nav"] [data-testid="stColumn"]{min-width:0!important;flex:1 1 0%!important;}
    [class*="st-key-period_nav_"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:4px!important;}
    [class*="st-key-period_nav_"] [data-testid="stColumn"]{min-width:0!important;flex:1 1 0%!important;}
    [class*="st-key-category_filters"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:4px!important;}
    [class*="st-key-category_filters"] [data-testid="stColumn"]{min-width:0!important;flex:1 1 0%!important;}
    [class*="st-key-daily_nav"] button{padding:4px!important;min-width:0!important;font-size:14px!important;}

    [class*="st-key-daily_nav"]{display:none;}
    [class*="st-key-mobile_utilities"]{display:none;}
    [class*="st-key-setup_navigation"] [data-testid="stHorizontalBlock"], [class*="st-key-plan_totals"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:4px!important;}
    [class*="st-key-setup_navigation"] [data-testid="stColumn"], [class*="st-key-plan_totals"] [data-testid="stColumn"]{min-width:0!important;flex:1 1 0%!important;}
    @media(max-width:768px){
      .stMainBlockContainer{padding-bottom:calc(110px + env(safe-area-inset-bottom,0px))!important;}
      [class*="st-key-mobile_utilities"]{display:block;}
      [class*="st-key-mobile_utilities"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:4px!important;}
      [class*="st-key-mobile_utilities"] [data-testid="stColumn"]{min-width:0!important;flex:1 1 0%!important;}
      [class*="st-key-daily_nav"]{display:block;position:fixed;bottom:0;left:0;right:0;z-index:998;background:var(--background-color,#fff);border-top:1px solid #dce3ea;padding:6px 6px calc(6px + env(safe-area-inset-bottom,0px));}
      [class*="st-key-daily_nav"] button{flex-direction:column;gap:2px!important;min-height:58px!important;}
      [class*="st-key-daily_nav"] button [data-has-shortcut]{display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:2px!important;width:100%;min-width:0;}
      [class*="st-key-daily_nav"] [data-testid="stMarkdownContainer"]{overflow:visible!important;text-overflow:clip!important;white-space:normal!important;max-width:100%;}
      [class*="st-key-daily_nav"] button p{font-size:12px!important;white-space:normal!important;}
      .budget-keyboard-open [class*="st-key-daily_nav"]{position:static;}
    }
    @media(max-width:768px) and (max-height:450px){[class*="st-key-daily_nav"]{position:static!important;}}
    [data-testid="stMain"] button [data-testid="stMarkdownContainer"]{white-space:normal!important;text-overflow:clip!important;overflow:visible!important;}
    [data-testid="stMain"] button p{white-space:normal!important;}
    [data-testid="stMain"] button{min-height:44px;white-space:normal;}
    [data-testid="stMetricLabel"], summary p{overflow-wrap:anywhere;}
    [data-testid="stMain"] [role="radiogroup"]{flex-wrap:wrap;}
    @media(max-width:640px){
      .stMainBlockContainer{padding:3.75rem 0.65rem 0.8rem;}
      [data-testid="stMain"] h1{font-size:1.3rem!important;line-height:1.3!important;}
      [data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:0.45rem;}
      [data-testid="stColumn"]{min-width:min(100%,260px)!important;flex:1 1 100%!important;}
      [data-testid="stMetric"]{padding:10px!important;}
      [data-testid="stMetricValue"]{font-size:1.35rem!important;}
      [data-testid="stVerticalBlockBorderWrapper"]{min-width:0;}
      .vega-embed{max-width:100%;}
      [data-testid="stDataFrame"]{max-width:100%;}
      h1,h2,h3,p{overflow-wrap:anywhere;}
      [class*="st-key-expense_header_"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;}
      [class*="st-key-expense_header_"] [data-testid="stColumn"]{min-width:0!important;flex:1 1 0%!important;}
      [class*="st-key-expense_header_"] [data-testid="stColumn"]:last-child{flex:0 0 44px!important;}
    }
    </style>''')


def financial_rows(st,rows,key):
    """Disclosure cards keep every column readable without a sideways table."""
    for n,row in enumerate(rows):
        values=list(row.items())
        if not values:continue
        with st.expander(str(values[0][1]),key=key+':'+str(n)):
            for label,value in values[1:]:st.write(f'**{label}**: {value}')


def responsive_table(st,data,**kwargs):
    # A compact, keyboard-accessible record view adapts to phone widths.
    rows=data.to_dict('records') if hasattr(data,'to_dict') else data
    if not rows:st.caption('No records in this selection.');return
    with st.expander('Desktop spreadsheet (optional)'):
        st.dataframe(data,**kwargs)
    if len(rows)>12:
        import hashlib
        identity=hashlib.sha256(repr(rows).encode()).hexdigest()[:20]
        selected=st.selectbox('Choose a financial record',range(len(rows)),format_func=lambda i,items=tuple(rows):' · '.join(str(v) for v in list(items[i].values())[:2]),key='financial-record-'+identity)
        rows=[rows[selected]]
    for row in rows:
        parts=list(row.items())
        title=' · '.join(str(value) for _,value in parts[:2])
        with st.expander(title):
            for label,value in parts:st.write(f'**{label}**: {value}')
