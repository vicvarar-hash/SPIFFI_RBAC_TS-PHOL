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

### Iteration 4B: Real SPIFFE/SPIRE Integration (Workload Identity)
Replaces the simulated UI identity selectors with an authentic, cryptographically-backed Workload API query. 
- Integrated **SPIRE Server & Agent** zero-dependency docker cluster.
- **Python Workload Service**: Consumes `pyspiffe` to fetch the default SVID running on the host/container.
- **Seamless Fallback**: Directly downgrades the UI back to the simulated Persona dropdown if SPIRE cannot be reached, without crashing the AI pipelines.
- **Identity Tracing**: Logs distinctly record whether an execution used a `Real SPIFFE Identity` or a `Simulated` token.

The **Unified Decision Engine** operates in a strict 5-step sequence:
1. **Pre-LLM Gate (SPIFFE Identity & Transport Allowlist)**: Verifies the caller identity format, existence, and mTLS access restrictions.
2. **LLM Inference**: LLM runs to perform selection or validation. Skipped if Step 1 fails.
3. **RBAC**: Evaluates the caller's allowed/denied permissions against the requested MCP tools.
4. **TS-PHOL Rules**: Executes complex heuristics evaluating metadata (Domain Risk Level, Contains Write, Dominant Action Type, Task capabilities matching Tools, LLM Confidence). Marked `NOT_EVALUATED` if RBAC fails.
5. **Final Synthesis**: Explicitly isolates standard Benchmark evaluations from the Runtime Security blocks to yield a clear, highly traceable pipeline output logging into `decision_logs.jsonl`.

#### Prediction Lab Integration
The Parallel Reasoning Lab features a fully integrated **Execution Pipeline Panel**. It dynamically runs the 5-step engine, producing detailed traces separating benchmark results from logic reasoning. Raw LLM Inference vs Runtime Features are cleanly isolated in the view.

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
