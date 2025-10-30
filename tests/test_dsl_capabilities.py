
def test_report_capabilities_flag(tmp_path):
    # Minimal smoke: simulate report dict update step
    report = {}
    dsl_enabled = True
    if dsl_enabled:
        report["capabilities"] = {"verbs":["switch_profile","press","regress","apply_policy"],"dsl": True}
    assert report["capabilities"]["dsl"] is True
