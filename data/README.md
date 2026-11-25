# data/

Series data for the (fictional) Las Acacias plant, published with Taligent's permission ([ADR-0024](../docs/adr/0024-version-course-dataset.md)).

```
data/
├── snapshots/    # S001.json … S060.json + llegadas.csv (arrival order; one snapshot arrives twice)
├── planta/       # plan_produccion.csv, tiempos_estandar.csv, embarques.csv, turnos.csv
├── reglas/       # umbrales.yaml, criterio.md (the domain rules)
└── bitacoras/    # T01.txt … T30.txt (one logbook per shift)
```

- **Held-out days:** days 8–10 (shifts T22–T30, snapshots S043–S060) are the final test. The system reads them only with `HELDOUT_OPEN=true`.
- **Another location:** point `DATA_DIR` in `.env` to it.
- **Tests do not depend on this folder:** they use synthetic fixtures in `tests/fixtures/`.
