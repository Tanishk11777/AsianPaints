"""Management views and portable, offline report exports."""
from __future__ import annotations

import hashlib
import html
import io
import json
import math
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

INK = '#211c39'
PURPLE = '#6d42cb'
TEAL = '#087f83'
AMBER = '#b67b0c'
ROSE = '#c44763'
MUTED = '#77758b'
COLORS = {'Introduction': '#9d8ad8', 'Growth': PURPLE, 'Maturity': TEAL,
          'Decline': '#cf972e', 'Exit': ROSE, 'Unclassified': '#9695a3'}

CSS = """
:root{--ink:#211c39;--purple:#6d42cb;--teal:#087f83;--muted:#77758b}
body,.gradio-container{font-family:Arial,Helvetica,sans-serif!important;background:#f5f5fa!important;color:var(--ink)!important}
.gradio-container{max-width:1600px!important;margin:auto!important;padding:22px 30px!important}
footer{display:none!important}
.hero{background:linear-gradient(112deg,#201934,#37245c 68%,#483170);color:white;border-radius:20px;padding:30px 36px;margin-bottom:14px;position:relative;overflow:hidden}
.hero::after{content:'';position:absolute;width:210px;height:210px;border:38px solid #ffffff08;border-radius:50%;right:20px;top:-60px}
.eyebrow{font-size:11px;letter-spacing:2.3px;text-transform:uppercase;font-weight:700;opacity:.75;margin-bottom:11px}
.hero h1{font-size:34px!important;font-weight:700;letter-spacing:-1px;margin:0 0 9px!important;color:white!important}
.hero p{font-size:14px;color:#ded7ee;margin:0;max-width:780px;line-height:1.55}
.hero .hero-meta{margin-top:18px;display:flex;gap:10px;flex-wrap:wrap}
.pill{display:inline-block;font-size:11px;letter-spacing:.5px;border-radius:100px;padding:6px 11px;background:#ffffff15;color:#f6f1ff;border:1px solid #ffffff25}
.source-strip{font-size:12px;color:#696277;padding:8px 0 15px;line-height:1.55}
.source-strip strong{color:var(--ink)}
#sidebar{background:#fff;border:1px solid #e3e0eb;border-radius:16px;padding:18px!important;gap:12px!important;min-width:260px!important}
#sidebar label{font-size:12px!important;font-weight:600!important}
#sidebar .block{border-radius:10px!important}
#simulate{background:var(--purple)!important;color:#fff!important;border:0!important;font-size:15px!important;min-height:48px!important;box-shadow:0 5px 14px #6d42cb25}
.step-title{font-weight:700;font-size:12px;letter-spacing:1px;text-transform:uppercase;color:#6d42cb;margin:6px 0 2px}
.step-note{font-size:12px;color:#77758b;line-height:1.55}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:8px 0 15px}
.metric{background:#fff;border:1px solid #e7e3ef;border-radius:14px;padding:19px 18px;min-height:128px;box-sizing:border-box}
.metric-label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#77758b;margin-bottom:12px}
.metric-value{font-size:28px;letter-spacing:-1px;line-height:1.12;font-weight:700;color:#211c39}
.metric-detail{font-size:11px;color:#77758b;line-height:1.5;margin-top:9px}
.good{color:#087f83!important}.bad{color:#ba415f!important}.amber{color:#a76c06!important}
.decision{display:flex;gap:18px;align-items:flex-start;border-radius:13px;padding:18px 21px;background:#e9f5f3;border:1px solid #cce9e2;margin:4px 0 17px}
.decision.warn{background:#fff5e6;border-color:#f0dfbb}.decision.neutral{background:#eeeaf8;border-color:#e0d7f1}
.decision strong{display:block;font-size:15px;margin-bottom:5px;color:#211c39}
.decision p{font-size:13px;line-height:1.55;margin:0;color:#5c596c}
.decision .decision-mark{font-size:12px;font-weight:700;background:#fff;border-radius:7px;padding:7px 10px;white-space:nowrap}
.section-head{margin:14px 0 9px}.section-head h2{font-size:19px!important;font-weight:700!important;letter-spacing:-.3px;margin:0 0 5px!important}
.section-head p{font-size:12px;color:#77758b;line-height:1.5;margin:0}
.empty{background:linear-gradient(135deg,#fff,#f0ecfa);border:1px solid #e1daee;border-radius:16px;padding:65px 35px;text-align:center;margin:12px 0}
.empty h2{font-size:27px!important;color:#31214f!important;margin-bottom:13px!important}.empty p{max-width:580px;margin:0 auto;color:#767086;font-size:14px;line-height:1.8}
.state-note{font-size:12px;line-height:1.6;padding:9px 12px;background:#f0edf6;border-radius:9px;color:#5b4f74}
.gradio-container .tab-nav{border-bottom:1px solid #ddd5ec!important;padding:0 0 6px!important;gap:4px!important}
.gradio-container .tab-nav button{font-size:13px!important;padding:10px 13px!important;border-radius:9px!important}
.gradio-container .tab-nav button.selected{background:#eee8fa!important;color:#6036bf!important;border:none!important}
.gradio-container .plot-container{border-radius:14px!important;overflow:hidden;border:1px solid #e7e3ef!important}
.dataframe{font-size:12px!important}.gradio-container .prose p,.gradio-container .prose li{line-height:1.65!important}
.help-card{background:#fff;border:1px solid #e3deee;border-radius:13px;padding:19px;margin-bottom:12px;line-height:1.7;font-size:13px}
.help-card h3{font-size:15px;margin:0 0 9px}.help-card code{font-size:12px;color:#6333aa;background:#f2edf9;padding:2px 5px;border-radius:3px}
@media(max-width:1000px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.hero h1{font-size:28px!important}.gradio-container{padding:12px!important}}
@media(max-width:600px){.cards{grid-template-columns:1fr 1fr;gap:8px}.metric{padding:13px;min-height:118px}.metric-value{font-size:23px}.hero{padding:23px}.hero h1{font-size:25px!important}}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def money(value):
    if value is None or not np.isfinite(float(value)):
        return '—'
    value = float(value)
    sign = '−' if value < 0 else ''
    a = abs(value)
    if a >= 1e7:
        return f'{sign}₹{a / 1e7:,.2f} Cr'
    if a >= 1e5:
        return f'{sign}₹{a / 1e5:,.2f} lakh'
    return f'{sign}₹{a:,.0f}'


def num(value, decimals=0):
    if value is None or not np.isfinite(float(value)):
        return '—'
    return f'{float(value):,.{decimals}f}'


def title(text, subtitle=''):
    return f'<div class="section-head"><h2>{esc(text)}</h2><p>{esc(subtitle)}</p></div>'


def hero():
    return '''<div class="hero"><div class="eyebrow">E100 / IIM Mumbai / Chain Reaction</div>
    <h1>Every SKU. A clear decision.</h1><p>Lifecycle evidence, inventory choices and measurable outcomes in one planning workspace.</p>
    <div class="hero-meta"><span class="pill">01 CLASSIFY</span><span class="pill">02 REVIEW POLICY</span><span class="pill">03 TEST OUTCOMES</span></div></div>'''


def dataset_strip(data, label='Input workbook'):
    products = data['Products']
    settings = dict(zip(data['Settings'].parameter, data['Settings'].value))
    origin = str(settings.get('data_origin', 'User supplied; provenance unverified'))
    return (f'<div class="source-strip"><strong>{esc(label)}</strong> · {len(products)} SKUs · '
            f'{data["Positions"].location.nunique()} stocking locations · '
            f'{len(data["History"]):,} monthly observations · As of {esc(settings.get("as_of_date", ""))}'
            f'<br>{esc(origin)}. All quantities in litres; financial values in INR.</div>')


def metric_card(label, value, detail, tone=''):
    return f'<div class="metric"><div class="metric-label">{esc(label)}</div><div class="metric-value {tone}">{value}</div><div class="metric-detail">{esc(detail)}</div></div>'


def overview_cards(result):
    k = result['kpis']
    diff = float(k.get('proposed_fill_pct', 0)) - float(k.get('baseline_fill_pct', 0))
    gain = k.get('simulated_net_benefit_inr', 0)
    return '<div class="cards">' + ''.join([
        metric_card('Owned stock · observed', money(k.get('stock_value_inr')), 'Snapshot book value; includes aged stock'),
        metric_card('Exposed value · screen', money(k.get('at_risk_value_inr')), 'Projected expiry exposure; not a write-off', 'amber'),
        metric_card('Net cost benefit · simulated', money(gain),
                    f'P10–P90: {money(k.get("benefit_p10_inr"))} to {money(k.get("benefit_p90_inr"))}', 'good' if gain >= 0 else 'bad'),
        metric_card('Quantity fill · simulated', num(k.get('proposed_fill_pct'), 1) + '%',
                    f'Current {num(k.get("baseline_fill_pct"),1)}% · change {diff:+.1f} pp', 'good' if diff >= -0.01 else 'bad')
    ]) + '</div>'


def recommendation(result):
    k = result['kpis']
    approved = int(k.get('approved_positions', 0))
    breaches = int(k.get('service_floor_breaches', 0))
    benefit = float(k.get('simulated_net_benefit_inr', 0))
    if not approved:
        heading = 'Baseline established. Select policies to test.'
        detail = 'No policy changes are approved in this scenario. Current and proposed results should match. Review the D2 recommendations, then approve selected SKUs in Human decisions.'
        tone, badge = 'neutral', 'REVIEW'
    elif breaches:
        heading = 'Service needs attention before any rollout.'
        detail = f'{breaches} SKU-location service floors are missed in the proposed simulation. Review shortages and dated commitments in D3 before acting on a positive cost result.'
        tone, badge = 'warn', 'HOLD'
    elif benefit > 0:
        heading = 'The scenario supports a bounded pilot.'
        detail = f'{approved} positions use approved policy settings. The modeled cost result is favorable; test it with controlled execution and monitor expiry outcomes through usable life.'
        tone, badge = '', 'TEST'
    else:
        heading = 'The proposed settings do not yet earn a rollout.'
        detail = 'Under these assumptions the proposal adds cost or has no incremental benefit. Inspect the cost components, service result and approval choices before revising the scenario.'
        tone, badge = 'warn', 'REWORK'
    return f'<div class="decision {tone}"><div class="decision-mark">{badge}</div><div><strong>{heading}</strong><p>{detail}</p></div></div>'


def blank_plot(message='Run a simulation to populate this view'):
    fig = go.Figure()
    fig.add_annotation(text=message, x=.5, y=.5, xref='paper', yref='paper', showarrow=False, font=dict(size=15,color=MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style(fig, height=300)


def style(fig, title_text=None, height=330):
    fig.update_layout(template='plotly_white', font=dict(family='Arial',size=12,color=INK),
                      paper_bgcolor='#ffffff',plot_bgcolor='#ffffff',height=height,
                      margin=dict(l=50,r=24,t=78 if title_text else 30,b=47),
                      title=dict(text=title_text or '',font=dict(size=16,color=INK)),
                      legend=dict(orientation='h',y=1.15,yanchor='top',x=0,font=dict(size=11)),
                      hoverlabel=dict(bgcolor=INK,font=dict(color='white')), hovermode='closest')
    fig.update_xaxes(gridcolor='#f0edf5',zeroline=False)
    fig.update_yaxes(gridcolor='#f0edf5',zeroline=False)
    return fig


def inventory_chart(result):
    df=result['simulation_paths']
    fig=go.Figure()
    for label, color in [('Baseline',MUTED),('Proposed',TEAL)]:
        part=df[df.scenario.astype(str).str.lower().eq(label.lower())]
        if part.empty:
            continue
        value_col='owned_inventory_value_inr' if 'owned_inventory_value_inr' in part else 'inventory_value_inr'
        g=part.groupby('week')[value_col]
        # A short moving average removes presentation noise from synchronized
        # weekly reviews. Raw weekly paths remain in the evidence export.
        means=(g.mean()/1e5).rolling(5,center=True,min_periods=3).mean().bfill().ffill()
        if label=='Proposed':
            p90=(g.quantile(.9)/1e5).rolling(5,center=True,min_periods=3).mean().bfill().ffill()
            p10=(g.quantile(.1)/1e5).rolling(5,center=True,min_periods=3).mean().bfill().ffill()
            fig.add_trace(go.Scatter(x=means.index,y=p90,mode='lines',line=dict(width=0),showlegend=False,hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=means.index,y=p10,mode='lines',line=dict(width=0),fill='tonexty',fillcolor='rgba(8,127,131,.12)',name='Proposed P10–P90',hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=means.index,y=means,mode='lines',name=label,line=dict(color=color,width=3,dash='dot' if label=='Baseline' else 'solid'),hovertemplate='Week %{x}<br>₹%{y:,.2f} lakh<extra>'+label+'</extra>'))
    fig.update_xaxes(title='Simulation week')
    fig.update_yaxes(title='Owned stock + pipeline · ₹ lakh')
    return style(fig,'Inventory trend · 5-week centered average',360)


def stage_chart(result):
    c=result['classification']
    p=result['policy']
    if c.empty or p.empty:
        return blank_plot('Select at least one SKU')
    values=p.assign(value=p.stock_l*p.unit_cost_inr_l).groupby('stage').value.sum()/1e5
    counts=c.groupby('stage').size()
    stages=[s for s in COLORS if s in values.index]
    for s in values.index:
        if s not in stages: stages.append(s)
    fig=go.Figure(go.Bar(x=stages,y=[values.get(s,0) for s in stages],marker_color=[COLORS.get(s,MUTED) for s in stages],
                        text=[f'{counts.get(s,0)} SKUs' for s in stages],textposition='outside',cliponaxis=False))
    fig.update_yaxes(title='Snapshot stock value · ₹ lakh')
    return style(fig,'Where lifecycle exposure sits',360)


def confidence_chart(result):
    c=result['classification']
    if c.empty:
        return blank_plot('Select at least one SKU')
    stages=[s for s in COLORS if s in set(c.stage)]
    stages += [s for s in c.stage.unique() if s not in stages]
    fig=go.Figure()
    for conf,color in [('High',TEAL),('Medium','#9c84d7'),('Low',AMBER),('Suspended',ROSE),('Insufficient',MUTED)]:
        part=c[c.confidence.astype(str).str.lower().eq(conf.lower())]
        count=part.groupby('stage').size()
        fig.add_trace(go.Bar(x=stages,y=[count.get(s,0) for s in stages],name=conf,marker_color=color))
    fig.update_layout(barmode='stack')
    fig.update_yaxes(title='SKU count',dtick=1)
    return style(fig,'Confidence determines the review route',340)


def signal_chart(result):
    c=result['classification'].copy()
    if c.empty:
        return blank_plot('Select at least one SKU')
    fig=go.Figure()
    for st,g in c.groupby('stage'):
        fig.add_trace(go.Scatter(x=g.trend_pct,y=g.peak_ratio,mode='markers',name=st,
             marker=dict(size=12,color=COLORS.get(st,MUTED),opacity=.8,line=dict(width=1,color='white')),
             text=g.sku,customdata=g[['product_name','confidence']].values,
             hovertemplate='%{text}<br>%{customdata[0]}<br>Trend %{x:.1f}% · peak ratio %{y:.2f}<br>%{customdata[1]} confidence<extra></extra>'))
    fig.add_vline(x=0,line_color='#c7c0d6',line_dash='dot')
    fig.update_xaxes(title='Demand trend · %')
    fig.update_yaxes(title='Current / historical peak')
    return style(fig,'Signals explain the stage; no single cutoff decides',340)


def policy_chart(result):
    p=result['policy']
    if p.empty:
        return blank_plot('Select at least one SKU')
    g=p.groupby('stage')[['current_order_up_to_l','proposed_order_up_to_l','effective_order_up_to_l']].sum()
    stages=[s for s in COLORS if s in g.index]+[s for s in g.index if s not in COLORS]
    fig=go.Figure()
    for col,label,color in [('current_order_up_to_l','Current',MUTED),('proposed_order_up_to_l','Suggested','#b6a3e1'),('effective_order_up_to_l','Approved scenario',TEAL)]:
        fig.add_trace(go.Bar(x=stages,y=g.reindex(stages)[col],name=label,marker_color=color))
    fig.update_layout(barmode='group')
    fig.update_yaxes(title='Order-up-to target · L')
    return style(fig,'Direction from lifecycle, quantity from local constraints',350)


def cost_chart(result):
    df=result['simulation_paths']
    components=[('holding_cost_inr','Holding'),('expiry_cost_inr','Expiry'),('shortage_cost_inr','Unserved-demand penalty')]
    changes=[]
    for col,label in components:
        agg=df.groupby(['scenario','run'])[col].sum().groupby(level=0).mean()
        agg.index=agg.index.astype(str).str.lower()
        changes.append(float(agg.get('baseline',0)-agg.get('proposed',0))/1e5)
    fig=go.Figure(go.Waterfall(x=[x[1] for x in components]+['Net benefit'],y=changes+[sum(changes)],
         measure=['relative']*3+['total'],increasing=dict(marker=dict(color=TEAL)),decreasing=dict(marker=dict(color=ROSE)),
         totals=dict(marker=dict(color=PURPLE)),connector=dict(line=dict(color='#ddd6e9')),
         text=[f'{n:+.2f}' for n in changes]+[f'{sum(changes):+.2f}'],textposition='outside'))
    fig.update_yaxes(title='Current cost less proposed cost · ₹ lakh')
    return style(fig,'What creates or erodes the modeled benefit',360)


def sku_chart(data, sku):
    if sku is None or sku not in set(data['Products'].sku):
        return blank_plot('Select a SKU')
    g=data['History'].query('sku == @sku').groupby('month')[['orders_l','shipments_l','forecast_l']].sum().sort_index()
    fig=go.Figure()
    for col,label,color,dash in [('orders_l','Orders',PURPLE,'solid'),('shipments_l','Shipments',TEAL,'solid'),('forecast_l','Forecast',MUTED,'dot')]:
        fig.add_trace(go.Scatter(x=g.index,y=g[col],name=label,mode='lines',line=dict(color=color,width=2.5,dash=dash)))
    fig.update_yaxes(title='Monthly volume · L')
    return style(fig,f'{sku} · the demand evidence',320)


def pretty_frame(df, columns=None):
    if df is None or df.empty:
        return pd.DataFrame({'Status':['No rows for this selection']})
    out=df.copy()
    if columns:
        out=out[[c for c in columns if c in out]]
    for col in out.select_dtypes(include='number'):
        out[col]=out[col].round(2)
    out.columns=[str(c).replace('_',' ').replace('inr','₹').replace('pct','%').title() for c in out.columns]
    return out


def safe_csv(df):
    df=df.copy()
    for col in df.select_dtypes(include=['object','string']).columns:
        df[col]=df[col].map(lambda v: "'"+v if isinstance(v,str) and v[:1] in '=+-@\t\r' else v)
    return df.to_csv(index=False).encode('utf-8-sig')


def report_table(df, limit=200):
    view=pretty_frame(df).head(limit)
    tail=f'<p class="note">Showing {limit} of {len(df):,} rows. Full data are in the evidence ZIP.</p>' if len(df)>limit else ''
    return '<div class="table-wrap">'+view.to_html(index=False,escape=True,na_rep='—',border=0,classes='data-table')+'</div>'+tail


def chart_html(fig, chart_id):
    payload=fig.to_json().replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return f'<div id="{chart_id}" class="chart"></div><script>var s_{chart_id}={payload};Plotly.newPlot("{chart_id}",s_{chart_id}.data,s_{chart_id}.layout,{{responsive:true,displaylogo:false}});</script>'


def sku_filter_html(data):
    """Portable all-selected checkbox filter plus an aggregate/individual history chart."""
    products=data['Products'][['sku','product_name']].copy()
    names=dict(zip(products.sku.astype(str),products.product_name.astype(str)))
    skus=products.sku.astype(str).tolist()
    history=data['History'][['month','sku','orders_l','shipments_l','forecast_l']].copy()
    history['month']=pd.to_datetime(history['month']).dt.strftime('%Y-%m-%d')
    payload=json.dumps(history.to_dict(orient='records'),separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    boxes=''.join(
        f'<label class="sku-option"><input type="checkbox" class="sku-check" value="{esc(sku)}" checked onchange="applySkuFilter()"><span><b>{esc(sku)}</b><small>{esc(names.get(sku,""))}</small></span></label>'
        for sku in skus
    )
    return f'''<details class="sku-filter" ontoggle="if(this.open)setTimeout(()=>Plotly.Plots.resize(document.getElementById('skuHistory')),0)"><summary>SKU view filter · <span id="skuCount">{len(skus)} of {len(skus)} selected</span></summary>
      <p class="note">All SKUs start selected. Deselect any SKU to focus the SKU-level tables and demand-history chart. Portfolio KPI cards and simulation totals remain the scenario originally run.</p>
      <div class="sku-actions"><input id="skuSearch" type="search" placeholder="Search SKU or product" oninput="searchSkus(this.value)"><button onclick="setAllSkus(true)">Select all</button><button onclick="setAllSkus(false)">Clear</button></div>
      <div class="sku-options">{boxes}</div><div id="skuHistory" class="chart"></div>
    </details><script>
      const skuHistoryRows={payload};
      function chosenSkus(){{return new Set(Array.from(document.querySelectorAll('.sku-check:checked')).map(x=>x.value));}}
      function setAllSkus(state){{document.querySelectorAll('.sku-check').forEach(x=>x.checked=state);applySkuFilter();}}
      function searchSkus(q){{q=q.toLowerCase();document.querySelectorAll('.sku-option').forEach(x=>x.style.display=x.innerText.toLowerCase().includes(q)?'flex':'none');}}
      function applySkuFilter(){{
        const selected=chosenSkus();document.getElementById('skuCount').textContent=selected.size+' of {len(skus)} selected';
        document.querySelectorAll('table.data-table').forEach(table=>{{
          const heads=Array.from(table.querySelectorAll('thead th'));const skuCol=heads.findIndex(h=>h.textContent.trim().toLowerCase()==='sku');
          if(skuCol<0)return;table.querySelectorAll('tbody tr').forEach(row=>{{const cell=row.children[skuCol];row.style.display=cell&&selected.has(cell.textContent.trim())?'':'none';}});
        }});
        const byMonth={{}};skuHistoryRows.forEach(r=>{{if(!selected.has(String(r.sku)))return;const m=r.month;(byMonth[m]??={{orders_l:0,shipments_l:0,forecast_l:0}});byMonth[m].orders_l+=Number(r.orders_l)||0;byMonth[m].shipments_l+=Number(r.shipments_l)||0;byMonth[m].forecast_l+=Number(r.forecast_l)||0;}});
        const months=Object.keys(byMonth).sort();const one=selected.size===1?Array.from(selected)[0]:'Selected SKUs';
        const traces=[['orders_l','Orders','#6d42cb','solid'],['shipments_l','Shipments','#087f83','solid'],['forecast_l','Forecast','#77758b','dot']].map(s=>({{x:months,y:months.map(m=>byMonth[m][s[0]]),name:s[1],mode:'lines',line:{{color:s[2],width:2.5,dash:s[3]}}}}));
        Plotly.react('skuHistory',traces,{{template:'plotly_white',height:330,margin:{{l:55,r:24,t:78,b:47}},title:{{text:one+' · monthly demand evidence',font:{{family:'Arial',size:16,color:'#211c39'}}}},font:{{family:'Arial',size:12,color:'#211c39'}},legend:{{orientation:'h',y:1.0,yanchor:'top',x:0}},xaxis:{{gridcolor:'#f0edf5'}},yaxis:{{title:'Monthly volume · L',gridcolor:'#f0edf5'}}}},{{responsive:true,displaylogo:false}});
      }}
      window.addEventListener('DOMContentLoaded',applySkuFilter);
    </script>'''


def create_exports(data, result, overrides, source_text='', root=None):
    folder=Path(tempfile.mkdtemp(prefix='chain_reaction_',dir=root))
    report_path=folder/'Chain_Reaction_Dashboard.html'
    evidence_path=folder/'Chain_Reaction_Evidence.zip'
    timestamp=datetime.now(timezone.utc).isoformat()
    normalized={name:frame.to_json(orient='split',date_format='iso') for name,frame in data.items() if isinstance(frame,pd.DataFrame)}
    fingerprint=hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest()
    meta={'generated_at_utc':timestamp,'input_sha256':fingerprint,'as_of':str(result['as_of']),
          'controls':result['controls'],'assumptions':result['assumptions'],'warnings':result['warnings'],
          'model_version':'1.0','result_type':'scenario simulation, not measured impact'}
    with zipfile.ZipFile(evidence_path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,frame in result.items():
            if isinstance(frame,pd.DataFrame):z.writestr('results/'+name+'.csv',safe_csv(frame))
        for name,frame in data.items():
            if isinstance(frame,pd.DataFrame):z.writestr('inputs/'+name+'.csv',safe_csv(frame))
        z.writestr('human_decisions.csv',safe_csv(overrides))
        z.writestr('scenario.json',json.dumps(meta,indent=2,default=str))
        z.writestr('SOURCES.md',source_text)
        z.writestr('README.txt','All output values are scenario results or explicitly labeled observations. CSV inputs + scenario.json + human_decisions.csv reproduce this run with engine.py. Network-transfer candidates are outside the simulation. No inventory principal is counted as recurring cost savings. Cost improvement = baseline minus proposed. Service improvement = proposed minus baseline. Percentile bands are scenario ranges, not confidence intervals.\n')
    parts=[f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Chain Reaction | Scenario report</title><style>{CSS}',
      'main{max-width:1370px;margin:24px auto;padding:0 25px}.report-nav{position:sticky;top:0;background:#f5f5faf5;display:flex;gap:14px;padding:15px 0;z-index:10}.report-nav a{font-size:13px;color:#5c3b95;text-decoration:none;font-weight:700}.report-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.chart{background:white;border-radius:14px;overflow:hidden;border:1px solid #e7e3ef}.report-section{margin-top:25px;scroll-margin-top:60px}.table-wrap{overflow:auto;max-height:470px;background:white;border:1px solid #e3deeb;border-radius:12px}.data-table{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap}.data-table th{position:sticky;top:0;background:#30254b;color:white;text-align:left;padding:11px}.data-table td{padding:9px 11px;border-bottom:1px solid #eeeaf4}.data-table tr:nth-child(even){background:#f9f7fc}.note{font-size:12px;color:#77758b;line-height:1.7}.sources{font-size:12px;white-space:pre-wrap;line-height:1.6;background:white;padding:22px;border-radius:12px}.print-btn,.sku-actions button{border:0;background:#6d42cb;color:white;border-radius:7px;padding:7px 13px;cursor:pointer}.print-btn{margin-left:auto}.sku-filter{background:#fff;border:1px solid #e3deeb;border-radius:14px;padding:16px 18px;margin:6px 0 20px}.sku-filter summary{cursor:pointer;font-weight:700;color:#30254b}.sku-actions{display:flex;gap:8px;margin:12px 0}.sku-actions input{min-width:280px;border:1px solid #d7d0e2;border-radius:7px;padding:8px 10px}.sku-options{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;max-height:230px;overflow:auto;margin-bottom:14px}.sku-option{display:flex;gap:7px;align-items:flex-start;background:#f8f6fb;border-radius:8px;padding:8px;font-size:12px}.sku-option small{display:block;color:#77758b;margin-top:2px}.sku-option input{margin-top:2px}@media print{.report-nav,.print-btn,.sku-filter{display:none}.report-section{break-inside:avoid}.table-wrap{max-height:none;overflow:visible}.report-grid{display:block}.hero{print-color-adjust:exact}.chart{break-inside:avoid}body{background:white!important}}@media(max-width:900px){.report-grid{grid-template-columns:1fr}.report-nav{flex-wrap:wrap}.sku-options{grid-template-columns:repeat(2,minmax(0,1fr))}}',
      '</style><script>'+get_plotlyjs()+'</script></head><body><main>',hero(),dataset_strip(data,'Scenario report'),
      '<nav class="report-nav"><a href="#overview">Overview</a><a href="#d1">D1 Classification</a><a href="#d2">D2 Policy</a><a href="#d3">D3 Outcomes</a><a href="#method">Assumptions</a><button class="print-btn" onclick="window.print()">Print / save PDF</button></nav>',sku_filter_html(data),
      '<section id="overview" class="report-section">',overview_cards(result),recommendation(result),
      '<div class="report-grid">',chart_html(inventory_chart(result),'inventory'),chart_html(stage_chart(result),'stage'),'</div></section>',
      '<section id="d1" class="report-section">',title('D1 · Explain the lifecycle decision','Five stages, confidence, observability and a recorded human decision.'),
      '<div class="report-grid">',chart_html(confidence_chart(result),'confidence'),chart_html(signal_chart(result),'signals'),'</div>',report_table(result['classification']),'</section>',
      '<section id="d2" class="report-section">',title('D2 · Review each stocking decision','Suggested targets and approved simulation settings remain separate.'),chart_html(policy_chart(result),'policy'),report_table(result['policy']),
      title('Batch exposure','Expiry risk is a screening estimate using the supplied batches and usable life.'),report_table(result['batch_risk']),
      title('Network candidates','Screened transfer suggestions only; no transfer benefit is included in the simulation.'),report_table(result['transfers']),
      title('Exit obligations · dated coverage'),report_table(result.get('exit_coverage',pd.DataFrame())),'</section>',
      '<section id="d3" class="report-section">',title('D3 · Evaluate the trade-off','Paired scenarios; P10–P90 show modeled uncertainty, not statistical confidence.'),chart_html(cost_chart(result),'cost'),report_table(result['simulation_summary']),
      title('Local service and commitment guardrails'),report_table(result.get('service_evidence',pd.DataFrame())),
      title('Observed performance'),report_table(result['observed']),title('Stage scorecard'),report_table(result['stage_metrics']),'</section>',
      '<section id="method" class="report-section">',title('Assumptions, approvals and evidence'),'<div class="help-card"><ul>',
      ''.join('<li>'+esc(x)+'</li>' for x in result['assumptions']),'</ul></div>',title('Warnings'),'<div class="help-card">',
      '<br>'.join(esc(x) for x in result['warnings']) or 'No input-validation warnings.', '</div>',title('Scenario settings'),
      report_table(pd.DataFrame([{'Parameter':k,'Value':v} for k,v in result['controls'].items()])),title('Human decisions'),report_table(overrides),
      title('Sources and data provenance'),'<div class="sources">'+esc(source_text)+'</div>',
      f'<p class="note">Generated {esc(timestamp)} · Model v1.0 · Input SHA256 {fingerprint}<br>Illustrative policy simulator. Results require calibration and an executed, controlled pilot before any claim of company savings.</p></section></main></body></html>']
    report_path.write_text(''.join(parts),encoding='utf-8')
    return str(report_path),str(evidence_path)
