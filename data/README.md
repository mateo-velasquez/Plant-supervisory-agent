# data/

Datos de la serie de la Planta Las Acacias (ficticia). **No se versionan**: solo este README.

## Cómo obtenerlos
Copiar el material del curso a esta carpeta, respetando la estructura:

```
data/
├── snapshots/    # S001.json … + llegadas.csv (orden de llegada; uno llega dos veces)
├── planta/       # plan_produccion.csv, tiempos_estandar.csv, embarques.csv, turnos.csv
├── reglas/       # umbrales.yaml, criterio.md
└── bitacoras/    # T01.txt … T30.txt (una por turno)
```

Si los datos están en otra ubicación, apuntar `DATA_DIR` en `.env` hacia ella.

Los tests no dependen de esta carpeta: usan fixtures sintéticos en `tests/fixtures/`.
