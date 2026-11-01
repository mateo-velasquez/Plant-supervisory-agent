"""T3: typed loaders for the plant CSVs (BOM, ISO datetimes, row validation, plan completeness)."""

import codecs
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import PlanRow, Shift, Shipment, StandardTime
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
PLAN_CSV = "plan_produccion.csv"
STANDARDS_CSV = "tiempos_estandar.csv"
SHIPMENTS_CSV = "embarques.csv"
SHIFTS_CSV = "turnos.csv"
ALL_CSVS = [PLAN_CSV, STANDARDS_CSV, SHIPMENTS_CSV, SHIFTS_CSV]


def fixture_shifts() -> list[Shift]:
    """The three fixture shifts, built directly so plan tests don't depend on load_shifts."""
    raw = [
        ("T01", "2026-03-02T06:00", "2026-03-02T14:00", "S001", "S002"),
        ("T02", "2026-03-02T14:00", "2026-03-02T22:00", "S003", "S004"),
        ("T03", "2026-03-02T22:00", "2026-03-03T06:00", "S005", "S006"),
    ]
    return [
        Shift.model_validate(
            {"turno_id": t, "inicio": i, "fin": f, "snapshot_medio": m, "snapshot_cierre": c}
        )
        for t, i, f, m, c in raw
    ]


def load_any(path: Path) -> list[object]:
    """Dispatch to the loader that owns the file name."""
    loaders: dict[str, Callable[[Path], list[object]]] = {
        PLAN_CSV: lambda p: list(load_plan(p, fixture_shifts())),
        STANDARDS_CSV: lambda p: list(load_standards(p)),
        SHIPMENTS_CSV: lambda p: list(load_shipments(p)),
        SHIFTS_CSV: lambda p: list(load_shifts(p)),
    }
    return loaders[path.name](path)


def fixture_lines(name: str) -> list[str]:
    """Lines of a fixture CSV, BOM stripped."""
    return (FIXTURES / name).read_text(encoding="utf-8-sig").splitlines()


def write_csv(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write a CSV variant with a UTF-8 BOM, keeping the real file name."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig", newline="\n")
    return path


def set_cell(lines: list[str], line_no: int, column: str, value: str) -> list[str]:
    """Copy of lines with one cell replaced; line_no is the 1-based physical line (header = 1)."""
    header = lines[0].split(",")
    cells = lines[line_no - 1].split(",")
    cells[header.index(column)] = value
    out = list(lines)
    out[line_no - 1] = ",".join(cells)
    return out


def drop_column(lines: list[str], column: str) -> list[str]:
    """Copy of lines without one column."""
    idx = lines[0].split(",").index(column)
    return [",".join(c for i, c in enumerate(line.split(",")) if i != idx) for line in lines]


def plan_line_no(lines: list[str], shift: str, model: str, market: str) -> int:
    """Physical line number of a plan row by its shift and combination key."""
    for i, line in enumerate(lines, start=1):
        cells = line.split(",")
        if (cells[0], cells[3], cells[4]) == (shift, model, market):
            return i
    raise AssertionError(f"no plan row {shift} {model} {market}")


def plan_by_key(rows: list[PlanRow]) -> dict[tuple[str, Model, Market], int]:
    """Plan rows indexed by (turno_id, modelo, mercado)."""
    return {(r.turno_id, r.modelo, r.mercado): r.unidades_plan for r in rows}


def names_row(message: str, line_no: int) -> bool:
    """True if the message names the given row as `row N` or `line N`."""
    return re.search(rf"\b(?:row|line) {line_no}\b", message, flags=re.IGNORECASE) is not None


# --- error type ---


def test_data_load_error_is_a_value_error() -> None:
    assert issubclass(DataLoadError, ValueError)


# --- BOM ---


@pytest.mark.parametrize("name", ALL_CSVS)
def test_fixture_csvs_start_with_a_bom(name: str) -> None:
    assert (FIXTURES / name).read_bytes().startswith(codecs.BOM_UTF8)


def test_bom_stripped_plan_first_column_parsed() -> None:
    rows = load_plan(FIXTURES / PLAN_CSV, fixture_shifts())
    assert {r.turno_id for r in rows} == {"T01", "T02", "T03"}


def test_bom_stripped_standards_first_column_parsed() -> None:
    rows = list(load_standards(FIXTURES / STANDARDS_CSV))
    assert {r.modelo for r in rows} == {Model.SEDAN, Model.SUV, Model.PICKUP}


def test_bom_stripped_shipments_first_column_parsed() -> None:
    rows = list(load_shipments(FIXTURES / SHIPMENTS_CSV))
    assert "BRA-0304" in {r.embarque_id for r in rows}


def test_bom_stripped_shifts_first_column_parsed() -> None:
    shifts = load_shifts(FIXTURES / SHIFTS_CSV)
    assert [s.turno_id for s in shifts] == ["T01", "T02", "T03"]


# --- happy paths ---


def test_load_shifts_parses_iso_inicio_fin_and_snapshots() -> None:
    shifts = {s.turno_id: s for s in load_shifts(FIXTURES / SHIFTS_CSV)}
    assert all(isinstance(s, Shift) for s in shifts.values())
    assert shifts["T01"].inicio == datetime(2026, 3, 2, 6, 0)
    assert shifts["T01"].fin == datetime(2026, 3, 2, 14, 0)
    assert (shifts["T01"].snapshot_medio, shifts["T01"].snapshot_cierre) == ("S001", "S002")
    assert (shifts["T02"].snapshot_medio, shifts["T02"].snapshot_cierre) == ("S003", "S004")


def test_fecha_ignored_night_shift_ends_next_day_from_fin() -> None:
    t03 = next(s for s in load_shifts(FIXTURES / SHIFTS_CSV) if s.turno_id == "T03")
    assert t03.inicio == datetime(2026, 3, 2, 22, 0)
    assert t03.fin == datetime(2026, 3, 3, 6, 0)


@pytest.mark.parametrize("fecha", ["3/9/2026", "12/31/2026", "sin fecha"])
def test_fecha_ignored_in_favor_of_inicio_fin(tmp_path: Path, fecha: str) -> None:
    path = write_csv(tmp_path, SHIFTS_CSV, set_cell(fixture_lines(SHIFTS_CSV), 2, "fecha", fecha))
    t01 = next(s for s in load_shifts(path) if s.turno_id == "T01")
    assert t01.inicio == datetime(2026, 3, 2, 6, 0)
    assert t01.fin == datetime(2026, 3, 2, 14, 0)


def test_load_plan_returns_every_shift_combination_row() -> None:
    rows = load_plan(FIXTURES / PLAN_CSV, fixture_shifts())
    assert all(isinstance(r, PlanRow) for r in rows)
    assert len(rows) == 27
    by_key = plan_by_key(rows)
    assert by_key[("T01", Model.SEDAN, Market.LOCAL)] == 12
    assert by_key[("T02", Model.SUV, Market.EUROPE)] == 10
    assert by_key[("T03", Model.PICKUP, Market.BRAZIL)] == 10


def test_load_standards_values_from_worked_examples() -> None:
    rows = list(load_standards(FIXTURES / STANDARDS_CSV))
    assert all(isinstance(r, StandardTime) for r in rows)
    assert len(rows) == 12
    by_key = {(r.modelo, r.etapa): r for r in rows}
    assert by_key[(Model.SEDAN, Stage.ASSEMBLY)].minutos_estandar == 600
    assert by_key[(Model.SEDAN, Stage.QUALITY)].minutos_estandar == 180
    assert by_key[(Model.SUV, Stage.PAINT)].minutos_estandar == 480
    assert by_key[(Model.SUV, Stage.PAINT)].minutos_retrabajo == 360
    assert by_key[(Model.SUV, Stage.ASSEMBLY)].minutos_estandar == 660
    assert by_key[(Model.SUV, Stage.QUALITY)].minutos_estandar == 180


def test_load_standards_empty_rework_cell_is_none() -> None:
    rows = list(load_standards(FIXTURES / STANDARDS_CSV))
    assembly = next(r for r in rows if (r.modelo, r.etapa) == (Model.SUV, Stage.ASSEMBLY))
    assert assembly.minutos_retrabajo is None


def test_load_shipments_parses_iso_cutoff_and_departure() -> None:
    rows = {r.embarque_id: r for r in load_shipments(FIXTURES / SHIPMENTS_CSV)}
    assert all(isinstance(r, Shipment) for r in rows.values())
    assert rows["LOC-0302"].mercado is Market.LOCAL
    assert rows["LOC-0302"].corte_en_patio == datetime(2026, 3, 2, 14, 0)
    assert rows["LOC-0302"].salida == datetime(2026, 3, 2, 16, 0)
    assert rows["EUR-0305"].corte_en_patio == datetime(2026, 3, 4, 20, 0)
    assert rows["EUR-0305"].salida == datetime(2026, 3, 5, 14, 0)
    assert rows["EUR-0312"].salida == datetime(2026, 3, 12, 14, 0)


def test_fixture_brasil_shipments_end_at_bra_0304() -> None:
    brasil = [r for r in load_shipments(FIXTURES / SHIPMENTS_CSV) if r.mercado is Market.BRAZIL]
    last = max(brasil, key=lambda r: r.corte_en_patio)
    assert last.embarque_id == "BRA-0304"
    assert last.corte_en_patio == datetime(2026, 3, 4, 6, 0)


# --- malformed rows ---


@pytest.mark.parametrize(
    ("name", "field", "bad"),
    [
        (PLAN_CSV, "unidades_plan", "doce"),
        (PLAN_CSV, "unidades_plan", "-1"),
        (PLAN_CSV, "unidades_plan", ""),
        (PLAN_CSV, "mercado", "Chile"),
        (STANDARDS_CSV, "minutos_estandar", "seiscientos"),
        (STANDARDS_CSV, "etapa", "horno"),
        (SHIPMENTS_CSV, "corte_en_patio", "2026-03-02 14h"),
        (SHIPMENTS_CSV, "mercado", "Chile"),
        (SHIFTS_CSV, "inicio", "3/2/2026 06:00"),
        (SHIFTS_CSV, "fin", "mañana"),
    ],
)
def test_malformed_row_names_file_row_and_field(tmp_path: Path, name: str, field: str, bad: str) -> None:
    path = write_csv(tmp_path, name, set_cell(fixture_lines(name), 3, field, bad))
    with pytest.raises(DataLoadError) as info:
        load_any(path)
    message = str(info.value)
    assert name in message
    assert names_row(message, 3), message
    assert field in message


@pytest.mark.parametrize("name", ALL_CSVS)
def test_extra_trailing_cell_names_file_and_row(tmp_path: Path, name: str) -> None:
    lines = fixture_lines(name)
    lines[2] += ",extra"
    with pytest.raises(DataLoadError) as info:
        load_any(write_csv(tmp_path, name, lines))
    message = str(info.value)
    assert name in message
    assert names_row(message, 3), message


@pytest.mark.parametrize(
    ("name", "field"),
    [
        (PLAN_CSV, "unidades_plan"),
        (STANDARDS_CSV, "minutos_estandar"),
        (SHIPMENTS_CSV, "salida"),
        (SHIFTS_CSV, "snapshot_cierre"),
    ],
)
def test_missing_column_names_file_and_field(tmp_path: Path, name: str, field: str) -> None:
    path = write_csv(tmp_path, name, drop_column(fixture_lines(name), field))
    with pytest.raises(DataLoadError) as info:
        load_any(path)
    assert name in str(info.value)
    assert field in str(info.value)


# --- plan completeness ---


def test_plan_missing_combination_row_names_file_shift_and_combination(tmp_path: Path) -> None:
    lines = fixture_lines(PLAN_CSV)
    del lines[plan_line_no(lines, "T02", "SUV", "Brasil") - 1]
    with pytest.raises(DataLoadError) as info:
        load_plan(write_csv(tmp_path, PLAN_CSV, lines), fixture_shifts())
    message = str(info.value)
    assert PLAN_CSV in message
    assert "T02" in message
    assert "SUV" in message
    assert "Brasil" in message


def test_plan_shift_with_no_rows_fails_naming_the_shift(tmp_path: Path) -> None:
    lines = [line for line in fixture_lines(PLAN_CSV) if not line.startswith("T03,")]
    with pytest.raises(DataLoadError) as info:
        load_plan(write_csv(tmp_path, PLAN_CSV, lines), fixture_shifts())
    message = str(info.value)
    assert PLAN_CSV in message
    assert "T03" in message
    assert any(m.value in message for m in Model)
    assert any(m.value in message for m in Market)


def test_plan_explicit_zero_loads(tmp_path: Path) -> None:
    lines = fixture_lines(PLAN_CSV)
    lines = set_cell(lines, plan_line_no(lines, "T02", "SUV", "Europa"), "unidades_plan", "0")
    rows = load_plan(write_csv(tmp_path, PLAN_CSV, lines), fixture_shifts())
    assert len(rows) == 27
    assert plan_by_key(rows)[("T02", Model.SUV, Market.EUROPE)] == 0


@pytest.mark.parametrize("units", ["10", "7"], ids=["identical", "conflicting"])
def test_plan_duplicate_shift_combination_row_fails(tmp_path: Path, units: str) -> None:
    lines = fixture_lines(PLAN_CSV)
    lines.append(f"T01,3/2/2026,mañana,Pickup,Local,{units}")
    with pytest.raises(DataLoadError) as info:
        load_plan(write_csv(tmp_path, PLAN_CSV, lines), fixture_shifts())
    message = str(info.value)
    assert PLAN_CSV in message
    assert "T01" in message
    assert "Pickup" in message
    assert "Local" in message


def test_plan_row_for_shift_absent_from_turnos_fails(tmp_path: Path) -> None:
    lines = fixture_lines(PLAN_CSV)
    lines.append("T99,3/9/2026,noche,Sedán,Local,12")
    with pytest.raises(DataLoadError) as info:
        load_plan(write_csv(tmp_path, PLAN_CSV, lines), fixture_shifts())
    message = str(info.value)
    assert PLAN_CSV in message
    assert "T99" in message
    assert "Sedán" in message
    assert "Local" in message


def test_plan_rows_for_shift_not_passed_in_fail() -> None:
    shifts = [s for s in fixture_shifts() if s.turno_id != "T03"]
    with pytest.raises(DataLoadError) as info:
        load_plan(FIXTURES / PLAN_CSV, shifts)
    assert PLAN_CSV in str(info.value)
    assert "T03" in str(info.value)
