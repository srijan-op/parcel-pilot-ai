from __future__ import annotations

import json
from typing import Any


def _parse_json_blob(text: str) -> dict[str, Any] | list[Any] | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _collect_tool_payloads(tools_used: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize tools_used entries into {tool, args, payload}."""
    collected: list[dict[str, Any]] = []
    for item in tools_used:
        preview = item.get("result_preview")
        payload = _parse_json_blob(preview) if isinstance(preview, str) else preview
        collected.append(
            {
                "tool": item.get("tool"),
                "args": item.get("args") or {},
                "payload": payload,
            }
        )
    return collected


def _calc_data(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    # Some paths may return calculator dict at top level
    if "fee_inr" in payload or "eligible" in payload or "breached" in payload:
        return payload
    return None


def synthesize_trust(
    *,
    answer: str,
    tools_used: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Post-agent trust synthesis: confidence, conflicts, citations, flags.
    Deterministic — does not call the LLM.
    """
    calls = _collect_tool_payloads(tools_used)
    conflicts: list[dict[str, str]] = []
    citations: list[dict[str, Any]] = []
    flags: list[str] = []
    facts: dict[str, Any] = {}

    used_calc = False
    used_search = False
    used_lookup = False
    access_denied = False
    abstain = False
    needs_manager_approval = False
    recommend_escalation = False
    needs_confirmation = False
    agreement_override = False

    for call in calls:
        tool = call["tool"]
        args = call.get("args") or {}
        raw_payload = call.get("payload")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}

        if isinstance(raw_payload, dict) and raw_payload.get("error") == "access_denied":
            access_denied = True
            flags.append("access_denied")

        if tool == "document_search":
            used_search = True
            for chunk in payload.get("chunks") or []:
                if not isinstance(chunk, dict):
                    continue
                citations.append(
                    {
                        "type": "document",
                        "id": chunk.get("doc_id") or chunk.get("filename"),
                        "title": chunk.get("title"),
                        "status": chunk.get("status"),
                        "authority_rank": chunk.get("authority_rank"),
                        "section": chunk.get("section_title") or chunk.get("section_path"),
                    }
                )
                if str(chunk.get("status", "")).upper() == "DEPRECATED":
                    conflicts.append(
                        {
                            "claim": "policy_version",
                            "winner": "current_or_agreement",
                            "detail": (
                                f"Deprecated source retrieved ({chunk.get('doc_id')}); "
                                "do not use for current answers."
                            ),
                        }
                    )
                    flags.append("deprecated_source_seen")

        if tool == "structured_data_query":
            # Read intent from args even when result_preview failed to parse
            intent = payload.get("intent") or args.get("intent")
            data = _calc_data(payload) if payload else None
            if intent and str(intent).startswith("calc_"):
                used_calc = True
            elif intent:
                used_lookup = True
            elif args:
                # Tool ran but intent unknown — still counts as grounded lookup
                used_lookup = True

            if data:
                if "fee_inr" in data or "allowed" in data:
                    facts["cancellation"] = {
                        "allowed": data.get("allowed"),
                        "fee_inr": data.get("fee_inr"),
                        "sop_would_charge_inr": data.get("sop_would_charge_inr"),
                        "agreement_override": data.get("agreement_override"),
                    }
                    if data.get("agreement_override") and data.get("sop_would_charge_inr") not in (
                        None,
                        data.get("fee_inr"),
                    ):
                        agreement_override = True
                        conflicts.append(
                            {
                                "claim": "cancellation_fee",
                                "winner": "agreement",
                                "detail": (
                                    f"Agreement fee INR {data.get('fee_inr')}; "
                                    f"SOP would charge INR {data.get('sop_would_charge_inr')}."
                                ),
                            }
                        )
                    for src in data.get("sources") or []:
                        if isinstance(src, dict):
                            citations.append(
                                {
                                    "type": src.get("type") or "source",
                                    "id": src.get("id"),
                                    "note": src.get("note"),
                                }
                            )

                if "eligible" in data or "amount_inr" in data:
                    facts["service_credit"] = {
                        "eligible": data.get("eligible"),
                        "amount_inr": data.get("amount_inr"),
                        "sop_would_amount_inr": data.get("sop_would_amount_inr"),
                        "agreement_override": data.get("agreement_override"),
                        "abstain": data.get("abstain"),
                        "needs_manager_approval": data.get("needs_manager_approval"),
                    }
                    if data.get("abstain"):
                        abstain = True
                        flags.append("abstain_credit")
                    if data.get("needs_manager_approval"):
                        needs_manager_approval = True
                        flags.append("manager_approval_required")
                    if data.get("agreement_override") and data.get("sop_would_amount_inr") not in (
                        None,
                        data.get("amount_inr"),
                    ):
                        agreement_override = True
                        conflicts.append(
                            {
                                "claim": "service_credit",
                                "winner": "agreement",
                                "detail": (
                                    f"Agreement credit INR {data.get('amount_inr')}; "
                                    f"SOP would suggest INR {data.get('sop_would_amount_inr')}."
                                ),
                            }
                        )
                    for src in data.get("sources") or []:
                        if isinstance(src, dict):
                            citations.append(
                                {
                                    "type": src.get("type") or "source",
                                    "id": src.get("id"),
                                    "note": src.get("note"),
                                }
                            )

                if "breached" in data or "target_minutes" in data:
                    facts["sla"] = {
                        "severity": data.get("severity"),
                        "target_minutes": data.get("target_minutes"),
                        "elapsed_minutes": data.get("elapsed_minutes"),
                        "breached": data.get("breached"),
                        "agreement_override": data.get("agreement_override"),
                        "policy_default_minutes": data.get("policy_default_minutes"),
                        "recommend_escalation": data.get("recommend_escalation"),
                    }
                    if data.get("recommend_escalation") or data.get("breached"):
                        recommend_escalation = True
                        flags.append("recommend_escalation")
                    if (
                        data.get("agreement_override")
                        and data.get("policy_default_minutes")
                        and data.get("target_minutes") != data.get("policy_default_minutes")
                    ):
                        agreement_override = True
                        conflicts.append(
                            {
                                "claim": "sla_target",
                                "winner": "agreement",
                                "detail": (
                                    f"Agreement target {data.get('target_minutes')} min; "
                                    f"policy default {data.get('policy_default_minutes')} min."
                                ),
                            }
                        )
                    for src in data.get("sources") or []:
                        if isinstance(src, dict):
                            citations.append(
                                {
                                    "type": src.get("type") or "source",
                                    "id": src.get("id"),
                                    "note": src.get("note"),
                                }
                            )

            if intent in ("get_order", "get_ticket", "get_account") and payload.get("data"):
                used_lookup = True
                entity = payload["data"]
                if isinstance(entity, dict):
                    citations.append(
                        {
                            "type": "structured",
                            "id": entity.get("order_id")
                            or entity.get("ticket_id")
                            or entity.get("account_id"),
                            "note": intent,
                        }
                    )

        if tool in (
            "create_escalation",
            "update_ticket",
            "create_follow_up_task",
        ) and isinstance(payload, dict):
            facts["action_type"] = payload.get("action_type") or tool
            if payload.get("needs_confirmation"):
                needs_confirmation = True
                flags.append("needs_confirmation")
                pending = payload.get("pending_action") or {}
                facts["pending_action_id"] = pending.get("pending_id")
            if payload.get("hitl") == "confirmed" and payload.get("executed"):
                facts["last_action"] = {
                    "tool": tool,
                    "result_ref": payload.get("result_ref"),
                    "result": payload.get("result"),
                }
                citations.append(
                    {
                        "type": "action",
                        "id": payload.get("result_ref") or tool,
                        "note": f"{tool} confirmed",
                    }
                )
    # Deduplicate citations by id+type
    seen: set[str] = set()
    unique_citations: list[dict[str, Any]] = []
    for cite in citations:
        key = f"{cite.get('type')}:{cite.get('id')}:{cite.get('section') or cite.get('note')}"
        if key in seen:
            continue
        seen.add(key)
        unique_citations.append(cite)

    confidence = _score_confidence(
        answer=answer,
        used_calc=used_calc,
        used_search=used_search,
        used_lookup=used_lookup,
        access_denied=access_denied,
        abstain=abstain,
        conflicts=conflicts,
        citations=unique_citations,
    )

    enriched_answer = _maybe_append_conflict_note(answer, conflicts, agreement_override)

    return {
        "confidence": confidence,
        "conflicts": conflicts,
        "citations": unique_citations,
        "flags": sorted(set(flags)),
        "facts": facts,
        "agreement_override": agreement_override,
        "abstain": abstain,
        "needs_manager_approval": needs_manager_approval,
        "recommend_escalation": recommend_escalation,
        "needs_confirmation": needs_confirmation,
        "answer": enriched_answer,
        "trust_summary": _trust_summary(
            confidence=confidence,
            conflicts=conflicts,
            abstain=abstain,
            recommend_escalation=recommend_escalation,
            needs_confirmation=needs_confirmation,
        ),
    }


def _score_confidence(
    *,
    answer: str,
    used_calc: bool,
    used_search: bool,
    used_lookup: bool,
    access_denied: bool,
    abstain: bool,
    conflicts: list[dict[str, str]],
    citations: list[dict[str, Any]],
) -> str:
    if access_denied and not (used_calc or used_lookup):
        return "low"
    if abstain:
        return "low"
    if not answer.strip():
        return "low"
    # Calculator + grounded lookup/search → high even when agreement/SOP conflict is recorded
    if used_calc:
        return "high"
    if used_lookup and used_search:
        return "high"
    if used_lookup or used_search:
        return "medium"
    # Answer with no tools — likely hallucinated
    if not used_calc and not used_search and not used_lookup:
        return "low"
    return "medium"


def _maybe_append_conflict_note(
    answer: str,
    conflicts: list[dict[str, str]],
    agreement_override: bool,
) -> str:
    if not conflicts or not answer:
        return answer

    # If the model already mentioned conflict/override, don't double-append.
    lowered = answer.lower()
    if any(
        word in lowered
        for word in ("override", "overrides", "conflict", "instead of", "rather than sop", "agreement wins")
    ):
        return answer

    lines = ["", "---", "Trust note:"]
    for c in conflicts:
        lines.append(f"- {c['claim']}: {c['detail']} (winner: {c['winner']})")
    if agreement_override:
        lines.append("- Precedence: signed agreement beats SOP/policy defaults.")
    return answer.rstrip() + "\n" + "\n".join(lines)


def _trust_summary(
    *,
    confidence: str,
    conflicts: list[dict[str, str]],
    abstain: bool,
    recommend_escalation: bool,
    needs_confirmation: bool,
) -> str:
    parts = [f"confidence={confidence}"]
    if conflicts:
        parts.append(f"{len(conflicts)} conflict(s) — agreement/policy precedence applied")
    if abstain:
        parts.append("abstain: do not promise credit/action")
    if recommend_escalation:
        parts.append("recommend escalation")
    if needs_confirmation:
        parts.append("pending action awaiting user confirm")
    return "; ".join(parts)
