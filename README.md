# SPIFFI_RBACK_TS-PHOL

Research and demonstration platform for secure, agentic tool orchestration using the Model Context Protocol (MCP).

## Architecture & Iterations

### Iteration 1 & 2: Core Prediction Flow & Dual-Mode Reasoning
- **LLM-ResM (Selection)**: Autonomous selection of up to 3 MCP tools based on task description.
- **Validation**: Independent evaluation of ASTRA dataset candidate bundles.
- **Parallel Reasoning Lab**: Side-by-side UI layout comparing Selection vs Validation against ASTRA Groundtruth.

### Iteration 3 & 4A/4A.1: Persona Identities, Realistic Policy, & Semantic Heuristics
Introduces a configuration and visualization layer for a real-world security architecture. The architecture is explicitly decoupled from dataset groundtruth, meaning the application is evaluated dynamically as if it were running natively in production.

Features include:
- **6-Persona Model**: Differentiating **Agent Personas** (e.g. `Finance Agent` or `DevOps Agent`) from internal restrictive **Service Identities** (e.g., `Automation Gateway`), mapped safely to backing `spiffe://` IDs. Backwards compatible auto-migration handles deprecated config keys natively.
- **Dynamic Risk Models**: `MCPRiskService` configures independent operational risk levels per MCP domain.
- **Realistic RBAC**: Identity-based authorization modeled heavily on real-world MCP tool domain scopes.
- **Semantic Rule Inferences**: The TS-PHOL heuristic engine consumes raw ASTRA Task strings to algorithmically infer risks (`missing_required_capability`, `irrelevant_tool_detected`, `cumulative_risk_score`) to simulate high-fidelity Contextual Access Constraints.

### Iteration 4A.2 (Revised): Staged Execution Pipeline & Evaluation States
This iteration refactors the pipeline for efficiency and complete transparency:
- **Pre-LLM Gate**: A short-circuit mechanism evaluates deterministic checks (Identity and Transport) *before* invoking expensive LLM calls. If these checks fail, the LLM is entirely bypassed.
- **Strict Evaluation States**: The pipeline uses explicit `ALLOW`, `DENY`, and `NOT_EVALUATED` states, clearly differentiating between a security rule explicitly denying a request versus a downstream step never executing because of a prior block.
- **LLM Transparency & Derived Features**: The UI strictly separates the raw AI output (Predicted MCPs/Tools, Justification, Confidence) from the System-Derived Features calculated post-inference (Operation risk score, tool counts, read/write heuristics). This eliminates "black box" behavior.

### Iteration 4C & 4E: Intent-Aware Predicate-Based Reasoning + Declarative Engine
This iteration transforms the security engine into a formal logic reasoning system (Tractable Scoped Probabilistic Higher-Order Logic, or TS-PHOL) that understands **intent** and **capabilities**.
- **Intent Decomposition & Capability Mapping**: Extracts the "Why" behind an agent's request (e.g., `InvestigateAnomaly` vs `SystemUpdate`) and maps tools to abstract capabilities like `MetricsQuery` or `LogAnalysis`.
- **Declarative TS-PHOL**: Rules are now evaluated using formal logic predicates (e.g., `ConfidenceValue < 0.9 ∧ HasWriteCapability → DENY`) through a generic logic interpreter.
- **ABAC Baseline Layer**: A parallel, strictly attribute-based access control tier (Role, MCP, Action, Confidence) provides a comparison point for the more advanced TS-PHOL logic.
- **Logical Reasoning Traces**: The UI exposes a multi-step logical derivation trace showing how base predicates were combined to reach a security decision.

### Iteration 4F: Predicate & Intent Extraction Refinement (Tool-Centric)
This iteration hardens the "fact extraction" layer by shifting from text heuristics to **tool-centric inference**.
- **Tool Classifier Service**: A central authority that maps tools to action categories (read, write, delete, search, etc.) and granular capabilities.
- **Refined Intent Extraction**: Intent properties (`ContainsRead`, `ContainsWrite`) and required capabilities are now derived primarily from the actual selected tools, ensuring reasoning is faithful to the request.
- **Advanced Logic Predicates**: Introduces `ContainsReadBeforeWrite` and `DominantActionType` to support realistic workflow safety reasoning.
- **Predicate Audit View**: A new UI section in the Prediction Lab providing full transparency into how each tool was classified and the request-level predicates generated.

### Iteration 4G: Domain-Aware Policies & ABAC Calibration
This iteration transforms the security engine into a **domain-aware reasoning system** with realistic baseline performance.
- **Domain-Aware Intent Taxonomy**: Transitioning from general keyword matching to domain-specific (Atlassian, Wikipedia, Grafana) intent classification.
- **Capability Enrichment**: Maps over 15 specific tools to unique, granular capabilities (e.g., `TopicSummarization`, `AlertRuleReview`) with source tracking (Curated vs Heuristic).
- **ABAC Calibration**: Refines the baseline access control thresholds to produce a realistic performance mix: `ALLOW` for low-to-medium risk read tasks with sufficient confidence, and `DENY` for high-risk writes.
- **Audit Source Transparency**: The Prediction Lab UI now identifies whether a tool mapping was derived from a curated catalog or a heuristic fallback.

### Iteration 4H: Required Capability Alignment & Policy Studio Visibility
This iteration refines the capability requirement engine for maximum accuracy and transparency.
- **Tool-Grounded Requirements**: `RequiredCapabilities` now default to only those directly mapped from selected tools, eliminating "noisy" over-generation.
- **Rule-Based Intent Inference**: Task-text signals now add extra requirements only through formal, domain-scoped rules with configurable confidence thresholds.
- **Policy Studio Controls**: A new dedicated section for managing the **Domain Capability Catalog**, **Inference Rules**, and the **Global Confidence Threshold**.
- **Requirement Provenance Audit**: The Decision View explicitly breaks down requirement sources (Tool vs. Intent) and shows filtering/rejection status for explainable security.

### Iteration 4H.1: Dynamic & Expandable Domain Capability Catalog
This iteration scales the capability inference system to support the full ecosystem of MCP domains with dynamic management.
- **Full Domain Expansion**: Refactored taxonomy to support all 9 MCP domains (Notion, Stripe, MongoDB, Azure, Hummingbot, Research, etc.).
- **Dynamic Domain Management**: Added a new UI section to **Add, Update, and Delete Domains** directly from the Policy Studio.
- **String-Based Routing**: Decoupled inference logic from fixed Enums, allowing for real-time catalog expansion without code changes.
- **Seeded Capability Knowledge**: Pre-populated the catalog with over 45 curated capabilities across all 9 domains for high-fidelity reasoning.

### Iteration 4L: Comprehensive Inference & Rule CRUD
This iteration completes the Capability Inference system by seeding knowledge for the entire MCP ecosystem and providing full CRUD controls.
- **Ecosystem-Wide Seeding**: Added high-fidelity inference rules for all 9 domains (Notion, Stripe, Azure, MongoDB, Hummingbot, Research), ensuring the system responds intelligently to keywords like "payment", "subscription", and "arxiv".
- **Full Rule CRUD Lifecycle**: Upgraded the Policy Studio to support the **Update** operation for existing rules. You can now modify rule names, domains, keywords, and confidence levels in-place.
- **Unified Domain Taxonomy**: Synchronized the inference engine with the 9-domain taxonomy to prevent cross-domain capability leakage.

### Iteration 4I: Capability Enrichment & ABAC Tracing
This iteration matures the system's semantic intelligence and explainability.
- **Enriched Capability Mapping**: Eliminated `GenericToolUse` for core domains (Grafana, Jira, Wikipedia) by adding granular mappings (e.g., `AlertRuleReview`).
- **Capability Hierarchy**: Introduced abstract reasoning layers (e.g., `AlertRuleReview` -> `ObservabilityRead`) allowing TS-PHOL to reason at multiple levels of abstraction.
- **ABAC Reasoning Trace**: The ABAC baseline now provides a detailed logic trace, explaining exactly which attribute conditions were met.
- **Full Predicate Synchrony**: Refactored the internal data flow to ensure `tool_aggregates` from the fact extraction layer are strictly identical to the input of the TS-PHOL engine.
- **Enhanced Audit UI**: Improved the Predicate Audit view with better JSON rendering (sorting, set-to-list conversion) and distinct provenance indicators.

### Iteration 4K: TS-PHOL Rule Audit Transparency
This iteration ensures full explainability for every security decision, including those that result in an `ALLOW`.
- **Positive Evaluation Traces**: TS-PHOL now evaluates and records the status of *every* rule, even when they do not trigger a denial.
- **Structured Audit Result**: Each rule evaluation produces a high-fidelity record containing `evaluated`, `triggered`, `passed`, and a human-readable `reason`.
- **Human-Readable Rationale**: Refactored the interpreter to provide logical explanations for rule decisions (e.g., "ContainsWrite is false -> safe").
- **Audit UI Table**: Added a dedicated "Rule Evaluation Audit" section to the Prediction Lab, showing a clear PASS/FAIL breakdown for every security policy.
- **Zero-Empty Trace Policy**: Ensured that the TS-PHOL trace is never empty, providing a definitive proof of safety for every execution.

The **Unified Decision Engine** operates in a strict 6-step sequence:
1. **Pre-LLM Gate (SPIFFE Identity & Transport Allowlist)**: Verifies the caller identity format, existence, and mTLS access restrictions.
2. **LLM Inference**: LLM runs to perform selection or validation. Skipped if Step 1 fails.
3. **Fact Extraction (Tool Audit & Intent Decomposition)**: Performs tool-centric action classification, capability mapping, and intent inference.
4. **RBAC**: Evaluates the caller's allowed/denied permissions against the requested MCP tools.
5. **ABAC Baseline (Parallel)**: Evaluates simple attribute-based rules for comparison and transparency.
6. **TS-PHOL (Tractable Scoped Probabilistic Higher-Order Logic) Reasoning**: Executes formal predicate logic to reach the final authoritative decision.

#### Prediction Lab Integration
The Parallel Reasoning Lab features a fully integrated **Execution Pipeline Panel**. It dynamically runs the 6-step engine, producing detailed traces separating benchmark results from logical reasoning. Intent decomposition, ABAC baselines, and formal predicate traces are cleanly isolated in the view.

## Installation

1. Ensure Python 3.9+ is installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### 1. Start Identity Infrastructure (SPIRE)
If you wish to test with genuine cryptographic identities instead of simulating them, you can instantly spin up the Docker-Compose network and register the agents by running:
```bash
python deploy_spire.py
```

### 2. Run the Application
Start the Streamlit reasoning lab:
```bash
streamlit run main.py
```
*Configure your OpenAI API key in the Streamlit Sidebar.*

## File Structure

- `app/services/`: Core logic (`decision_engine`, `prediction_service`, `policy_loader`, `rbac_service`, etc.)
- `app/ui/`: Streamlit components (`prediction_lab`, `policy_studio`)
- `policies/`: JSON and YAML configuration files managed by the Policy Studio.
- `results/`: Output logs (`prediction_logs.jsonl`, `decision_logs.jsonl`, `policy_changes.jsonl`).
