from typing import List, Dict, Set

# Strong Task Capability Ontology (Iteration 4Q)
# Defines required capability sets for specific intent/domain combinations

DOMAIN_CAPABILITIES = {
    "Hummingbot": {
        "MarketAnalysis": {
            "required": ["MarketDataRetrieval", "ExchangeInteraction"],
            "optional": ["PriceAnalysis", "TrendAnalysis", "MarketDepthAnalysis"]
        },
        "StrategyExecution": {
            "required": ["OrderCreation", "BalanceCheck", "ExchangeInteraction"],
            "optional": ["PositionMonitoring"]
        }
    },
    "Wikipedia": {
        "InformationDiscovery": {
            "required": ["KnowledgeSearch"],
            "optional": ["TopicSummarization", "ContentSynthesis", "ContextualSynthesis"]
        },
        "ReferenceExploration": {
            "required": ["KnowledgeSearch", "SourceVerification"],
            "optional": ["ReferenceReview"]
        }
    },
    "Atlassian": {
        "IssueReview": {
            "required": ["IssueRead", "HistoryReview"],
            "optional": ["CommentInspection", "IssueCreation"]
        },
        "TaskManagement": {
            "required": ["IssueUpdate", "IssueRead", "WorkflowTransition"],
            "optional": ["BacklogPrioritization"]
        },
        "IssueCreation": {
            "required": ["IssueCreation", "AtlassianWrite"],
            "optional": []
        }
    },
    "Grafana": {
        "AlertAudit": {
            "required": ["AlertRuleReview", "DatasourceReview"],
            "optional": ["OncallUserInspection", "VariableReview"]
        },
        "IncidentCorrelation": {
            "required": ["LogAnalysis", "MetricsQuery", "IncidentCorrelation"],
            "optional": ["DashboardInspection"]
        }
    },
    "MongoDB": {
        "DataHealth": {
            "required": ["CollectionScan", "IndexReview"],
            "optional": ["PerformanceAudit"]
        },
        "SecurityAudit": {
            "required": ["UserInspection", "AccessReview"],
            "optional": ["QueryAnalysis"]
        }
    }
}

class DomainCapabilityOntology:
    @staticmethod
    def get_capabilities_for_intent(domain: str, intent: str) -> Dict[str, List[str]]:
        """
        Retrieves the standard capability set for a given domain and intent.
        Returns: {"required": [...], "optional": [...]}
        """
        domain_intents = DOMAIN_CAPABILITIES.get(domain, {})
        data = domain_intents.get(intent)
        if isinstance(data, dict):
            return data
        return {"required": [], "optional": []}

    @staticmethod
    def infer_minimum_capabilities(domain: str) -> Dict[str, List[str]]:
        """
        Fallback mechanism for unknown intents within a known domain.
        Returns: {"required": [...], "optional": [...]}
        """
        req = []
        if domain == "Hummingbot":
            req = ["StrategyReview", "MarketDataAnalysis"]
        elif domain == "Atlassian":
            req = ["IssueRead"]
        elif domain == "Wikipedia":
            req = ["KnowledgeSearch"]
        elif domain == "Grafana":
            req = ["MetricsQuery", "AlertRuleReview"]
        else:
            req = ["GenericRead"] # Universal fallback
            
        return {"required": req, "optional": []}

    # 4T: Canonical set of abstract/grouping capabilities to hide from UI
    # 6C Refinement: Ensure tool-level capabilities like MarketDataAnalysis stay visible
    ABSTRACT_CAPABILITIES = {
        "AtlassianRead", "AtlassianWrite", 
        "ObservabilityRead", "ObservabilityWrite",
        "GenericRead", "GenericWrite",
        "FinanceRead", "FinanceWrite", 
        "DevOpsRead", "DevOpsWrite",
        "EquityRead", "EquityWrite",
        "HummingbotRead", "HummingbotWrite",
        "InformationDiscovery", "ReferenceExploration",
        "AlertAudit", "IncidentCorrelation",
        "DataHealth", "SecurityAudit",
        "IssueReview", "TaskManagement"
    }

    CAPABILITY_IMPLICATIONS = {
        "IssueUpdate": ["IssueRead", "IssueReview"],
        "IssueCreation": ["IssueRead", "AtlassianWrite"],
        "StrategyExecution": ["StrategyReview", "MarketDataAnalysis", "BalanceCheck"],
        "OrderCreation": ["MarketDataRetrieval", "ExchangeInteraction"],
        "PlaceOrder": ["StrategyExecution"],
        "CancelOrder": ["StrategyExecution"],
        "UpdateSubscription": ["FinancialRead", "FinancialWrite"],
        "IncidentAnnotation": ["IncidentCorrelation", "InvestigationLookup"]
    }

    @staticmethod
    def expand_capabilities(caps: Set[str]) -> Set[str]:
        """
        Performs Capability Subsumption:
        Computes the complete semantic closure of capabilities based on hierarchical implication rules.
        """
        expanded = set(caps)
        # Simple iterative transitive closure (in case of nested implications)
        changed = True
        while changed:
            changed = False
            for cap in list(expanded):
                for implied in DomainCapabilityOntology.CAPABILITY_IMPLICATIONS.get(cap, []):
                    if implied not in expanded:
                        expanded.add(implied)
                        changed = True
        return expanded

    @staticmethod
    def is_concrete(capability: str) -> bool:
        """
        Filters for visible concrete capabilities (excludes groupings).
        """
        return capability not in DomainCapabilityOntology.ABSTRACT_CAPABILITIES
