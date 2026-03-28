from app.detectors.error_detection import normalize_error_signature
from app.schemas.common import NormalizedEvent


def build_event(message: str, *, level: str = "ERROR", method_name: str | None = None, exception_type: str | None = None, component: str | None = None) -> NormalizedEvent:
    return NormalizedEvent(
        source_file="a.log",
        parser_name="error_log",
        message=message,
        raw_text=message,
        level=level,
        method_name=method_name,
        exception_type=exception_type,
        component=component,
    )


def test_connection_lost_is_more_specific_than_timeout():
    event = build_event(
        "Ice.ConnectionLostException request id 123 timeout:285 at D:\\Code\\a.cs:445",
        method_name="SendFluidicsBoardInfos",
        exception_type="Ice.ConnectionLostException",
    )
    sig, family, severity = normalize_error_signature(event)
    assert sig is not None
    assert family == "connection_lost"
    assert severity == "error"
    assert event.extra_json["error_family_display"] == "连接中断"


def test_message_based_error_family_split_for_common_workflow_errors():
    cases = [
        ("Wait for AF timeout:0.200,final status:False", "af_timeout"),
        ("SlideVacuumON: Slide F vacuum adsorption start, sv:SV1_Adsorption, vp:VP1_Adsorption, ps:PS1_Gas, pressure threshold:-20, timeoutSec:10", "vacuum_pressure_timeout"),
        ("Sequencing not ready, cannot send remain time.", "sequencing_not_ready"),
        ("Skip setup runInfo the runinfo already setup:HLAB1078", "runinfo_state_conflict"),
        ("MoveAxisRelative [10,-10] at axis [X1,X2]", "motion_axis_error"),
        ("Reset XYZStage when image finished error, Traceback (most recent call last):", "stage_reset_error"),
        ("Run failed, Traceback (most recent call last):", "workflow_traceback"),
        ("Ending Status: Exception - \"C:\\ISW\\Scripts\\Imaging\\Giraffe_TDIImagingRunTwoDirectionOptimal.py\"", "script_execution_exception"),
        ("Imaging ISWDeviceException: Traceback (most recent call last):", "imaging_device_exception"),
        ("Script Message: Id: 183 StatusType: Warning Date: 2026/3/16 9:53:35 Message: Coarse theta 1: Color Channel3 NOT-registered   Status 1", "registration_alignment_warning"),
    ]

    for message, expected_family in cases:
        event = build_event(message, component="Workflow")
        sig, family, severity = normalize_error_signature(event)
        assert sig is not None
        assert family == expected_family, message
        assert severity == "error"


def test_unmatched_error_falls_back_to_general_error():
    event = build_event("Unhandled unexpected failure while switching workflow state")
    sig, family, severity = normalize_error_signature(event)
    assert sig is not None
    assert family == "general_error"
    assert severity == "error"
