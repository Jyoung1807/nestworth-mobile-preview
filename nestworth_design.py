"""Nestworth presentation tokens and components; no financial state or I/O."""
from html import escape

FOREST='#173F39'
SAGE='#D9E5DC'
GOLD='#AA8245'
INK='#213832'
MUTED='#677870'
NEGATIVE='#AD4941'
PALETTE=['#173F39','#789A85','#AA8245','#466D82','#A7899B','#9DA570','#A96F55','#64798D']


def styles(st):
    st.markdown('''<style>
    :root{--nw-forest:#173F39;--nw-sage:#D9E5DC;--nw-ink:#213832;--nw-muted:#677870;--nw-border:#DFE6DF;}
    .stApp{background:#F6F7F3;color:var(--nw-ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
    .stMainBlockContainer{max-width:1200px;padding-top:3.75rem;}
    h1,h2,h3{color:var(--nw-forest);letter-spacing:-.035em;font-weight:600!important;}
    h1{font-size:2.2rem!important;} h2{font-size:1.65rem!important;} h3{font-size:1.2rem!important;}
    p,label{line-height:1.5;} [data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:#56695E!important;}
    [data-testid="stSidebar"]{background:#EAF0E9;border-right:1px solid var(--nw-border);}
    [data-testid="stSidebar"] [role="radiogroup"]{gap:5px;}
    [data-testid="stSidebar"] [data-testid="stRadio"] label{padding:9px 12px;border-radius:10px;}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:var(--nw-forest);color:white;}
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p{color:white;}
    button{border-radius:9px!important;font-weight:550!important;}
    [data-testid="stBaseButton-primary"],button[kind="primary"]{background:#173F39!important;border-color:#173F39!important;color:white!important;}
    button[kind="secondary"]{border-color:var(--nw-border)!important;background:#fff!important;color:var(--nw-forest)!important;}
    button:focus-visible,input:focus-visible{outline:3px solid #AA8245!important;outline-offset:2px;}
    [data-testid="stProgressBar"] [role="progressbar"]>div{background:var(--nw-forest)!important;}
    [data-testid="stMetric"]{background:white;border:1px solid var(--nw-border);border-radius:14px;padding:18px 16px;}
    [data-testid="stMetricValue"]{font-size:clamp(1.25rem,2.4vw,2rem)!important;letter-spacing:-.045em;color:var(--nw-forest);}
    [data-testid="stMetricDelta"],[data-testid="stMetricDelta"] div,[data-testid="stMetricDelta"] span,[data-testid="stMetricLabel"] div,[data-testid="stMetricLabel"] p{white-space:normal!important;overflow:visible!important;text-overflow:clip!important;}
    [data-testid="stMetricDelta"] svg{display:none;}
    [data-testid="stMetricLabel"]{font-size:.8rem;letter-spacing:.01em;color:var(--nw-muted);}
    [data-testid="stVerticalBlockBorderWrapper"]>div{border-color:var(--nw-border)!important;border-radius:13px!important;}
    [data-testid="stExpander"]{border:1px solid var(--nw-border);border-radius:10px;background:#fff;}
    [data-testid="stTextInput"] input,[data-testid="stNumberInput"] input{font-size:16px!important;}
    [data-testid="stAppDeployButton"],[data-testid="stMainMenu"]{display:none;}
    .nw-demo-banner{font-size:14px;font-weight:650;padding:8px 12px;border-radius:9px;background:#E9DDB8;color:#594820;margin-bottom:12px;}
    [class*="st-key-financial_alert_warning"]{border-left:5px solid #AA5342!important;background:#FFF6EC;border-radius:12px;padding:16px;}
    [class*="st-key-financial_alert_critical"]{border-left:5px solid #A03E36!important;background:#FFEEE9;border-radius:12px;padding:16px;}
    [class*="st-key-financial_alert_info"]{border-left:5px solid #8FAE91!important;background:#EDF3E8;border-radius:12px;padding:16px;}
    .nw-brand{display:flex;align-items:center;gap:11px;margin:0 0 1.6rem;color:#173F39;}
    .nw-mark{width:39px;height:39px;display:grid;place-items:center;border-radius:12px;background:#173F39;color:#E4C996;font-size:24px;}
    .nw-wordmark{font-size:29px;letter-spacing:-1.3px;font-weight:650;line-height:1.1;}
    .nw-tagline{font-size:11px;letter-spacing:.07em;color:#677870;margin-top:5px;}
    .nw-eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#677870;margin:12px 0 8px;font-weight:600;}
    .nw-intro{font-family:Georgia,serif;font-size:clamp(1.8rem,4vw,2.8rem);line-height:1.15;letter-spacing:-.04em;color:#173F39;margin:0 0 10px;}
    .nw-line{display:flex;justify-content:space-between;align-items:baseline;gap:14px;padding:12px 0;border-bottom:1px solid #E6EBE5;}
    .nw-line strong{color:#173F39;font-variant-numeric:tabular-nums;white-space:nowrap;}
    .nw-line small{display:block;color:#677870;font-size:12px;margin-top:3px;}
    .nw-empty{padding:26px;border:1px dashed #B8CABD;border-radius:16px;background:#EFF4ED;margin:12px 0;color:#173F39;}
    [class*="st-key-nw_hero"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:12px!important;}
    [class*="st-key-nw_hero"] [data-testid="stColumn"]{flex:1 1 20%!important;min-width:0!important;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"]{background:#173F39;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [data-testid="stMetricValue"]{color:#fff;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [data-testid="stMetricLabel"]{color:#D9E5DC;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [class*="_unfavourable"] [data-testid="stMetricDelta"]{color:#FFD2C3!important;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [class*="_favourable"] [data-testid="stMetricDelta"]{color:#D6EACF!important;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [class*="_neutral"] [data-testid="stMetricDelta"]{color:#D9E5DC!important;}
    [class*="st-key-nw_editor"]{background:white;border:1px solid #DFE6DF;border-radius:16px;padding:20px;}
    [data-testid="stMain"] [data-testid="stCheckbox"] [data-testid="stWidgetLabel"]{max-width:100%;}
    @media(max-width:768px){
      [class*="st-key-nw_hero"] [data-testid="stColumn"]{flex:1 1 44%!important;min-width:0!important;}
      [class*="st-key-nw_hero"] [data-testid="stMetric"]{min-height:112px;padding:12px!important;}
      [class*="st-key-nw_hero"] [data-testid="stMetricValue"]{font-size:clamp(1.1rem,4.9vw,1.55rem)!important;}
      [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [class*="_unfavourable"] [data-testid="stMetricDelta"]{color:#FFD2C3!important;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [class*="_favourable"] [data-testid="stMetricDelta"]{color:#D6EACF!important;}
    [class*="st-key-nw_hero_annual"] [data-testid="stColumn"]:nth-child(3) [class*="_neutral"] [data-testid="stMetricDelta"]{color:#D9E5DC!important;}
    [class*="st-key-nw_editor"]{padding:14px;}
      [data-testid="stMain"] [role="radiogroup"]{gap:8px;flex-wrap:wrap;}
      .nw-wordmark{font-size:25px;} .nw-brand{margin-bottom:1rem;}
      .nw-line{font-size:14px;gap:8px;} .nw-line>div{min-width:0;overflow-wrap:anywhere;}
    }
    </style>''',unsafe_allow_html=True)


def brand(st):
    st.markdown('<div class="nw-brand"><div class="nw-mark" aria-hidden="true">⌂</div><div><div class="nw-wordmark">Nestworth</div><div class="nw-tagline">Your household. Your future.</div></div></div>',unsafe_allow_html=True)


def intro(st,eyebrow,title):
    st.markdown('<div class="nw-eyebrow">'+escape(eyebrow)+'</div><div class="nw-intro">'+escape(title)+'</div>',unsafe_allow_html=True)


def line(st,title,value,detail=''):
    st.markdown('<div class="nw-line"><div>'+escape(str(title))+'<small>'+escape(str(detail))+'</small></div><strong>'+escape(str(value))+'</strong></div>',unsafe_allow_html=True)


def empty(st,title,detail):
    st.markdown('<div class="nw-empty"><strong>'+escape(title)+'</strong><p>'+escape(detail)+'</p></div>',unsafe_allow_html=True)


def chart_style(chart):
    return chart.configure_view(stroke=None).configure_axis(labelFontSize=12,titleFontSize=12,domain=False,gridColor='#E5EBE4',labelColor=MUTED,titleColor=MUTED).configure_legend(labelColor=INK,labelFontSize=12,padding=12)
