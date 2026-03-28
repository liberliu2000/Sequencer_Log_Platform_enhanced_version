from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Pattern


@dataclass(frozen=True)
class ParameterDefinition:
    parameter_name: str
    display_name: str
    threshold_seconds: float | None
    expected_seconds: float | None
    source_type: Literal["log", "metrics", "derived", "inferred"]
    aggregation_rule: str = "per_cycle"
    cycle_binding_rule: str = "cycle"
    unit: str = "seconds"
    notes: str = ""


@dataclass(frozen=True)
class PairingRule:
    parameter_name: str
    display_name: str
    start_pattern: Pattern[str]
    end_pattern: Pattern[str]
    cycle_from_match: bool = False
    slide_from_match: bool = False
    source_type: Literal["log", "metrics", "derived", "inferred"] = "derived"
    threshold_seconds: float | None = None
    expected_seconds: float | None = None
    notes: str = ""
    target_temp: float | None = None
    target_temp_tolerance: float = 2.0

    def is_temperature_rule(self) -> bool:
        return self.target_temp is not None


PARAMETER_DEFINITIONS: list[ParameterDefinition] = [
    ParameterDefinition("cycle_time", "cycle time", 530.0, 500.0, "derived", notes="Current imaging cycle n+1 - Current imaging cycle n"),
    ParameterDefinition("imaging_time", "imaging time", 150.0, 125.0, "derived", notes="Imaging complete for cycle n - Imaging at cycle n"),
    ParameterDefinition("imaging_time_real", "imaging time real", 150.0, 125.0, "derived", notes="Imaging complete for cycle n - Imaging start for cycle n"),
    ParameterDefinition("coarse_theta", "CoarseTheta", 5.0, 3.0, "log", notes="CoarseThetaWithoutMoveStage duration"),
    ParameterDefinition("finealign", "Finealign", 10.0, 5.0, "log", notes="FineAlign Completed in ..."),
    ParameterDefinition("row_scan", "row scan", 1.36, 1.15, "log", notes="Row scan Done in ..."),
    ParameterDefinition("cpas_priming", "cPAS primming", 40.0, 30.0, "derived", cycle_binding_rule="before_cycle", notes="cPAS reagent priming completed before cycle=n - start before cycle=n"),
    ParameterDefinition("cpas_time", "cPAS time", 360.0, 330.0, "derived", notes="cPAS completed for cycle=n - start for cycle=n"),
    ParameterDefinition("transfer_time", "transfer time", 20.0, 15.0, "derived", notes="Move slide from imager to chuck stage finished - start"),
    ParameterDefinition("temperature_rise_n", "temperature rise N", 13.0, 11.0, "derived", notes="Slide N set 58C"),
    ParameterDefinition("temperature_rise_f", "temperature rise F", 13.0, 11.0, "derived", notes="Slide F set 58C"),
    ParameterDefinition("temperature_drop_n", "temperature drop N", 13.0, 11.0, "derived", notes="Slide N set 15C"),
    ParameterDefinition("temperature_drop_f", "temperature drop F", 13.0, 11.0, "derived", notes="Slide F set 15C"),
    ParameterDefinition("row_scan_metric_avg", "row scan metric avg", None, None, "metrics", notes="94-row average metric duration per stage"),
]


ROW_SCAN_METRIC_STAGES = [
    "setup",
    "move2start",
    "setTDIdir",
    "caculateImageType",
    "waitForBCSRearyTime",
    "completeAcq",
    "sendrowInfo",
    "setupPEG",
    "endmove2start",
    "waitForAFTime",
    "enablePEG",
    "startAcqAndOpenLaser",
    "scan",
    "turnLaserOffTime",
    "scanTotalTime",
]


DIRECT_DURATION_RULES = [
    {
        "parameter_name": "coarse_theta",
        "display_name": "CoarseTheta",
        "matchers": ["coarsethetawithoutmovestage"],
        "threshold_seconds": 5.0,
        "expected_seconds": 3.0,
    },
    {
        "parameter_name": "finealign",
        "display_name": "Finealign",
        "matchers": ["finealign"],
        "threshold_seconds": 10.0,
        "expected_seconds": 5.0,
    },
    {
        "parameter_name": "row_scan",
        "display_name": "row scan",
        "matchers": ["row scan done"],
        "threshold_seconds": 1.36,
        "expected_seconds": 1.15,
    },
]


PAIRING_RULES: list[PairingRule] = [
    PairingRule(
        parameter_name="transfer_time",
        display_name="transfer time",
        start_pattern=re.compile(r"move slide from imager to chuck stage start\.?\s*([A-Za-z]\d+)?", re.I),
        end_pattern=re.compile(r"move slide from imager to chuck stage finished\.?\s*([A-Za-z]\d+)?", re.I),
        slide_from_match=True,
        threshold_seconds=20.0,
        expected_seconds=15.0,
        notes="机械臂转移时间",
    ),
    PairingRule(
        parameter_name="cpas_priming",
        display_name="cPAS primming",
        start_pattern=re.compile(r"([A-Za-z]\d+)\s+cpas reagent priming start before cycle\s*=\s*(\d+)", re.I),
        end_pattern=re.compile(r"([A-Za-z]\d+)\s+cpas reagent priming completed before cycle\s*=\s*(\d+)", re.I),
        cycle_from_match=True,
        slide_from_match=True,
        threshold_seconds=40.0,
        expected_seconds=30.0,
        notes="cPAS 预吸液时间",
    ),
    PairingRule(
        parameter_name="cpas_time",
        display_name="cPAS time",
        start_pattern=re.compile(r"([A-Za-z]\d+)\s+cpas start for cycle\s*=\s*(\d+)", re.I),
        end_pattern=re.compile(r"([A-Za-z]\d+)\s+cpas completed for cycle\s*=\s*(\d+)", re.I),
        cycle_from_match=True,
        slide_from_match=True,
        threshold_seconds=360.0,
        expected_seconds=330.0,
        notes="cPAS 时间",
    ),
    PairingRule(
        parameter_name="imaging_time",
        display_name="imaging time",
        start_pattern=re.compile(r"imaging at cycle\s*=?\s*(\d+)", re.I),
        end_pattern=re.compile(r"imaging complete(?:d)? for cycle\s*=?\s*(\d+)", re.I),
        cycle_from_match=True,
        threshold_seconds=150.0,
        expected_seconds=125.0,
        notes="拍照时间旧口径",
    ),
    PairingRule(
        parameter_name="imaging_time_real",
        display_name="imaging time real",
        start_pattern=re.compile(r"imaging start for cycle\s*=?\s*(\d+)", re.I),
        end_pattern=re.compile(r"imaging complete(?:d)? for cycle\s*=?\s*(\d+)", re.I),
        cycle_from_match=True,
        threshold_seconds=150.0,
        expected_seconds=125.0,
        notes="拍照时间真实口径",
    ),
    PairingRule(
        parameter_name="temperature_rise_n",
        display_name="temperature rise N",
        start_pattern=re.compile(r"setslidetemperature:\s*slide\s*N\s*setting temperature to\s*(\d+(?:\.\d+)?)", re.I),
        end_pattern=re.compile(r"setslidetemperature:\s*slide\s*N\s*successfully set temperature to\s*(\d+(?:\.\d+)?)", re.I),
        threshold_seconds=13.0,
        expected_seconds=11.0,
        target_temp=58.0,
        notes="升温时间 N",
    ),
    PairingRule(
        parameter_name="temperature_rise_f",
        display_name="temperature rise F",
        start_pattern=re.compile(r"setslidetemperature:\s*slide\s*F\s*setting temperature to\s*(\d+(?:\.\d+)?)", re.I),
        end_pattern=re.compile(r"setslidetemperature:\s*slide\s*F\s*successfully set temperature to\s*(\d+(?:\.\d+)?)", re.I),
        threshold_seconds=13.0,
        expected_seconds=11.0,
        target_temp=58.0,
        notes="升温时间 F",
    ),
    PairingRule(
        parameter_name="temperature_drop_n",
        display_name="temperature drop N",
        start_pattern=re.compile(r"setslidetemperature:\s*slide\s*N\s*setting temperature to\s*(\d+(?:\.\d+)?)", re.I),
        end_pattern=re.compile(r"setslidetemperature:\s*slide\s*N\s*successfully set temperature to\s*(\d+(?:\.\d+)?)", re.I),
        threshold_seconds=13.0,
        expected_seconds=11.0,
        target_temp=15.0,
        notes="降温时间 N",
    ),
    PairingRule(
        parameter_name="temperature_drop_f",
        display_name="temperature drop F",
        start_pattern=re.compile(r"setslidetemperature:\s*slide\s*F\s*setting temperature to\s*(\d+(?:\.\d+)?)", re.I),
        end_pattern=re.compile(r"setslidetemperature:\s*slide\s*F\s*successfully set temperature to\s*(\d+(?:\.\d+)?)", re.I),
        threshold_seconds=13.0,
        expected_seconds=11.0,
        target_temp=15.0,
        notes="降温时间 F",
    ),
]


def parameter_definition_map() -> dict[str, ParameterDefinition]:
    return {d.parameter_name: d for d in PARAMETER_DEFINITIONS}
