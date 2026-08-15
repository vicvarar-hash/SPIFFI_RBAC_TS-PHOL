# PALADIN — Policy-Authoring Brief (RBAC + ABAC)

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

| persona key | SPIFFE id | clearance | department | trust | description |
|---|---|---|---|---|---|
| `devops_agent` | `spiffe://demo.local/agent/devops` | L3 | Engineering | 1.0 | Handles monitoring and operational diagnostics |
| `incident_agent` | `spiffe://demo.local/agent/incident` | L2 | Operations | 0.88 | Handles incident tracking and escalation |
| `finance_agent` | `spiffe://demo.local/agent/finance` | L2 | Finance | 0.95 | Handles billing and financial workflows |
| `research_agent` | `spiffe://demo.local/agent/research` | L1 | Research | 0.75 | Handles low-risk information discovery |
| `automation_gateway` | `spiffe://demo.local/service/gateway` | L3 | Infrastructure | 1.0 | Executes approved tool operations |
| `security_engine` | `spiffe://demo.local/service/security` | L3 | Security | 1.0 | Evaluates transport, RBAC, and TRAC rules |

Subject attributes you may condition on: `attributes.clearance_level` (`L1` < `L2` < `L3`),
`attributes.department`, `attributes.trust_score` (real 0.0–1.0, supplied as a string).

## The nine tool domains (objects / resources)

| domain (`mcp`) | risk_level | compliance_tier | data_sensitivity | trust_boundary |
|---|---|---|---|---|
| `wikipedia-mcp` | low | General | Public | Third-Party |
| `paper-search` | low | General | Public | Third-Party |
| `notion` | medium | General | Internal | Vetted-Partner |
| `grafana` | medium | Monitoring | Metadata | Internal |
| `atlassian` | high | General | Internal | Vetted-Partner |
| `mongodb` | high | General | Financial | Internal |
| `azure` | high | Enterprise | Infrastructure | Vetted-Partner |
| `stripe` | high | PCI-DSS | Financial | Vetted-Partner |
| `hummingbot-mcp` | high | Financial | Private-Key | Experimental |

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

### `wikipedia-mcp`
- **read** (10): `extract_key_facts`, `get_article`, `get_coordinates`, `get_links`, `get_related_topics`, `get_sections`, `get_summary`, `search_wikipedia`, `summarize_article_for_query`, `summarize_article_section`

### `paper-search`  (low-risk read-only reference domain; tools not separately classified)

### `notion`
- **read** (9): `API-get-block-children`, `API-get-self`, `API-get-user`, `API-get-users`, `API-retrieve-a-block`, `API-retrieve-a-comment`, `API-retrieve-a-database`, `API-retrieve-a-page`, `API-retrieve-a-page-property`
- **privileged_write** (9): `API-create-a-comment`, `API-create-a-database`, `API-patch-block-children`, `API-patch-page`, `API-post-database-query`, `API-post-page`, `API-post-search`, `API-update-a-block`, `API-update-a-database`
- **destructive_write** (1): `API-delete-a-block`

### `grafana`
- **read** (40): `fetch_pyroscope_profile`, `find_error_pattern_logs`, `find_slow_requests`, `generate_deeplink`, `get_alert_rule_by_uid`, `get_assertions`, `get_current_oncall_users`, `get_dashboard_by_uid`, `get_dashboard_panel_queries`, `get_dashboard_property`, `get_dashboard_summary`, `get_datasource_by_name`, `get_datasource_by_uid`, `get_incident`, `get_oncall_shift`, `get_sift_analysis`, `get_sift_investigation`, `list_alert_rules`, `list_contact_points`, `list_datasources`, `list_incidents`, `list_loki_label_names`, `list_loki_label_values`, `list_oncall_schedules`, `list_oncall_teams`, `list_oncall_users`, `list_prometheus_label_names`, `list_prometheus_label_values`, `list_prometheus_metric_metadata`, `list_prometheus_metric_names`, `list_pyroscope_label_names`, `list_pyroscope_label_values`, `list_pyroscope_profile_types`, `list_sift_investigations`, `list_teams`, `list_users_by_org`, `query_loki_logs`, `query_loki_stats`, `query_prometheus`, `search_dashboards`
- **benign_write** (1): `add_activity_to_incident`
- **privileged_write** (2): `create_incident`, `update_dashboard`

### `atlassian`
- **read** (19): `confluence_get_comments`, `confluence_get_labels`, `confluence_get_page`, `confluence_get_page_children`, `confluence_search`, `jira_batch_get_changelogs`, `jira_download_attachments`, `jira_get_agile_boards`, `jira_get_board_issues`, `jira_get_issue`, `jira_get_link_types`, `jira_get_project_issues`, `jira_get_project_versions`, `jira_get_sprint_issues`, `jira_get_sprints_from_board`, `jira_get_user_profile`, `jira_get_worklog`, `jira_search`, `jira_search_fields`
- **benign_write** (8): `confluence_add_comment`, `confluence_add_label`, `jira_add_comment`, `jira_add_worklog`, `jira_create_issue_link`, `jira_get_transitions`, `jira_link_to_epic`, `jira_transition_issue`
- **privileged_write** (7): `confluence_create_page`, `confluence_update_page`, `jira_batch_create_issues`, `jira_create_issue`, `jira_create_sprint`, `jira_update_issue`, `jira_update_sprint`
- **destructive_write** (3): `confluence_delete_page`, `jira_delete_issue`, `jira_remove_issue_link`

### `mongodb`
- **read** (13): `aggregate`, `collection-indexes`, `collection-schema`, `collection-storage-size`, `connect`, `count`, `db-stats`, `explain`, `export`, `find`, `list-collections`, `list-databases`, `mongodb-logs`
- **privileged_write** (5): `create-collection`, `create-index`, `insert-many`, `rename-collection`, `update-many`
- **destructive_write** (3): `delete-many`, `drop-collection`, `drop-database`

### `azure`
- **read** (26): `azmcp-appconfig-account-list`, `azmcp-appconfig-kv-list`, `azmcp-appconfig-kv-lock`, `azmcp-appconfig-kv-set`, `azmcp-appconfig-kv-show`, `azmcp-appconfig-kv-unlock`, `azmcp-cosmos-account-list`, `azmcp-cosmos-database-container-item-query`, `azmcp-cosmos-database-container-list`, `azmcp-cosmos-database-list`, `azmcp-extension-az`, `azmcp-extension-azd`, `azmcp-group-list`, `azmcp-monitor-log-query`, `azmcp-monitor-table-list`, `azmcp-monitor-workspace-list`, `azmcp-search-index-describe`, `azmcp-search-index-list`, `azmcp-search-index-query`, `azmcp-search-service-list`, `azmcp-storage-account-list`, `azmcp-storage-blob-container-details`, `azmcp-storage-blob-container-list`, `azmcp-storage-blob-list`, `azmcp-storage-table-list`, `azmcp-subscription-list`
- **destructive_write** (1): `azmcp-appconfig-kv-delete`

### `stripe`
- **read** (10): `finalize_invoice`, `list_coupons`, `list_customers`, `list_invoices`, `list_payment_intents`, `list_prices`, `list_products`, `list_subscriptions`, `retrieve_balance`, `search_stripe_documentation`
- **privileged_write** (10): `create_coupon`, `create_customer`, `create_invoice`, `create_invoice_item`, `create_payment_link`, `create_price`, `create_product`, `list_disputes`, `update_dispute`, `update_subscription`
- **destructive_write** (2): `cancel_subscription`, `create_refund`

### `hummingbot-mcp`
- **read** (9): `explore_controllers`, `get_active_bots_status`, `get_candles`, `get_funding_rate`, `get_order_book`, `get_orders`, `get_portfolio_balances`, `get_positions`, `get_prices`
- **privileged_write** (5): `deploy_bot_with_controllers`, `modify_controllers`, `place_order`, `set_account_position_mode_and_leverage`, `setup_connector`
- **destructive_write** (1): `stop_bot_or_controllers`


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
      - { mcp: "grafana", tools: ["*"], action: "allow", rule_name: "allow_grafana" }
      - { mcp: "mongodb", tools: ["find_documents", "count_documents"], action: "allow", rule_name: "mongo_read" }
      - { mcp: "*", tools: ["*"], action: "deny", rule_name: "default_deny" }
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
      - { source: "resource", attribute: "risk_level",               value: "high", op: "==" }
      - { source: "subject",  attribute: "attributes.clearance_level", value: "L3",  op: "!=" }
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
