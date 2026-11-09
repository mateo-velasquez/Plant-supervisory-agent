"""Synthetic builders for 008 cause evaluation tests: the T01-T21 calendar and notices with causes."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from plant_monitor.domain.causes import Cause, CauseCategory, Evidence
from plant_monitor.domain.enums import Stage
from plant_monitor.domain.models import Shift
from plant_monitor.domain.notices import Notice

_FIRST_START = datetime(2026, 3, 2, 6, 0)
_SHIFT_HOURS = 8
SHIFT_COUNT = 21


def t21_shifts() -> list[Shift]:
    """Shifts T01 to T21 where Tn has snapshots S(2n-1) and S(2n)."""
    shifts: list[Shift] = []
    for n in range(1, SHIFT_COUNT + 1):
        start = _FIRST_START + timedelta(hours=_SHIFT_HOURS * (n - 1))
        shifts.append(
            Shift(
                turno_id=f"T{n:02d}",
                inicio=start,
                fin=start + timedelta(hours=_SHIFT_HOURS),
                snapshot_medio=f"S{2 * n - 1:03d}",
                snapshot_cierre=f"S{2 * n:03d}",
            )
        )
    return shifts


def with_cause(
    notice: Notice, categoria: CauseCategory, etapa: Stage | None, evidence: Sequence[Evidence] = ()
) -> Notice:
    """A copy of 'notice' carrying the given cause and evidence, rebuilt through validation."""
    data = notice.model_dump()
    data["causa"] = Cause(categoria=categoria, etapa=etapa)
    data["evidencia"] = tuple(evidence)
    return Notice.model_validate(data)
