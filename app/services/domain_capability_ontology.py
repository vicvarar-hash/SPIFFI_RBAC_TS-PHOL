from typing import List, Dict, Set

# Strong Task Capability Ontology (Iteration 4Q)
# Defines required capability sets for specific intent/domain combinations

DOMAIN_CAPABILITIES = {
    "Hummingbot": {
        "MarketAnalysis": {
            "hard": ["MarketDataAnalysis"],
            "soft": ["ExchangeInteraction", "PriceAnalysis", "TrendAnalysis", "MarketDepthAnalysis"],
            "required": ["MarketDataAnalysis", "ExchangeInteraction"],
            "optional": ["PriceAnalysis", "TrendAnalysis", "MarketDepthAnalysis"]
        },
        "StrategyExecution": {
            "hard": ["StrategyExecution"],
            "soft": ["BalanceCheck", "ExchangeInteraction", "PositionMonitoring"],
            "required": ["OrderCreation", "BalanceCheck", "ExchangeInteraction"],
            "optional": ["PositionMonitoring"]
        }
    },
    "Wikipedia": {
        "InformationDiscovery": {
            "hard": ["KnowledgeSearch"],
            "soft": ["TopicSummarization", "ContentSynthesis", "ContextualSynthesis"],
            "required": ["KnowledgeSearch"],
            "optional": ["TopicSummarization", "ContentSynthesis", "ContextualSynthesis"]
        },
        "ReferenceExploration": {
            "hard": ["KnowledgeSearch"],
            "soft": ["SourceVerification", "ReferenceReview"],
            "required": ["KnowledgeSearch", "SourceVerification"],
            "optional": ["ReferenceReview"]
        }
    },
    "Atlassian": {
        "IssueReview": {
            "hard": ["IssueRead"],
            "soft": ["HistoryReview", "CommentInspection", "IssueCreation"],
            "required": ["IssueRead", "HistoryReview"],
            "optional": ["CommentInspection", "IssueCreation"]
        },
        "TaskManagement": {
            "hard": ["IssueRead", "IssueUpdate"],
            "soft": ["WorkflowTransition", "BacklogPrioritization"],
            "required": ["IssueUpdate", "IssueRead", "WorkflowTransition"],
            "optional": ["BacklogPrioritization"]
        },
        "IssueCreation": {
            "hard": ["IssueCreation"],
            "soft": ["AtlassianWrite"],
            "required": ["IssueCreation", "AtlassianWrite"],
            "optional": []
        }
    },
    "Grafana": {
        "AlertAudit": {
            "hard": ["AlertRuleReview"],
            "soft": ["DatasourceReview", "OncallUserInspection", "VariableReview"],
            "required": ["AlertRuleReview", "DatasourceReview"],
            "optional": ["OncallUserInspection", "VariableReview"]
        },
        "IncidentCorrelation": {
            "hard": ["MetricsQuery"],
            "soft": ["LogAnalysis", "IncidentCorrelation", "DashboardInspection"],
            "required": ["LogAnalysis", "MetricsQuery", "IncidentCorrelation"],
            "optional": ["DashboardInspection"]
        },
        "ObservabilityReview": {
            "hard": ["MetricsQuery"],
            "soft": ["DatasourceReview", "DashboardInspection", "AlertRuleReview", "LogQuery"],
            "required": ["MetricsQuery"],
            "optional": ["DatasourceReview", "DashboardInspection", "AlertRuleReview"]
        }
    },
    "MongoDB": {
        "DataHealth": {
            "hard": ["CollectionScan"],
            "soft": ["IndexReview", "PerformanceAudit"],
            "required": ["CollectionScan", "IndexReview"],
            "optional": ["PerformanceAudit"]
        },
        "SecurityAudit": {
            "hard": ["CollectionScan"],
            "soft": ["QueryAnalysis", "IndexReview"],
            "required": ["UserInspection", "AccessReview"],
            "optional": ["QueryAnalysis"]
        }
    },
    "Stripe": {
        "PaymentProcessing": {
            "hard": ["FinancialWrite"],
            "soft": ["FinancialRead"],
            "required": ["FinancialWrite"],
            "optional": ["FinancialRead"]
        },
        "FinancialReview": {
            "hard": ["FinancialRead"],
            "soft": ["SubscriptionUpdate"],
            "required": ["FinancialRead"],
            "optional": ["SubscriptionUpdate"]
        }
    },
    "Azure": {
        "CloudManagement": {
            "hard": ["CloudResourceRead"],
            "soft": ["CloudResourceWrite", "CloudMonitoring"],
            "required": ["CloudResourceRead"],
            "optional": ["CloudResourceWrite", "CloudMonitoring"]
        },
        "InfrastructureAudit": {
            "hard": ["CloudResourceRead"],
            "soft": ["CloudMonitoring"],
            "required": ["CloudResourceRead"],
            "optional": ["CloudMonitoring"]
        }
    },
    "Notion": {
        "ContentManagement": {
            "hard": ["NotionRead"],
            "soft": ["NotionWrite"],
            "required": ["NotionRead"],
            "optional": ["NotionWrite"]
        },
        "KnowledgeBase": {
            "hard": ["NotionRead"],
            "soft": [],
            "required": ["NotionRead"],
            "optional": []
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
        Returns: {"required": [...], "optional": [], "hard": [...], "soft": [...]}
        """
        req = []
        if domain == "Hummingbot":
            req = ["MarketDataAnalysis"]
        elif domain == "Atlassian":
            req = ["IssueRead"]
        elif domain == "Wikipedia":
            req = ["KnowledgeSearch"]
        elif domain == "Grafana":
            req = ["MetricsQuery"]
        elif domain == "Stripe":
            req = ["FinancialRead"]
        elif domain == "Azure":
            req = ["CloudResourceRead"]
        elif domain == "Notion":
            req = ["NotionRead"]
        elif domain == "MongoDB":
            req = ["CollectionScan"]
        else:
            req = ["GenericRead"]
            
        return {"required": req, "optional": [], "hard": req, "soft": []}

    @staticmethod
    def get_hard_capabilities(domain: str, intent: str) -> Set[str]:
        """
        Returns the set of hard (mission-critical) capabilities for a domain/intent.
        Missing a hard capability = DENY. Missing a soft capability = audit warning.
        """
        domain_intents = DOMAIN_CAPABILITIES.get(domain, {})
        data = domain_intents.get(intent)
        if isinstance(data, dict) and "hard" in data:
            return set(data["hard"])
        # Fallback: if no hard/soft distinction, treat all required as hard
        if isinstance(data, dict):
            return set(data.get("required", []))
        # Domain fallback
        fallback = DomainCapabilityOntology.infer_minimum_capabilities(domain)
        return set(fallback.get("hard", fallback.get("required", [])))

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
        # Atlassian
        "IssueUpdate": ["IssueRead", "IssueReview"],
        "IssueCreation": ["IssueRead", "AtlassianWrite"],
        "IssueSearch": ["IssueRead"],
        "WorkflowTransition": ["IssueRead", "IssueUpdate"],
        "HistoryReview": ["IssueRead"],
        # Hummingbot/Trading
        "StrategyExecution": ["StrategyReview", "MarketDataAnalysis", "BalanceCheck"],
        "OrderCreation": ["MarketDataRetrieval", "ExchangeInteraction"],
        "PlaceOrder": ["StrategyExecution"],
        "CancelOrder": ["StrategyExecution"],
        "MarketDataAnalysis": ["MarketDataRetrieval"],
        # Finance/Stripe
        "FinancialWrite": ["FinancialRead"],
        "SubscriptionUpdate": ["FinancialRead", "FinancialWrite"],
        "UpdateSubscription": ["FinancialRead", "FinancialWrite"],
        # Grafana/Observability
        "ObservabilityRead": ["AlertRuleReview", "DatasourceReview", "MetricsQuery"],
        "LogAnalysis": ["LogQuery"],
        "DashboardInspection": ["DatasourceReview"],
        "IncidentCorrelation": ["AlertRuleReview", "MetricsQuery"],
        "IncidentAnnotation": ["IncidentCorrelation", "InvestigationLookup"],
        "InvestigationLookup": ["AlertRuleReview"],
        "IncidentCreation": ["IncidentCorrelation"],
        "OncallScheduleReview": ["OncallUserInspection"],
        "ProfilingAnalysis": ["MetricsQuery"],
        # Azure/Cloud
        "CloudResourceWrite": ["CloudResourceRead"],
        "CloudMonitoring": ["CloudResourceRead"],
        # Notion
        "NotionWrite": ["NotionRead"],
        # MongoDB
        "QueryAnalysis": ["CollectionScan"],
        "IndexReview": ["CollectionScan"],
        "PerformanceAudit": ["CollectionScan"],
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
