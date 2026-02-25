"""
AURORA 1.0 - Lead Company Enrichment via Serper
================================================
After initial AI scoring, enrich_lead_score() fires a Serper web search
and re-weights the lead score using structured company signals.

Flow in POST /api/lead:
    initial_score = await score_lead(lead)
    score, signals = await enrich_lead_score(lead, initial_score)
    # score.score / score.tier may have shifted; score.budget_signals extended

Fail-open: if SERPER_API_KEY is missing or the request fails, the original
LeadScore is returned unchanged with an empty CompanySignals.

Env vars:
    SERPER_API_KEY  - https://serper.dev (free tier: 2,500 searches/month)
"""
import os
import re
import logging
from dataclasses import dataclass, field

import httpx

from models import LeadCreate, LeadScore, LeadTier

logger = logging.getLogger("aurora.enrichment")

SERPER_URL = "https://google.serper.dev/search"
_SERPER_TIMEOUT = 8  # seconds

# ---- Regex patterns --------------------------------------------------------

# 2-200 employees is our ICP sweet-spot
_SMALL_TEAM_RE = re.compile(
    r"\b(\d{1,3})\s*(?:to|[-])\s*(\d{1,3})\s*(?:employees?|staff|people|team members?)\b"
    r"|\b([1-9]|[1-9]\d|1\d{2}|200)\s*(?:employees?|staff|people|team members?)\b",
    re.IGNORECASE,
)

_LARGE_ORG_RE = re.compile(
    r"\b(?:fortune\s*500|fortune\s*1000|enterprise(?:\s+company)?|"
    r"\d{1,3},\d{3}\s*employees?|global\s+corporation)\b",
    re.IGNORECASE,
)

_FUNDING_RE = re.compile(
    r"\b(?:raised|series\s+[a-d]|seed\s+funding|venture\s+capital|"
    r"angel\s+(?:round|funding)|pre[-\s]seed|crunchbase|backed\s+by)\b",
    re.IGNORECASE,
)

_LINKEDIN_RE = re.compile(r"linkedin\.com/company/", re.IGNORECASE)

_STUDENT_RE = re.compile(
    r"\b(?:student|university|college|freelancer|freelance\s+\w+|personal\s+project)\b",
    re.IGNORECASE,
)

# Personal / free email domains — company lookup is noise for these
_FREE_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "protonmail.com", "tutanota.com",
    "aol.com", "me.com",
})

INDUSTRY_TOKENS = [
    "saas", "fintech", "healthtech", "ecommerce", "b2b", "agency",
    "consultancy", "startup", "martech", "proptech", "edtech", "insurtech",
]


# ---- Data model ------------------------------------------------------------

@dataclass
class CompanySignals:
    """Structured signals extracted from Serper search results."""
    found: bool = False
    employee_range: str = ""          # "2-10" | "10-50" | "50-200" | "200+" | "unknown"
    has_funding: bool = False
    has_linkedin: bool = False
    is_large_enterprise: bool = False
    is_student_or_freelancer: bool = False
    industry_signals: list[str] = field(default_factory=list)
    raw_snippets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "employee_range": self.employee_range,
            "has_funding": self.has_funding,
            "has_linkedin": self.has_linkedin,
            "is_large_enterprise": self.is_large_enterprise,
            "is_student_or_freelancer": self.is_student_or_freelancer,
            "industry_signals": self.industry_signals,
        }


# ---- Serper search ---------------------------------------------------------

async def company_lookup(
    company: str,
    email_domain: str = "",
) -> CompanySignals:
    """
    POST to Serper's search API for '{company} {domain} employees funding'.

    Parses organic results + knowledge graph + answer box for ICP signals.
    Returns CompanySignals(found=False) silently on any error.
    """
    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if not api_key:
        logger.debug("SERPER_API_KEY not set - skipping company enrichment")
        return CompanySignals()

    company = (company or "").strip()
    if not company or company.lower() in ("n/a", "none", "unknown", "not provided"):
        logger.debug("No company name to look up")
        return CompanySignals()

    # Build search query
    query_parts = [company]
    if email_domain and email_domain not in _FREE_DOMAINS:
        query_parts.append(email_domain)
    query_parts.append("company employees funding")
    query = " ".join(query_parts)

    logger.debug("Serper lookup: %r", query)

    try:
        async with httpx.AsyncClient(timeout=_SERPER_TIMEOUT) as client:
            resp = await client.post(
                SERPER_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": 5},
            )
        if resp.status_code != 200:
            logger.warning("Serper HTTP %d for company=%r", resp.status_code, company)
            return CompanySignals()
        data = resp.json()
    except Exception as exc:
        logger.warning("Serper request failed for company=%r: %s", company, exc)
        return CompanySignals()

    return _parse_serper_response(data)


def _parse_serper_response(data: dict) -> CompanySignals:
    """Extract ICP signals from a Serper response dict."""
    signals = CompanySignals(found=True)
    snippets: list[str] = []
    result_links: list[str] = []

    # Organic results
    for item in data.get("organic", []):
        result_links.append(item.get("link", ""))
        for key in ("title", "snippet"):
            if isinstance(item.get(key), str):
                snippets.append(item[key])
        for sl in item.get("sitelinks", []) if isinstance(item.get("sitelinks"), list) else []:
            if isinstance(sl, dict):
                snippets.append(f"{sl.get('title', '')} {sl.get('snippet', '')}")

    # Knowledge graph
    kg = data.get("knowledgeGraph", {})
    for key in ("title", "type", "description"):
        if isinstance(kg.get(key), str):
            snippets.append(kg[key])
    for attr_val in kg.get("attributes", {}).values():
        if isinstance(attr_val, str):
            snippets.append(attr_val)

    # Answer box
    ab = data.get("answerBox", {})
    for key in ("title", "answer", "snippet"):
        if isinstance(ab.get(key), str):
            snippets.append(ab[key])

    signals.raw_snippets = snippets[:10]
    combined = " ".join(snippets)

    # LinkedIn company page
    signals.has_linkedin = any(_LINKEDIN_RE.search(link) for link in result_links)

    # Enterprise / large org (check first — overrides small team RE)
    if _LARGE_ORG_RE.search(combined):
        signals.is_large_enterprise = True
        signals.employee_range = "200+"
    else:
        m = _SMALL_TEAM_RE.search(combined)
        if m:
            # Extract any matched number group
            groups = [g for g in m.groups() if g is not None]
            emp_count = int(groups[0]) if groups else 0
            if emp_count <= 10:
                signals.employee_range = "2-10"
            elif emp_count <= 50:
                signals.employee_range = "10-50"
            elif emp_count <= 200:
                signals.employee_range = "50-200"
            else:
                signals.employee_range = "200+"
                signals.is_large_enterprise = True
        else:
            signals.employee_range = "unknown"

    signals.has_funding = bool(_FUNDING_RE.search(combined))
    signals.is_student_or_freelancer = bool(_STUDENT_RE.search(combined))
    signals.industry_signals = [t for t in INDUSTRY_TOKENS if t in combined.lower()]

    return signals


# ---- Score adjustment ------------------------------------------------------

# Score delta rules applied cumulatively
_DELTA_RULES: list[tuple[str, int]] = [
    # (signal description for budget_signals, delta)
    ("startup with funding signals",             +10),
    ("verified LinkedIn company page",           +7),
    ("ICP-sized team (10-50 employees)",         +8),   # applied conditionally below
    ("ICP-sized team (50-200 employees)",        +8),   # applied conditionally below
    ("small team (2-10 employees)",              +3),   # applied conditionally below
    ("large enterprise - outside ICP",           -8),
    ("student/freelancer signals - not a buyer", -12),
    ("company not found via search",             -5),
]


def _adjust_score(score: LeadScore, signals: CompanySignals) -> LeadScore:
    """
    Re-weight the initial AI score using Serper company signals.

    Delta rules (cumulative, bounded to 0-100):
        +10  funded startup
        + 7  has LinkedIn company page
        + 8  employee count in ICP sweet-spot (10-200)
        + 3  very small team (2-10) — in ICP but less certain
        - 8  large enterprise / Fortune 500
        -12  student or freelancer signals
        - 5  company not found at all (confidence penalty)
    """
    delta = 0
    extra_signals: list[str] = []

    if not signals.found:
        delta -= 5
        extra_signals.append("company not found via search - scored on form data only")
    else:
        if signals.has_funding:
            delta += 10
            extra_signals.append("startup with funding signals")

        if signals.has_linkedin:
            delta += 7
            extra_signals.append("verified LinkedIn company page")

        if signals.employee_range in ("10-50", "50-200"):
            delta += 8
            extra_signals.append(f"ICP-sized team ({signals.employee_range} employees)")
        elif signals.employee_range == "2-10":
            delta += 3
            extra_signals.append("small team (2-10 employees)")
        elif signals.is_large_enterprise:
            delta -= 8
            extra_signals.append("large enterprise - outside ICP size")

        if signals.is_student_or_freelancer:
            delta -= 12
            extra_signals.append("student/freelancer signals - likely not a buyer")

    new_score = max(0, min(100, score.score + delta))

    # Re-tier if the delta crossed a boundary
    if new_score >= 80:
        new_tier = LeadTier.HIGH
        new_delay = 5
    elif new_score >= 50:
        new_tier = LeadTier.MEDIUM
        new_delay = 15
    else:
        new_tier = LeadTier.LOW
        new_delay = 60

    icp_fit = score.icp_fit and not signals.is_student_or_freelancer

    if delta != 0:
        logger.info(
            "Enrichment delta %+d: %d->%d (%s->%s) signals=%s",
            delta, score.score, new_score,
            score.tier.value, new_tier.value,
            extra_signals,
        )

    return LeadScore(
        score=new_score,
        tier=new_tier,
        reasoning=score.reasoning,
        icp_fit=icp_fit,
        urgency=score.urgency,
        budget_signals=list(score.budget_signals) + extra_signals,
        recommended_delay_minutes=new_delay,
    )


# ---- Public entry point ----------------------------------------------------

async def enrich_lead_score(
    lead: LeadCreate,
    score: LeadScore,
) -> tuple[LeadScore, CompanySignals]:
    """
    Main enrichment entry point.  Called from POST /api/lead after score_lead().

    Args:
        lead:   The inbound lead from the landing page form.
        score:  The initial LeadScore returned by score_lead().

    Returns:
        (enriched_score, signals) tuple.
        On any failure, returns the original score unchanged + empty signals
        (fail-open — identical to score_lead behaviour).
    """
    try:
        email_domain = lead.email.split("@")[-1] if "@" in lead.email else ""
        signals = await company_lookup(
            company=lead.company or "",
            email_domain=email_domain,
        )
        enriched = _adjust_score(score, signals)
        return enriched, signals

    except Exception as exc:
        logger.error("enrich_lead_score failed for %s: %s", lead.email, exc)
        return score, CompanySignals()
