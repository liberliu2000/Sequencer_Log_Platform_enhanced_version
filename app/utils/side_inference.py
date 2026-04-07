from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.settings import get_settings
from app.utils.rules import load_yaml

WHOLE_INSTRUMENT_SCOPE = "Whole Instrument"
UNASSIGNED_SCOPE_TOKEN = "__UNASSIGNED__"

_DEFAULT_FILENAME_PATTERNS = [r"(?:^|[_\-.])(A\d{0,2}|B\d{0,2})(?=(?:[_\-.]|$))"]
_DEFAULT_STAGE_PATTERNS = {
    "stage_key": [r"\bStageKey\s*[:=]\s*([A-Za-z]\d{0,2})\b"],
    "stage_name": [
        r"\bStageName\s*[:=]\s*([A-Za-z]\d{0,2})\b",
        r"\bgroupName\s*[:=]\s*([A-Za-z]\d{0,2})\b",
    ],
    "workflow_stage": [
        r"\b(?:Start\s+optical\s+CPAS\s+Workflow\s+For\s+Stage|Workflow\s+For\s+Stage)\s+([A-Za-z]\d{0,2})\b",
        r"\bFor\s+Stage\s+([A-Za-z]\d{0,2})\b",
    ],
    "source_chuck": [
        r"\bSourceChuck\s*[:=]\s*([A-Za-z]\d{0,2}-\d+)\b",
        r"\b(?:TargetChuck|ChuckNo|Chuck)\s*[:=]\s*([A-Za-z]\d{0,2}-\d+)\b",
    ],
    "slot_no": [r"\b(?:SlotNo|SourceSlot|TargetSlot|Slot)\s*[:=]\s*([A-Za-z0-9_-]+)\b"],
}
_DEFAULT_CONTEXT_PATTERNS = [
    r"\b(?:request imager|hold imager|transfer command|set transfer slide data|update slide position|move slide|transfer slide)\b[^\n]{0,120}?\b(A\d{0,2}|B\d{0,2})\b",
    r"\b(A\d{0,2}|B\d{0,2})\b[^\n]{0,120}?\b(?:request imager|hold imager|transfer command|set transfer slide data|update slide position|move slide|transfer slide)\b",
    r"\b(A\d{0,2}|B\d{0,2})\b[^\n]{0,80}?\bcpas\s+reagent\s+priming\b",
    r"\bcpas\s+reagent\s+priming\b[^\n]{0,80}?\b(A\d{0,2}|B\d{0,2})\b",
    r"\bSpray[-_/ ](A\d{0,2}|B\d{0,2})\b[^\n]{0,160}?\b(?:Fluidic|status|[A-Za-z0-9_]+\.py)\b",
    r"(?<!\S)(A\d{1,2}|B\d{1,2})(?!\S)",
]
_DEFAULT_CHIP_PATTERNS = [
    r"\b(?:SlideUniqueNo|slide\s*unique\s*no|slide[_\s-]?[NF]?|chip[_\s-]?name|slide\s*name|flowcell\s*id)\s*[:=, ]+(\d{2}\.M\d_[A-Z]{2}_(?:HLAA|HLAB)[A-Za-z0-9]+)\b",
    r"\b(?:SlideUniqueNo|slide\s*unique\s*no|slide[_\s-]?[NF]?|chip[_\s-]?name|slide\s*name|flowcell\s*id)\s*[:=, ]+((?:HLAA|HLAB)[A-Za-z0-9]{4,})\b",
    r"\b(\d{2}\.M\d_[A-Z]{2}_(?:HLAA|HLAB)[A-Za-z0-9]+)\b",
    r"\b((?:HLAA|HLAB)[A-Za-z0-9]{4,})\b",
]
_DEFAULT_NEAR_PATTERNS = [r"\b(?:near|Near)\b", r"\bchip\s*position\s*[:=]\s*N(?:ear)?\b"]
_DEFAULT_FAR_PATTERNS = [r"\b(?:far|Far)\b", r"\bchip\s*position\s*[:=]\s*F(?:ar)?\b"]


@dataclass(slots=True)
class ScopeInference:
    instrument_scope: str | None = WHOLE_INSTRUMENT_SCOPE
    side_scope: str | None = None
    side_group: str | None = None
    chip_name: str | None = None
    chip_position: str | None = None
    chuck_no: str | None = None
    slot_no: str | None = None
    stage_key: str | None = None
    side_confidence: float | None = None
    side_evidence: dict[str, Any] = field(default_factory=dict)

    def model_fields(self) -> dict[str, Any]:
        return {
            "instrument_scope": self.instrument_scope,
            "side_scope": self.side_scope,
            "side_group": self.side_group,
            "chip_name": self.chip_name,
            "chip_position": self.chip_position,
            "chuck_no": self.chuck_no,
            "slot_no": self.slot_no,
            "stage_key": self.stage_key,
            "side_confidence": self.side_confidence,
            "side_evidence": dict(self.side_evidence or {}),
        }


@lru_cache(maxsize=1)
def _side_rules() -> dict[str, Any]:
    data = load_yaml(get_settings().side_rules_path)
    return data if isinstance(data, dict) else {}


def _rule_list(*path: str, default: list[str]) -> list[str]:
    node: Any = _side_rules()
    for part in path:
        if not isinstance(node, dict):
            return list(default)
        node = node.get(part)
    if isinstance(node, list):
        return [str(item) for item in node if str(item or "").strip()]
    return list(default)


@lru_cache(maxsize=64)
def _compiled_patterns_cached(path_key: tuple[str, ...], default_patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in _rule_list(*path_key, default=list(default_patterns)))


def _compiled_patterns(*path: str, default: list[str]) -> list[re.Pattern[str]]:
    return list(_compiled_patterns_cached(tuple(path), tuple(default)))


def normalize_side_scope(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    match = re.fullmatch(r"([A-Z]+)(\d{0,2})", text)
    if not match:
        return None
    prefix, suffix = match.groups()
    return f"{prefix}{suffix}" if suffix else prefix


def infer_side_group(side_scope: str | None) -> str | None:
    normalized = normalize_side_scope(side_scope)
    if not normalized:
        return None
    match = re.match(r"([A-Z]+)", normalized)
    return match.group(1) if match else normalized


def side_specificity(side_scope: str | None) -> int:
    normalized = normalize_side_scope(side_scope)
    if not normalized:
        return 0
    return 2 if re.search(r"\d", normalized) else 1


def prefer_specific_side(primary: str | None, secondary: str | None) -> str | None:
    left = normalize_side_scope(primary)
    right = normalize_side_scope(secondary)
    if not left:
        return right
    if not right:
        return left
    if infer_side_group(left) == infer_side_group(right) and side_specificity(right) > side_specificity(left):
        return right
    return left


def normalize_chip_name(value: str | None) -> str | None:
    text = str(value or "").strip().strip("'\"[](){}<>")
    text = re.sub(r"[,;:]+$", "", text)
    return text or None


def is_chip_name_candidate(value: str | None) -> bool:
    text = normalize_chip_name(value)
    if not text:
        return False
    upper = text.upper()
    return bool(
        re.fullmatch(r"\d{2}\.M\d_[A-Z]{2}_(?:HLAA|HLAB)[A-Z0-9]+", upper)
        or re.fullmatch(r"(?:HLAA|HLAB)[A-Z0-9]{4,}", upper)
    )


def extract_chip_name(*texts: Any) -> str | None:
    patterns = _compiled_patterns("chip_patterns", default=_DEFAULT_CHIP_PATTERNS)
    for raw in texts:
        text = str(raw or "")
        if not text:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            value = normalize_chip_name(match.group(1) if match.lastindex else match.group(0))
            if is_chip_name_candidate(value):
                return value
    return None


def extract_stage_key(*texts: Any) -> str | None:
    for pattern in _compiled_patterns("stage_patterns", "stage_key", default=_DEFAULT_STAGE_PATTERNS["stage_key"]):
        for raw in texts:
            match = pattern.search(str(raw or ""))
            if match:
                return normalize_side_scope(match.group(1))
    return None


def extract_stage_name_side(*texts: Any) -> str | None:
    pattern_sets = (
        _compiled_patterns("stage_patterns", "stage_name", default=_DEFAULT_STAGE_PATTERNS["stage_name"]),
        _compiled_patterns("stage_patterns", "workflow_stage", default=_DEFAULT_STAGE_PATTERNS["workflow_stage"]),
    )
    for patterns in pattern_sets:
        for pattern in patterns:
            for raw in texts:
                match = pattern.search(str(raw or ""))
                if match:
                    return normalize_side_scope(match.group(1))
    return None


def extract_chuck_no(*texts: Any) -> str | None:
    for pattern in _compiled_patterns("stage_patterns", "source_chuck", default=_DEFAULT_STAGE_PATTERNS["source_chuck"]):
        for raw in texts:
            match = pattern.search(str(raw or ""))
            if match:
                value = str(match.group(1) or "").strip().upper()
                return value or None
    return None


def extract_slot_no(*texts: Any) -> str | None:
    for pattern in _compiled_patterns("stage_patterns", "slot_no", default=_DEFAULT_STAGE_PATTERNS["slot_no"]):
        for raw in texts:
            match = pattern.search(str(raw or ""))
            if match:
                value = str(match.group(1) or "").strip()
                return value or None
    return None


def extract_side_from_filename(source_file: str | None) -> str | None:
    text = str(source_file or "")
    if not text:
        return None
    matches: list[str] = []
    for pattern in _compiled_patterns("filename_side_patterns", default=_DEFAULT_FILENAME_PATTERNS):
        matches.extend(filter(None, (normalize_side_scope(item) for item in pattern.findall(text))))
    unique = list(dict.fromkeys(matches))
    if not unique:
        return None
    stem = Path(text).stem.upper()
    if len(unique) == 1 and unique[0] in {"A", "B"} and stem in {"A", "B"}:
        return None
    if len(unique) == 1:
        return unique[0]
    return unique[-1]


def extract_context_side(*texts: Any) -> str | None:
    for pattern in _compiled_patterns("context_side_patterns", default=_DEFAULT_CONTEXT_PATTERNS):
        for raw in texts:
            match = pattern.search(str(raw or ""))
            if match:
                return normalize_side_scope(match.group(1))
    return None


def infer_chip_position(*texts: Any, chip_name: str | None = None) -> str | None:
    normalized_chip = normalize_chip_name(chip_name)
    if normalized_chip:
        escaped_chip = re.escape(normalized_chip)
        for raw in texts:
            text = str(raw or "")
            if not text:
                continue
            if re.search(rf"\bslide_N\s*[:=]\s*{escaped_chip}\b", text, re.IGNORECASE):
                return "Near"
            if re.search(rf"\bslide_F\s*[:=]\s*{escaped_chip}\b", text, re.IGNORECASE):
                return "Far"
    for raw in texts:
        text = str(raw or "")
        if not text:
            continue
        for pattern in _compiled_patterns("chip_position_patterns", "near", default=_DEFAULT_NEAR_PATTERNS):
            if pattern.search(text):
                return "Near"
        for pattern in _compiled_patterns("chip_position_patterns", "far", default=_DEFAULT_FAR_PATTERNS):
            if pattern.search(text):
                return "Far"
    chip_fragment_rules = _side_rules().get("chip_position_by_chip_fragment")
    if isinstance(chip_fragment_rules, dict) and chip_name:
        upper_chip = str(chip_name).upper()
        for fragment, mapped_value in chip_fragment_rules.items():
            if fragment and str(fragment).upper() in upper_chip:
                value = str(mapped_value or "").strip()
                if value:
                    return value
    return None


def infer_scope_from_texts(
    *,
    source_file: str | None,
    message: str | None,
    raw_text: str | None = None,
    chip_name: str | None = None,
    stage_name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> ScopeInference:
    evidence: dict[str, Any] = {}
    extra = dict(extra or {})
    extra_text = " ".join(f"{key}={value}" for key, value in extra.items())
    explicit_chip = normalize_chip_name(chip_name)
    chip_value = explicit_chip if is_chip_name_candidate(explicit_chip) else extract_chip_name(message, raw_text, extra_text, source_file)
    if chip_value:
        evidence["from_chip"] = chip_value

    filename_side = extract_side_from_filename(source_file)
    if filename_side:
        evidence["from_filename"] = filename_side

    stage_key = extract_stage_key(message, raw_text, extra_text)
    if stage_key:
        evidence["from_stagekey"] = stage_key

    direct_stage_side = normalize_side_scope(stage_name) or extract_stage_name_side(message, raw_text, extra_text)
    if direct_stage_side:
        evidence["from_stagename"] = direct_stage_side

    chuck_no = extract_chuck_no(message, raw_text, extra_text)
    if chuck_no:
        evidence["from_sourcechuck"] = chuck_no

    slot_no = extract_slot_no(message, raw_text, extra_text)
    if slot_no:
        evidence["from_slot"] = slot_no

    context_side = extract_context_side(message, raw_text, extra_text)
    if context_side:
        evidence["from_context"] = context_side

    candidates: list[tuple[str, float, str]] = []
    if filename_side:
        filename_score = 0.95 if re.search(r"\d", filename_side) else 0.84
        candidates.append((filename_side, filename_score, "from_filename"))
    if stage_key:
        candidates.append((stage_key, 0.94, "from_stagekey"))
    if direct_stage_side:
        candidates.append((direct_stage_side, 0.92, "from_stagename"))
    if chuck_no:
        chuck_side = normalize_side_scope(chuck_no.split("-", 1)[0])
        if chuck_side:
            candidates.append((chuck_side, 0.93, "from_sourcechuck"))
    if context_side:
        candidates.append((context_side, 0.76, "from_context"))

    side_scope = None
    side_confidence = None
    if candidates:
        def _selection_score(item: tuple[str, float, str]) -> float:
            side, base_score, _source = item
            return min(0.99, base_score + (0.12 if side_specificity(side) > 1 else 0.0))

        ordered = sorted(
            candidates,
            key=lambda item: (
                _selection_score(item),
                side_specificity(item[0]),
                len(item[0]),
            ),
            reverse=True,
        )
        side_scope, _raw_confidence, chosen_key = ordered[0]
        side_confidence = _selection_score(ordered[0])
        evidence["selected_side_source"] = chosen_key
        distinct_sides = {candidate[0] for candidate in ordered}
        if len(distinct_sides) > 1:
            evidence["side_conflicts"] = {source: value for value, _score, source in ordered}

    chip_position = infer_chip_position(message, raw_text, extra_text, chip_name=chip_value)
    if chip_position:
        evidence["from_chip_position"] = chip_position

    return ScopeInference(
        instrument_scope=WHOLE_INSTRUMENT_SCOPE,
        side_scope=side_scope,
        side_group=infer_side_group(side_scope),
        chip_name=chip_value,
        chip_position=chip_position,
        chuck_no=chuck_no,
        slot_no=slot_no,
        stage_key=stage_key,
        side_confidence=side_confidence,
        side_evidence=evidence,
    )


def has_strong_side_evidence(inference: ScopeInference) -> bool:
    evidence = inference.side_evidence or {}
    strong_keys = {"from_filename", "from_stagekey", "from_stagename", "from_sourcechuck"}
    return bool(inference.side_scope and any(key in evidence for key in strong_keys))
