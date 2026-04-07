from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utils.side_inference import ScopeInference, has_strong_side_evidence, infer_scope_from_texts, infer_side_group


@dataclass(slots=True)
class ChipBinding:
    chip_name: str
    side_scope: str | None = None
    side_group: str | None = None
    chuck_no: str | None = None
    slot_no: str | None = None
    chip_position: str | None = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)


class TaskSideRegistry:
    def __init__(self) -> None:
        self._chip_bindings: dict[str, ChipBinding] = {}
        self._chuck_to_side: dict[str, str] = {}
        self._chuck_to_chip: dict[str, str] = {}
        self._slot_to_side: dict[str, str] = {}

    @property
    def chip_bindings(self) -> dict[str, ChipBinding]:
        return self._chip_bindings

    def observe_inference(self, inference: ScopeInference) -> None:
        chip_name = inference.chip_name
        if inference.chuck_no and inference.side_scope:
            self._chuck_to_side[inference.chuck_no] = inference.side_scope
        if inference.slot_no and inference.side_scope and inference.slot_no not in self._slot_to_side:
            self._slot_to_side[inference.slot_no] = inference.side_scope

        if not chip_name:
            return

        if inference.chuck_no:
            self._chuck_to_chip[inference.chuck_no] = chip_name

        existing = self._chip_bindings.get(chip_name)
        if existing is None:
            existing = ChipBinding(chip_name=chip_name)
            self._chip_bindings[chip_name] = existing

        if inference.chip_position and not existing.chip_position:
            existing.chip_position = inference.chip_position
        if inference.slot_no and not existing.slot_no:
            existing.slot_no = inference.slot_no
        if inference.chuck_no and not existing.chuck_no:
            existing.chuck_no = inference.chuck_no

        candidate_confidence = float(inference.side_confidence or 0.0)
        if inference.side_scope and (
            has_strong_side_evidence(inference)
            or candidate_confidence >= existing.confidence
            or existing.side_scope is None
        ):
            existing.side_scope = inference.side_scope
            existing.side_group = inference.side_group or infer_side_group(inference.side_scope)
            existing.confidence = max(candidate_confidence, existing.confidence)
            existing.evidence = dict(inference.side_evidence or {})

    def observe_event(
        self,
        *,
        source_file: str | None,
        message: str | None,
        raw_text: str | None = None,
        chip_name: str | None = None,
        stage_name: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ScopeInference:
        inference = infer_scope_from_texts(
            source_file=source_file,
            message=message,
            raw_text=raw_text,
            chip_name=chip_name,
            stage_name=stage_name,
            extra=extra,
        )
        self.observe_inference(inference)
        return inference

    def resolve_inference(self, inference: ScopeInference) -> ScopeInference:
        evidence = dict(inference.side_evidence or {})
        chip_binding = self._chip_bindings.get(inference.chip_name or "")

        if chip_binding and chip_binding.side_scope:
            evidence["from_registry_chip"] = chip_binding.side_scope
            if inference.side_scope and inference.side_scope != chip_binding.side_scope:
                evidence["side_resolution_rule"] = "chip_registry_priority"
                evidence["side_conflict_with_registry"] = {
                    "direct_side": inference.side_scope,
                    "registry_side": chip_binding.side_scope,
                }
            inference.side_scope = chip_binding.side_scope
            inference.side_group = chip_binding.side_group or infer_side_group(chip_binding.side_scope)
            inference.side_confidence = max(float(inference.side_confidence or 0.0), max(chip_binding.confidence, 0.98))
            inference.chuck_no = inference.chuck_no or chip_binding.chuck_no
            inference.slot_no = inference.slot_no or chip_binding.slot_no
            inference.chip_position = inference.chip_position or chip_binding.chip_position
            inference.side_evidence = evidence
            return inference

        if not inference.side_scope and inference.chuck_no:
            chuck_side = self._chuck_to_side.get(inference.chuck_no)
            if chuck_side:
                evidence["from_registry_chuck"] = inference.chuck_no
                inference.side_scope = chuck_side
                inference.side_group = infer_side_group(chuck_side)
                inference.side_confidence = max(float(inference.side_confidence or 0.0), 0.88)

        if not inference.side_scope and inference.slot_no:
            slot_side = self._slot_to_side.get(inference.slot_no)
            if slot_side:
                evidence["from_registry_slot"] = inference.slot_no
                inference.side_scope = slot_side
                inference.side_group = infer_side_group(slot_side)
                inference.side_confidence = max(float(inference.side_confidence or 0.0), 0.82)

        if not inference.chip_name and inference.chuck_no:
            chip_name = self._chuck_to_chip.get(inference.chuck_no)
            if chip_name:
                evidence["from_registry_chuck_chip"] = chip_name
                inference.chip_name = chip_name
                chip_binding = self._chip_bindings.get(chip_name)
                if chip_binding and chip_binding.chip_position and not inference.chip_position:
                    inference.chip_position = chip_binding.chip_position
                if chip_binding and chip_binding.slot_no and not inference.slot_no:
                    inference.slot_no = chip_binding.slot_no

        inference.side_group = inference.side_group or infer_side_group(inference.side_scope)
        inference.side_evidence = evidence
        return inference
