# Launch Readiness Copilot

A reference implementation of an AI-assisted launch readiness system that synthesizes operational signals across inventory, fulfillment, merchandising, and customer feedback into a structured launch assessment.

Rather than asking an LLM to inspect raw business data and make an unconstrained judgment, the application first analyzes each domain deterministically, assembles the results into a typed `LaunchReadinessContext`, and then gives the model that bounded context for reasoning and explanation.

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