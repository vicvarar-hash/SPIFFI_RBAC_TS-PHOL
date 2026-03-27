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

The **Unified Decision Engine** operates in a strict 5-step sequence:
1. **SPIFFE Identity Registry**: Verifies the caller identity format and existence.
2. **Transport Allowlist**: Simulates mTLS access control—blocks unauthorized connections.
3. **RBAC**: Evaluates the caller's allowed/denied permissions against the requested MCP tools.
4. **TS-PHOL Rules**: Executes complex heuristics evaluating metadata (Domain Risk Level, Contains Write, Dominant Action Type, Task capabilities matching Tools, LLM Confidence). This is decoupled entirely from benchmark groundtruth. If RBAC denies the request earlier in the chain, it gracefully flags TS-PHOL as bypassed.
5. **Final Synthesis**: Explicitly isolates standard Benchmark evaluations from the Runtime Security blocks to yield a clear, highly traceable pipeline output logging into `decision_logs.jsonl`.

#### Prediction Lab Integration
The Parallel Reasoning Lab features a fully integrated **Execution Pipeline Panel**. It dynamically runs the 5-step engine on both the LLM's Selection output and the baseline Validation bundle, producing detailed traces separating benchmark results from logic reasoning.

## Installation

1. Ensure Python 3.9+ is installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the Streamlit app:
```bash
streamlit run main.py
```
*Configure your OpenAI API key in the Streamlit Sidebar.*

## File Structure

- `app/services/`: Core logic (`decision_engine`, `prediction_service`, `policy_loader`, `rbac_service`, etc.)
- `app/ui/`: Streamlit components (`prediction_lab`, `policy_studio`)
- `policies/`: JSON and YAML configuration files managed by the Policy Studio.
- `results/`: Output logs (`prediction_logs.jsonl`, `decision_logs.jsonl`, `policy_changes.jsonl`).
