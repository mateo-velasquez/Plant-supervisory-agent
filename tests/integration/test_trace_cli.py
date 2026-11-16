"""013 T2, T3, T9: the 'plant-monitor trace' command over synthetic runs, no model (E1-E8, E13)."""

import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import trace_builders
from cli_builders import cli_deps, cli_settings, write_cli_data
from incident_runs import F5
from multi_agent_builders import ALL, S002, S004, S005, SECOND_START, STARTED
from trace_builders import PRICES, copied, traced

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.model import ModelCallFailed
from plant_monitor.cases.registry.notice_reader import read_notice
from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.config import Settings
from plant_monitor.domain.notices import Notice
from plant_monitor.domain.stored import StoredNotice
from plant_monitor.runner.cli import main
from plant_monitor.telemetry.trace import read_trace_files
from plant_monitor.telemetry.trace_query import build_notice_trace

from builders import isolate_settings_env

PL_ALERT = "S010-alerta_inmediata-S010-Pickup-Local"
TH_ALERT = "S012-alerta_inmediata-S010-Pickup-Local"
SE_ALERT = "S005-alerta_inmediata-S005-SUV-Europa"
FIRST_FILE = "trace-20260302T230000Z.jsonl"
SECOND_FILE = "trace-20260302T233000Z.jsonl"

E1 = """\
notice S010-alerta_inmediata-S010-Pickup-Local
case S010-Pickup-Local, snapshot S010
type alerta_inmediata, estado escalado, severidad critica, severidad_maxima critica
metrics at S010: gap -4.0 units (-13.3 %), delay 0.0 days, bottleneck montaje
severity at S010: minimum media, effective critica, raised yes
transition: — → escalado (S010)
motivo: bitacora
severity set by: agente
text written by: agent
texto: "Agente: S010-alerta_inmediata-S010-Pickup-Local"
cause: parada_de_linea, etapa montaje, recorded at S010 from S010-causa-1
evidence:
  T05: "‹F5›"
active causes:
  S010-causa-1: parada_de_linea, Pickup in montaje, any market; linked at S010; in force at S010
    opened at S010 by T05: "‹F5›"
    raise opened at S010 (trace-20260302T230000Z.jsonl):
      investigator proposal {"id":"S010-p1","tipo":"raise","categoria":"parada_de_linea","etapa":"montaje","modelo":"Pickup","mercado":null,"bitacora":"T05","fragmento":"‹F5›","estado_causa":"activa_sin_fecha"}
      coordinator turn 1 apply_proposal {"propuesta":"S010-p1"}
trace: committed line in trace-20260302T230000Z.jsonl (decision call, reason text_needed)
investigator (outcome done, trigger review):
  turn 1 get_logbook {"turno_id":"T05"}
  proposal {"id":"S010-p1","tipo":"raise","categoria":"parada_de_linea","etapa":"montaje","modelo":"Pickup","mercado":null,"bitacora":"T05","fragmento":"‹F5›","estado_causa":"activa_sin_fecha"}
coordinator (outcome done):
  turn 1 apply_proposal {"propuesta":"S010-p1"} → this case
  turn 2 get_logbook {"turno_id":"T05"} [error: tool get_logbook is not allowed for the coordinator]
  turn 3 emit_alert {"case_id":"S010-Pickup-Local","texto":"Agente: S010-alerta_inmediata-S010-Pickup-Local"} → this case
  turn 3 emit_alert {"case_id":"S010-Pickup-Brasil","texto":"Agente: S010-alerta_inmediata-S010-Pickup-Brasil"}
  turn 3 emit_shift_report {"textos":[{"case_id":"S010-Pickup-Local","texto":"Agente: S010-informe_de_turno-S010-Pickup-Local"},{"case_id":"S010-Pickup-Brasil","texto":"Agente: S010-informe_de_turno-S010-Pickup-Brasil"}]} → this case
hooks:
  coordinator pre_tool allowlist (get_logbook, turn 2): tool get_logbook is not allowed for the coordinator
tokens at S010: input 15000, output 1000, cache read 0, cache write 0 (5m) 0 (1h), usd 0.00200000
""".replace("‹F5›", F5)  # noqa: E501, RUF001

E2 = """\
notice S012-alerta_inmediata-S010-Pickup-Local
case S010-Pickup-Local, snapshot S012
type alerta_inmediata, estado escalado, severidad critica, severidad_maxima critica
metrics at S012: gap -11.0 units (-36.7 %), delay 0.0 days, bottleneck none
severity at S012: minimum critica, effective critica, raised no
transition: en_seguimiento (S011) → escalado (S012)
motivo: gap
severity set by: umbral
text written by: template
texto: "<texto>"
cause: no_declarada, etapa none
evidence: none
active causes: none
trace: threshold-only run: no agent was involved
"""

E3 = """\
notice S005-alerta_inmediata-S005-SUV-Europa
case S005-SUV-Europa, snapshot S005
type alerta_inmediata, estado escalado, severidad critica, severidad_maxima critica
metrics at S005: gap -4.0 units (-13.3 %), delay 0.0 days, bottleneck calidad
severity at S005: minimum media, effective critica, raised yes
transition: — → escalado (S005)
motivo: bitacora
severity set by: agente
text written by: agent
texto: "Agente: S005-alerta_inmediata-S005-SUV-Europa"
cause: retencion_de_calidad, etapa calidad, recorded at S005 from S004-causa-1
evidence:
  T02: "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
active causes:
  S004-causa-1: retencion_de_calidad, SUV in calidad, Europa; linked at S005; in force at S005
    opened at S004 by T02: "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
    raise opened at S004 (trace-20260302T230000Z.jsonl):
      investigator proposal {"id":"S004-p1","tipo":"raise","categoria":"retencion_de_calidad","etapa":"calidad","modelo":"SUV","mercado":"Europa","bitacora":"T02","fragmento":"llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación","estado_causa":"activa_sin_fecha"}
      coordinator turn 1 apply_proposal {"propuesta":"S004-p1"}
trace: committed line in trace-20260302T230000Z.jsonl (decision call, reason text_needed)
coordinator (outcome done):
  turn 1 emit_alert {"case_id":"S005-SUV-Europa","texto":"Agente: S005-alerta_inmediata-S005-SUV-Europa"} → this case
hooks: none
tokens at S005: input 3000, output 200, cache read 0, cache write 0 (5m) 0 (1h), usd 0.00040000
"""  # noqa: E501

COMMITTED_S005 = "trace: committed line in trace-20260302T230000Z.jsonl (decision call, reason text_needed)"
ABORTED = (
    f"aborted attempt in {FIRST_FILE}: outcome aborted:ModelCallFailed, input 0, output 0,"
    " cache read 0, cache write 0 (5m) 0 (1h), usd 0.00000000"
)
E5 = E3.replace(
    COMMITTED_S005,
    f"trace: committed line in {SECOND_FILE} (decision call, reason text_needed)\n{ABORTED}",
)

agent_dir = trace_builders.agent_dir
thresholds_dir = trace_builders.thresholds_dir


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def test_e1_agent_alert_with_hook_block_matches_block_and_held_out_sets(
    agent_dir: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """E1: byte-exact stdout, and every snapshot and shift id printed is in the R11 shown sets."""
    code, out, err = traced(agent_dir, PL_ALERT, capsys)

    assert (code, err) == (0, "")
    assert out == E1
    stored = read_notice(agent_dir.registry_path, PL_ALERT)
    assert isinstance(stored, StoredNotice)
    view = build_notice_trace(stored, read_trace_files(agent_dir.traces_dir))
    assert set(re.findall(r"\bS\d{3}\b", out)) <= view.shown_snapshots()
    assert set(re.findall(r"\bT\d{2}\b", out)) <= view.shown_shifts()


def test_e2_threshold_only_alert_has_no_agent_trace(
    thresholds_dir: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """E2: byte-exact stdout of a threshold-only alert, with the stored 'texto'."""
    texto = next(
        n.texto for n in read_deliverables(thresholds_dir.registry_path)
        if isinstance(n, Notice) and n.notice_id == TH_ALERT
    )  # fmt: skip

    code, out, err = traced(thresholds_dir, TH_ALERT, capsys)

    assert (code, err) == (0, "")
    assert out == E2.replace("<texto>", texto)


def test_e3_raise_opened_at_another_snapshot(agent_dir: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    """E3: byte-exact stdout; the later lift of 'S004-causa-1' at S008 is not shown."""
    code, out, err = traced(agent_dir, SE_ALERT, capsys)

    assert (code, err) == (0, "")
    assert out == E3


@pytest.mark.parametrize(
    ("notice_id", "message"),
    [
        pytest.param(
            "S099-alerta_inmediata-S010-Pickup-Local",
            "unknown notice_id: S099-alerta_inmediata-S010-Pickup-Local",
            id="a-unknown",
        ),
        pytest.param(
            "T05-informe",
            "T05-informe is a shift report, not a notice; its novedades: "
            "S010-informe_de_turno-S010-Pickup-Local, S010-informe_de_turno-S010-Pickup-Brasil",
            id="b-report",
        ),
    ],
)
def test_e4_unknown_and_report_ids_exit_1(
    agent_dir: Settings, capsys: pytest.CaptureFixture[str], notice_id: str, message: str
) -> None:
    """E4a-b: an unknown id and a report id exit 1 with one stderr line and no stdout."""
    code, out, err = traced(agent_dir, notice_id, capsys)

    assert (code, out) == (1, "")
    assert err.splitlines() == [message]


@pytest.mark.parametrize(
    ("notice_id", "message"),
    [
        pytest.param(TH_ALERT, f"notice {TH_ALERT}: S012 is held out", id="a-notice"),
        pytest.param("T06-informe", "report T06-informe: S012 is held out", id="b-report"),
    ],
)
def test_e7_held_out_refusal_exit_2(
    thresholds_dir: Settings, capsys: pytest.CaptureFixture[str], notice_id: str, message: str
) -> None:
    """E7a-b: with the guard closed (first shift T06) a held-out notice or report exits 2, no stdout."""
    closed = thresholds_dir.model_copy(update={"heldout_open": False})

    code, out, err = traced(closed, notice_id, capsys)

    assert (code, out) == (2, "")
    assert err.splitlines() == [message]


def test_e8a_trace_reads_without_writing(
    thresholds_dir: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """E8a: Risk: a trace that migrates or journals the registry would change its bytes or the paths."""
    registry = thresholds_dir.registry_path
    digest = hashlib.sha256(registry.read_bytes()).hexdigest()
    paths = {p.relative_to(thresholds_dir.output_dir) for p in thresholds_dir.output_dir.rglob("*")}

    code, _out, _err = traced(thresholds_dir, TH_ALERT, capsys)

    assert code == 0
    assert hashlib.sha256(registry.read_bytes()).hexdigest() == digest
    assert {p.relative_to(thresholds_dir.output_dir) for p in thresholds_dir.output_dir.rglob("*")} == paths


def test_e8b_missing_registry_exit_2_and_nothing_created(
    thresholds_dir: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E8b: Risk: opening a missing registry for reading must not create it."""
    missing = tmp_path / "O2"

    code, _out, err = traced(thresholds_dir.model_copy(update={"output_dir": missing}), TH_ALERT, capsys)

    assert code == 2
    assert "registry not found" in err
    assert not missing.exists()


def test_e5_resumed_run_lists_aborted_attempt_and_reads_committed_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E5: a trace after a resumed run shows the second file's committed line and the first's abort."""
    data, out = write_cli_data(tmp_path / "data", ALL[:5]), tmp_path / "out"
    settings = cli_settings(data, out, **PRICES)
    failing = FakeModel([*S002, *S004, ModelCallFailed("create", 529)])
    assert main(["run"], deps=cli_deps(settings, failing, now=STARTED)) == 2
    assert main(["run"], deps=cli_deps(settings, FakeModel(S005), now=SECOND_START)) == 0
    capsys.readouterr()

    code, text, err = traced(settings, SE_ALERT, capsys)

    assert (code, err) == (0, "")
    assert text == E5


def test_e6_agent_mode_silence_with_no_agent(agent_dir: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    """E6: a 'sin_aviso' skipped without any agent says so, in order; E1 never does."""
    code, out, err = traced(agent_dir, "S007-sin_aviso-S005-SUV-Europa", capsys)

    assert (code, err) == (0, "")
    expected = [
        "type sin_aviso, estado escalado, severidad critica, severidad_maxima critica",
        "metrics at S007: gap 0.0 units (0.0 %), delay 0.0 days, bottleneck none",
        "severity at S007: minimum ninguna, effective critica, raised yes",
        "transition: escalado (S006) → escalado (S007)",
        "motivo: bitacora",
        "severity set by: agente",
        "text written by: template",
        f"trace: committed line in {FIRST_FILE} (decision skip, reason no_text_needed)",
        "agents: none, no agent was involved",
        "hooks: none",
        "tokens at S007: input 0, output 0, cache read 0, cache write 0 (5m) 0 (1h), usd 0.00000000",
    ]
    lines = out.splitlines()
    positions = [lines.index(line) for line in expected]
    assert positions == sorted(positions)
    assert "no agent was involved" not in E1


@pytest.mark.parametrize(
    ("which", "notice_id", "message"),
    [
        pytest.param(
            "thresholds",
            TH_ALERT,
            "traces: trace-20260301T000000Z.jsonl is not a readable trace file (ValidationError)",
            id="a-unreadable",
        ),
        pytest.param(
            "agent",
            SE_ALERT,
            f"traces: two committed lines for S005 ({FIRST_FILE}, trace-20260302T235900Z.jsonl)",
            id="b-duplicate-committed",
        ),
    ],
)
def test_e13_corrupt_traces_exit_2(
    thresholds_dir: Settings,
    agent_dir: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    which: str,
    notice_id: str,
    message: str,
) -> None:
    """E13a-b: an unreadable trace file and a duplicate committed line exit 2 with one 'traces: ' line."""
    settings = copied(thresholds_dir if which == "thresholds" else agent_dir, tmp_path)
    if which == "thresholds":
        settings.traces_dir.mkdir()
        (settings.traces_dir / "trace-20260301T000000Z.jsonl").write_text("{broken\n", encoding="utf-8")
    else:
        shutil.copy(settings.traces_dir / FIRST_FILE, settings.traces_dir / "trace-20260302T235900Z.jsonl")

    code, out, err = traced(settings, notice_id, capsys)

    assert (code, out) == (2, "")
    assert err.splitlines() == [message]


def test_x11_report_without_news_says_none(
    agent_dir: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """X11 (R3): a stored report with empty 'novedades' exits 1 with 'its novedades: none'."""
    settings = copied(agent_dir, tmp_path)
    with closing(sqlite3.connect(settings.registry_path)) as conn, conn:
        (payload,) = conn.execute("SELECT payload FROM notices WHERE notice_id = 'T05-informe'").fetchone()
        emptied = {**json.loads(payload), "novedades": []}
        conn.execute("UPDATE notices SET payload = ? WHERE notice_id = 'T05-informe'", (json.dumps(emptied),))

    code, out, err = traced(settings, "T05-informe", capsys)

    assert (code, out) == (1, "")
    assert err.splitlines() == ["T05-informe is a shift report, not a notice; its novedades: none"]
