"""Chain Reaction MVP. Run: streamlit run streamlit_app.py"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

import pandas as pd
import streamlit as st

import engine
from make_demo import make_demo
from views import (CSS, confidence_chart, cost_chart, create_exports, dataset_strip,
                   hero, inventory_chart, overview_cards, policy_chart, pretty_frame,
                   recommendation, signal_chart, sku_chart, stage_chart)

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='Chain Reaction | E100',page_icon='◉',layout='wide')
STYLES='''
.block-container{max-width:1460px;padding-top:1.6rem;padding-bottom:2rem}
[data-testid="stSidebar"]{background:#f0edf6;border-right:1px solid #e2ddeb}
[data-testid="stAppViewContainer"]{background:#f5f5fa}
[data-testid="stHeader"]{background:#f5f5faee}
[data-testid="stSidebar"] h2{font-size:1.1rem}
[data-testid="stSidebar"] label{font-size:12px}
.stButton button[kind="primary"]{background:#6d42cb;border:0}
[data-baseweb="tab-list"]{gap:16px}
button[data-baseweb="tab"]{font-size:14px}
[data-testid="stPlotlyChart"]{border:1px solid #e6e1ef;border-radius:14px;overflow:hidden;background:white}
.stDownloadButton button{border-radius:9px;border-color:#d9cdec}
#MainMenu,[data-testid="stToolbar"]{visibility:hidden}
html{color-scheme:light!important}
'''
st.markdown('<style>'+CSS+STYLES+'</style>',unsafe_allow_html=True)
st.markdown(hero(),unsafe_allow_html=True)


def source_text():
    return (ROOT/'SOURCES.md').read_text(encoding='utf-8')


def initial_decisions(data):
    p=data['Products']
    return pd.DataFrame({'sku':p.sku.tolist(),'stage_override':['Auto']*len(p),
                         'commercial_status':p.commercial_status.tolist(),
                         'approve_policy':[False]*len(p),'reason':['']*len(p)})


def prepare_decisions(data, edited, mode, reason):
    frame=edited.copy()
    if mode=='Current policy only':
        frame['approve_policy']=False
    elif mode in ['Decline / exit proposals','All eligible proposals']:
        if len(reason.strip())<5:raise ValueError('Please enter a brief reason for the group approval.')
        prior=data['Products'].set_index('sku').prior_stage
        selected=frame.sku.map(prior).isin(['Decline','Exit']) if mode=='Decline / exit proposals' else pd.Series(True,index=frame.index)
        frame['approve_policy']=selected
        # Keep a specific analyst reason; fill only approval reasons that are blank.
        empty=frame.reason.fillna('').astype(str).str.strip().str.len()<5
        frame.loc[selected & empty,'reason']=reason.strip()
    return frame


def show_table(frame, height=320, columns=None):
    st.dataframe(pretty_frame(frame,columns),hide_index=True,width='stretch',height=height)


with st.sidebar:
    st.header('Scenario inputs')
    if 'upload_version' not in st.session_state:st.session_state.upload_version=0
    if 'use_sample' not in st.session_state:st.session_state.use_sample=True
    upload=st.file_uploader('Upload one Excel workbook',type=['xlsx'],key=f'workbook_upload_{st.session_state.upload_version}',help='Use the supplied input workbook; preserve the named tabs and headers.')
    template=ROOT/'Chain_Reaction_Input.xlsx'
    if template.exists():
        if st.button('Use sample data',width='stretch',help='Load the included workbook directly without downloading and uploading it.'):
            st.session_state.use_sample=True
            st.session_state.upload_version+=1
            st.rerun()
        st.download_button('Download sample Excel',template.read_bytes(),file_name=template.name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',width='stretch')
    if upload is not None:st.session_state.use_sample=False
    st.caption('Sample Excel is active.' if st.session_state.use_sample else f'Uploaded file is active: {upload.name}')
    mode=st.selectbox('Policies to test',['Current policy only','Decline / exit proposals','All eligible proposals','My SKU decisions'],help='Decline/exit group uses the prior approved stage in the workbook. Review gates still apply.')
    group_reason=st.text_input('Group approval reason',value='MVP scenario test; validate in a controlled pilot',disabled=mode in ['Current policy only','My SKU decisions'])
    horizon=st.slider('Horizon · weeks',4,52,26)
    runs=st.select_slider('Paired scenario runs',options=[5,10,20,30,50],value=20)
    demand=st.slider('Demand change · %',-50,100,0,5)
    lead=st.slider('Lead-time change · %',-50,150,0,5)
    with st.expander('Policy and economic assumptions'):
        cycle=st.slider('Design cycle-service quantile · %',70.,99.,95.,.5,help='This determines z for safety stock. Simulated quantity fill is measured separately.')
        review=st.select_slider('Review interval · days',options=[7,14,21,28],value=7)
        decline=st.slider('Decline cover · days',7,90,28)
        growth=st.slider('Additional growth cover · days',0,42,14)
        holding=st.slider('Annual holding cost · %',0,40,18)
        shortage=st.slider('Shortage penalty / unit margin',0.,5.,1.,.25)
        life_buffer=st.slider('Extra usable-life buffer · days',0,60,7)
    with st.expander('Classification assumptions'):
        threshold=st.slider('Trend evidence threshold · %',5,40,12)
        persistence=st.slider('Confirmation periods',1,6,2)
        min_history=st.slider('Minimum history · months',3,18,6)
        seed=st.number_input('Scenario seed',min_value=0,max_value=2147483647,value=42,step=1)

raw=upload.getvalue() if upload is not None else (template.read_bytes() if template.exists() else b'SYNTHETIC_EXAMPLE_V2')
input_id=hashlib.sha256(raw).hexdigest()
if st.session_state.get('input_id')!=input_id:
    try:
        if upload is not None:
            if len(raw)>30*1024*1024:raise ValueError('Workbook exceeds the MVP’s 30 MB limit.')
            with tempfile.TemporaryDirectory(prefix='chain_input_') as folder:
                path=Path(folder)/'input.xlsx'
                path.write_bytes(raw)
                data=engine.load_workbook(path)
        elif template.exists():
            data=engine.load_workbook(template)
        else:
            data=engine.validate_data(make_demo())
        st.session_state.update(input_id=input_id,data=data,decisions=initial_decisions(data),result=None,exports=None,run_id=None)
    except Exception as exc:
        st.error('Please correct the workbook: '+str(exc))
        st.stop()

data=st.session_state.data
st.markdown(dataset_strip(data,upload.name if upload is not None else 'Sample Excel workbook'),unsafe_allow_html=True)
with st.expander('Human inputs · stage, commercial status and SKU approvals',expanded=False):
    st.caption('Edit only where human judgement is needed. A stage override or changed commercial status needs a reason. Select “My SKU decisions” in the sidebar to use the approval column.')
    decisions=st.data_editor(st.session_state.decisions,hide_index=True,width='stretch',height=300,
       disabled=['sku'],key='editor_'+input_id,
       column_config={
        'sku':st.column_config.TextColumn('SKU'),
        'stage_override':st.column_config.SelectboxColumn('Stage override',options=['Auto']+engine.STAGES,required=True),
        'commercial_status':st.column_config.SelectboxColumn('Commercial status',options=['Active','Phase-out','Discontinued','Hold','Relaunch'],required=True),
        'approve_policy':st.column_config.CheckboxColumn('Approve for simulation'),
        'reason':st.column_config.TextColumn('Decision reason',width='large')})

controls=dict(horizon_weeks=horizon,runs=runs,seed=seed,demand_shock_pct=demand,
    lead_time_shock_pct=lead,annual_holding_pct=holding,shortage_penalty_multiplier=shortage,
    decline_cover_days=decline,review_days=review,growth_cover_days=growth,
    trend_threshold_pct=threshold,persistence_periods=persistence,min_history_months=min_history,
    expiry_buffer_days=life_buffer,design_cycle_service_pct=cycle)
signature=hashlib.sha256((input_id+json.dumps(controls,sort_keys=True)+decisions.to_json()+mode+group_reason).encode()).hexdigest()
with st.sidebar:
    do_run=st.button('Simulate',type='primary',width='stretch')
    st.caption('All actions stay inside this what-if model. No live replenishment or transfer is executed.')

if do_run:
    try:
        approved=prepare_decisions(data,decisions,mode,group_reason)
        with st.spinner('Checking lifecycle evidence and simulating paired policies…'):
            result=engine.analyze(data,controls,approved)
            # Session-private bytes survive download reruns; temporary report files are removed.
            with tempfile.TemporaryDirectory(prefix='chain_report_') as folder:
                html_path,zip_path=create_exports(data,result,approved,source_text(),root=folder)
                exports=(Path(html_path).read_bytes(),Path(zip_path).read_bytes())
        st.session_state.update(result=result,exports=exports,run_id=signature)
    except Exception as exc:
        st.error('Simulation could not run: '+str(exc))

result=st.session_state.result
if result is None:
    st.markdown('<div class="empty"><div class="eyebrow">COMPACT PLANNING MVP</div><h2>Upload. Review. Simulate.</h2><p>Choose <strong>Decline / exit proposals</strong> to test the submitted policy idea on the example, or run <strong>Current policy only</strong> to establish the baseline. The output explains each stage, stocking decision and cost/service trade-off.</p></div>',unsafe_allow_html=True)
    st.stop()

if st.session_state.run_id!=signature:
    st.warning('Inputs changed. The figures below belong to the previous run. Click Simulate to refresh; downloads are disabled until then.')

all_skus=data['Products'].sku.tolist()
filter_key='sku_filter_'+input_id
if filter_key not in st.session_state:st.session_state[filter_key]=all_skus
with st.expander(f'SKU view filter · {len(st.session_state[filter_key])} of {len(all_skus)} selected',expanded=False):
    selected_skus=st.multiselect('SKUs shown in detailed views',all_skus,key=filter_key,help='All SKUs are selected initially. Deselect SKUs to focus the D1/D2 tables and SKU-level evidence. Portfolio simulation cards remain the scenario that was run.')
if not selected_skus:st.warning('No SKU is selected. Select at least one SKU to populate the detailed views.')

def filtered(frame):
    if frame is None or not isinstance(frame,pd.DataFrame) or 'sku' not in frame:return frame
    return frame[frame.sku.isin(selected_skus)].copy()

view_result={k:(filtered(v) if isinstance(v,pd.DataFrame) else v) for k,v in result.items()}
st.caption(f'Showing {len(selected_skus)} of {len(all_skus)} SKUs in detailed views. Portfolio KPI cards and paired-simulation totals remain unchanged until you edit inputs and click Simulate.')

st.markdown(overview_cards(result),unsafe_allow_html=True)
st.markdown(recommendation(result),unsafe_allow_html=True)
overview,d1,d2,d3,method=st.tabs(['Overview','D1 · Classify','D2 · Inventory','D3 · Outcomes','Method and sources'])
with overview:
    left,right=st.columns(2)
    with left:st.plotly_chart(inventory_chart(result),width='stretch',config={'displaylogo':False},key='ov_inventory')
    with right:st.plotly_chart(stage_chart(view_result),width='stretch',config={'displaylogo':False},key='ov_stages')
    st.caption(f'{result["controls"]["runs"]} paired paths × {result["controls"]["horizon_weeks"]} weeks. Inventory lines use a centered 5-week management trend; raw weekly paths remain in the evidence ZIP. Shaded P10–P90 is a scenario range. The owned-stock chart includes on-hand and ordered pipeline under the model’s ownership assumption.')
    st.subheader('Download this scenario')
    a,b=st.columns(2)
    with a:st.download_button('Download dashboard · HTML',st.session_state.exports[0],file_name='Chain_Reaction_Dashboard.html',mime='text/html',disabled=st.session_state.run_id!=signature,width='stretch')
    with b:st.download_button('Download evidence · ZIP',st.session_state.exports[1],file_name='Chain_Reaction_Evidence.zip',mime='application/zip',disabled=st.session_state.run_id!=signature,width='stretch')
    st.caption('The HTML report works offline. Use its Print / save PDF button for a printable copy. Evidence contains inputs, decisions, scenario settings and all result tables.')
with d1:
    st.subheader('Lifecycle decision register')
    st.caption('Candidate and retained/overridden stage are separate. Archetype context is a revisable description, not a prediction of a product’s future.')
    st.plotly_chart(confidence_chart(view_result),width='stretch',config={'displaylogo':False},key='classification_conf')
    show_table(view_result['classification'],height=350)
    sku=st.selectbox('Inspect a SKU',selected_skus,index=0 if selected_skus else None,placeholder='Select at least one SKU',disabled=not selected_skus)
    if sku:
        cr=result['classification'].set_index('sku').loc[sku]
        st.info(f'{cr.product_name} · {cr.stage} · {cr.confidence} confidence · reference trajectory: {cr.trajectory_reference or "Not supplied"}. {cr.decision_reason}')
        st.plotly_chart(sku_chart(data,sku),width='stretch',config={'displaylogo':False},key='sku_history')
with d2:
    st.subheader('From lifecycle stage to inventory action')
    st.plotly_chart(policy_chart(view_result),width='stretch',config={'displaylogo':False},key='policy_targets')
    locations=['All locations']+sorted(view_result['policy'].location.unique())
    location=st.selectbox('Stocking location',locations)
    selected=view_result['policy'] if location=='All locations' else view_result['policy'].loc[lambda p:p.location.eq(location)]
    show_table(selected,height=360)
    with st.expander('Batch expiry exposure'):
        show_table(view_result['batch_risk'],height=330)
    with st.expander('Screened network transfer candidates'):
        st.caption('Candidates only. Economics need validation; no transfer is executed or counted in modeled benefits.')
        show_table(view_result['transfers'],height=280)
    with st.expander('Exit obligations · dated coverage'):
        st.caption('Current usable stock is allocated once across due dates. A deficit is a review action, even when portfolio inventory is high.')
        show_table(view_result.get('exit_coverage',pd.DataFrame()),height=280)
with d3:
    st.subheader('Cost reduction must preserve service')
    st.plotly_chart(cost_chart(result),width='stretch',config={'displaylogo':False},key='cost_bridge')
    show_table(result['simulation_summary'],height=380)
    with st.expander('Local service floors and commitments',expanded=True):
        show_table(view_result.get('service_evidence',pd.DataFrame()),height=280)
    with st.expander('Observed measures and stage scorecard'):
        show_table(result['observed'],height=230)
        show_table(result['stage_metrics'],height=350)
    st.caption('Blank measures mean the required ledger, launch plan or cohort evidence was not supplied. A scenario result is not measured company impact.')
with method:
    st.subheader('What the simulation assumes')
    for line in result['assumptions']:st.markdown('- '+str(line))
    if result['warnings']:
        st.subheader('Review items')
        for line in result['warnings']:st.markdown('- '+str(line))
    with st.expander('Scenario settings'):st.json(result['controls'])
    with st.expander('Sources and data provenance'):st.markdown(source_text())
    with st.expander('Excel field dictionary'):st.markdown((ROOT/'DATA_DICTIONARY.md').read_text(encoding='utf-8'))
