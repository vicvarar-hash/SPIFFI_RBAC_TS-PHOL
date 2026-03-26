# SPIFFI_RBACK_TS-PHOL

Research and demonstration platform for secure, agentic tool orchestration using the Model Context Protocol (MCP).

## Architecture & Iterations

### Iteration 1 & 2: Core Prediction Flow & Dual-Mode Reasoning
- **LLM-ResM (Selection)**: Autonomous selection of up to 3 MCP tools based on task description.
- **Validation**: Independent evaluation of ASTRA dataset candidate bundles.
- **Parallel Reasoning Lab**: Side-by-side UI layout comparing Selection vs Validation against ASTRA Groundtruth.

### Iteration 3 & 3.5: Policy Studio & Unified Decision Engine
Introduces a configuration and visualization layer for a real-world security architecture, backed by a unified **Decision Engine** that processes pipelines to yield an active logical simulation of an `ALLOW`, `DENY`, or `FLAG` decision.

The **Unified Decision Engine** operates in a strict 5-step sequence:
1. **SPIFFE Identity Registry (`spiffe_registry.json`)**: Verifies the caller identity format and existence.
2. **Transport Allowlist (`spiffe_allowlist.json`)**: Simulates mTLS access control—blocks unauthorized connections.
3. **RBAC (`rbac.yaml`)**: Evaluates the caller's allowed/denied permissions against the requested MCP tools. Supports `*` wildcards.
4. **TS-PHOL Rules (`tsphol_rules.yaml`)**: Executes heuristics evaluating metadata (Risk Level, Tool Count, Action Type) and LLM Confidence.
5. **Final Synthesis**: Returns `DENY` if any hard block is hit, `FLAG` if TS-PHOL requires human-in-the-loop review, or `ALLOW` if all checks pass.

#### Prediction Lab Integration
The Parallel Reasoning Lab features a fully integrated **Security Decision Panel**. It dynamically runs the 5-step engine on both the LLM's Selection output and the baseline Validation bundle, producing color-coded decision badges and highly detailed security traces.

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
