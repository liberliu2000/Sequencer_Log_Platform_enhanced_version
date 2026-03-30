from app.utils.text import infer_cycle_from_text, infer_chip_name


def test_infer_cycle():
    assert infer_cycle_from_text("Cycle309_service.log", "Start step", "") == 309
    assert infer_cycle_from_text("a.log", "scanner S309 run", "") == 309


def test_infer_chip():
    assert infer_chip_name("chip_name=B1.log", "x", "") == "B1"
    assert infer_chip_name("a.log", "slide=SLIDE01", "") == "SLIDE01"
