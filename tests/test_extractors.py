from app.utils.text import infer_cycle_from_text, infer_chip_name


def test_infer_cycle():
    assert infer_cycle_from_text("Cycle309_service.log", "Start step", "") == 309
    assert infer_cycle_from_text("a.log", "scanner S309 run", "") == 309


def test_infer_chip_from_real_patterns():
    assert (
        infer_chip_name(
            "ISW.ZebraMammoth.Service-All.log",
            "Set transfer slide data: StageKey: A2, SlideUniqueNo:40.M1_UR_HLAA2QY03263, SlideNo:1, SlotNo:2",
            "",
        )
        == "40.M1_UR_HLAA2QY03263"
    )
    assert (
        infer_chip_name(
            "ISW.ZebraMammoth.Service-ScriptRunnerA1-20260327.log",
            "Basecall 1 setup slide 40.M1_UL_HLAA1QY03261 completed",
            "",
        )
        == "40.M1_UL_HLAA1QY03261"
    )


def test_infer_chip_rejects_false_positives_from_real_logs():
    assert infer_chip_name("ISW.ZebraMammoth.Service-ScriptRunnerA1-20260327.log", "Start optical CPAS Workflow For Stage A1", "") is None
    assert (
        infer_chip_name(
            "ISW.ZebraMammoth.Service-ScriptRunnerA1-20260327.log",
            'A script file name C:\\ISW\\Scripts\\Workflows\\T100_Workflow_SetupRun_All_A1 - QY-0326.py is started TEST',
            "",
        )
        is None
    )
