# 006 · Logbook store and MCP server — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `domain/verbatim.py` | New | `normalize_whitespace`, `contains_verbatim` (moved unchanged from `evaluation/golden.py`). |
| `domain/errors.py` | New | `RejectedRequest`: base of every refusal whose message is safe to show the model. |
| `domain/calendar.py` | Adds | `calendar_order`, `closed_shifts`; `HeldOutPolicy.from_calendar` uses `calendar_order`. |
| `evaluation/golden.py` | Changes | `from plant_monitor.domain.verbatim import contains_verbatim as contains_verbatim`; the local copy and `_collapse` are removed. |
| `logbooks/__init__.py` | New | Re-exports the store, the errors and `render_logbook`. |
| `logbooks/errors.py` | New | `UnknownLogbook`, `LogbookHeldOut`, `LogbookNotAvailable`, `EmptyFragment`, `FragmentNotFound`. |
| `logbooks/store.py` | New | `LogbookLoader`, `Logbook`, `LogbookStore`. |
| `logbooks/render.py` | New | `render_logbook` (R6). |
| `mcp_server/__init__.py` | New | Minimal: package docstring only. |
| `mcp_server/context.py` | New | `SnapshotFrame`, `FrameHolder`, `CaseReader`, `ToolContext`, `NoCurrentSnapshot`, `UnknownCase`. |
| `mcp_server/views.py` | New | View models and pure builders (R8–R11), floats rounded here. |
| `mcp_server/budget.py` | New | `to_text`, `fit_list`, `check_budget`, `OverBudget` (R12). |
| `mcp_server/read_tools.py` | New | The six tools as plain sync functions `(ctx, frames, args) -> str`; no `mcp` import. |
| `mcp_server/server.py` | New | `build_server(ctx, frames) -> MCPServer`: async wrappers, error mapping (R13). |
| `mcp_server/client.py` | New | `ToolClient`, `ToolSpec`, `ToolOutcome`: the only door `agents` uses (D4). |
| `config.py`, `.env.example` | Adds | `tool_output_max_chars`, `logbook_max_chars`. |
| `tests/fixtures/bitacoras/T01–T03.txt` | New | Synthetic logbooks of the spec's notation. |

## Types and interfaces

### `contains_verbatim`
`def contains_verbatim(text: str, fragment: str) -> bool` and `def normalize_whitespace(value: str) -> str`. Spec 005's behavior, byte for byte (E10, D2).

### `RejectedRequest`
`class RejectedRequest(Exception)`: `str(error)` is the message after the SDK prefix (R13). It is the single type `server.py` maps to `ToolError`, and write tools (007, 008) reuse it.

### `calendar_order`
`def calendar_order(shifts: Iterable[Shift]) -> tuple[Shift, ...]`: shifts sorted by `inicio`. It is the one ordering used by `HeldOutPolicy.from_calendar` and `closed_shifts`; 005's E4 must pass unchanged.

### `closed_shifts`
`def closed_shifts(shifts: Iterable[Shift], snapshot_id: str) -> tuple[Shift, ...]`: over `calendar_order` (mid, then closing per shift), the shifts whose `snapshot_cierre` position is ≤ the snapshot's position (D1). An unknown snapshot raises `ValueError`.

### Logbook errors
In `logbooks/errors.py`, subclasses of `RejectedRequest` with the R3 and R5 messages:
- `UnknownLogbook(turno_id)`;
- `LogbookHeldOut(turno_id)`;
- `LogbookNotAvailable(turno_id, snapshot_id, closes_at)`;
- `EmptyFragment(turno_id)`;
- `FragmentNotFound(turno_id)`.

### `LogbookLoader`
`LogbookLoader = Callable[[Path, Iterable[str], HeldOutPolicy], dict[str, str]]`: the signature of `read_logbook_texts`.

### `Logbook`
`@dataclass(frozen=True) class Logbook: turno_id: str; closed_at: str; text: str`. The raw loaded text (LF, no BOM).

### `LogbookStore`
`class LogbookStore`:
- `__init__(self, directory: Path, shifts: Sequence[Shift], policy: HeldOutPolicy, loader: LogbookLoader = read_logbook_texts) -> None`: opens nothing.
- `available(self, snapshot_id: str) -> tuple[tuple[str, str], ...]`: (`turno_id`, `closed_at`) pairs; `closed_shifts` minus `policy.refused_shifts` (R2).
- `get(self, turno_id: str, snapshot_id: str) -> Logbook`: R3 checks 1–3 in order, then `loader(directory, [turno_id], policy)` on a cache miss (R4).
- `verify_citation(self, turno_id: str, fragment: str, snapshot_id: str) -> None`: `get`, then the empty check on `normalize_whitespace(fragment)`, then `contains_verbatim` (R5).

### `render_logbook`
`def render_logbook(logbook: Logbook) -> str`: the R6 block. One compiled pattern, `(?i)<(/?bitacora)`, is replaced by `&lt;\1`; trailing `\n` are stripped first.

### `SnapshotFrame`
`@dataclass(frozen=True) class SnapshotFrame: snapshot_id: str; at: datetime; metrics: Mapping[Combination, CombinationMetrics]; units: tuple[Unit, ...]`. Built by the composition root (007) from what the pipeline already computed.

### `FrameHolder`
`class FrameHolder`:
- `current(self) -> SnapshotFrame` raises `NoCurrentSnapshot` (`no snapshot is being processed`).
- `entered(self, frame: SnapshotFrame) -> AbstractContextManager[None]`: `ValueError` if a frame is already entered; it always clears on exit.
- **Note for 007:** entering a frame checks `frame.snapshot_id == registry.current_snapshot()`. That check belongs to the composition root, because `mcp_server` does not know the registry type.

### `CaseReader`
`class CaseReader(Protocol)`: `active_cases() -> tuple[Case, ...]`, `get_case(case_id: str) -> Case | None`, `history(case_id: str) -> tuple[CaseHistoryRow, ...]`. `SqliteCaseRepository` satisfies it structurally. It is read-only by type (R14). The writer protocols of D3 (`CaseWriter`, `NoticeWriter`) are added to `ToolContext` by 007 and 008.

### `ToolContext`
`@dataclass(frozen=True) class ToolContext`, fixed per run:
- `plant: PlantContext` (shifts, standards, shipments, thresholds);
- `cases: CaseReader`, `logbooks: LogbookStore`;
- `view_max_chars: int`, `logbook_max_chars: int` (from `Settings`, passed in).

`UnknownCase(case_id)` is a `RejectedRequest`: `unknown case <id>`.

### View models
`mcp_server/views.py`, frozen pydantic models with Spanish field names from the output contract (ADR-0005):
- `DeviationRow` (R8 fields), `DeviationsView(snapshot_id, combinaciones)`;
- `ActiveCasesView(snapshot_id, casos: tuple[ActiveCaseRow, ...])`, via `cases.novelty.active_rows`;
- `LastReport`, `HistoryRow` (R10), `CaseView` (`historial` newest first, `historial_omitido: int = 0`);
- `AvailableLogbook(turno_id, cerrada_en)`, `LogbooksView(snapshot_id, disponibles)`;
- `DelayedUnit` (R11), `DelayedUnitsView(snapshot_id, modelo, mercado, etapa_cuello, unidades, omitidas: int = 0)`.

### View builders
They are pure and typed, and they round floats to 1 decimal themselves:
- `def deviations_view(frame: SnapshotFrame, active: Sequence[Case]) -> DeviationsView`
- `def active_cases_view(frame: SnapshotFrame, active: Sequence[Case]) -> ActiveCasesView`
- `def case_view(case: Case, history: Sequence[CaseHistoryRow], kept: int | None = None) -> CaseView`
- `def delayed_units_view(frame: SnapshotFrame, combination: Combination, plant: PlantContext, kept: int | None = None) -> DelayedUnitsView`

`kept` keeps the first `kept` list items and sets the omitted count. Delayed units reuse `is_delayed`, `projected_yard_arrival`, `reachable_shipment`, `unit_delay_days` and `bottleneck_stage`, with no formula duplicated.

### Budget
- `def to_text(view: BaseModel) -> str`: `json.dumps(view.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))`.
- `def fit_list(full: BaseModel, rebuild: Callable[[int | None], BaseModel], total: int, tool: str, max_chars: int) -> str`: tries the already-built `full` view, then `rebuild(k)` for decreasing `k` until the text fits. It raises `OverBudget` when even `rebuild(0)` does not fit. No field-name strings.
- `def check_budget(text: str, tool: str, max_chars: int) -> str`: returns `text` or raises `OverBudget`.
- `class OverBudget(RejectedRequest)`: `<tool> output is <n> characters, over the budget of <max>`. `get_logbook` logs its overflow at WARNING before raising.

### Read tools
Sync and pure, in `mcp_server/read_tools.py`, each `(ctx: ToolContext, frames: FrameHolder, …) -> str`:
- `list_available_logbooks`;
- `get_logbook(turno_id: str)`;
- `get_deviations`;
- `get_active_cases`;
- `get_case(case_id: str)`;
- `get_delayed_units(modelo: Model, mercado: Market)`.

Each one applies `check_budget` or `fit_list` itself.

### `build_server`
`def build_server(ctx: ToolContext, frames: FrameHolder) -> MCPServer` (`mcp.server.mcpserver`). It registers six **`async def`** wrappers under the names in `READ_TOOLS: Final[tuple[str, ...]]`. Each wrapper calls its sync tool directly, catches `RejectedRequest`, and raises `ToolError(str(error))` from it. Other exceptions are left to the SDK (R13). The model-visible signatures carry no snapshot argument; `modelo` and `mercado` are typed `Model` and `Market`.

### `ToolClient`
`class ToolClient` in `mcp_server/client.py` wraps `mcp.Client(server)` in-process (D4):
- `async def list_tools(self) -> tuple[ToolSpec, ...]`;
- `async def call(self, name: str, arguments: Mapping[str, object]) -> ToolOutcome`;
- it is an async context manager.

`ToolSpec(name: str, description: str, input_schema: Mapping[str, object])` and `ToolOutcome(text: str, is_error: bool)` are frozen dataclasses with no `mcp` types. `agents` (007) depends only on these.

### Settings
- `tool_output_max_chars: int = Field(default=4000, gt=0)`.
- `logbook_max_chars: int = Field(default=4000, gt=0)`: about 4× the longest of T01–T21 (999 characters).

## Design notes
- **Threading.** The SDK runs sync tools through `anyio.to_thread.run_sync`, and `SqliteRegistry` opens its connection with `check_same_thread=True`. Registering `async def` wrappers makes every tool run on the event-loop thread, which is the runner's thread under the in-process transport. **Never fix this with `check_same_thread=False`**: that would break the single-connection, single-thread writer of ADR-0003 and D3. E17 guards it with a real file-backed registry.
- **Why a frame, not an argument (R7).** Availability is a security property, so the snapshot comes from code. The holder is passed beside `ToolContext` because it changes per snapshot while the context is fixed per run.
- **Pure tools, thin server, thin client.** `read_tools.py` and `views.py` import no `mcp`. `server.py` registers tools and maps errors, and `client.py` converts to plain types. Write tools (007, 008) plug into the same context, gaining writer protocols (D3), and the same mapping.
- **One verbatim function** in `domain`, because both `logbooks` and `evaluation` may import `domain` and neither may import the other.
- **One loader, injected.** The store never touches the filesystem. The held-out refusal runs twice: once in the store, to give a clean message without opening anything, and again in `read_logbook_texts`. The 005 golden loader works the same way.
- **Order of checks** (unknown → held out → not closed) hides a held-out shift's timing.
- **Budgets are in characters**, which is deterministic and free. Per-request token limits are 007's guard (NFR-02). Logbooks get their own limit so a long logbook never competes with list truncation.
- **Dependency rule:** `agents → mcp_server (client) → cases / metrics / logbooks → domain`; `logbooks → ingestion → domain`. `mcp_server` never reads `config`.

## Test strategy
- **Unit (no MCP):** `calendar_order`, `closed_shifts` (E1–E2); the store with an injected spy loader (E4 check order, E5, E8–E9); `render_logbook` at text level (E6–E7); E10; settings (E19).
- **Through `ToolClient` over the in-process server** (`@pytest.mark.anyio`; anyio's pytest plugin ships with the SDK): E3, E4 messages, E6–E7 via `get_logbook`, E11–E17. One layer per rule: tool rules are asserted only at the client.
- **Fixtures:** `tests/fixtures/bitacoras/`; registry rows from `case_with` and `history_row` in `tests/builders.py`; frames from `metrics_with` and unit payloads. E17 uses a `tmp_path` `SqliteRegistry` inside `processing`.
- **Import scan:** extend `tests/unit/test_import_boundaries.py` (E18). Add `logbooks` to `SDK_FREE_PACKAGES`, keep `agents` forbidden from importing `mcp`, and add an allow-list for `mcp_server`.
- **Not tested here:** model behavior on injected text (009, 010 evals).

## Risks
- **Leaky views** blow the token budget. E15 guards it, and lists are truncatable by design.
- **Thread-affinity regressions** if a tool is registered sync: E17 fails.
- **Stale frame:** `entered` clears on exit, E11 covers calls outside a frame, and 007 checks the frame against the registry's current snapshot.
- **SDK API churn** (`mcp` 2.x `MCPServer` / `Client`, the error prefix text) is contained in `server.py` and `client.py`. E4 and E16 pin the visible text.
