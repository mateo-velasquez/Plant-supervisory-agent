"""005 T7: golden YAML models, 'load_golden' and 'contains_verbatim' (E1-E3, E5b-e, E30)."""

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.notices import Reason
from plant_monitor.evaluation.golden import GoldenSet, contains_verbatim, load_golden
from plant_monitor.ingestion.errors import DataLoadError

from builders import held_out_policy
from eval_builders import (
    PL,
    SEL,
    Item,
    fixture_shifts,
    golden_alert,
    golden_cause,
    golden_evidence,
    golden_file,
    golden_news,
    write_golden,
)

SE = "S003-SUV-Europa"
DAY_01 = "day_01.yaml"
DAY_02 = "day_02.yaml"
LOGBOOK = (
    "Producción: 40 de 45.\nAuditoría de homologación: retuvo en calidad\n"
    "las SUV de exportación hasta nuevo aviso.\n"
)


def _no_logbooks(ids: frozenset[str]) -> Mapping[str, str]:
    raise AssertionError(f"logbook reader called with {sorted(ids)}")


def _load(
    directory: Path,
    *,
    policy: HeldOutPolicy | None = None,
    logbooks: Callable[[frozenset[str]], Mapping[str, str]] = _no_logbooks,
) -> GoldenSet:
    chosen = policy if policy is not None else held_out_policy("T03", is_open=True)
    return load_golden(directory, fixture_shifts(), chosen, logbooks)


def _expect_error(
    directory: Path,
    tokens: tuple[str, ...],
    *,
    policy: HeldOutPolicy | None = None,
    logbooks: Callable[[frozenset[str]], Mapping[str, str]] = _no_logbooks,
) -> None:
    with pytest.raises(DataLoadError) as info:
        _load(directory, policy=policy, logbooks=logbooks)
    message = str(info.value)
    for token in tokens:
        assert token in message, f"{token!r} not in {message!r}"


def _valid() -> Item:
    return golden_file(["T01", "T02"], alerts=[golden_alert(SEL, "S003")], news=[golden_news("T01")])


# --- E1 ---


def test_e1_golden_load_with_labels_and_requires(tmp_path: Path) -> None:
    (tmp_path / "incidents.md").write_text("# not golden\n", encoding="utf-8")
    data = golden_file(
        ["T01", "T02"],
        alerts=[
            golden_alert(
                SEL,
                "S003",
                id="sel-escalates",
                motivo=["gap"],
                justification="criterio 2 y 4: escala en S003, gap -18 u (-50 %) llega a critica (35 %)",
            )
        ],
        news=[
            golden_news("T01", justification="criterio 4: caso nuevo; criterio 2: gap -12 u (-33 %) es alta"),
            golden_news(
                "T02",
                estado="escalado",
                severidad="critica",
                maxima="critica",
                justification="criterio 3 y 4: cambian estado y severidad",
            ),
        ],
        causes=[
            golden_cause(
                SEL,
                justification="criterio 6: ninguna bitácora nombra la causa; solo gap, sin cuello",
                depends_on=["Q-17"],
            )
        ],
    )
    write_golden(tmp_path, DAY_01, data)

    golden = _load(tmp_path)

    assert golden.covered_shifts == ("T01", "T02")
    (alert,) = golden.alerts
    assert alert.item.case.case_id == SEL
    assert alert.label == f"{DAY_01}#sel-escalates"
    assert alert.item.motivo == (Reason.GAP,)
    assert alert.item.requires == ()
    assert [n.label for n in golden.news] == [f"{DAY_01}#news[0]", f"{DAY_01}#news[1]"]
    (cause,) = golden.causes
    assert cause.item.etapa is None
    assert cause.item.depends_on == ("Q-17",)


def test_e1_files_load_in_name_order_and_covered_shifts_follow_the_calendar(tmp_path: Path) -> None:
    """Determinism (NFR-04): results follow file name order, whatever the creation order."""
    write_golden(tmp_path, DAY_02, golden_file(["T03"], alerts=[golden_alert(PL, "S005")]))
    write_golden(tmp_path, DAY_01, golden_file(["T01", "T02"], alerts=[golden_alert(SEL, "S003")]))

    golden = _load(tmp_path)

    assert [a.label for a in golden.alerts] == [f"{DAY_01}#alerts[0]", f"{DAY_02}#alerts[0]"]
    assert golden.covered_shifts == ("T01", "T02", "T03")


# --- E2: schema and file checks ---


def _raw_duplicate_key() -> str:
    return (
        "covers: [T01, T02]\n"
        "alerts:\n"
        '  - justification: "criterio 4: clave duplicada"\n'
        "    case: {modelo: Sedán, mercado: Local, abre_en: S001}\n"
        "    snapshot_id: S003\n"
        "    snapshot_id: S003\n"
    )


def _bad_case(**overrides: object) -> Item:
    case = golden_alert()["case"]
    assert isinstance(case, dict)
    return golden_file(["T01", "T02"], alerts=[golden_alert(case={**case, **overrides})])


def _with_cause(cause: Item, *, covers: tuple[str, ...] = ("T01", "T02")) -> Item:
    return golden_file(covers, alerts=[golden_alert(SEL, "S003")], news=[golden_news("T01")], causes=[cause])


E2_CASES: list[tuple[str, Callable[[], object], tuple[str, ...]]] = [
    (
        "a_extra_key",
        lambda: golden_file(["T01", "T02"], alerts=[golden_alert(severity="alta")]),
        ("severity",),
    ),
    (
        "b_missing_justification",
        lambda: golden_file(["T01"], news=[golden_news("T01", drop=["justification"])]),
        ("justification",),
    ),
    (
        "b_blank_justification",
        lambda: golden_file(["T01"], news=[golden_news("T01", justification="   ")]),
        ("justification",),
    ),
    (
        "b_justification_without_rule",
        lambda: golden_file(["T01"], news=[golden_news("T01", justification="new case")]),
        ("justification",),
    ),
    (
        "b_justification_with_criterio_but_no_number",
        lambda: golden_file(["T01"], news=[golden_news("T01", justification="criterio: caso nuevo")]),
        ("justification",),
    ),
    (
        "c_news_turno_not_in_covers",
        lambda: golden_file(["T01", "T02"], news=[golden_news("T03")]),
        ("news[0].turno_id", "T03", "not in covers"),
    ),
    (
        "d_alert_snapshot_outside_covered_shifts",
        lambda: golden_file(["T01", "T02"], alerts=[golden_alert(SEL, "S005")]),
        ("alerts[0].snapshot_id", "S005"),
    ),
    (
        "e_two_alerts_for_one_case",
        lambda: golden_file(["T01", "T02"], alerts=[golden_alert(SEL, "S003"), golden_alert(SEL, "S004")]),
        ("alerts[0]", "alerts[1]"),
    ),
    (
        "f_maxima_below_severity",
        lambda: golden_file(["T01"], news=[golden_news("T01", severidad="alta", maxima="media")]),
        ("severidad_maxima",),
    ),
    (
        "g_resolved_with_severity",
        lambda: golden_file(
            ["T01"], news=[golden_news("T01", "S001-Sedán-Local", "resuelto", "media", "media")]
        ),
        ("severidad",),
    ),
    (
        "h_depends_on_bad_shape",
        lambda: golden_file(["T01"], news=[golden_news("T01", depends_on=["Q17"])]),
        ("depends_on",),
    ),
    (
        "h_depends_on_duplicate",
        lambda: golden_file(["T01"], news=[golden_news("T01", depends_on=["Q-17", "Q-17"])]),
        ("depends_on",),
    ),
    (
        "h_requires_unknown_capability",
        lambda: golden_file(["T01"], news=[golden_news("T01", requires=["model"])]),
        ("requires",),
    ),
    (
        "h_requires_duplicate",
        lambda: golden_file(["T01"], news=[golden_news("T01", requires=["agent", "agent"])]),
        ("requires",),
    ),
    ("i_duplicate_yaml_key", _raw_duplicate_key, ("snapshot_id",)),
    ("j_integer_abre_en", lambda: _bad_case(abre_en=1), ("abre_en",)),
    ("j_scalar_covers", lambda: {**_valid(), "covers": "T01"}, ("covers",)),
    ("j_unknown_model", lambda: _bad_case(modelo="Camión"), ("modelo",)),
    (
        "k_cause_without_etapa",
        lambda: _with_cause(golden_cause(SEL, drop=["etapa"])),
        ("etapa",),
    ),
    (
        "l_report_cause_without_turno_id",
        lambda: _with_cause(golden_cause(SEL, "informe_de_turno")),
        ("turno_id",),
    ),
    (
        "l_alert_cause_with_turno_id",
        lambda: _with_cause(golden_cause(SEL, turno_id="T02")),
        ("turno_id",),
    ),
    (
        "m_report_cause_without_news_item",
        lambda: _with_cause(golden_cause(SEL, "informe_de_turno", turno_id="T02")),
        ("causes[0]",),
    ),
    (
        "n_alert_before_case_opens",
        lambda: golden_file(["T01", "T02"], alerts=[golden_alert("S004-Sedán-Local", "S003")]),
        ("abre_en",),
    ),
    ("o_empty_file", lambda: "", ()),
    ("o_top_level_list", lambda: "- a\n- b\n", ()),
    (
        "q_declared_cause_without_evidence",
        lambda: _with_cause(golden_cause(SEL, categoria="retencion_de_calidad", etapa="calidad")),
        ("evidencia",),
    ),
    (
        "q_undeclared_cause_with_evidence",
        lambda: _with_cause(golden_cause(SEL, evidencia=golden_evidence("T01", "x"))),
        ("evidencia",),
    ),
    (
        "r_bad_item_id",
        lambda: golden_file(["T01", "T02"], alerts=[golden_alert(SEL, "S003", id="Sel Escalates")]),
        ("id",),
    ),
    (
        "news_opened_after_its_shift_closes",
        lambda: golden_file(["T01"], news=[golden_news("T01", "S003-Sedán-Local")]),
        ("abre_en",),
    ),
    (
        "news_duplicate_turno_and_case",
        lambda: golden_file(["T01"], news=[golden_news("T01"), golden_news("T01")]),
        ("news",),
    ),
    ("covers_empty", lambda: golden_file([]), ("covers",)),
    ("covers_duplicate", lambda: golden_file(["T01", "T01"]), ("covers",)),
    (
        "abre_en_not_in_calendar",
        lambda: golden_file(["T01"], news=[golden_news("T01", "S099-Sedán-Local")]),
        ("abre_en",),
    ),
]


@pytest.mark.parametrize(("make", "tokens"), [pytest.param(m, t, id=name) for name, m, t in E2_CASES])
def test_e2_schema_and_file_checks_raise_a_load_error_naming_the_file(
    tmp_path: Path, make: Callable[[], object], tokens: tuple[str, ...]
) -> None:
    write_golden(tmp_path, DAY_01, make())
    _expect_error(tmp_path, (DAY_01, *tokens))


def test_e2p_directory_without_yaml_files_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "incidents.md").write_text("# catalog\n", encoding="utf-8")
    _expect_error(tmp_path, (str(tmp_path),))


def test_e2_item_ids_must_be_unique_within_a_file(tmp_path: Path) -> None:
    data = golden_file(
        ["T01", "T02"],
        alerts=[golden_alert(SEL, "S003", id="same")],
        news=[golden_news("T01", id="same")],
    )
    write_golden(tmp_path, DAY_01, data)
    _expect_error(tmp_path, (DAY_01, "same"))


# --- E3: cross-file checks ---


def test_e3a_a_shift_covered_by_two_files(tmp_path: Path) -> None:
    write_golden(tmp_path, DAY_01, golden_file(["T01", "T02"]))
    write_golden(tmp_path, DAY_02, golden_file(["T02", "T03"]))
    _expect_error(tmp_path, ("T02", DAY_01, DAY_02))


def test_e3b_an_alert_case_in_two_files(tmp_path: Path) -> None:
    write_golden(tmp_path, DAY_01, golden_file(["T02"], alerts=[golden_alert(SEL, "S003")]))
    write_golden(tmp_path, DAY_02, golden_file(["T03"], alerts=[golden_alert(SEL, "S005")]))
    _expect_error(tmp_path, (SEL, DAY_01, DAY_02))


def test_e3c_an_alert_cause_without_an_alert_item_for_its_case(tmp_path: Path) -> None:
    write_golden(tmp_path, DAY_01, golden_file(["T01"]))
    write_golden(tmp_path, DAY_02, golden_file(["T02"], causes=[golden_cause(PL)]))
    _expect_error(tmp_path, (f"{DAY_02}#causes[0]", PL))


def test_e3d_identical_causes_in_two_files(tmp_path: Path) -> None:
    write_golden(
        tmp_path, DAY_01, golden_file(["T02"], alerts=[golden_alert(SEL, "S003")], causes=[golden_cause(SEL)])
    )
    write_golden(tmp_path, DAY_02, golden_file(["T03"], causes=[golden_cause(SEL)]))
    _expect_error(tmp_path, (f"{DAY_01}#causes[0]", f"{DAY_02}#causes[0]"))


def test_e3e_the_same_id_in_two_files(tmp_path: Path) -> None:
    write_golden(tmp_path, DAY_01, golden_file(["T02"], alerts=[golden_alert(SEL, "S003", id="x")]))
    write_golden(tmp_path, DAY_02, golden_file(["T03"], alerts=[golden_alert(PL, "S005", id="x")]))
    _expect_error(tmp_path, (f"{DAY_01}#x", f"{DAY_02}#x"))


# --- E5b-e: held out ---


def _held_out_cases() -> list[tuple[str, Item, str]]:
    cause = golden_cause(
        SEL,
        "informe_de_turno",
        "retencion_de_calidad",
        "calidad",
        turno_id="T02",
        evidencia=golden_evidence("T03", "x"),
    )
    return [
        ("e5b_covers", golden_file(["T02", "T03"], news=[golden_news("T02"), golden_news("T03")]), "T03"),
        (
            "e5c_snapshot_before_coverage_check",
            golden_file(["T02"], alerts=[golden_alert(SEL, "S005")]),
            "S005",
        ),
        ("e5d_evidence_logbook", golden_file(["T02"], news=[golden_news("T02")], causes=[cause]), "T03"),
        ("turno_id_before_coverage_check", golden_file(["T02"], news=[golden_news("T03")]), "T03"),
        (
            "abre_en_before_order_check",
            golden_file(["T02"], news=[golden_news("T02", "S005-Sedán-Local")]),
            "S005",
        ),
    ]


@pytest.mark.parametrize(("data", "token"), [pytest.param(d, t, id=name) for name, d, t in _held_out_cases()])
def test_e5_closed_policy_refuses_held_out_ids_before_other_checks(
    tmp_path: Path, data: Item, token: str
) -> None:
    write_golden(tmp_path, DAY_01, data)
    _expect_error(tmp_path, (DAY_01, token, "held out"), policy=held_out_policy("T03"))


def test_e5e_the_open_policy_loads_a_file_that_covers_a_held_out_shift(tmp_path: Path) -> None:
    write_golden(tmp_path, DAY_01, golden_file(["T02", "T03"], news=[golden_news("T02"), golden_news("T03")]))
    golden = _load(tmp_path, policy=held_out_policy("T03", is_open=True))
    assert golden.covered_shifts == ("T02", "T03")


# --- E30: verbatim check and golden evidence ---


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        pytest.param("retuvo en calidad las SUV de exportación", True, id="a_line_break_normalized"),
        pytest.param("retuvo  en calidad\tlas SUV", True, id="b_runs_of_whitespace"),
        pytest.param("Retuvo en calidad", False, id="c_case_sensitive"),
        pytest.param("retuvo las SUV en calidad", False, id="d_order_matters"),
        pytest.param("", False, id="e_empty"),
        pytest.param("   ", False, id="e_blank"),
    ],
)
def test_e30_contains_verbatim(fragment: str, expected: bool) -> None:
    assert contains_verbatim(LOGBOOK, fragment) is expected


def _evidence_file(fragment: str) -> Item:
    news = golden_news("T02", SE, "abierto", "alta", "alta", requires=["agent"])
    cause = golden_cause(
        SE,
        "informe_de_turno",
        "retencion_de_calidad",
        "calidad",
        turno_id="T02",
        requires=["agent"],
        evidencia=golden_evidence("T02", fragment),
    )
    return golden_file(["T02"], news=[news], causes=[cause])


def test_e30f_a_fragment_in_its_logbook_loads_with_one_reader_call(tmp_path: Path) -> None:
    write_golden(tmp_path, DAY_02, _evidence_file("retuvo en calidad las SUV de exportación"))
    calls: list[frozenset[str]] = []

    def logbooks(ids: frozenset[str]) -> Mapping[str, str]:
        calls.append(ids)
        return {"T02": LOGBOOK}

    golden = _load(tmp_path, policy=held_out_policy("T03"), logbooks=logbooks)

    assert calls == [frozenset({"T02"})]
    assert golden.causes[0].item.evidencia is not None


def test_e30g_a_fragment_missing_from_its_logbook_is_a_load_error(tmp_path: Path) -> None:
    write_golden(tmp_path, DAY_02, _evidence_file("retuvo en calidad las SUV para Europa"))
    _expect_error(
        tmp_path,
        (f"{DAY_02}#causes[0]", "T02"),
        policy=held_out_policy("T03"),
        logbooks=lambda ids: {"T02": LOGBOOK},
    )


def test_e30_the_logbook_reader_is_not_called_when_another_check_fails(tmp_path: Path) -> None:
    """Spec: evidence is verified after every other check, so a file error never reads logbooks."""
    data = _evidence_file("retuvo en calidad las SUV de exportación")
    data["covers"] = ["T01"]
    write_golden(tmp_path, DAY_02, data)
    _expect_error(tmp_path, (DAY_02,), policy=held_out_policy("T03"))
