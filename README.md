# 🛡️ PALADIN — Policy-Aware Layered Agentic Decision Intelligence

A composable governance framework for securing LLM-based agentic tool selection
through layered identity, attribute, and formal logic policies.

> **Live Demo:** [paladin-duutz4i3lmxwm.thankfulsea-2363085b.eastus.azurecontainerapps.io](https://paladin-duutz4i3lmxwm.thankfulsea-2363085b.eastus.azurecontainerapps.io/)

---

## Problem Statement

Modern autonomous AI agents operate in open, federated ecosystems using protocols like the
**Model Context Protocol (MCP)**. These agents select and invoke tools on behalf of users —
but current security models offer only **flat RBAC** ("can this agent use this tool?") or
**prompt-level guardrails** that are brittle and non-auditable.

This creates a critical **governance gap**: probabilistic LLM decisions must be grounded by
**non-repudiable identity**, **contextual risk awareness**, and **formal logic verification**
— all *before* any tool is executed.

### Research Questions

| # | Question |
|---|----------|
| **RQ1** | Does a composable governance stack (RBAC → ABAC → TS-PHOL) provide measurably superior security over any single layer alone? |
| **RQ2** | Can Typed Security Policy Higher-Order Logic (TS-PHOL) provide a deterministic safety floor for probabilistic LLM inferences, including deception routing? |
| **RQ3** | Does PALADIN produce complete predicate traces sufficient for post-hoc audit of every tool-use decision? *(Evidence: trace logs in the Experiment Lab detail every predicate evaluation per task.)* |

---

## Technical Novelty

### 1. Composable Layered Governance
Unlike flat RBAC systems, PALADIN enforces three complementary security layers
with distinct failure modes — each catching threats the others miss:

| Layer | Catches | Example |
|---|---|---|
| **RBAC** | Identity mismatches | Finance agent → DevOps tools |
| **ABAC** | Contextual risk | Right role but after-hours + high-risk write |
| **TS-PHOL** | Logical inconsistency | Domain mismatch, capability gaps |

Ablation experiments prove each layer provides **irreplaceable value** —
removing any one leaves exploitable gaps.

### 2. TS-PHOL: Typed Formal Logic for Agentic Security
TS-PHOL doesn't just ask *"Can this agent use this tool?"* — it asks:
> *"Does the selected tool bundle satisfy the mission's capability requirements
> with sufficient confidence and domain alignment?"*

- **Post-inference, pre-execution** verification gate
- **Deception routing** — a third enforcement mode beyond ALLOW/DENY that honeypots
  suspicious requests for threat intelligence.
  Current evaluation measures detection accuracy; false-positive impact on availability
  is noted as a limitation and future work direction.
- **Complete predicate traces** — every decision is formally auditable

### 3. OPA Baseline Validation
PALADIN is validated against **Open Policy Agent (OPA)** — the CNCF-graduated
industry standard — by translating all rules into Rego and replaying
the same evaluations through a flat policy engine:

- **Rule equivalence** — high agreement on RBAC/ABAC confirms correct implementation
- **Layered advantage** — PALADIN's TS-PHOL predicates catch threats OPA's flat model misses
- **Deception routing gap** — OPA's binary ALLOW/DENY cannot express honeypot containment

### 4. Mission-Permission Decoupling
Unlike every existing RBAC/ABAC framework — which asks *"Is this caller allowed
to invoke this tool?"* — PALADIN evaluates tool selections against **task intent
and capability requirements**, not just caller identity.

TS-PHOL predicates verify that the *selected tool bundle* satisfies the
*mission's capability profile*: correct domain alignment, sufficient action
coverage, and adequate confidence — independently of who the caller is.
This means a legitimately authorized agent can still be denied if its tool
choice is wrong *for the task at hand*, closing a class of over-privilege
vulnerabilities that identity-only models cannot detect.

> **Limitations:** Single-model evaluation (GPT-4o), purpose-built dataset (ASTRA),
> and no production-scale latency benchmarks. See paper §7 for full discussion.

---

## Governance Pipeline Architecture

Every tool-use request flows through a **layered pipeline** where each layer independently
evaluates and can deny or redirect the request:

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Phase I:        │     │  Phase II:        │     │  Phase III:       │
│  Pre-LLM         │ ──► │  LLM Inference    │ ──► │  Post-LLM Logic   │
│                  │     │                   │     │                   │
│  ◆ SPIFFE ID     │     │  ◆ Tool Selection │     │  ◆ RBAC Check     │
│  ◆ Registry      │     │  ◆ Confidence     │     │  ◆ ABAC Rules     │
│  ◆ Allowlist     │     │  ◆ Justification  │     │  ◆ Fact Extraction│
│                  │     │                   │     │  ◆ TS-PHOL Rules  │
└─────────────────┘     └──────────────────┘     └──────────────────┘
                                                          │
                                                ┌────────┼────────┐
                                                ▼        ▼        ▼
                                              ALLOW    DENY   DECEPTION
```

### Unified Decision Engine (6-Step Sequence)
1. **Pre-LLM Gate (SPIFFE Identity & Transport Allowlist)** — Verifies the caller identity format, existence, and mTLS access restrictions
2. **LLM Inference** — Autonomous selection/validation of MCP tools. Skipped if Step 1 fails
3. **Fact Extraction (Tool Audit & Intent Decomposition)** — Tool-centric action classification, capability mapping, and intent inference
4. **RBAC** — Evaluates the caller's allowed/denied permissions against requested MCP tools
5. **ABAC Baseline** — Evaluates attribute-based contextual rules (role, MCP, action, confidence, risk)
6. **TS-PHOL Reasoning** — Executes formal predicate logic to reach the final authoritative decision

---

## Policy Layers (9 Configurable)

| # | Layer | File | Purpose |
|---|-------|------|---------|
| 1 | SPIFFE Registry | `policies/spiffe_registry.json` | Cryptographic identity anchoring (SPIFFE IDs → roles, trust, clearance) |
| 2 | Transport Allowlist | `policies/spiffe_allowlist.json` | Pre-LLM identity gate (DENY if caller not in allowlist) |
| 3 | MCP Attributes | `policies/mcp_attributes.yaml` | Risk metadata per MCP server (risk levels, compliance tiers) |
| 4 | RBAC Policies | `policies/rbac.yaml` | Role → permitted MCP domains/tools mapping |
| 5 | ABAC Rules | `policies/abac_rules.yaml` | Context-aware attribute-based access enforcement |
| 6 | Domain Catalog | `policies/domain_capability_catalog.json` | Tool → domain → action classification |
| 7 | Capability Ontology | `policies/domain_capability_ontology.json` | Intent → required capabilities mapping |
| 8 | Heuristic Logic | `policies/heuristic_policy.json` | Fallback tool classification via verb-prefix matching |
| 9 | TS-PHOL Rules | `policies/tsphol_rules.yaml` | Formal logic safety predicates (10 typed rules + DECEPTION mode) |

All policies are editable through the **Policy Studio** UI — changes take effect immediately.

---

## SPIRE Integration

PALADIN includes a fully integrated **SPIFFE/SPIRE** identity infrastructure:

- **Cloud (Azure Container Apps):** SPIRE server + agent run as a sidecar in the container.
  Real X.509 SVIDs are issued automatically on startup — 6 workload identities registered.
- **Local (Docker Compose):** Deploy SPIRE via `python deploy_spire.py` or the UI's
  built-in **🔧 SPIRE Deployment Controls** button.
- **Simulation mode:** If SPIRE is unavailable, the system operates with simulated identities.

Trust domain: `spiffe://demo.local`

---

## Application Sections

| Section | Description |
|---------|-------------|
| **🏠 Home** | Problem statement, research questions, novelty overview, pipeline architecture, and system state |
| **🛡️ Policy Studio** | Configure and inspect all 9 policy layers. SPIFFE Identity Registry with live SPIRE controls |
| **🤖 MCP Persona Explorer** | Browse the MCP server catalog — tools, descriptions, and domain scope per persona |
| **🔍 ASTRA Task Explorer** | Explore the evaluation dataset. Filter by MCP server, task category, and match tag |
| **🔮 Prediction Lab** | Run individual tasks through the full governance pipeline with detailed predicate traces |
| **🧪 Experiment Lab** | Run batch experiments (E1–E4) with ablation analysis. OPA baseline comparison tab. Access Decision Matrix (6,942 rows). AI-powered assessment |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Frontend** | Streamlit |
| **Language** | Python 3.12 |
| **LLM** | OpenAI GPT (configurable model) |
| **Identity** | SPIFFE/SPIRE 1.9.6 |
| **Policy Baseline** | OPA-equivalent Rego engine (Python) |
| **Hosting** | Azure Container Apps |
| **Container** | Docker (Python 3.12-slim + SPIRE sidecar) |
| **CI/CD** | Azure Developer CLI (`azd`) |

---

## Installation & Usage

### Prerequisites
- Python 3.10+ (3.12 recommended)
- OpenAI API key (for LLM-powered experiments)
- Docker (optional — for local SPIRE infrastructure)

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/vicvarar-hash/SPIFFI_RBAC_TS-PHOL.git
cd SPIFFI_RBAC_TS-PHOL

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Start SPIRE identity infrastructure
python deploy_spire.py

# 4. Run the application
streamlit run main.py
```

Configure your **OpenAI API key** in the Streamlit sidebar.

### Azure Deployment

The application is configured for Azure Container Apps with SPIRE sidecar:

```bash
# Login to Azure
az login

# Deploy (provisions infrastructure + builds + deploys)
azd up
```

Infrastructure is defined in `infra/` using Bicep (ACR + Container Apps Environment + Container App + Log Analytics).

---

## File Structure

```
├── main.py                          # Streamlit entrypoint
├── Dockerfile                       # Container image (Python + SPIRE sidecar)
├── azure.yaml                       # Azure Developer CLI config
├── requirements.txt                 # Python dependencies
├── deploy_spire.py                  # Local SPIRE deployment script
├── .gitattributes                   # Line ending rules (LF for .sh, .conf)
│
├── app/
│   ├── models/                      # Data models (AstraTask, MCPPersona)
│   ├── services/                    # Core logic
│   │   ├── decision_engine.py       # 6-step unified decision pipeline
│   │   ├── prediction_service.py    # LLM inference service
│   │   ├── policy_loader.py         # Policy file loader
│   │   ├── rbac_service.py          # RBAC evaluation
│   │   ├── abac_rule_service.py     # ABAC evaluation
│   │   ├── tsphol_rule_service.py   # TS-PHOL formal logic engine
│   │   ├── spiffe_registry_service.py   # SPIFFE identity management
│   │   ├── spiffe_workload_service.py   # SPIRE integration (sidecar + Docker)
│   │   ├── capability_inference_service.py  # Capability mapping
│   │   ├── opa_comparison_engine.py     # OPA baseline comparison
│   │   └── ...
│   └── ui/                          # Streamlit UI components
│       ├── home.py                  # Home page
│       ├── policy_studio.py         # Policy Studio + SPIRE controls
│       ├── prediction_lab.py        # Prediction Lab
│       ├── experiment_lab.py        # Experiment Lab + OPA tab
│       └── ...
│
├── policies/                        # Configurable policy files (JSON/YAML)
│   ├── spiffe_registry.json
│   ├── spiffe_allowlist.json
│   ├── rbac.yaml
│   ├── abac_rules.yaml
│   ├── tsphol_rules.yaml
│   ├── mcp_attributes.yaml
│   ├── domain_capability_catalog.json
│   ├── domain_capability_ontology.json
│   ├── heuristic_policy.json
│   └── rego/                        # OPA Rego translations
│       ├── rbac.rego
│       ├── abac.rego
│       └── tsphol.rego
│
├── datasets/                        # ASTRA dataset & generated artifacts
│   ├── astra_tasks.json
│   ├── mcp_personas.json
│   └── access_decision_matrix.json  # Generated (6,942 rows)
│
├── infra/                           # Azure infrastructure (Bicep)
│   ├── main.bicep                   # Subscription-scoped entry point
│   ├── main.parameters.json
│   ├── modules/
│   │   └── web.bicep                # Container Apps + ACR + Log Analytics
│   └── spire/
│       ├── sidecar/                 # Cloud SPIRE configs
│       │   ├── server.conf
│       │   ├── agent.conf
│       │   └── start-spire.sh       # Container startup orchestrator
│       ├── server/server.conf       # Local Docker SPIRE server config
│       ├── agent/agent.conf         # Local Docker SPIRE agent config
│       ├── docker-compose.yml       # Local SPIRE containers
│       └── register_workloads.sh
│
└── results/                         # Runtime output logs
    ├── prediction_logs.jsonl
    ├── decision_logs.jsonl
    └── policy_changes.jsonl
```

---

## License

This project is a research platform for studying layered policy governance over LLM-based agentic systems.

© 2026 PALADIN — Policy-Aware Layered Agentic Decision Intelligence

