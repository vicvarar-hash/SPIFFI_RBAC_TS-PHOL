from enum import Enum
from typing import Optional
from app.services.normalization import normalize_domain_name

class CanonicalDomain(str, Enum):
    UNKNOWN = "uncertain"
    MULTI_DOMAIN = "multi_domain"
    
def resolve_domain(raw_domain: Optional[str]) -> str:
    """
    Standardizes raw domain strings into a consistent canonical space.
    If it's an expected or actual domain, ensures it maps cleanly to
    either the raw normalized string or the fallback CanonicalDomains.
    """
    if not raw_domain:
        return CanonicalDomain.UNKNOWN.value
        
    normalized = normalize_domain_name(raw_domain)
    if normalized in ["unknown", "uncertain"]:
        return CanonicalDomain.UNKNOWN.value
    if normalized in ["multi-domain", "multi_domain"]:
        return CanonicalDomain.MULTI_DOMAIN.value
        
    return normalized
