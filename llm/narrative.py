"""Turns validated analytics + evidence + persona + confidence + recommendation
into a natural-language narrative.

Input is always: validated analytics + validated evidence + persona +
confidence + recommendations -> narrative.

Never: raw database -> LLM -> "analysis". The LLM only explains numbers
that were already computed deterministically in analytics/ and evidence/.
"""
import pathlib
import yaml
from core.models import InsightPackage
from llm.client import call_llm

ROOT = pathlib.Path(__file__).resolve().parent.parent
with open(ROOT / "config" / "personas.yaml") as f:
    _PERSONAS = yaml.safe_load(f)["personas"]


def _build_prompt(pkg: InsightPackage) -> str:
    conf = pkg.confidence
    attribution = conf.attribution
    detection = attribution.detection
    kpi = detection.kpi
    persona_cfg = _PERSONAS.get(pkg.persona, _PERSONAS["branch_head"])

    driver_lines = []
    for d in attribution.drivers[:3]:
        driver_lines.append(f"- {d.label}: {d.contribution_pct:+.0%} of the movement")
        for sd in d.sub_drivers[:3]:
            driver_lines.append(f"    - {sd.label}: {sd.contribution_pct:.0%}")

    evidence_lines = []
    for e in conf.evidence[:6]:
        evidence_lines.append(f"- [{e.stance}] ({e.source_type}) {e.title}: {e.snippet}")

    rec_line = "None — evidence is too weak/contradictory to recommend an action." \
        if not pkg.recommendation else \
        f"{pkg.recommendation.action} (owner: {pkg.recommendation.owner}, lever: {pkg.recommendation.lever})"

    question_line = f"User question: {pkg.question}\nAnswer the user's question directly before adding context.\n" if pkg.question else ""
    history_lines = "\n".join(
        f"- {item.get('question', '')}: {item.get('answer', '')[:500]}"
        for item in pkg.conversation_history[-4:]
    ) or "- none"

    return f"""You are a banking analytics assistant. Write a short narrative (120-180 words)
for a {persona_cfg['label']} with tone: {persona_cfg['tone']}. Detail level: {persona_cfg['detail_level']}.

Do NOT invent any numbers beyond what is given below. Only explain and contextualize them.
{question_line}
Recent conversation context:
{history_lines}

KPI: {kpi.label}
Month: {kpi.month}
Actual: {kpi.actual:,.2f} ({kpi.unit})
Expected (baseline): {kpi.expected:,.2f}
Change: {kpi.change_pct:+.1%}
Materiality: {detection.materiality_band}
Confidence: {conf.confidence_band} ({conf.confidence_score})
Confidence rationale: {conf.rationale}

Top drivers:
{chr(10).join(driver_lines) if driver_lines else "- none identified"}

Evidence:
{chr(10).join(evidence_lines) if evidence_lines else "- none found"}

Recommended action: {rec_line}

Write the narrative now. If confidence is ABSTAIN or LOW with contradictory
evidence, explicitly say the system is not confident enough to recommend
an action and explain why in plain language."""


def generate_narrative(pkg: InsightPackage) -> dict:
    prompt = _build_prompt(pkg)
    result = call_llm(prompt, stage="llm_narrative", max_tokens=350)
    return result


def generate_chat_response(pkg: InsightPackage, context: dict) -> dict:
    """Answer a user question using only the validated banking context."""
    history = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')[:800]}"
        for item in pkg.conversation_history[-8:]
    ) or "No previous messages."
    prompt = f"""You are a domain-grounded banking performance analyst for a relationship manager.
Answer the user's question directly and specifically. Use only the supplied context.
Do not give generic advice, invent facts, expose restricted customer data, or recalculate metrics.
If the context does not answer the question, say exactly what is missing and ask one focused follow-up.
Explain the distinction between measured fact, evidence-backed hypothesis, and recommendation.
If confidence is LOW or ABSTAIN, clearly state that the cause is not established and do not present it as fact.
Use the user's role and branch scope. Keep the answer concise but useful, with numbers and source names when relevant.

USER QUESTION:
{pkg.question}

RECENT CHAT:
{history}

VALIDATED BANKING CONTEXT (JSON-like):
{context}

Answer the user now. For follow-up questions, refer to the previous conversation and answer the new question rather than repeating the entire KPI summary."""
    return call_llm(prompt, stage="llm_chat", max_tokens=450)


def offline_chat_response(pkg: InsightPackage, context: dict) -> str:
    """Answer common questions from validated context without an LLM."""
    question = (pkg.question or "").lower()
    kpi = context["kpi"]
    detection = context["detection"]
    drivers = context.get("drivers") or []
    evidence = context.get("evidence") or []
    recommendation = context.get("recommendation")
    comparisons = context.get("comparisons") or {}
    scope_comparisons = context.get("scope_comparisons") or {}

    if "branch" in question and any(term in question for term in ("compare", "comparison", "performance", "better")):
        branches = scope_comparisons.get("branches")
        if not branches:
            return "Branch comparison is not available for your role or current scope."
        details = "; ".join(f"{item['id']}: {item['kpi']:,.2f}" for item in branches)
        best = max(branches, key=lambda item: item["kpi"])
        return f"Branch KPI comparison for {kpi['label']}: {details}. {best['id']} is highest for this KPI."

    if ("rm" in question or "manager" in question) and any(term in question for term in ("compare", "comparison", "performance", "better")):
        rms = scope_comparisons.get("rms")
        if not rms:
            return "RM comparison is not available for your role or current scope."
        details = "; ".join(f"{item['id']}: {item['kpi']:,.2f}" for item in rms)
        best = max(rms, key=lambda item: item["kpi"])
        return f"RM KPI comparison for {kpi['label']}: {details}. {best['id']} is highest for this KPI."

    if any(term in question for term in ("why", "driver", "cause", "evidence")):
        driver_text = ", ".join(driver["label"] for driver in drivers[:3]) or "no drivers were identified"
        evidence_text = f" {len(evidence)} scoped evidence item(s) were retrieved."
        if context["confidence"]["band"] in ("LOW", "ABSTAIN"):
            evidence_text += " The confidence is low, so these are hypotheses rather than established causes."
        return f"{kpi['label']} moved {kpi['change_pct']:+.1%} versus baseline. The leading drivers are {driver_text}.{evidence_text}"

    if any(term in question for term in ("action", "next", "recommend", "do")):
        if not recommendation:
            return "No action is recommended until the evidence is reviewed."
        return f"Recommended action: {recommendation['action']} Owner: {recommendation['owner']}."

    if any(term in question for term in ("compare", "comparison", "last year", "quarter", "rolling")):
        return (f"For {kpi['period']}, actual {kpi['actual']:,.2f} is compared with "
                f"same-month-last-year {comparisons.get('same_month_last_year', 'not available')}, "
                f"prior-quarter average {comparisons.get('prior_quarter_average', 'not available')}, "
                f"and rolling-year average {comparisons.get('rolling_year_average', 'not available')}.")

    if any(term in question for term in ("role", "access", "scope", "branch")):
        return (f"You are {context['user']} ({context['role']}) with {context['branch_scope']} scope. "
                "Relationship managers see their own customers, branch heads see all customers in their branch, "
                "and admins can see all branches."
                )

    if any(term in question for term in ("what changed", "movement", "actual", "baseline", "kpi")):
        return (f"{kpi['label']} was {kpi['actual']:,.2f} in {kpi['period']} versus a baseline of "
                f"{kpi['baseline']:,.2f}, a {kpi['change_pct']:+.1%} movement. "
                f"Materiality is {detection['materiality_band']} and confidence is {context['confidence']['band']}.")

    return ("I can answer questions about what changed, drivers, evidence, recommended action, "
            "period comparisons, or your role and data scope. Ask one of those questions about the selected KPI.")


def offline_template_narrative(pkg: InsightPackage) -> str:
    """Non-LLM fallback narrative, built purely from validated fields —
    useful for tests and for the offline demo path."""
    conf = pkg.confidence
    attribution = conf.attribution
    detection = attribution.detection
    kpi = detection.kpi

    top = attribution.drivers[0].label if attribution.drivers else "no clear driver"
    lines = [
        f"{kpi.label} for {kpi.month} came in at {kpi.actual:,.2f} vs an expected "
        f"{kpi.expected:,.2f} ({kpi.change_pct:+.1%}), a {detection.materiality_band}-materiality move.",
        f"The largest contributing factor is {top}.",
        f"Confidence in this attribution is {conf.confidence_band} ({conf.rationale}).",
    ]
    if pkg.recommendation:
        lines.append(f"Recommended next step: {pkg.recommendation.action} (owner: {pkg.recommendation.owner}).")
    else:
        lines.append("No action is recommended until evidence is reviewed by an analyst.")
    return " ".join(lines)
