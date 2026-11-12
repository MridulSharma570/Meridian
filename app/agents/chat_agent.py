"""Agent 4 — Chat: grounded follow-up Q&A over an existing report."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from app.agents.base import BaseAgent, compact
from app.api import answer_policy
from app.api.llm_router import call_llm, effective_slot, is_configured
from app.config import settings
from app.database import queries


class ChatAgent(BaseAgent):
    name = "chat"
    slot = "chat"
    icon = "💬"
    description = "Answers follow-up questions using the gathered research context"

    SUGGESTIONS = [
        "What about the rural / tier-2 market?",
        "Compare the top two competitors in more detail",
        "What are the biggest risks to the forecast?",
        "Which sources support the market size estimate?",
        "Summarise the SWOT in three bullets",
        "What should we do in the next 90 days?",
    ]

    def local_run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        q = ctx.get("question", "")
        # Sample mode only: ChatAgent.answer() is the production entry point and
        # refuses to use this template when no provider API is configured.
        return {"answer": self._local_answer(ctx, q), "suggestions": self.SUGGESTIONS}

    def llm_prompt(self, ctx: Dict[str, Any]) -> str:
        return ""

    def _local_answer(self, ctx: Dict[str, Any], question: str) -> str:
        d = ctx.get("dataset", {})
        r = ctx.get("researcher", {})
        a = ctx.get("analyst", {})
        f = ctx.get("forecast", {})
        fc = ctx.get("factcheck", {})
        w = ctx.get("writer", {})
        company = d.get("company", "the subject")
        ql = question.lower().strip()
        src = r.get("sources") or d.get("sources", [])
        ref = " ".join(f"[{s['id']}]" for s in src[:2])

        if any(k in ql for k in ("rural", "tier-2", "tier 2", "tier-3", "village", "bharat")):
            return (
                f"**Rural / tier-2 opportunity.** Our segmentation model allocates "
                f"{d['segments'][2]['value']:.1f}% of demand to SMB and "
                f"{d['segments'][3]['value']:.1f}% to consumer cohorts — the pools most "
                "exposed to tier-2 and rural distribution. Digitisation is the enabling "
                f"variable: digital penetration in {d.get('region','the region')} is modelled at "
                f"{d['macro'].get('Digital Penetration (%)', 0):.0f}%. Practical playbook: "
                "(1) hub-and-spoke distribution with regional partners, (2) vernacular and "
                "assisted onboarding, (3) bundled financing at lower ticket sizes, and "
                "(4) service reliability over feature breadth. **Caveat:** the current dataset "
                "does not disaggregate urban vs rural, so treat these as directional shares "
                f"and validate with primary field data. {ref}"
            )
        if any(k in ql for k in ("compare", "versus", " vs ", "competitor", "rival")):
            cs = d.get("competitors", [])[:3]
            lines = [f"- **{c['name']}** — {c['share']:.1f}% share, "
                     f"${c['revenue_usd_b']:.1f}B est. revenue, {c['growth_pct']:+.1f}% growth, "
                     f"sentiment {c['sentiment']*100:.0f}/100" for c in cs]
            return ("**Head-to-head (top 3 tracked players).**\n\n" + "\n".join(lines) +
                    f"\n\nThe leader's advantage is distribution breadth rather than price; "
                    f"rivalry intensity scores {a.get('porter', [{}])[0].get('intensity', 4)}/5 "
                    f"in the Porter analysis. {ref}")
        if any(k in ql for k in ("risk", "threat", "downside", "worry", "concern")):
            risks = d.get("risk_events", [])
            return ("**Principal risks.**\n\n" + "\n".join(
                f"- {x['event']} — {x['probability']*100:.0f}% likelihood, {x['impact']} impact"
                for x in risks) +
                f"\n\nThe 12-month pessimistic scenario lands at "
                f"${f.get('pessimistic_end', 0):.1f}B "
                f"({f.get('downside_pct', 0):.1f}% below base). Reliability is scored "
                f"{fc.get('reliability_score', 0)}/100 with "
                f"{fc.get('flagged_count', 0)} flagged claim(s). {ref}")
        if any(k in ql for k in ("source", "citation", "evidence", "prove", "verify")):
            return ("**Evidence base.** " + f"{len(src)} sources were collected. The five "
                    "highest-reliability references are:\n\n" + "\n".join(
                        f"- [{s['id']}] {s['publisher']} — {s['title']} "
                        f"({s['reliability']}/100)" for s in
                        sorted(src, key=lambda x: x.get("reliability", 0), reverse=True)[:5]) +
                    f"\n\nVerification method: {fc.get('method','')} {fc.get('disclaimer','')}")
        if any(k in ql for k in ("swot", "strength", "weakness", "pestle", "porter")):
            sw = a.get("swot", {})
            return ("**Strategic snapshot.**\n\n" + "\n".join(
                f"- **{k}:** {v[0]}" for k, v in sw.items()) +
                "\n\nFull tables are in sections 5–7 of the report.")
        if any(k in ql for k in ("90 day", "next step", "recommend", "should we", "action", "do now")):
            recs = w.get("recommendations") or a.get("strategic_priorities") or []
            base = [
                "Lock pricing guardrails and measure share weekly",
                "Launch a mid-market pilot with two measurable conversion targets",
                "Dual-source the top three cost inputs",
                "Re-run this Meridian report at the end of the quarter",
            ]
            chosen = [str(x) for x in recs[:3]] if recs else base
            return ("**Next 90 days.**\n\n" + "\n".join(
                f"{i+1}. {x}" for i, x in enumerate(chosen)) +
                "\n\nEach item has an owner-ready output and can be tracked in the dashboard.")
        if any(k in ql for k in ("forecast", "predict", "future", "growth", "projection")):
            return (f"**12-month outlook.** Base case reaches "
                    f"${f.get('base_end', 0):.1f}B ({f.get('expected_growth_pct', 0):+.1f}%), "
                    f"with an optimistic band at ${f.get('optimistic_end', 0):.1f}B and a "
                    f"pessimistic floor of ${f.get('pessimistic_end', 0):.1f}B. "
                    f"Method: {f.get('method','')}. {f.get('note','')}")
        if any(k in ql for k in ("market size", "how big", "tam", "sam", "som")):
            s = a.get("sizing", {})
            return (f"**Sizing.** TAM ${s.get('TAM (USD B)',0):.1f}B · "
                    f"SAM ${s.get('SAM (USD B)',0):.1f}B · "
                    f"SOM ${s.get('SOM (USD B)',0):.1f}B · "
                    f"current market ${d.get('market_size_usd_b',0):.1f}B at "
                    f"{d.get('cagr_pct',0):.1f}% CAGR. {ref}")
        if any(k in ql for k in ("hello", "hi ", "hey", "help", "what can you")):
            return ("I'm Meridian's Chat Agent. I answer questions grounded in **this report** — "
                    "market sizing, competitors, risks, forecast bands, sources and next steps. "
                    "Try one of the suggested prompts below.")
        return (
            f"**On “{question.strip()}”.** Within the scope of this report on "
            f"**{company}** ({d.get('sector','')}, {d.get('region','Global')}), the most "
            f"relevant evidence is: {a.get('summary','')} "
            f"The model currently tracks {len(d.get('competitors', []))} competitors, "
            f"{len(src)} sources and a {d.get('cagr_pct',0):.1f}% CAGR. "
            f"For a deeper cut, ask about a specific segment, competitor, risk or time horizon. {ref}"
        )

    def answer(self, ctx: Dict[str, Any], question: str, report_id: str = "") -> Dict[str, Any]:
        """Grounded answer. In verified mode the LLM is the ONLY answer source."""
        ctx = dict(ctx)
        ctx["question"] = question
        answer = ""
        provider, model = "Meridian Local Engine", "grounded-context-v1"

        if answer_policy.strict_mode():
            answer_policy.require_api("chat answer")
            sources = (ctx.get("dataset", {}) or {}).get("verified_sources") or []
            prompt = (
                "You are Meridian's follow-up analyst. Answer the QUESTION using "
                "ONLY the REPORT CONTEXT and VERIFIED SOURCES supplied. Cite real "
                "source ids like [L01] where they genuinely apply. Never invent a "
                "figure, publisher, URL or citation. If the context cannot answer "
                "the question, say exactly what is missing instead of guessing. "
                "Chart series in the context are unverified placeholders: never "
                "quote their numbers as measurements. Max 180 words.\n\n"
                f"QUESTION: {question}\n\n"
                "VERIFIED SOURCES:\n" + compact(sources, 3000) + "\n\n"
                "REPORT CONTEXT:\n" + compact({
                    "query": ctx.get("query"),
                    "company": (ctx.get("dataset", {}) or {}).get("company"),
                    "region": ctx.get("region"),
                    "analyst_summary": (ctx.get("analyst", {}) or {}).get("summary"),
                    "writer_markdown": ((ctx.get("writer", {}) or {}).get("markdown")
                                        or "")[:3500],
                }, 5200)
            )
            try:
                res = call_llm(effective_slot("chat"),
                               "You are a precise, evidence-bound research analyst.",
                               prompt, max_tokens=420, temperature=0.3,
                               timeout=settings.agent_timeout_s)
            except Exception as exc:
                raise answer_policy.AnswerUnavailable(
                    f"The configured provider could not answer this question: {exc}",
                    "Check the key, model and quota in Settings → API Keys.",
                    "provider_failed") from exc
            answer = (res.get("text") or "").strip()
            if len(answer) < 20:
                raise answer_policy.AnswerUnavailable(
                    "The provider returned an empty chat answer; Meridian will "
                    "not substitute a canned template.",
                    "Try again or pick a different model in Settings → API Keys.",
                    "unusable_output")
            allowed = {str(x.get("id")) for x in sources if isinstance(x, dict)}
            answer = re.sub(r"\[([A-Z]\d{2})\]",
                            lambda m: m.group(0) if m.group(1) in allowed else "[unverified]",
                            answer)
            provider, model = res["provider"], res["model"]
        else:
            answer = self._local_answer(ctx, question)
            if is_configured("chat"):
                try:
                    prompt = (
                        "You are Meridian's follow-up analyst. Answer using ONLY the supplied "
                        "report context. Be specific, cite reference ids like [S01] where relevant, "
                        "and say so if the context cannot answer. Max 180 words.\n\n"
                        f"QUESTION: {question}\n\nCONTEXT:\n" + compact({
                            "dataset": {k: ctx.get("dataset", {}).get(k) for k in
                                        ("company", "sector", "region", "market_size_usd_b",
                                         "cagr_pct", "competitors", "segments", "macro",
                                         "sentiment", "risk_events")},
                            "analyst_summary": ctx.get("analyst", {}).get("summary"),
                            "forecast": {k: ctx.get("forecast", {}).get(k) for k in
                                         ("base_end", "optimistic_end", "pessimistic_end",
                                          "expected_growth_pct")},
                            "sources": ctx.get("researcher", {}).get("sources", [])[:8],
                            "local_draft": answer,
                        }, 5200)
                    )
                    res = call_llm("chat", "You are a precise, evidence-bound research analyst.",
                                   prompt, max_tokens=420, temperature=0.35,
                                   timeout=settings.agent_timeout_s)
                    if len(res["text"]) > 40:
                        answer, provider, model = res["text"], res["provider"], res["model"]
                except Exception:
                    pass  # sample mode only

        if report_id:
            queries.add_chat_message(report_id, "user", question)
            queries.add_chat_message(report_id, "assistant", answer)
        return {"answer": answer, "provider": provider, "model": model,
                "suggestions": self.SUGGESTIONS}
