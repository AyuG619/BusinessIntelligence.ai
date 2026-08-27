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
