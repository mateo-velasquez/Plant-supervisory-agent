"""011 T5: idempotent repeats (E13) and a stable cached prefix over the IF series (E14)."""

import json
import logging
from pathlib import Path

import pytest
from incident_builders import INCIDENTS, incident_snapshot, write_incident_series
from multi_agent_builders import (
    HEAD,
    S002,
    S004,
    S005,
    S006,
    SECOND_START,
    STARTED,
    Recorder,
    out_files,
    query,
    run_full,
    run_ids,
    split_requests,
)

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.output import investigator_output_schema
from plant_monitor.agents.prefix import prefix_hash
from plant_monitor.config import Settings
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.ingestion.hashing import content_hash
from plant_monitor.telemetry.trace import trace_path

from builders import isolate_settings_env

TABLES = (
    "processed_snapshots",
    "known_units",
    "released_units",
    "cases",
    "case_history",
    "notices",
    "active_causes",
    "active_cause_links",
    "case_causes",
    "logbook_reviews",
    "anomalies",
)
SIX = tuple(f"S{n:03d}" for n in range(1, 7))
EIGHT = tuple(f"S{n:03d}" for n in range(1, 9))


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Default settings with the IF logbooks under 'data_dir'."""
    isolate_settings_env(monkeypatch, tmp_path)
    return Settings(anthropic_api_key="k", data_dir=INCIDENTS)


def rows_of(path: Path) -> dict[str, list[tuple[object, ...]]]:
    """Every row of every registry table, in a stable order."""
    return {t: sorted(query(path, f"SELECT * FROM {t}"), key=repr) for t in TABLES}


def test_e13_a_repeated_snapshot_sends_no_request_and_changes_nothing(
    tmp_path: Path, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """E13, R11, FR-02: identical and different-bytes repeats are skipped, with no write or delivery."""
    caplog.set_level(logging.INFO, logger="plant_monitor.runner.series")
    base = write_incident_series(tmp_path / "snapshots", SIX)
    first = [
        *base[:4],
        base[3].model_copy(update={"orden": 5}),
        base[4].model_copy(update={"orden": 6}),
        base[5].model_copy(update={"orden": 7}),
    ]
    root = tmp_path / "e13"
    path = root / "registry.sqlite3"
    model1 = FakeModel([*S002, *S004, *S005, *S006])
    summary1 = run_full(root, first, settings, model1, Recorder(), STARTED)
    assert len(model1.requests) == 10
    assert summary1.processed == SIX
    assert summary1.skipped == ("S004",)
    assert "S004 skipped: already processed" in caplog.messages
    before = rows_of(path)
    files_before = out_files(root / "out")

    bis_path = tmp_path / "snapshots" / "S005-bis.json"
    payload = incident_snapshot("S005")
    bis_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    h1 = content_hash((tmp_path / "snapshots" / "S005.json").read_bytes())
    h2 = content_hash(bis_path.read_bytes())
    bis = Arrival(orden=8, snapshot_id="S005", archivo=bis_path, recibido=base[4].recibido)
    caplog.clear()
    caplog.set_level(logging.INFO, logger="plant_monitor.runner.series")
    model2 = FakeModel([])
    recorder2 = Recorder()
    summary2 = run_full(root, [*first, bis], settings, model2, recorder2, SECOND_START)

    assert model2.requests == []
    assert summary2.processed == ()
    assert len(summary2.skipped) == 8
    assert [(a.kind.value, a.snapshot_id) for a in summary2.anomalies] == [
        ("repeated_with_different_content", "S005")
    ]
    assert (
        f"S005 repeated with different content (hash {h2}); first processed version (hash {h1}) kept"
        in caplog.messages
    )
    after = rows_of(path)
    assert len(after["anomalies"]) == len(before["anomalies"]) + 1
    assert {t: r for t, r in after.items() if t != "anomalies"} == {
        t: r for t, r in before.items() if t != "anomalies"
    }
    assert next(r for r in after["processed_snapshots"] if r[0] == "S005")[1] == h1
    assert recorder2.calls == []
    assert out_files(root / "out") == files_before
    assert not trace_path(root / "traces", SECOND_START).exists()


def test_e14_each_agent_keeps_one_prefix_hash_over_the_series(
    tmp_path: Path, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """E14, R2, R8, R9: one hash per agent, they differ, the format is the investigator's only."""
    caplog.set_level(logging.WARNING, logger="plant_monitor.agents.prefix")
    model, lines = run_ids(tmp_path / "e14", settings, HEAD, EIGHT)
    inv, coord = split_requests(model)
    inv_hashes = {c.prefix_hash for line in lines if line.investigator for c in line.investigator.model_calls}
    coord_hashes = {c.prefix_hash for line in lines for c in line.model_calls}
    assert len(inv_hashes) == 1
    assert len(coord_hashes) == 1
    assert inv_hashes != coord_hashes
    assert None not in coord_hashes
    assert coord_hashes == {prefix_hash(coord[0].system, coord[0].tools, None)}
    first = inv[0]
    assert inv_hashes == {prefix_hash(first.system, first.tools, first.output_schema)}
    assert [r.output_schema for r in inv] == [investigator_output_schema()] * len(inv)
    assert [r.output_schema for r in coord] == [None] * len(coord)
    assert [m for m in caplog.messages if "prefix changed" in m] == []
