from pathlib import Path

from app.normalizers.event_normalizer import normalize_record
from app.parsers.registry import ParserRegistry
from app.services.side_registry import TaskSideRegistry
from app.utils.side_inference import infer_scope_from_texts


SERVICE_ALL_A1_A2_LINES = """2026-03-27 10:02:10.2783 | T100Scheduler | INFO | 187 | Script2 | Set transfer slide data: StageKey: A2, SlideUniqueNo:40.M1_UR_HLAA2QY03263, SlideNo:1, SlotNo:2 | | SetTransferSlideData | D:\\Code\\T100Scheduler.cs:164
2026-03-27 10:52:02.0965 | T100Scheduler | INFO | 219 | Script2 | Set transfer slide data: StageKey: A1, SlideUniqueNo:40.M1_UL_HLAA1QY03261, SlideNo:1, SlotNo:0 | | SetTransferSlideData | D:\\Code\\T100Scheduler.cs:164
""".strip()


def test_side_inference_matches_real_filename_stagekey_sourcechuck_and_group_name():
    workflow = infer_scope_from_texts(
        source_file="T100_Workflow_SetupRun_All_A1.py",
        message="Script started",
        raw_text="",
    )
    assert workflow.side_scope == "A1"
    assert workflow.side_group == "A"

    stage_key = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-All.log",
        message="Set transfer slide data: StageKey: A2, SlideUniqueNo:40.M1_UR_HLAA2QY03263, SlideNo:1, SlotNo:2",
        raw_text="",
    )
    assert stage_key.side_scope == "A2"
    assert stage_key.stage_key == "A2"
    assert stage_key.slot_no == "2"
    assert stage_key.chip_name == "40.M1_UR_HLAA2QY03263"

    source_chuck = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-RobotScheduler_A-20260326.log",
        message="<<<<<<<< Slide:40.M1_UL_HLAA2QY03264,Position:Imager,SourceChuck:A2-2,SourceSlot:3 >>>>>>>>",
        raw_text="",
    )
    assert source_chuck.side_scope == "A2"
    assert source_chuck.side_group == "A"
    assert source_chuck.chuck_no == "A2-2"
    assert source_chuck.slot_no == "3"
    assert source_chuck.chip_name == "40.M1_UL_HLAA2QY03264"

    workflow_group = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-ScriptRunnerA1-20260327.log",
        message="Set transfer slides data start from Chuck 1, groupName:A1, slide_N:40.M1_UL_HLAA1QY03261, slide_F:40.M1_UR_HLAA1QY03262",
        raw_text="",
    )
    assert workflow_group.side_scope == "A1"
    assert workflow_group.chip_name == "40.M1_UL_HLAA1QY03261"
    assert workflow_group.chip_position == "Near"


def test_chip_registry_inherits_side_from_real_patterns():
    registry = TaskSideRegistry()
    registry.observe_event(
        source_file="Service-All-A1A2-subset.log",
        message="Set transfer slide data: StageKey: A2, SlideUniqueNo:40.M1_UR_HLAA2QY03263, SlideNo:1, SlotNo:2",
        raw_text="Set transfer slide data: StageKey: A2, SlideUniqueNo:40.M1_UR_HLAA2QY03263, SlideNo:1, SlotNo:2",
    )

    follow_up = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-ScriptRunnerA2-20260327.log",
        message="Basecall 2 setup slide 40.M1_UR_HLAA2QY03263 completed",
        raw_text="Basecall 2 setup slide 40.M1_UR_HLAA2QY03263 completed",
    )
    resolved = registry.resolve_inference(follow_up)

    assert resolved.chip_name == "40.M1_UR_HLAA2QY03263"
    assert resolved.side_scope == "A2"
    assert resolved.slot_no == "2"
    assert resolved.side_evidence.get("from_registry_chip") == "A2"


def test_side_inference_matches_cpas_priming_and_spray_message_patterns():
    priming_start = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-All_20260326_00.log",
        message="<<<<<<<< a2 cPAS reagent priming start before cycle= 1 >>>>>>>>",
        raw_text="",
    )
    assert priming_start.side_scope == "A2"
    assert priming_start.side_evidence.get("from_context") == "A2"

    priming_end = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-All_20260326_00.log",
        message="<<<<<<<< b1 cPAS reagent priming completed before cycle= 4, span time: 44.019s >>>>>>>>",
        raw_text="",
    )
    assert priming_end.side_scope == "B1"
    assert priming_end.side_evidence.get("from_context") == "B1"

    spray_message = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-RobotScheduler_A-20260326.log",
        message=r"Spray-A2 Fluidic\T100_Seg2_CpasReagentPrime.py status:Running, errorCode:",
        raw_text="",
    )
    assert spray_message.side_scope == "A2"
    assert spray_message.side_group == "A"
    assert spray_message.side_evidence.get("from_filename") == "A"
    assert spray_message.side_evidence.get("from_context") == "A2"
    assert spray_message.side_evidence.get("selected_side_source") == "from_context"

    spray_b1 = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-All_20260326_00.log",
        message=r"Spray-B1 Fluidic\T100_Seq2_CPAS.py status:Running, errorCode:",
        raw_text="",
    )
    assert spray_b1.side_scope == "B1"
    assert spray_b1.side_evidence.get("from_context") == "B1"


def test_side_inference_matches_standalone_side_tokens_in_message():
    token_only = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-All_20260326_00.log",
        message="device action a2 completed successfully",
        raw_text="",
    )
    assert token_only.side_scope == "A2"
    assert token_only.side_evidence.get("from_context") == "A2"

    token_overrides_coarse_filename = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-RobotScheduler_A-20260326.log",
        message="manual status b2 ready",
        raw_text="",
    )
    assert token_overrides_coarse_filename.side_scope == "B2"
    assert token_overrides_coarse_filename.side_evidence.get("from_filename") == "A"
    assert token_overrides_coarse_filename.side_evidence.get("from_context") == "B2"
    assert token_overrides_coarse_filename.side_evidence.get("selected_side_source") == "from_context"

    token_from_raw_text = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-All_20260326_00.log",
        message="status update",
        raw_text="operator note b1 finished",
    )
    assert token_from_raw_text.side_scope == "B1"
    assert token_from_raw_text.side_evidence.get("from_context") == "B1"

    bare_side_should_not_match = infer_scope_from_texts(
        source_file="ISW.ZebraMammoth.Service-All_20260326_00.log",
        message="device action A completed successfully",
        raw_text="",
    )
    assert bare_side_should_not_match.side_scope is None


def test_combined_service_all_log_is_split_by_event_side(tmp_path: Path):
    path = tmp_path / "Service-All-A1A2-subset.log"
    path.write_text(SERVICE_ALL_A1_A2_LINES, encoding="utf-8")

    parser_name, generator = ParserRegistry().parse_file(path)
    events = [normalize_record(record) for record in generator]

    assert parser_name == "service_log"
    assert len(events) == 2
    assert {event.side_scope for event in events} == {"A1", "A2"}
    assert {event.chip_name for event in events} == {"40.M1_UL_HLAA1QY03261", "40.M1_UR_HLAA2QY03263"}
