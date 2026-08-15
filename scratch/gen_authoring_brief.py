"""Generate the leak-free policy-authoring brief for the LLM-authored-rules experiment.

Pulls exact personas, domain attributes, and per-domain tool catalogs from the
authoritative source files so every panel model receives identical, accurate inputs.
Writes policies/llm_authored/AUTHORING_BRIEF.md. NO match_tags, NO legitimate
pairings, NO evaluation rows, NO production rules are included (leak-free).
"""
from __future__ import annotations
import json, os, sys, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.services.experiment_config import PERSONAS  # noqa: E402
import yaml  # noqa: E402

ATTRS = yaml.safe_load(open(os.path.join(ROOT, "policies", "mcp_attributes.yaml"), encoding="utf-8"))["mcp_attributes"]
CLS = json.load(open(os.path.join(ROOT, "datasets", "tool_classification.json"), encoding="utf-8"))

DOMAIN_ORDER = ["wikipedia-mcp", "paper-search", "notion", "grafana",
                "atlassian", "mongodb", "azure", "stripe", "hummingbot-mcp"]

CLASS_ORDER = ["read", "benign_write", "privileged_write", "destructive_write"]


def personas_block() -> str:
    lines = ["| persona key | SPIFFE id | clearance | department | trust | description |",
             "|---|---|---|---|---|---|"]
    for k, p in PERSONAS.items():
        a = p["attributes"]
        lines.append(f"| `{k}` | `{p['spiffe_id']}` | {a['clearance_level']} | "
                     f"{a['department']} | {a['trust_score']} | {p['description']} |")
    return "\n".join(lines)


def domains_block() -> str:
    lines = ["| domain (`mcp`) | risk_level | compliance_tier | data_sensitivity | trust_boundary |",
             "|---|---|---|---|---|"]
    for d in DOMAIN_ORDER:
        a = ATTRS.get(d, {})
        lines.append(f"| `{d}` | {a.get('risk_level','?')} | {a.get('compliance_tier','?')} | "
                     f"{a.get('data_sensitivity','?')} | {a.get('trust_boundary','?')} |")
    return "\n".join(lines)


def tools_block() -> str:
    out = []
    for d in DOMAIN_ORDER:
        cls = CLS.get(d)
        if not cls:
            out.append(f"### `{d}`  (low-risk read-only reference domain; tools not separately classified)\n")
            continue
        out.append(f"### `{d}`")
        for c in CLASS_ORDER:
            names = cls.get(c, [])
            if not names:
                continue
            joined = ", ".join(f"`{n}`" for n in names)
            out.append(f"- **{c}** ({len(names)}): {joined}")
        out.append("")
    return "\n".join(out)


BRIEF = f"""# PALADIN — Policy-Authoring Brief (RBAC + ABAC)

You are a senior access-control engineer. Design the **best least-privilege RBAC and
ABAC policy you can** for a fleet of six autonomous agent personas that call tools on
nine MCP (Model Context Protocol) tool servers. Your policy will be enforced,
unmodified, as the RBAC and ABAC layers of a deterministic authorization pipeline and
scored on how well it **denies inadmissible tool bundles while admitting legitimate
work**. Author purely from the schema below — you are given no examples, no labels, and
no answer key, exactly as a real security engineer designing policy from first
principles.

## The enforcement objective

Each request is a `(persona, task, tool-bundle)` triple: a persona wants to run a
*bundle* of tools (all from a single MCP server) to accomplish a natural-language task.
Two classes of request are **inadmissible** and should be denied:

- **`wrong`** — the bundle is on the *correct* MCP server for the task but contains the
  *wrong tools* (a plausible but incorrect tool choice within the right domain).
- **`null`** — the bundle is on the *wrong* MCP server entirely (cross-domain: e.g. a
  billing task routed to the monitoring server).

Legitimate requests use the right server **and** the right tools **and** are within the
persona's job function and clearance. Your RBAC+ABAC should maximise denials of `wrong`
and `null` bundles and minimise denials of legitimate ones. (A separate, fixed
task-relevance layer runs after yours; do **not** try to model it — focus on the best
role- and attribute-based policy.)

## The six agent personas (subjects)

{personas_block()}

Subject attributes you may condition on: `attributes.clearance_level` (`L1` < `L2` < `L3`),
`attributes.department`, `attributes.trust_score` (real 0.0–1.0, supplied as a string).

## The nine tool domains (objects / resources)

{domains_block()}

Resource attributes you may condition on: `risk_level` (`low`/`medium`/`high`),
`compliance_tier` (`General`/`Monitoring`/`Enterprise`/`PCI-DSS`/`Financial`),
`data_sensitivity` (`Public`/`Metadata`/`Internal`/`Financial`/`Infrastructure`/`Private-Key`),
`trust_boundary` (`Third-Party`/`Vetted-Partner`/`Internal`/`Experimental`).

Action attributes (derived per bundle) you may condition on: `contains_write` (bool),
`contains_destructive_write` (bool, a subset of writes: delete/drop/purge/truncate…),
`contains_read_before_write` (bool).

## Per-domain tool catalog (grouped by operation class)

Use these exact tool names if you choose tool-level RBAC grants. `read` tools are
non-mutating; `benign_write` are low-impact writes; `privileged_write` are
state-changing writes; `destructive_write` are irreversible.

{tools_block()}

## Output 1 — RBAC (`rbac.yaml`)

One policy block per persona, addressed by `spiffe_id`. Each `rule` allows or denies a
persona a set of `tools` on an `mcp`. `tools: ["*"]` grants the whole domain; or list
specific tool names for fine-grained control. Rules are evaluated in order; end each
persona with an explicit `default_deny` (a `deny` rule on `mcp: "*"`) for least
privilege. Exact schema:

```yaml
policies:
  - spiffe_id: "spiffe://demo.local/agent/devops"
    description: "..."
    rules:
      - {{ mcp: "grafana", tools: ["*"], action: "allow", rule_name: "allow_grafana" }}
      - {{ mcp: "mongodb", tools: ["find_documents", "count_documents"], action: "allow", rule_name: "mongo_read" }}
      - {{ mcp: "*", tools: ["*"], action: "deny", rule_name: "default_deny" }}
```

Valid `mcp` values: `wikipedia-mcp`, `paper-search`, `notion`, `grafana`, `atlassian`,
`mongodb`, `azure`, `stripe`, `hummingbot-mcp`. Use the exact `spiffe_id`s from the
persona table.

## Output 2 — ABAC (`abac_rules.yaml`)

A flat list of **deny** rules. A rule fires (denies) when **every** condition in
`match_attributes` holds (logical AND); the request is denied if **any** rule fires. A
condition whose attribute is absent does **not** match (fail-closed), except `!=` which
holds for an absent attribute. Supported `source`: `subject`, `resource`, `action`.
Supported `op`: `==`, `!=`, `<`, `>`, `<=`, `>=`, `in`. Exact schema:

```yaml
rules:
  - id: "abac_example_clearance"
    action: "deny"
    description: "..."
    failure_reason: "..."
    match_attributes:
      - {{ source: "resource", attribute: "risk_level",               value: "high", op: "==" }}
      - {{ source: "subject",  attribute: "attributes.clearance_level", value: "L3",  op: "!=" }}
```

You may author as many or as few ABAC rules as you judge optimal. Think about:
clearance graduated by risk and destructiveness, department/compliance isolation,
trust-gated writes, and trust-boundary constraints — but design what **you** think is
best, not what you think we did.

## Hard constraints (do not violate)

1. Author **only** from the schema above. You have **no** task texts, **no** ground-truth
   labels, and **no** list of which persona–domain pairings are "correct". Infer sensible
   job functions from the persona descriptions and attributes.
2. Emit **exactly two** fenced code blocks: first the complete `rbac.yaml`, then the
   complete `abac_rules.yaml`. No prose between or after them beyond a short (≤5 line)
   design rationale comment block **inside** each YAML (as `#` comments).
3. Every rule must be syntactically valid against the schemas above and reference only
   the listed attributes, ops, domains, tool names, and spiffe_ids.
4. Optimise for the stated objective (deny `wrong`/`null`, admit legitimate). Do not
   blanket-deny everything (that trivially denies all bundles and is scored as useless).
"""


def main():
    out_dir = os.path.join(ROOT, "policies", "llm_authored")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "AUTHORING_BRIEF.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(BRIEF)
    print(f"wrote {path}  ({len(BRIEF)} chars)")


if __name__ == "__main__":
    main()
