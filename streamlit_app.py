"""Business-facing local demo over the same services used by the CLI."""
import os
import json
from pathlib import Path

import streamlit as st

from app.demo.scenarios import SCENARIOS, DEMO_DATE, DemoModel, LostDeliveryResponse, prepare_scenario, change_sources
from app.workflow.service import WorkflowService, WorkflowError
from app.workflow.delivery import DeliveryService, LocalTaskInbox
from app.validation.inputs import InputValidationError

st.set_page_config(page_title='Campaign readiness', page_icon='📋', layout='wide')
st.markdown('''<style>
    .stApp {background-color: #f7f8fa;}
    h1, h2, h3 {letter-spacing: -0.025em;}
    [data-testid="stMetric"] {background: white; border: 1px solid #e3e7ee;
        border-radius: 12px; padding: 16px;}
    [data-testid="stSidebar"] {background-color: #edf1f6;}
</style>''', unsafe_allow_html=True)

root = Path(os.environ.get('READINESS_DEMO_DIR', str(Path(__file__).resolve().parent / '.demo')))
with st.sidebar:
    st.title('Campaign readiness')
    st.caption('A retail workflow demonstration')
    scenario = st.selectbox('Choose a scenario', list(SCENARIOS),
                            format_func=lambda key: SCENARIOS[key][0], key='scenario')
    st.write(SCENARIOS[scenario][1])
    st.divider()
    st.caption(f'Reproducible assessment date: {DEMO_DATE:%B %d, %Y}')
    st.caption('Synthetic data · simulated model · local task inbox')

data_dir = prepare_scenario(root, scenario)
workflow = WorkflowService(root / scenario / 'workflow.sqlite3')
deliveries = DeliveryService(workflow)
inbox = LocalTaskInbox(root / scenario / 'inbox.sqlite3')

st.caption('LAUNCH OPERATIONS / SOFT LOUNGE')
st.title('Is this campaign ready?')
st.write('Inspect the evidence, record a review, and follow the handoff through to completion.')

flash = st.session_state.pop('flash', None)
if flash:
    st.success(flash)

left, right = st.columns([3, 1])
with left:
    st.subheader(SCENARIOS[scenario][0])
with right:
    if st.button('Run assessment', type='primary', key='assess', use_container_width=True):
        try:
            with st.spinner('Checking sources, analyzing findings, and enforcing readiness rules…'):
                record = workflow.assess(data_dir, DemoModel(scenario), DEMO_DATE)
            st.session_state[f'selected_{scenario}'] = record['id']
            st.session_state['flash'] = 'Assessment saved with its evidence and source snapshot.'
            st.rerun()
        except (WorkflowError, InputValidationError) as exc:
            st.error(str(exc))

records = workflow.history(data_dir, DEMO_DATE)
if not records:
    st.info('Choose a scenario and run an assessment to begin. Nothing is sent until you review and deliver it.')
    with st.expander('Preview the source data'):
        for name in ('product_catalog.json', 'inventory.csv', 'campaign_checklist.json', 'source_metadata.json'):
            st.caption(name)
            st.code((data_dir / name).read_text())
    st.stop()

identifiers = [row['id'] for row in records]
selection_key = f'selected_{scenario}'
if st.session_state.get(selection_key) not in identifiers:
    st.session_state[selection_key] = identifiers[0]
selected = st.selectbox('Saved assessment', identifiers,
    format_func=lambda identifier: next(f"{r['created_at'][:19].replace('T', ' ')} UTC · {r['result']['overall_status']} · {r['id'][:8]}" for r in records if r['id'] == identifier),
    key=selection_key)
record = workflow.get(selected, data_dir, DEMO_DATE)
result, context = record['result'], record['context']
blockers = [finding for finding in context['signals'] if finding['severity'] == 'blocker']
quality = [finding for finding in context['signals'] if finding['signal_id'].startswith('DQ-')]
a, b, c, d = st.columns(4)
a.metric('Readiness', result['overall_status'])
b.metric('Launch blockers', len(blockers))
c.metric('Data quality findings', len(quality))
d.metric('Confidence', result['confidence'])
if not record['snapshot_current']:
    st.warning('Sources changed after this assessment. Run a new assessment before reviewing or delivering it.')

overview, evidence, review, history = st.tabs(['Launch overview', 'Findings & evidence', 'Review & follow-up', 'History'])
with overview:
    st.subheader('Assessment')
    if record['model'].get('overall_status') != result['overall_status']:
        st.info('The model response was changed or rejected by validation and business rules. The readiness shown above governs review.')
    st.caption('Model explanation / validated fallback')
    st.write(result['executive_summary'])
    if result['human_review_required']:
        st.warning(result['human_review_reason'])
    st.caption('Readiness is enforced by business rules. Confidence is a bounded rating, not a probability.')
    st.subheader('Proposed follow-up')
    actions = result['recommended_actions']
    if not actions:
        st.info('No validated model actions are available for this assessment.')
    for action in actions:
        st.write(action['action'])
        st.caption('Findings: ' + ', '.join(action['signal_ids'] + action['conflict_fields']))
    with st.expander('Compare the model response with the enforced result'):
        first, second = st.columns(2)
        with first:
            st.write('Original model response')
            st.json(record['model'])
        with second:
            st.write('Validated and enforced result')
            st.json(result)
    st.divider()
    st.subheader('What if the source data changes?')
    st.write('Update the demo notes to show why a saved review applies only to its assessed snapshot.')
    if st.button('Simulate a source update', key='change_sources'):
        change_sources(data_dir)
        st.session_state['flash'] = 'Source notes updated. The earlier assessment now requires reassessment.'
        st.rerun()

with evidence:
    st.caption(f"Source presence: {context['data_completeness_score']:.0%}. Coverage and freshness are checked separately.")
    if not context['signals']:
        st.success('No readiness findings detected in this snapshot.')
    for finding in context['signals']:
        with st.expander(f"{finding['severity'].upper()} · {finding['title']}"):
            st.write(finding['description'])
            st.caption(f"{finding['signal_id']} · {finding['domain']} · {finding['signal_type']}")
            if finding['requires_llm_interpretation']:
                st.caption('This finding requires interpretation; inspect the source excerpt.')
            for source in finding['evidence']:
                st.caption(f"{source['source_file']} → {source['field_path']}")
                st.text(source['excerpt'])
                st.json({'raw_value': source['raw_value']})
    if context['conflicts']:
        st.subheader('Cross-source discrepancies')
        st.json(context['conflicts'])
    with st.expander('Inspect the current source files'):
        st.caption('These are current sources. Findings above belong to the saved assessment snapshot.')
        for path in sorted(data_dir.iterdir()):
            if not path.name.startswith('.'):
                st.caption(path.name)
                st.code(path.read_text())

with review:
    st.subheader('Record accountable review')
    st.caption('Reviewer names are demo attribution, not authenticated identities. Approval records review; it does not authorize launch.')
    st.write('Review state: ' + record['review_state'].replace('_', ' ').title())
    if record['review']:
        decision = record['review']
        st.write(f"{decision['reviewer']} · {decision['decision'].title()} · {decision['reviewed_at'][:19]} UTC")
        st.write(decision['reason'])
    elif record['snapshot_current']:
        can_approve = result['overall_status'] in ('Ready', 'At Risk')
        if not can_approve:
            st.info('Approval is unavailable for a blocked or unavailable assessment. You can reject it with a reason.')
        with st.form(f'review_{selected}'):
            reviewer = st.text_input('Reviewer', key='reviewer')
            reason = st.text_area('Review reason', key='review_reason')
            approve_col, reject_col = st.columns(2)
            with approve_col:
                approve = st.form_submit_button('Approve assessment', disabled=not can_approve)
            with reject_col:
                reject = st.form_submit_button('Reject assessment')
        if approve or reject:
            try:
                workflow.review(selected, data_dir, reviewer, 'approve' if approve else 'reject', reason, DEMO_DATE)
                st.session_state['flash'] = 'Review decision saved.'
                st.rerun()
            except WorkflowError as exc:
                st.error(str(exc))
    st.divider()
    st.subheader('Deliver the follow-up task')
    st.write('Queue one task for this assessment, then deliver it to the local inbox. Each delivery attempt is recorded.')
    current = record['review_state'] == 'approved'
    if st.button('Queue follow-up task', disabled=not current, key='queue'):
        try:
            deliveries.enqueue(selected, data_dir, DEMO_DATE)
            st.session_state['flash'] = 'Follow-up queued. Repeat queue requests return the same task.'
            st.rerun()
        except WorkflowError as exc:
            st.error(str(exc))
    for delivery in deliveries.history():
        if delivery['assessment_id'] != selected:
            continue
        st.write('Delivery state: ' + delivery['state'].title())
        st.caption(f"Delivery {delivery['id'][:12]} · attempts: {len(delivery['attempts'])}")
        if delivery['state'] in ('pending', 'failed'):
            label = 'Retry delivery' if delivery['state'] == 'failed' else 'Deliver task'
            if st.button(label, key='send_' + delivery['id']):
                connector = LostDeliveryResponse(inbox) if scenario == 'delivery_failure' and not delivery['attempts'] else inbox
                try:
                    sent = deliveries.dispatch(delivery['id'], data_dir, connector, DEMO_DATE)
                    if sent['state'] == 'failed':
                        st.session_state['flash'] = 'Simulated response lost. The inbox accepted the task; retry uses the same key.'
                    elif sent['state'] == 'cancelled':
                        st.session_state['flash'] = 'Delivery cancelled because the approval is no longer current.'
                    else:
                        st.session_state['flash'] = 'Task delivered. The receipt and attempt are saved.'
                    st.rerun()
                except WorkflowError as exc:
                    st.error(str(exc))
        if delivery['attempts']:
            st.dataframe(delivery['attempts'], hide_index=True, use_container_width=True)
    st.subheader('Local task inbox')
    tasks = inbox.tasks()
    st.caption(f'{len(tasks)} task(s) in this scenario. A lost response and retry should still leave one task.')
    for task in tasks:
        with st.expander(task['payload']['title']):
            st.json(task['payload'])

with history:
    st.subheader('Assessment and review history')
    st.dataframe([{
        'Assessment': row['id'], 'Created (UTC)': row['created_at'],
        'Readiness': row['result']['overall_status'], 'Review state': row['review_state'],
        'Current snapshot': row['snapshot_current'],
        'Reviewer': row['review']['reviewer'] if row['review'] else '',
        'Reason': row['review']['reason'] if row['review'] else '',
    } for row in records], hide_index=True, use_container_width=True)
    st.subheader('Delivery history')
    st.json(deliveries.history())
    st.download_button('Download selected assessment', data=json.dumps(record, indent=2),
                       file_name=f'assessment-{selected}.json', mime='application/json')

st.caption('Assessments, decisions, and delivery attempts persist across restarts. Each scenario has its own history.')
