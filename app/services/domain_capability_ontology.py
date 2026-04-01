from typing import List, Dict, Set

# Strong Task Capability Ontology (Iteration 4Q)
# Defines required capability sets for specific intent/domain combinations

DOMAIN_CAPABILITIES = {
    "Hummingbot": {
        "MarketAnalysis": [
            "MarketDataRetrieval",
            "PriceAnalysis",
            "TrendAnalysis",
            "ExchangeInteraction"
        ],
        "StrategyExecution": [
            "OrderCreation",
            "BalanceCheck",
            "ExchangeInteraction"
        ]
    },
    "Wikipedia": {
        "InformationDiscovery": [
            "KnowledgeSearch",
            "TopicSummarization",
            "ContentSynthesis"
        ],
        "ReferenceExploration": [
            "SourceVerification",
            "KnowledgeSearch"
        ]
    },
    "Atlassian": {
        "IssueReview": [
            "IssueRead",
            "HistoryReview",
            "IssueCreation"
        ],
        "TaskManagement": [
            "IssueUpdate",
            "IssueRead",
            "WorkflowTransition"
        ],
        "IssueCreation": [
            "IssueCreation",
            "AtlassianWrite"
        ]
    },
    "Grafana": {
        "AlertAudit": [
            "AlertRuleReview",
            "DatasourceReview",
            "OncallUserInspection"
        ],
        "IncidentCorrelation": [
            "LogAnalysis",
            "MetricsQuery",
            "IncidentCorrelation"
        ]
    }
}

class DomainCapabilityOntology:
    @staticmethod
    def get_capabilities_for_intent(domain: str, intent: str) -> List[str]:
        """
        Retrieves the standard capability set for a given domain and intent.
        """
        domain_intents = DOMAIN_CAPABILITIES.get(domain, {})
        return domain_intents.get(intent, [])

    @staticmethod
    def infer_minimum_capabilities(domain: str) -> List[str]:
        """
        Fallback mechanism for unknown intents within a known domain.
        Returns a baseline capability set to ensure RequiredCapabilities is non-empty.
        """
        if domain == "Hummingbot":
            return ["StrategyReview", "MarketDataAnalysis"]
        if domain == "Atlassian":
            return ["IssueRead"]
        if domain == "Wikipedia":
            return ["KnowledgeSearch"]
        if domain == "Grafana":
            return ["MetricsQuery", "AlertRuleReview"]
        
        return ["GenericRead"] # Universal fallback

    # 4T: Canonical set of abstract/grouping capabilities to hide from UI
    ABSTRACT_CAPABILITIES = {
        "AtlassianRead", "AtlassianWrite", 
        "ObservabilityRead", "ObservabilityWrite",
        "GenericRead", "GenericWrite",
        "FinanceRead", "FinanceWrite", 
        "DevOpsRead", "DevOpsWrite",
        "EquityRead", "EquityWrite",
        "MarketAnalysis", "StrategyExecution",
        "InformationDiscovery", "ReferenceExploration",
        "AlertAudit", "IncidentCorrelation"
    }

    @staticmethod
    def is_concrete(capability: str) -> bool:
        """
        Filters for visible concrete capabilities (excludes groupings).
        """
        return capability not in DomainCapabilityOntology.ABSTRACT_CAPABILITIES
