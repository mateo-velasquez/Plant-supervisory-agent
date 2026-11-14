"""010 T5: 'targets' keeps well-formed (case_id, notice, texto) triples (I4, E13d, E13e)."""

from hook_builders import PL, SE, SEDAN_LOCAL, SL, n_pl, sa, sr, view_v

from plant_monitor.hooks.calls import targets


def test_e13d_targets_of_a_report_drop_items_without_a_notice_or_a_string_texto() -> None:
    """010 E13d: only the item with news and a string 'texto' survives."""
    call = sr((PL, "t1"), (SEDAN_LOCAL, "t2"), (SE, 5))
    assert targets(call, view_v()) == ((PL, n_pl(), "t1"),)


def test_e13e_a_news_only_case_has_no_alert_target() -> None:
    """010 E13e: 'emit_alert' targets the alert notice, and SL has only news."""
    assert targets(sa(SL, "t"), view_v()) == ()
