# Progreso

**Fase actual:** proyecto completo (v1.0.1). Verificación de requisitos en `docs/VERIFICACION.md`.

| Fase | Entregable | Aceptación | Estado | Tag | Fecha |
|---|---|---|---|---|---|
| 0 | Git, estructura, entorno, versiones exactas, script de modelos, lint/tests en verde | `pytest`, ruff, black, mypy pasan | Completada | v0.0.1 | 2026-10-19 |
| 1 | Core: scanner, detector, calidad, embedder, caché | Detecta y calcula embeddings en dataset de prueba; cobertura core ≥ 80 % | Completada | v0.1.0 | 2026-10-19 |
| 2 | Clustering + pipeline + CLI `scan --dry-run` | Agrupa dataset etiquetado con pureza ≥ 95 % | Completada | v0.2.0 | 2026-10-19 |
| 3 | Organizer: copiar/enlazar/mover, manifiesto, `undo` | Originales intactos (hash); undo restaura | Completada | v0.3.0 | 2026-10-19 |
| 4 | GUI: escaneo con progreso, revisión de grupos, aplicar | Flujo completo sin congelarse | Completada | v0.4.0 | 2026-10-19 |
| 5 | Duplicados: hashing exacto (SHA-256) + perceptual (dHash), servicio `dedupe`, CLI `dedupe`, pestaña GUI "Duplicados" con comparación lado a lado | Detecta el 100 % de duplicados exactos y los casi duplicados de un dataset sintético (redimensionado/recomprimido); nunca elimina todas las copias de un grupo; `undo` restaura; originales intactos por defecto | Completada | v0.5.0 | 2026-10-19 |
| 6 | Ajustes, reporte CSV, manejo de errores, docs finales (empaquetado .exe descartado por decisión del usuario) | Todo RF cumplido | Completada | v1.0.0 | 2026-10-19 |

## Pendientes y bloqueos
- Sin probar en macOS/Linux (RNF-05): no hay CI. Ver `docs/VERIFICACION.md`.

## Registro de sesiones
| Fecha | Qué se hizo | Siguiente paso |
|---|---|---|
| 2026-10-19 | Fase 0: git (main/develop), estructura `core/services/gui`, `config.py`, CLI esqueleto (`scan`, `gui`, `undo`), tests de humo, `.venv` con Python 3.12, versiones exactas, modelos ONNX descargados y verificados por SHA-256, lint/tests en verde | Fase 1: core (scanner, detector, calidad, embedder, caché) |
| 2026-10-19 | Fase 1: `scanner`, `image_io` (EXIF, HEIC), detector YuNet con reescalado, `Embedder` + SFace, filtro de calidad, caché SQLite (ADR 0004), script LFW. En LFW: 100 % de detección (300 fotos/60 personas), vecino más cercano correcto ≥ 95 %; cobertura core 99 % | Fase 2: clustering + pipeline + `scan --dry-run` |
| 2026-10-19 | Fase 2: `clustering` (umbral 0,55 calibrado, ADR 0005), `pipeline` con caché, progreso y cancelación, `plan` (reglas de colocación, nombres sin colisión, JSON), CLI `scan --dry-run --plan`. LFW: pureza 99,9 %, 99,2 % de rostros agrupados; 77 tests, cobertura 99 % | Fase 3: organizer (copiar/enlazar/mover, manifiesto, `undo`) |
| 2026-10-19 | Nueva Fase 5 "Duplicados" en requisitos (RF-16 a RF-20), arquitectura, ADR 0006 y guías; la antigua Fase 5 pasa a Fase 6. Corregida la tabla de fases (tenía filas del registro mezcladas) | Fase 3: organizer |
| 2026-10-19 | Fase 3: `organizer` (copias exclusivas verificadas por SHA-256, nunca sobrescribe, hardlink con respaldo a copia, mover en dos fases con confirmación, manifiesto incremental y atómico, `undo` que solo borra lo intacto creado por la app; ADR 0007), CLI `scan` aplica y `undo [--dry-run]`. 104 tests, cobertura 97 %; originales verificados por hash en todos los modos | Fase 4: GUI |
| 2026-10-19 | Fase 4: GUI PySide6 (escaneo en `QThread` con progreso y cancelar, revisión: renombrar/unir/separar/mover/excluir/restaurar con miniaturas en `QThreadPool`, vista previa, aplicar con confirmación de mover, deshacer), `services/review.py`, nombres de carpeta saneados (ADR 0008). Corregidos dos interbloqueos de hilos (lambdas en señales de workers y `quit` encolado). 134 tests (12 de GUI con pytest-qt), cobertura 94 % | Fase 5: duplicados |
| 2026-10-19 | Fase 5: `core/hashing.py` (dHash, Hamming con `np.bitwise_count`, búsqueda por bandas), tabla `image_hashes` (esquema v2, actualización en el sitio), `services/dedupe.py` (grupos exactos y casi duplicados, regla de conservación, verificación RF-19, mover vía organizer, papelera), CLI `dedupe`, página GUI "Duplicados" lado a lado. Umbral 6 calibrado en LFW (ADR 0009). Dataset sintético: 100 % de exactos y de variantes detectados, 0 falsos positivos; undo restaura. 169 tests, cobertura 94 % | Fase 6: ajustes, CSV, empaquetado, v1.0.0 |
| 2026-10-19 | Fase 6: regla RF-18 revisada (fecha EXIF antes que tamaño), ajustes persistentes con validación (JSON de usuario, `FACE_SORTER_HOME`), diálogo de Ajustes y «Borrar datos locales», reporte CSV (CLI `--csv` y GUI), log rotativo, mensajes de error claros y capturador global en la GUI, CLI y resúmenes traducidos al español, verificación de requisitos y medición de rendimiento. 192 tests, cobertura 95 % | Mantenimiento |
