# Progreso

**Fase actual:** 3 (pendiente de iniciar; Fase 2 cerrada en v0.2.0)

| Fase | Entregable | Aceptación | Estado | Tag | Fecha |
|---|---|---|---|---|---|
| 2026-10-19 | Fase 0: git (main/develop), estructura `core/services/gui`, `config.py`, CLI esqueleto (`scan`, `gui`, `undo`), tests de humo, `.venv` con Python 3.12, versiones exactas, modelos ONNX descargados y verificados por SHA-256, lint/tests en verde | Fase 1: core (scanner, detector, calidad, embedder, caché) |
| 2026-10-19 | Fase 1: `scanner`, `image_io` (EXIF, HEIC), detector YuNet con reescalado, `Embedder` + SFace, filtro de calidad, caché SQLite (ADR 0004), script LFW. En LFW: 100 % de detección (300 fotos/60 personas), vecino más cercano correcto ≥ 95 %; cobertura core 99 % | Fase 2: clustering + pipeline + `scan --dry-run` |
| 2026-10-19 | Fase 2: `clustering` (umbral 0,55 calibrado, ADR 0005), `pipeline` con caché, progreso y cancelación, `plan` (reglas de colocación, nombres sin colisión, JSON), CLI `scan --dry-run --plan`. LFW: pureza 99,9 %, 99,2 % de rostros agrupados; 77 tests, cobertura 99 % | Fase 3: organizer (copiar/enlazar/mover, manifiesto, `undo`) |
| 0 | Git, estructura, entorno, versiones exactas, script de modelos, lint/tests en verde | `pytest`, ruff, black, mypy pasan | Completada | v0.0.1 | 2026-10-19 |
| 1 | Core: scanner, detector, calidad, embedder, caché | Detecta y calcula embeddings en dataset de prueba; cobertura core ≥ 80 % | Completada | v0.1.0 | 2026-10-19 |
| 2 | Clustering + pipeline + CLI `scan --dry-run` | Agrupa dataset etiquetado con pureza ≥ 95 % | Completada | v0.2.0 | 2026-10-19 |
| 3 | Organizer: copiar/enlazar/mover, manifiesto, `undo` | Originales intactos (hash); undo restaura | Pendiente | v0.3.0 | |
| 4 | GUI: escaneo con progreso, revisión de grupos, aplicar | Flujo completo sin congelarse | Pendiente | v0.4.0 | |
| 5 | Ajustes, reporte CSV, manejo de errores, empaquetado opcional, docs finales | Todo RF cumplido | Pendiente | v1.0.0 | |

## Pendientes y bloqueos
- (ninguno)

## Registro de sesiones
| Fecha | Qué se hizo | Siguiente paso |
|---|---|---|
