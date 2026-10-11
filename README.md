# Launch Readiness Copilot

A reference implementation of an AI-assisted launch readiness system that synthesizes operational signals across inventory, fulfillment, merchandising, and customer feedback into a structured launch assessment.

Rather than asking an LLM to inspect raw business data and make an unconstrained judgment, the application first analyzes each domain deterministically, assembles the results into a typed `LaunchReadinessContext`, and then gives the model that bounded context for reasoning and explanation.

## Run the Example

From the repository root (Python 3.10 or later):

```bash
python -m pip install -r requirements.txt
LLM_BACKEND=mock python -m app.main
python -m pytest -q
```

The mock example requires no API key. For live inference, set `LLM_BACKEND=anthropic`
and `ANTHROPIC_API_KEY` in your environment before running the application.

## Enforced Readiness Rules

A launch assessment must preserve known business constraints even when the model
returns a contradictory recommendation. Python enforces these rules after inference;
the model supplies explanations and proposed actions.

| Business capability | Implementation | Verification |
| --- | --- | --- |
| Known blockers prevent a Ready assessment | `app/policy/readiness.py` | `tests/test_readiness_policy.py` tests a model returning Ready despite a blocker |
| Unresolved conflicts require review | Policy checks conflict resolution state | Tests cover unresolved, needs-review, and resolved conflicts |
| Missing sources prevent unqualified readiness | Below 80% completeness: at least At Risk; below 60%: required review | Boundary tests cover both thresholds |
| Quality feedback gets human attention | Feedback signals requiring interpretation trigger review and at least At Risk | Product quality review test |
| Model uncertainty remains visible | Unknown/invalid status requires review; stricter model status and lower confidence are preserved | Unavailable-model and conservative-assessment tests |

The completeness score currently measures **presence of the five input sources**,
not their freshness, validity, or coverage of every product variant. Confidence is
capped using that score; it is not a calibrated probability of correctness.

The assessment boundary validates the six required response fields, their types,
allowed status/confidence values, and review-reason consistency. Each proposed action
must contain `action`, `signal_ids`, and `conflict_fields`; every reference must exist
in the current context and at least one reference is required. String-only actions
from the earlier prototype are no longer accepted.

Invalid assessments are rejected in full. The report shows an explicit unavailable
assessment with no proposed model actions, Low confidence, and required human review.
Known blockers still enforce Not Ready; otherwise an invalid assessment remains
Unknown. Invalid JSON, interrupted generation, and unexpected provider content also
produce this reviewable failure. Raw malformed output is not displayed as a summary.

| Business capability | Implementation | Verification |
| --- | --- | --- |
| Prevent malformed assessments from entering reports | `app/validation/assessment.py`, called by `enforce_readiness` | `tests/test_assessment_validation.py` tests wrong types, missing/extra fields, and inconsistent review metadata |
| Require traceable proposed actions | Explicit signal and conflict reference arrays checked against the current context | Tests reject invented references and actions with no references |
| Surface model/provider failures for review | Anthropic adapter failure handling plus the shared policy boundary | Stubbed-provider tests cover invalid JSON, truncation, empty/unexpected content, and non-object JSON |

Reference validation proves that cited findings exist; it does not prove the action
text is supported by those findings. Generated prose may still contradict the enforced
status. Semantic evaluation and downstream authorization remain
subsequent workflow upgrades.

## Input Validation and Data Quality

Input contracts are checked before domain analysis. Missing/unreadable source files,
malformed input structures, invalid launch dates, duplicate identifiers, negative
inventory quantities, invalid CSV booleans, and malformed review records stop the CLI
with an explicit input error and nonzero exit status. No model call is made. The
launch date is never silently replaced with today's date.

Missing or blank descriptive catalog fields remain business findings rather than
being filled in. Valid but empty source collections reduce the source-presence score.
The report labels this metric **Source Presence**, so 100% does not imply complete
or current business information.

Inventory coverage is checked against the Cartesian product of each catalog product's
listed colors and sizes. Missing variant records and inventory variants that do not
match the catalog become `DQ-` findings. Missing records do not mean zero stock.
This prototype assumes every listed color/size combination belongs to the launch;
a production connector should supply an explicit expected assortment when that
assumption does not hold. Product association uses the catalog SKU base followed by
`-`; ambiguous matches require review.

Source freshness uses optional `data/source_metadata.json`, keyed by source filename:

```json
{
  "inventory.csv": {
    "updated_at": "2026-08-05",
    "max_age_days": 2
  }
}
```

Each source can set its own maximum age. Sources without metadata have **unknown
freshness**. Dates after the assessment date and sources older than their specified
limit also become findings. File modification times and free-text dates are not used
as substitutes for explicit metadata. Invalid metadata stops assessment.

Use an explicit date to reproduce freshness checks:

```bash
LLM_BACKEND=mock python -m app.main --as-of 2026-08-08
```

Without `--as-of`, freshness is checked against today's date. The historical sample
has no metadata and only partial variant records; its quality findings are intentional.
Any `DQ-` finding requires human review and caps confidence at Medium. These checks do
not establish source authenticity, calibrated confidence, or the semantic accuracy
of free-text analysis.

The implementation is in `app/validation/inputs.py` and
`app/analyzers/data_quality_analyzer.py`. `tests/test_input_quality.py` verifies invalid
inputs stop before analysis/inference, source gaps remain visible, and freshness
boundaries behave predictably.

## Persisted Assessments and Human Review

`app/workflow/service.py` provides the shared Python service for the workflow CLI
and the planned Streamlit UI. SQLite stores each assessment's typed context and
evidence, original model response, enforced result, assessment date, creation time,
and SHA-256 fingerprint of all five sources plus optional freshness metadata.

Run a historical sample assessment and inspect saved history:

```bash
LLM_BACKEND=mock python -m app.workflow_cli --db readiness.sqlite3 --as-of 2026-08-08 assess
python -m app.workflow_cli --db readiness.sqlite3 --as-of 2026-08-08 history
python -m app.workflow_cli --db readiness.sqlite3 --as-of 2026-08-08 show ASSESSMENT_ID
```

Replace `ASSESSMENT_ID` with the ID returned by `assess`. The sample contains blockers,
so it can be rejected but cannot be approved:

```bash
python -m app.workflow_cli --db readiness.sqlite3 --as-of 2026-08-08 review ASSESSMENT_ID --reviewer "Demo reviewer" --decision reject --reason "Resolve launch blockers and data quality findings."
```

| Business behavior | Enforced implementation | Evidence |
| --- | --- | --- |
| Retrieve evidence and decisions after restart | SQLite assessment snapshots and review records | Restart/persistence test in `tests/test_workflow.py` |
| Prevent approval of blocked or unavailable assessments | Approval allowed only for Ready or At Risk assessments | Blocker and invalid-model approval tests |
| Tie review to the assessed data | Byte-content fingerprints and assessment-date check | Source, metadata, and date-change tests |
| Preserve prior decisions when sources change | History keeps the decision; current view becomes reassessment_required | Previous-approval test |
| Avoid overwriting competing decisions | Transactional review with one decision per assessment | Concurrent approval/rejection test |

States are `pending_review`, `approved`, `rejected`, and `reassessment_required`.
Once reviewed, an assessment cannot be reviewed again; create a new assessment.
An At Risk assessment may be approved with a reason, but retains its At Risk status
and findings. Approval records a review; it does not authorize or perform a launch.

The source fingerprint is checked before and after analysis/inference; detected
changes prevent saving the assessment. Review checks the current sources and date.
The workflow requires reassessment on a new assessment date, even if the source
bytes are unchanged, so freshness checks are repeated. `--as-of` supports reproducible
historical demonstrations; use the default current date for current reviews.

**Demo boundary:** reviewer names are self-declared attribution, not authenticated
identities. Role authorization and identity-provider integration are not implemented.
The local database is not tamper-proof, and fingerprint checks do not lock externally
mutable files; a production integration needs versioned source snapshots. A record
retrieved without a source directory has `snapshot_current: null`; its historical
review state does not establish current approval validity. The CLI always checks
sources when showing records. Streamlit will call these same services.

## Architecture

```text
Inventory Data ───────► Inventory Analyzer ──────┐
                                                 │
Fulfillment Data ─────► Fulfillment Analyzer ────┤
                                                 │
Merchandising Data ───► Merchandising Analyzer ──┼──► LaunchReadinessContext
                                                 │             │
Customer Feedback ────► Feedback Analyzer ───────┘             ▼
                                                         LLM Reasoning
                                                               │
                                                               ▼
                                                     Readiness Assessment
```

The core pipeline is:

```text
Raw operational data
        ↓
Domain-specific analyzers
        ↓
Structured findings
        ↓
Typed launch-readiness context
        ↓
Bounded LLM reasoning
        ↓
Human-readable assessment
```

## Why This Architecture?

Launch readiness is not one question.

It is an aggregation problem across several different operational domains, each with its own signals and failure conditions.

The application separates:

- **fact discovery** from **reasoning**
- **domain analysis** from **cross-domain synthesis**
- **structured system state** from **generated explanation**

The model therefore does not need to rediscover facts that application code can establish first.

Instead, it reasons over an explicit representation of what the system currently knows.

## Domain Analyzers

The application contains dedicated analyzers for the major launch-readiness domains represented in the prototype.

### Inventory

Evaluates inventory-related launch conditions and surfaces relevant availability or stock concerns.

### Fulfillment

Examines fulfillment signals that may affect the ability to support a launch successfully.

### Merchandising

Evaluates merchandising readiness independently from inventory and fulfillment state.

### Customer Feedback

Extracts and classifies relevant signals from customer feedback so qualitative information can participate in the same readiness assessment as structured operational data.

Each analyzer produces structured findings rather than a final launch decision.

## Typed Launch Context

The outputs of the individual analyzers are assembled into a shared `LaunchReadinessContext`.

This acts as the semantic contract between deterministic analysis and model reasoning.

```text
Inventory findings
Fulfillment findings
Merchandising findings
Customer feedback
        │
        ▼
LaunchReadinessContext
        │
        ▼
Claude Sonnet 4.5
```

Using an explicit domain model provides several advantages:

- the model receives a predictable input structure
- individual analyzers can evolve independently
- findings can be inspected before model invocation
- deterministic behavior can be tested without an LLM
- model behavior can be evaluated against a known system state
- new readiness domains can be added without redesigning the entire reasoning layer

The ontology therefore serves as more than an output schema. It defines the concepts the reasoning layer is allowed to operate over.

## Model Boundary

Claude Sonnet 4.5 is responsible for **synthesis, interpretation, and explanation**.

It is not responsible for discovering every underlying operational fact from scratch.

```text
Application code:
    discover → classify → structure

Claude Sonnet 4.5:
    synthesize → reason → explain
```

This creates a narrower reasoning problem for the model and makes the system easier to inspect and evaluate.

If an underlying analyzer produces an incorrect finding, that can be investigated independently from whether the model reasoned correctly over the findings it received.

The model integration is also abstracted behind an `LLMClient` interface. The Anthropic implementation provides live Claude inference, while a mock implementation supports deterministic development and testing without requiring model calls.

## Cross-Domain Reasoning

The value of the reasoning layer emerges when signals interact.

A condition that looks acceptable within one domain may become important when combined with findings elsewhere in the launch.

For example:

```text
Inventory risk
      +
Fulfillment constraint
      +
Customer feedback signal
      ↓
Cross-domain launch concern
```

The structured context gives the model visibility across those domains without requiring each analyzer to encode every possible cross-domain relationship itself.

This preserves deterministic domain logic while allowing more flexible synthesis at the final reasoning stage.

## Evaluation

The repository includes tests across:

- domain analyzers
- pipeline behavior
- prompt construction
- ontology / typed context

This separation is intentional.

Analyzer behavior can be tested deterministically, while model-facing components can be evaluated independently.

That makes it easier to identify whether a failure originated in:

1. source analysis
2. context construction
3. prompt construction
4. model reasoning

rather than treating the entire AI pipeline as a single opaque operation.

The abstract LLM client and mock implementation also allow pipeline behavior to be tested without coupling deterministic tests to live model availability or behavior.

## Project Structure

```text
app/
  analyzers/        Domain-specific launch analysis
  llms/             LLM interface, Anthropic client, mock client, and factory
  prompts/          Model reasoning instructions
  ontology/         Typed launch-readiness domain model
  main.py           Application entry point

data/
  Sample operational and customer-feedback inputs

tests/
  Analyzer, pipeline, prompt, and ontology tests
```

## Technology

- **Python**
- **Anthropic Claude Sonnet 4.5** for cross-domain synthesis and readiness reasoning
- **Anthropic Python SDK**
- **Typed Python domain models / ontology**
- **Deterministic domain analyzers**
- **Abstract LLM client interface** supporting interchangeable live and mock backends
- **Fixture-based test data**
- **Automated tests** covering analyzers, pipeline behavior, prompt construction, and ontology contracts

## Extending the System

The architecture is designed so additional operational domains can be incorporated by adding another analyzer and extending the shared launch context.

For example:

```text
Pricing ──────────────► Pricing Analyzer ─────────┐
                                                  │
Marketing ────────────► Campaign Analyzer ────────┼──► LaunchReadinessContext
                                                  │
Returns ──────────────► Returns Analyzer ─────────┘
```

The reasoning layer can then incorporate those findings without requiring raw access to every underlying source or embedding all domain logic inside the prompt.

In a larger implementation, the same boundary could sit over APIs, databases, event streams, or other operational systems rather than local prototype data.

## Scope

This repository is a prototype demonstrating an architectural pattern for AI-assisted operational decision support.

It is intentionally bounded and does not represent a complete production launch-management platform.

The project focuses on:

- domain-specific deterministic analysis
- typed representations of business state
- separation of fact discovery from model reasoning
- cross-domain synthesis
- testable AI pipelines
- interchangeable model integrations

The central design principle is:

> **Structure what the system knows before asking the model what it means.**