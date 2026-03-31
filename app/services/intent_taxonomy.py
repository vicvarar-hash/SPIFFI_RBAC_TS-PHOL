from enum import Enum
from typing import List, Dict, Any

class Domain(Enum):
    ATLASSIAN = "Atlassian"
    WIKIPEDIA = "Wikipedia"
    GRAFANA = "Grafana"
    NOTION = "Notion"
    STRIPE = "Stripe"
    MONGODB = "MongoDB"
    AZURE = "Azure"
    HUMMINGBOT = "Hummingbot"
    RESEARCH = "Research"
    GENERAL = "General"

class IntentTaxonomy:
    """
    Defines domain-specific intent taxonomies for improved decomposition.
    """
    
    DOMAIN_INTENTS = {
        Domain.ATLASSIAN: {
            "IssueReview": ["get_issue", "view", "details", "read"],
            "HistoryReview": ["changelog", "history", "audit"],
            "IssueCreation": ["create", "new", "ticket"],
            "WorkflowTransition": ["transition", "status", "move", "close", "resolve"],
            "IssueSearch": ["search", "query", "find", "jql"]
        },
        Domain.WIKIPEDIA: {
            "KnowledgeDiscovery": ["search", "find", "explore", "lookup"],
            "TopicSummarization": ["summary", "abstract", "tldr", "overview"],
            "ReferenceExploration": ["related", "links", "references", "citations"],
            "ContentSynthesis": ["combine", "synthesis", "compare", "article"]
        },
        Domain.GRAFANA: {
            "AlertAudit": ["alert", "firing", "history", "silence"],
            "DatasourceReview": ["datasource", "connection", "database", "prometheus"],
            "OncallReview": ["oncall", "schedule", "rotation", "shift"],
            "MetricsInvestigation": ["query", "metrics", "graph", "dashboard"],
            "SystemHealthReview": ["health", "status", "uptime"]
        },
        Domain.NOTION: {
            "PageManagement": ["notion", "page", "block", "content", "database", "edit"],
            "WorkplaceAudit": ["audit", "log", "access", "history"]
        },
        Domain.STRIPE: {
            "FinancialTransactionSearch": ["charge", "payment", "transaction", "refund", "search"],
            "FinancialAudit": ["payout", "balance", "reconciliation", "report"]
        },
        Domain.AZURE: {
            "CloudResourceReview": ["container", "vm", "resource", "subscription", "compute"]
        },
        Domain.RESEARCH: {
            "AcademicSearch": ["paper", "author", "citation", "arxiv", "abstract", "research"]
        },
        Domain.HUMMINGBOT: {
            "BotStrategyReview": ["bot", "strategy", "order", "liquidity", "trading"]
        }
    }

    @staticmethod
    def get_domain_for_mcp(mcp_name: str) -> Domain:
        """
        Infers the domain from the MCP server name.
        Refined in 4H.1 to support all 9 MCPs.
        """
        m_name = mcp_name.lower()
        if "atlassian" in m_name or "jira" in m_name: return Domain.ATLASSIAN
        if "wikipedia" in m_name or "wiki" in m_name: return Domain.WIKIPEDIA
        if "grafana" in m_name or "prometheus" in m_name: return Domain.GRAFANA
        if "notion" in m_name: return Domain.NOTION
        if "stripe" in m_name: return Domain.STRIPE
        if "mongodb" in m_name or "mongo" in m_name: return Domain.MONGODB
        if "azure" in m_name: return Domain.AZURE
        if "hummingbot" in m_name: return Domain.HUMMINGBOT
        if "paper-search" in m_name: return Domain.RESEARCH
        
        return Domain.GENERAL

    @staticmethod
    def get_intents_for_domain(domain: Domain) -> Dict[str, List[str]]:
        """
        Returns the intent keywords for a specific domain.
        """
        return IntentTaxonomy.DOMAIN_INTENTS.get(domain, {})
