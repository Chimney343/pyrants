"""Shared helpers for catalog execution audit generation."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from game_setup.loaders import assemble_catalog_payload  # noqa: E402

DEFAULT_CARD_PATH = ROOT_DIR / "data" / "cards"
DEFAULT_STUCK_REPORT_PATH = ROOT_DIR / "artifacts" / "card_stuck_report.json"

SUPPORTED_CONDITIONAL_BONUS_CONDITIONS = {
    "selected_node_has_other_player_troop",
    "selected_node_total_spies_at_least",
    "focus_aspect_present",
    "player_trophy_hall_non_white_at_least",
    "player_inner_circle_at_least",
}
SUPPORTED_CUSTOM_EFFECT_KINDS = {
    "scaled_resource_from_player_zone",
    "give_insane_outcast_to_player_with_presence_on_last_selected_node",
    "give_insane_outcast_to_selected_player",
    "give_insane_outcast_to_each_opponent",
    "mill_deck_to_discard",
    "self_purge_to_supply",
    "steal_white_trophy_to_board",
}
SUPPORTED_IMMEDIATE_PROMOTE_FRAGMENTS = {
    "promote_top_of_deck",
    "single_promote_from_multiple_zones",
    "promote_from_discard",
    "threshold_self_promote",
}
SUPPORTED_END_OF_TURN_PROMOTE_FRAGMENTS = {
    "triggered_promote",
    "triggered_multi_promote",
    "triggered_promote_aspect_filtered",
    "triggered_multi_promote_by_tag",
}
SCALED_VP_SOURCE_FRAGMENTS = {
    "scaled_vp",
    "scaled_vp_from_controlled_sites",
    "scaled_vp_from_trophies",
    "scaled_vp_from_white_trophies",
    "scaled_vp_from_promoted_cards",
}
ANYWHERE_SENSITIVE_OPS = {"supplant_troop", "assassinate_troop", "deploy_troops"}
ANYWHERE_SOURCE_TOKENS = ("anywhere", "unrestricted")
EXPECTED_UNSUPPORTED_GENERIC_ACTIONS: set[tuple[str, str, str]] = set()

_RESOURCE_PATTERNS = {
    "power": re.compile(r"\bgain\s+(\d+)\s+power\b", re.IGNORECASE),
    "influence": re.compile(r"\bgain\s+(\d+)\s+influence\b", re.IGNORECASE),
}
_ACTION_PATTERNS = {
    "deploy_troops": re.compile(r"\bdeploy\s+(\d+)\s+troops?\b", re.IGNORECASE),
    "draw_cards": re.compile(r"\bdraw\s+(\d+)\s+cards?\b", re.IGNORECASE),
    "place_spy": re.compile(r"\bplace\s+(\d+)\s+sp(?:y|ies)\b", re.IGNORECASE),
    "assassinate_troop": re.compile(r"\bassassinate\s+(\d+)\s+(?:white\s+)?troops?\b", re.IGNORECASE),
}
_DYNAMIC_TEXT_TOKENS = (
    "for each",
    "for every",
    "if you have",
    "if another",
    "if there",
    "up to",
    "choose exactly one mode",
    "choose one",
    "either",
)
_DYNAMIC_METADATA_KEYS = {"count_from", "condition", "focus_aspect", "required_aspect", "max_cost"}


@dataclass(frozen=True)
class AuditFinding:
    finding_class: Literal["rules_text_mismatch", "runtime_gap", "heuristic_false_positive"]
    severity: Literal["low", "medium", "high"]
    summary: str
    evidence: tuple[str, ...]
    remediation_track: Literal["data_model_fix", "engine_fix", "audit_fix"]


@dataclass(frozen=True)
class CardAuditEntry:
    card_id: str
    name: str
    aspect: str
    cost: int
    rules_text: str
    execution_kind: str
    action_summaries: tuple[str, ...]
    verdict: Literal["clean", "mismatch", "runtime_gap", "heuristic-only"]
    findings: tuple[AuditFinding, ...]
    probe_status: str | None
    probe_reason: str | None


def load_catalog_payload(card_path: Path = DEFAULT_CARD_PATH) -> dict[str, Any]:
    return assemble_catalog_payload(card_path)


def load_probe_results(stuck_report_path: Path = DEFAULT_STUCK_REPORT_PATH) -> dict[str, dict[str, Any]]:
    if not stuck_report_path.exists():
        return {}

    payload = json.loads(stuck_report_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    if not isinstance(results, list):
        return {}
    return {
        str(result.get("card_id")): result
        for result in results
        if isinstance(result, dict) and result.get("card_id")
    }


def unsupported_generic_action_reason(action: dict[str, object]) -> str | None:
    op = str(action.get("op", "")).strip().lower()
    source_fragment = str(action.get("source_fragment", "")).strip().lower()
    metadata = action.get("metadata") or {}
    if not isinstance(metadata, dict):
        return "metadata_must_be_object"

    if op == "play_card":
        if source_fragment in {"play_from_inner_circle_without_removal", "play"}:
            return None
        return "play_card_not_implemented"

    if op == "conditional_bonus":
        condition = str(metadata.get("condition", "")).strip().lower()
        if not condition:
            return "conditional_bonus_missing_condition"
        if condition not in SUPPORTED_CONDITIONAL_BONUS_CONDITIONS:
            return f"conditional_bonus_unsupported:{condition}"

    if op == "custom_effect":
        effect_kind = str(metadata.get("effect_kind", "")).strip().lower()
        if not effect_kind:
            return "custom_effect_missing_effect_kind"
        if effect_kind not in SUPPORTED_CUSTOM_EFFECT_KINDS:
            return f"custom_effect_unsupported:{effect_kind}"

    if op == "promote_card":
        timing = str(action.get("timing", "")).strip().lower()
        if timing == "immediate" and source_fragment not in SUPPORTED_IMMEDIATE_PROMOTE_FRAGMENTS:
            return f"immediate_promote_unsupported:{source_fragment or '<empty>'}"
        if timing == "end_of_turn" and source_fragment not in SUPPORTED_END_OF_TURN_PROMOTE_FRAGMENTS:
            return f"end_of_turn_promote_unsupported:{source_fragment or '<empty>'}"

    if op in ANYWHERE_SENSITIVE_OPS and any(token in source_fragment for token in ANYWHERE_SOURCE_TOKENS):
        targeting = str(metadata.get("targeting", "")).strip().lower()
        if targeting != "anywhere" and not bool(metadata.get("ignore_presence_requirement", False)):
            return f"anywhere_targeting_unsupported:{op}:{source_fragment}"

    return None


def build_card_audit_entries(
    card_path: Path = DEFAULT_CARD_PATH,
    stuck_report_path: Path = DEFAULT_STUCK_REPORT_PATH,
) -> list[CardAuditEntry]:
    payload = load_catalog_payload(card_path)
    cards = payload.get("cards", [])
    if not isinstance(cards, list):
        raise ValueError("catalog payload must contain a cards list")

    probe_results = load_probe_results(stuck_report_path)
    entries: list[CardAuditEntry] = []

    for card in sorted(cards, key=lambda item: str(item.get("card_id", ""))):
        if not isinstance(card, dict):
            continue
        findings = [
            *build_structural_findings(card),
            *build_runtime_gap_findings(card),
        ]

        probe = probe_results.get(str(card.get("card_id", "")))
        if probe is not None:
            findings.extend(build_probe_findings(probe))

        findings_tuple = tuple(findings)
        entries.append(
            CardAuditEntry(
                card_id=str(card.get("card_id", "")),
                name=str(card.get("name", "")),
                aspect=str(card.get("aspect", "")),
                cost=int(card.get("cost", 0) or 0),
                rules_text=str(card.get("rules_text", "")).strip(),
                execution_kind=str((card.get("execution_model") or {}).get("kind", "unknown")),
                action_summaries=tuple(_format_action_summary(action) for action in _card_actions(card)),
                verdict=_determine_verdict(findings_tuple),
                findings=findings_tuple,
                probe_status=None if probe is None else str(probe.get("status", "")),
                probe_reason=None if probe is None else str(probe.get("stopped_reason", "")),
            )
        )

    return entries


def render_markdown_report(entries: list[CardAuditEntry], *, card_path: Path, stuck_report_path: Path) -> str:
    total_cards = len(entries)
    mismatch_cards = sum(1 for entry in entries if any(f.finding_class == "rules_text_mismatch" for f in entry.findings))
    runtime_gap_cards = sum(1 for entry in entries if any(f.finding_class == "runtime_gap" for f in entry.findings))
    heuristic_cards = sum(1 for entry in entries if any(f.finding_class == "heuristic_false_positive" for f in entry.findings))
    clean_cards = sum(1 for entry in entries if not entry.findings)
    blocked_or_stuck = sum(1 for entry in entries if entry.probe_status in {"blocked", "stuck", "error", "max_steps"})

    lines = [
        "# Catalog Execution Audit",
        "",
        f"Source catalog: {card_path.as_posix()}",
        f"Probe artifact: {stuck_report_path.as_posix() if stuck_report_path.exists() else 'not provided'}",
        "",
        "## Summary",
        "",
        f"- Total cards audited: {total_cards}",
        f"- Clean cards: {clean_cards}",
        f"- Cards with rules-text mismatches: {mismatch_cards}",
        f"- Cards with runtime gaps: {runtime_gap_cards}",
        f"- Cards flagged as heuristic-review only: {heuristic_cards}",
        f"- Cards blocked, errored, or stuck in the live probe: {blocked_or_stuck}",
        "",
        "## Cards With Findings",
        "",
        "| card_id | verdict | findings | probe |",
        "|---|---|---:|---|",
    ]

    for entry in entries:
        if not entry.findings:
            continue
        probe_status = entry.probe_status or "n/a"
        lines.append(f"| {entry.card_id} | {entry.verdict} | {len(entry.findings)} | {probe_status} |")

    lines.extend(["", "## Card Review", ""])

    for entry in entries:
        lines.append(f"### {entry.name} (`{entry.card_id}`)")
        lines.append("")
        lines.append(f"- Verdict: `{entry.verdict}`")
        lines.append(f"- Aspect: `{entry.aspect}`")
        lines.append(f"- Cost: `{entry.cost}`")
        if entry.probe_status is not None:
            lines.append(f"- Probe: `{entry.probe_status}` ({entry.probe_reason or 'n/a'})")
        lines.append(f"- Execution model: `{entry.execution_kind}`")
        lines.append(f"- Rules text: {entry.rules_text}")
        lines.append("- Actions:")
        for action_summary in entry.action_summaries:
            lines.append(f"  - {action_summary}")

        if not entry.findings:
            lines.append("- Findings: none")
            lines.append("")
            continue

        lines.append("- Findings:")
        for finding in entry.findings:
            lines.append(
                "  - "
                f"[{finding.finding_class}][{finding.severity}][{finding.remediation_track}] {finding.summary}"
            )
            for evidence_line in finding.evidence:
                lines.append(f"    - {evidence_line}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_structural_findings(card: dict[str, Any]) -> list[AuditFinding]:
    rules_text = str(card.get("rules_text", "")).strip()
    findings: list[AuditFinding] = []

    findings.extend(_resource_mismatch_findings(card, rules_text))
    findings.extend(_count_mismatch_findings(card, rules_text))

    if _looks_modal(rules_text) and str((card.get("execution_model") or {}).get("kind", "")).strip().lower() == "sequence":
        findings.append(
            AuditFinding(
                finding_class="rules_text_mismatch",
                severity="medium",
                summary="modal_text_but_execution_kind_sequence",
                evidence=(
                    "rules_text contains modal wording such as 'choose' or 'either/or'",
                    "execution_model.kind is sequence",
                ),
                remediation_track="data_model_fix",
            )
        )

    if _mentions_end_of_turn(rules_text) and not any(
        str(action.get("timing", "")).strip().lower() == "end_of_turn"
        for action in _card_actions(card)
    ):
        findings.append(
            AuditFinding(
                finding_class="rules_text_mismatch",
                severity="medium",
                summary="end_of_turn_text_but_no_end_of_turn_action",
                evidence=(
                    "rules_text references end-of-turn timing",
                    "no flattened action has timing=end_of_turn",
                ),
                remediation_track="data_model_fix",
            )
        )

    return findings


def build_runtime_gap_findings(card: dict[str, Any]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    for action in _card_actions(card):
        reason = unsupported_generic_action_reason(action)
        if reason is None:
            continue

        findings.append(
            AuditFinding(
                finding_class="runtime_gap",
                severity="high",
                summary=f"{action.get('action_id', '<unknown>')}: {reason}",
                evidence=(
                    _format_action_summary(action),
                    f"owning_engine_path={_runtime_gap_owner(reason)}",
                ),
                remediation_track="engine_fix",
            )
        )

    return findings


def build_probe_findings(probe_result: dict[str, Any]) -> list[AuditFinding]:
    status = str(probe_result.get("status", "")).strip().lower()
    if status not in {"blocked", "stuck", "error", "max_steps"}:
        return []

    stopped_reason = str(probe_result.get("stopped_reason", "")).strip() or "unknown"
    error = str(probe_result.get("error", "")).strip() or "none"
    return [
        AuditFinding(
            finding_class="runtime_gap",
            severity="high",
            summary=f"probe_{status}:{stopped_reason}",
            evidence=(
                f"probe status={status}",
                f"stopped_reason={stopped_reason}",
                f"error={error}",
            ),
            remediation_track="engine_fix",
        )
    ]


def _resource_mismatch_findings(card: dict[str, Any], rules_text: str) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    for resource, pattern in _RESOURCE_PATTERNS.items():
        expected = _sum_expected(pattern, rules_text)
        if expected <= 0:
            continue

        fixed_sum, has_action, has_nonfixed = _fixed_sum_for_resource(card, resource)
        if fixed_sum == expected:
            continue

        if _has_scaled_resource_custom_effect(card, resource) and _mentions_scaled_count_text(rules_text):
            continue

        heuristic_sensitive = _is_heuristic_sensitive(card, rules_text)
        if has_nonfixed and fixed_sum == 0:
            summary = f"gain_{resource}_expected_{expected}_but_no_fixed_quantity"
        else:
            summary = f"gain_{resource}_expected_{expected}_fixed_sum_{fixed_sum}"

        findings.append(
            AuditFinding(
                finding_class="heuristic_false_positive" if heuristic_sensitive else "rules_text_mismatch",
                severity="low" if heuristic_sensitive else "medium",
                summary=summary,
                evidence=(
                    f"rules_text fixed expectation for {resource}={expected}",
                    f"flattened resource gain fixed sum for {resource}={fixed_sum}",
                    f"matching actions present={has_action}, non_fixed={has_nonfixed}",
                ),
                remediation_track="audit_fix" if heuristic_sensitive else "data_model_fix",
            )
        )

    return findings


def _count_mismatch_findings(card: dict[str, Any], rules_text: str) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    for op, pattern in _ACTION_PATTERNS.items():
        expected = _sum_expected(pattern, rules_text)
        if expected <= 0:
            continue

        fixed_sum, has_action, has_nonfixed = _fixed_sum_for_action(card, op)
        if fixed_sum == expected:
            continue

        if has_nonfixed and _has_dynamic_count_from_action(card, op) and _mentions_scaled_count_text(rules_text):
            continue

        if not has_action:
            summary = f"{op}_expected_{expected}_but_action_missing"
        elif has_nonfixed and fixed_sum == 0:
            summary = f"{op}_expected_{expected}_but_no_fixed_quantity"
        else:
            summary = f"{op}_expected_{expected}_fixed_sum_{fixed_sum}"

        heuristic_sensitive = _is_heuristic_sensitive(card, rules_text)
        findings.append(
            AuditFinding(
                finding_class="heuristic_false_positive" if heuristic_sensitive else "rules_text_mismatch",
                severity="low" if heuristic_sensitive else "medium",
                summary=summary,
                evidence=(
                    f"rules_text fixed expectation for {op}={expected}",
                    f"flattened {op} fixed sum={fixed_sum}",
                    f"matching actions present={has_action}, non_fixed={has_nonfixed}",
                ),
                remediation_track="audit_fix" if heuristic_sensitive else "data_model_fix",
            )
        )

    return findings


def _is_heuristic_sensitive(card: dict[str, Any], rules_text: str) -> bool:
    lowered_text = rules_text.lower()
    if any(token in lowered_text for token in _DYNAMIC_TEXT_TOKENS):
        return True

    for action in _card_actions(card):
        quantity = action.get("quantity") or {}
        if isinstance(quantity, dict) and str(quantity.get("kind", "")).strip().lower() != "fixed":
            return True

        metadata = action.get("metadata") or {}
        if isinstance(metadata, dict) and any(key in metadata for key in _DYNAMIC_METADATA_KEYS):
            return True

        if str(action.get("op", "")).strip().lower() in {"conditional_bonus", "custom_effect"}:
            return True

        if str(action.get("source_fragment", "")).strip().lower() in SCALED_VP_SOURCE_FRAGMENTS:
            return True

    return False


def _determine_verdict(findings: tuple[AuditFinding, ...]) -> Literal["clean", "mismatch", "runtime_gap", "heuristic-only"]:
    if not findings:
        return "clean"
    if any(finding.finding_class == "runtime_gap" for finding in findings):
        return "runtime_gap"
    if any(finding.finding_class == "rules_text_mismatch" for finding in findings):
        return "mismatch"
    return "heuristic-only"


def _card_actions(card: dict[str, Any]) -> list[dict[str, Any]]:
    actions = card.get("actions", [])
    return [action for action in actions if isinstance(action, dict)] if isinstance(actions, list) else []


def _fixed_sum_for_action(card: dict[str, Any], op: str, *, resource: str | None = None) -> tuple[int, bool, bool]:
    fixed_sum = 0
    has_action = False
    has_nonfixed = False

    for action in _card_actions(card):
        if str(action.get("op", "")).strip().lower() != op:
            continue
        if resource is not None:
            metadata = action.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            if str(metadata.get("resource", "")).strip().lower() != resource:
                continue

        has_action = True
        quantity = action.get("quantity") or {}
        if not isinstance(quantity, dict):
            has_nonfixed = True
            continue
        if str(quantity.get("kind", "")).strip().lower() != "fixed":
            has_nonfixed = True
            continue
        value = quantity.get("value")
        if isinstance(value, int):
            fixed_sum += value

    return fixed_sum, has_action, has_nonfixed


def _fixed_sum_for_resource(card: dict[str, Any], resource: str) -> tuple[int, bool, bool]:
    fixed_sum, has_action, has_nonfixed = _fixed_sum_for_action(card, "gain_resource", resource=resource)

    for action in _card_actions(card):
        if str(action.get("op", "")).strip().lower() != "conditional_bonus":
            continue

        metadata = action.get("metadata") or {}
        if not isinstance(metadata, dict):
            has_nonfixed = True
            continue
        if str(metadata.get("resource", "")).strip().lower() != resource:
            continue

        has_action = True
        amount_raw = metadata.get("amount")
        if isinstance(amount_raw, int):
            fixed_sum += amount_raw
            continue
        if isinstance(amount_raw, str):
            try:
                fixed_sum += int(amount_raw)
                continue
            except ValueError:
                pass

        quantity = action.get("quantity") or {}
        if not isinstance(quantity, dict):
            has_nonfixed = True
            continue
        if str(quantity.get("kind", "")).strip().lower() != "fixed":
            has_nonfixed = True
            continue

        value = quantity.get("value")
        if isinstance(value, int):
            fixed_sum += value
        else:
            has_nonfixed = True

    return fixed_sum, has_action, has_nonfixed


def _has_scaled_resource_custom_effect(card: dict[str, Any], resource: str) -> bool:
    for action in _card_actions(card):
        if str(action.get("op", "")).strip().lower() != "custom_effect":
            continue
        metadata = action.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        effect_kind = str(metadata.get("effect_kind", "")).strip().lower()
        if effect_kind != "scaled_resource_from_player_zone":
            continue
        effect_resource = str(metadata.get("resource", "")).strip().lower()
        if effect_resource == resource:
            return True
    return False


def _sum_expected(pattern: re.Pattern[str], rules_text: str) -> int:
    return sum(int(match.group(1)) for match in pattern.finditer(rules_text))


def _looks_modal(rules_text: str) -> bool:
    lowered_text = rules_text.lower()
    return "choose exactly one mode" in lowered_text or ("either" in lowered_text and " or " in lowered_text)


def _mentions_end_of_turn(rules_text: str) -> bool:
    lowered_text = rules_text.lower()
    return "end of your turn" in lowered_text or "end of turn" in lowered_text


def _mentions_scaled_count_text(rules_text: str) -> bool:
    lowered_text = rules_text.lower()
    return "for each" in lowered_text or "for every" in lowered_text


def _has_dynamic_count_from_action(card: dict[str, Any], op: str) -> bool:
    for action in _card_actions(card):
        if str(action.get("op", "")).strip().lower() != op:
            continue
        metadata = action.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        count_from = str(metadata.get("count_from", "")).strip().lower()
        if count_from:
            return True
    return False


def _format_action_summary(action: dict[str, Any]) -> str:
    action_id = str(action.get("action_id", "<unknown>"))
    op = str(action.get("op", "<unknown>"))
    target_scope = str(action.get("target_scope", "<unknown>"))
    timing = str(action.get("timing", "<unknown>"))
    source_fragment = str(action.get("source_fragment", ""))
    quantity = action.get("quantity") or {}
    quantity_kind = str(quantity.get("kind", "<unknown>")) if isinstance(quantity, dict) else "<unknown>"
    quantity_value = quantity.get("value") if isinstance(quantity, dict) else None
    quantity_label = quantity_kind if quantity_value is None else f"{quantity_kind}:{quantity_value}"
    return (
        f"{action_id} -> {op} [{target_scope}] timing={timing} "
        f"quantity={quantity_label} source_fragment={source_fragment or '<empty>'}"
    )


def _runtime_gap_owner(reason: str) -> str:
    if reason.startswith("anywhere_targeting_unsupported"):
        return "engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action"
    if reason.startswith("scaled_grant_vp_unsupported"):
        return "engine/rules.py::_apply_generic_action"
    if reason.startswith("immediate_promote_unsupported") or reason.startswith("end_of_turn_promote_unsupported"):
        return "engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action + _apply_end_of_turn_generic_effects"
    if reason.startswith("custom_effect_"):
        return "engine/rules.py::_legal_generic_target_selection_moves + _apply_generic_action"
    if reason.startswith("conditional_bonus_"):
        return "engine/rules.py::_apply_generic_action"
    if reason.startswith("play_card_"):
        return "engine/rules.py::_apply_generic_action"
    return "engine/rules.py::_apply_generic_action"
