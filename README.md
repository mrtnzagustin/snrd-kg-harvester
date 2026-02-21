# snrd-neo4j-kg-harvester

CLI headless (Python 3.11+) para cosechar registros SNRD (VuFind API) y construir un KG en Neo4j.

## Validación contra Swagger (y decisión de estrategia)

Se implementó en base a los endpoints y parámetros indicados en la especificación oficial:
- `/vufind/api/v1/search`
- `/vufind/api/v1/record`
- params: `lookfor`, `type`, `field[]`, `filter[]`, `facet[]`, `sort`, `page`, `limit`, `id[]`

> Nota de entorno CI: desde este contenedor no fue posible descargar el swagger remoto (`403 CONNECT tunnel failed`), por lo que se usó como contrato la documentación que pasaste y se codificó con compatibilidad VuFind/Solr.

### Plan implementado (dual obligatorio)

Siempre se generan archivos Cypher en disco. Hay dos modos:
- **offline**: genera cypher + manifiestos + checkpoint state
- **online**: genera cypher + manifiestos + checkpoint state + aplica a Neo4j

Además, se usa estrategia `record_strategy=auto`:
- intenta usar `/search` si los campos vienen completos,
- cae a `/record` por lotes (`id[]`) si faltan campos clave.

## Instalación

### Con pip
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Con uv
```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Variables de entorno (.env)

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j
SNRD_BASE_URL=https://repositoriosdigitales.mincyt.gob.ar
```

## Comandos CLI

### Inicializar constraints
```bash
snrd-kg init-neo4j
```

### Backfill por rango de fechas (online)
```bash
snrd-kg harvest \
  --from-date 2022-01-01 \
  --until-date 2022-12-31 \
  --lookfor "*" \
  --type AllFields \
  --sort "publishDate asc" \
  --batch-size 30
```

### Incremental (desde última fecha)
```bash
snrd-kg harvest --from-date 2025-01-01 --until-date 2025-12-31 --window-size month
```

### Solo generar cypher (offline)
```bash
snrd-kg harvest --from-date 2023-01-01 --until-date 2023-01-31 --only-generate --no-apply
```

### Resume (reaplica pendientes sin volver a API)
```bash
snrd-kg resume
```

### Replay por ventana (sin API)
```bash
snrd-kg replay --from 2023-01-01__2023-01-31 --until 2023-03-01__2023-03-31
```

## Estructura de salida

- Cypher: `out/cypher/<window>/<page>/batch_<n>.cypher`
- Manifiestos: `out/manifests/<window>/<page>.json`
- Checkpoints sqlite: `state/checkpoints.sqlite3`
- Alternativa checkpoint json: `state/checkpoints.json`

## Fallback de filtro por fecha

Se intenta en este orden:
1. `publishDate:[YYYY-MM-DD TO YYYY-MM-DD]`
2. `publishDate:[YYYY-01-01 TO YYYY-12-31]`
3. `publishDate:YYYY`

Si una forma falla (error HTTP/parse), se prueba la siguiente automáticamente.
