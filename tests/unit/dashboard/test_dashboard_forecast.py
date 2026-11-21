"""016 T5-T6: forecast rows in the run view and the forecast payload (R12-R16; E15-E21)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
import trace_builders
from forecast_builders import SB, P, fc, forecast_calendar, forecast_view, fr, ft, plan_rows

from plant_monitor.cases.registry.run_reader import read_run_rows
from plant_monitor.config import Settings
from plant_monitor.dashboard.forecast import build_forecast
from plant_monitor.dashboard.source import Calendar, RunView, load_view
from plant_monitor.dashboard.state import build_state
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.enums import Market, Model, Severity
from plant_monitor.domain.forecast import ForecastRow
from plant_monitor.domain.models import Combination
from plant_monitor.ingestion.plant import load_shifts

from builders import isolate_settings_env

thresholds_dir = trace_builders.thresholds_dir
copied = trace_builders.copied

CLOSED_ROWS = 2


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _e15_rows() -> list[ForecastRow]:
    """E1's nine rows at S008 with an SB warning, after P's seven earlier rows."""
    earlier = [fr(k, "warm_up") for k in (1, 2, 3)] + [fr(k, "no_crossing") for k in (4, 5, 6, 7)]
    at_8 = [
        fr(8, "warning", combo=SB, points=3, crossing=9) if row.combination == SB else row
        for row in fc(8, 92, 52, plan=plan_rows(24))
    ]
    return [*earlier, *at_8]


def _e16_rows() -> list[ForecastRow]:
    """P's rows of E16: two warnings that a crossing at S011 fulfils."""
    return [
        fr(9, "warning", points=3, crossing=11),
        fr(10, "warning", points=3, crossing=11),
        fr(11, "no_crossing", gap=Severity.MEDIUM),
    ]


def _entry(payload: dict[str, Any], key: str = "combinations") -> dict[str, Any]:
    """Pickup and Local's entry of 'key'."""
    entry: dict[str, Any] = next(
        e for e in payload[key] if (e["modelo"], e["mercado"]) == (str(P.modelo), str(P.mercado))
    )
    return entry


def test_e15_warnings_are_ordered_by_hours_and_carry_the_basis_and_the_charts() -> None:
    """016 E15 (R11, R13; I11): SB (4 h) before P (8 h); P's basis, history and projection."""
    payload = ft(_e15_rows(), 8)
    assert [(w["modelo"], w["mercado"]) for w in payload["warnings"]] == [
        (str(SB.modelo), str(SB.mercado)),
        (str(P.modelo), str(P.mercado)),
    ]
    assert payload["warnings"][0]["label"] == "S009 · 18:00 (en 4 h)"
    p_warning = payload["warnings"][1]
    assert p_warning["label"] == "S010 · 22:00 (en 8 h)"
    assert p_warning["basis"] == {
        "rate": "10.00",
        "plan_per_snapshot": "12.00",
        "window": "S005–S008",  # noqa: RUF001
        "threshold": "7.2",
    }
    p = _entry(payload)
    assert [h["seq"] for h in p["history"]] == list(range(1, 9))
    assert p["history"][-1]["gap"] == pytest.approx(-4.0)
    assert [pt["gap"] for pt in p["projection"]] == pytest.approx([-6.0, -8.0, -10.0])
    lines = {"media": -7.2, "alta": -14.4, "critica": -25.2}
    assert all(pt["lines"] == pytest.approx(lines) for pt in p["projection"])


@pytest.mark.parametrize(
    ("at", "outcome", "crossing", "lead", "mean", "labels"),
    [
        (11, "fulfilled", "S011", 8, "8.0", []),
        (10, "pending", None, None, None, ["S011 · 02:00 (en 4 h)"]),
    ],
)
def test_e16_episode_is_fulfilled_by_the_crossing_or_still_pending(
    at: int, outcome: str, crossing: str | None, lead: int | None, mean: str | None, labels: list[str]
) -> None:
    """016 E16 (R14): the S009-S010 episode is fulfilled at 11 with 8 h lead; at 10 it is pending."""
    payload = ft(_e16_rows(), at)
    counts = {"fulfilled": 0, "not_fulfilled": 0, "pending": 0, "missed": 0, "no_forecast": 0}
    counts[outcome] = 1
    assert payload["accuracy"]["counts"] == counts
    assert payload["accuracy"]["mean_lead_hours"] == mean
    assert payload["accuracy"]["episodes"] == [
        {
            "modelo": str(P.modelo),
            "mercado": str(P.mercado),
            "level": "media",
            "first": "S009",
            "last": "S010",
            "outcome": outcome,
            "crossing": crossing,
            "lead_hours": lead,
        }
    ]
    assert [w["label"] for w in payload["warnings"]] == labels


@pytest.mark.parametrize(("at", "outcome"), [(15, "pending"), (16, "not_fulfilled")])
def test_e17_episode_is_not_fulfilled_once_its_deadline_is_reached(at: int, outcome: str) -> None:
    """016 E17 (R14, X5): no crossing; pending before the deadline S016, not fulfilled at it."""
    rows = [fr(13, "warning", points=3, crossing=16), *(fr(k, "no_crossing") for k in (14, 15, 16))]
    counts = ft(rows, at)["accuracy"]["counts"]
    assert counts[outcome] == 1
    assert sum(counts.values()) == 1


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([fr(17, "no_crossing"), fr(18, "no_crossing", gap=Severity.MEDIUM)], "missed"),
        ([fr(3, "warm_up"), fr(4, "no_crossing", gap=Severity.MEDIUM)], "no_forecast"),
        ([fr(20, "suppressed"), fr(21, "no_crossing", gap=Severity.MEDIUM)], "no_forecast"),
    ],
    ids=["a_missed", "b_after_warm_up", "c_after_suppressed"],
)
def test_e18_a_crossing_without_a_warning_is_missed_or_had_no_forecast(
    rows: list[ForecastRow], expected: str
) -> None:
    """016 E18 (R14; Q-131): after no_crossing it is 'missed'; after warm_up or suppressed 'no_forecast'."""
    counts = ft(rows, rows[-1].seq)["accuracy"]["counts"]
    assert counts[expected] == 1
    assert sum(counts.values()) == 1


def test_x3_a_jump_from_none_to_alta_fulfils_a_media_episode_and_is_not_missed() -> None:
    """016 X3 (R14): ninguna to alta fulfils the media episode and is not also counted as missed."""
    rows = [
        fr(9, "warning", points=3, crossing=11),
        fr(10, "warning", points=3, crossing=11),
        fr(11, "no_crossing", gap=Severity.HIGH),
    ]
    counts = ft(rows, 11)["accuracy"]["counts"]
    assert (counts["fulfilled"], counts["missed"], counts["no_forecast"]) == (1, 0, 0)


def _stored(settings: Settings, rows: list[ForecastRow]) -> None:
    """Replace the registry's forecast rows with 'rows'."""
    with closing(sqlite3.connect(settings.registry_path)) as conn:
        conn.execute("DELETE FROM gap_forecasts")
        conn.executemany(
            "INSERT INTO gap_forecasts (seq, snapshot_id, modelo, mercado, status, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    r.seq,
                    r.snapshot_id,
                    str(r.combination.modelo),
                    str(r.combination.mercado),
                    r.status,
                    r.model_dump_json(),
                )
                for r in rows
            ],
        )
        conn.commit()


def _closed_view(
    base: Settings, tmp_path: Path, rows: list[ForecastRow] | None = None
) -> tuple[RunView, Calendar]:
    """A copy of TH_DIR with the guard closed and 'rows' (default FR at S009 to S012), loaded."""
    settings = copied(base, tmp_path).model_copy(update={"heldout_open": False})
    _stored(settings, [fr(k, "no_crossing") for k in (9, 10, 11, 12)] if rows is None else rows)
    shifts = load_shifts(settings.plant_dir / "turnos.csv")
    policy = HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)
    return (
        load_view(settings.registry_path, settings.traces_dir, policy),
        Calendar.load(settings.plant_dir, policy),
    )


@pytest.mark.parametrize("damage", ["v4_without_table", "invalid_payload"])
def test_e19_reader_gives_no_forecasts_for_a_v4_copy_or_an_invalid_payload(
    thresholds_dir: Settings, tmp_path: Path, damage: str
) -> None:
    """016 E19 (R12; I7): 'forecasts' is None, the other tables read as in the intact copy."""
    intact = read_run_rows(thresholds_dir.registry_path)
    assert intact is not None
    assert intact.forecasts
    settings = copied(thresholds_dir, tmp_path)
    with closing(sqlite3.connect(settings.registry_path)) as conn:
        if damage == "v4_without_table":
            conn.execute("DROP TABLE gap_forecasts")
            conn.execute("PRAGMA user_version = 4")
        else:
            conn.execute("UPDATE gap_forecasts SET payload = '{}' WHERE rowid = 1")
        conn.commit()
    damaged = read_run_rows(settings.registry_path)
    assert damaged is not None
    assert damaged.forecasts is None
    assert (damaged.processed, damaged.cases, damaged.history, damaged.notices) == (
        intact.processed,
        intact.cases,
        intact.history,
        intact.notices,
    )


def test_e20_load_view_omits_rows_of_refused_snapshots_and_counts_them(
    thresholds_dir: Settings, tmp_path: Path
) -> None:
    """016 E20 (R15; I7): with the guard closed S011 and S012 rows are omitted and counted."""
    view, _ = _closed_view(thresholds_dir, tmp_path)
    assert view.rows.forecasts is not None
    assert [r.snapshot_id for r in view.rows.forecasts] == ["S009", "S010"]
    assert view.omitted.forecast_rows == CLOSED_ROWS


def test_e20_payloads_report_the_omitted_rows_and_leave_the_state_block_as_014(
    thresholds_dir: Settings, tmp_path: Path
) -> None:
    """016 E20 (R15; I8): forecast 'heldout' counts 2 rows, no refused id; the state keeps 014's keys."""
    view, calendar = _closed_view(thresholds_dir, tmp_path)
    at = view.resolve_at(None)
    forecast = json.dumps(build_forecast(view, calendar, at))
    state = json.dumps(build_state(view, calendar, at))
    block = json.loads(forecast)["heldout"]
    assert block["open"] is False
    assert block["omitted"]["forecast_rows"] == CLOSED_ROWS
    assert set(block["omitted"]) == {"snapshots", "notices", "trace_lines", "forecast_rows"}
    for body in (forecast, state):
        assert not any(name in body for name in ("S011", "S012", "T06"))
    assert set(json.loads(state)["heldout"]["omitted"]) == {"snapshots", "notices", "trace_lines"}


def test_e20_rows_that_name_a_refused_snapshot_are_omitted_whole(
    thresholds_dir: Settings, tmp_path: Path
) -> None:
    """016 E20 (R15, Q-133; 014 R13): rows naming a refused snapshot are omitted whole, others stay."""
    other = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
    rows = [
        fr(8, "warning", points=2, crossing=10),  # names S009-S010 only: stays
        fr(9, "warning", points=3, crossing=11),  # points and crossing name refused ids
        fr(10, "no_crossing", combo=SB, points=2),  # points only
        fr(10, "warning", combo=other, crossing=11),  # crossing only
        fr(10, "no_crossing"),  # names nothing: stays
    ]
    view, calendar = _closed_view(thresholds_dir, tmp_path, rows)
    assert view.rows.forecasts is not None
    assert [(r.seq, r.combination) for r in view.rows.forecasts] == [(8, P), (10, P)]
    assert view.omitted.forecast_rows == 3
    at = view.resolve_at(None)
    forecast = json.dumps(build_forecast(view, calendar, at))
    state = build_state(view, calendar, at)
    cells = json.dumps([cell["forecast"] for cell in state["cells"]])
    for body in (forecast, cells):
        assert not any(name in body for name in ("S011", "S012"))


@pytest.mark.parametrize(
    ("at", "marked"),
    [(10, {"target_level": "media", "label": "S011 · 02:00 (en 4 h)"}), (11, None)],
)
def test_e21_planta_cell_carries_the_marker_only_while_the_warning_is_active(
    at: int, marked: dict[str, str] | None
) -> None:
    """016 E21 (R16, R11): P's cell has 'forecast' at 10, every cell has null at 11."""
    view = forecast_view(_e16_rows())
    state = json.loads(json.dumps(build_state(view, forecast_calendar(), view.resolve_at(at))))
    forecasts = {(c["modelo"], c["mercado"]): c["forecast"] for c in state["cells"]}
    assert len(forecasts) == len(forecast_calendar().combinations)
    assert forecasts.pop((str(P.modelo), str(P.mercado))) == marked
    assert all(value is None for value in forecasts.values())
