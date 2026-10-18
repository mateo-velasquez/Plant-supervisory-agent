# data/

Series data for the (fictional) Las Acacias plant. **Not versioned**: only this README is.

## How to get it
Copy the course material into this folder, keeping this layout:

```
data/
├── snapshots/    # S001.json … + llegadas.csv (arrival order; one snapshot arrives twice)
├── planta/       # plan_produccion.csv, tiempos_estandar.csv, embarques.csv, turnos.csv
├── reglas/       # umbrales.yaml, criterio.md
└── bitacoras/    # T01.txt … T30.txt (one logbook per shift)
```

If the data lives elsewhere, point `DATA_DIR` in `.env` to it.

Tests do not depend on this folder: they use synthetic fixtures in `tests/fixtures/`.
