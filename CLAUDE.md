# face-sorter — Contexto del proyecto para Claude Code

## Objetivo
Aplicación de escritorio en Python que **agrupa por persona** las fotos de una carpeta: detecta rostros, calcula embeddings, los agrupa (clustering) y organiza las imágenes en carpetas (`Persona_001/`, `Persona_002/`, ...). El usuario revisa y nombra los grupos en una GUI antes de aplicar cambios. Además detecta fotos duplicadas (exactas y casi duplicadas) y las retira de forma segura y reversible.

**Alcance:** agrupación de rostros por persona + detección y retiro seguro de fotos duplicadas. No agregues redes sociales, nube, análisis de emociones/edad/género, ni nada fuera de `docs/REQUISITOS.md`.

## Regla de oro (seguridad de datos)
**Nunca modificar, mover ni borrar las fotos originales por defecto.** El modo por defecto es COPIAR (o hardlink) a una carpeta de salida. Mover solo con confirmación explícita del usuario. Toda operación sobre archivos debe poder deshacerse mediante un manifiesto (`manifest_*.json`) y tener modo `--dry-run`.

**Duplicados (`face-sorter dedupe`):** los duplicados **NUNCA se borran por defecto**. La acción por defecto es moverlos a `_duplicados/` con manifiesto y `undo`. Siempre queda al menos una copia por grupo, y se verifica antes de actuar. `dedupe` sin `--dry-run` pide confirmación (s/N o `--yes`) antes de mover. Borrar solo enviando a la papelera del sistema (`send2trash`) y con confirmación explícita; jamás borrado permanente.

## Stack
- Python 3.11+ (entorno de desarrollo: 3.12), `.venv`, `pyproject.toml`; versiones exactas en `requirements*.txt`
- Detección + embedding: OpenCV 5.x `FaceDetectorYN` (YuNet) + `FaceRecognizerSF` (SFace, embedding de 128 dims), modelos ONNX verificados por SHA-256. Embedder **intercambiable** (interfaz `Embedder`) para poder añadir InsightFace/ArcFace después.
- Duplicados: SHA-256 (exactos) + dHash con Pillow + numpy (casi duplicados, distancia de Hamming); papelera con `send2trash`
- Clustering: scikit-learn (`AgglomerativeClustering` con distancia coseno y umbral; `HDBSCAN` opcional)
- Caché: SQLite (`sqlite3` de la stdlib)
- Imágenes: Pillow (+ `pillow-heif` para HEIC), respetar orientación EXIF
- GUI: PySide6
- CLI: `argparse`
- Tests: pytest · Calidad: ruff + black + mypy
- 100 % local, sin enviar imágenes a ningún servicio externo

## Estructura
```
src/face_sorter/
  core/      scanner, image_io, detector, embedder, quality, clustering, cache, hashing (sha256, dHash, Hamming)
  services/  pipeline, plan (qué va a dónde), report (CSV), review (ediciones del usuario, sin Qt), organizer (copiar/enlazar/mover + manifiesto + undo), dedupe (grupos de duplicados, copia a conservar)
  gui/       main_window, duplicates_page, settings_dialog, workers (QThread), thumbnails (QThreadPool), errors, strings (textos ES), app
  config.py (rutas, umbrales, ajustes de usuario)  logging_setup.py  formatting.py  __main__.py (CLI)
tests/  docs/  docs/adr/  scripts/  models/  .claude/
```

## Comandos
```
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements-dev.txt && pip install -e .
python scripts/download_models.py                  # descarga modelos ONNX
python scripts/download_lfw.py                     # dataset de prueba LFW en data/ (tests)
face-sorter scan <carpeta> --out <salida> --dry-run [--plan plan.json] [--threshold 0.55]
face-sorter scan <carpeta> --out <salida> [--mode copy|hardlink|move] [--yes]   # aplica
face-sorter undo <salida>/manifest_<fecha>.json [--dry-run]
face-sorter dedupe <carpeta> --dry-run                 # lista duplicados
face-sorter dedupe <carpeta> [--near] [--trash] [--yes] # mueve a _duplicados (o papelera)
face-sorter scan <carpeta> --out <salida> --dry-run --csv reporte.csv  # reporte CSV
face-sorter gui
pytest -q --cov=face_sorter
ruff check . && black --check . && mypy src
```

## Convenciones
- Código, commits y nombres en inglés; documentación en español.
- Type hints y docstrings en funciones públicas.
- Commits **Conventional Commits** (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`), atómicos.
- Ramas: `main` (estable) · `develop` (integración) · `feature/<fase>-<nombre>`.
- Versionado **SemVer** con tags anotados al cerrar cada fase (ver `docs/PROGRESO.md`).
- Decisión técnica relevante → nuevo ADR en `docs/adr/` (usar `0000-plantilla.md`).
- No hardcodear rutas absolutas ni umbrales: todo en `config.py` / ajustes.
- Tareas pesadas SIEMPRE fuera del hilo de la GUI. Las señales de workers se conectan a **métodos** de la ventana, nunca a `lambda` (en PySide6 la lambda corre en el hilo del worker; ver ADR 0008). Textos de la GUI en `gui/strings.py`; diálogos vía `Dialogs` (sustituible en tests).
- Tests: nunca commitear fotos reales de personas. Usar fixtures sintéticos o un dataset público descargado por script (ignorado en git).

## Flujo de trabajo
1. Lee `docs/PROGRESO.md` para saber la fase actual.
2. Trabaja una fase a la vez; no avances si los tests fallan.
3. Al terminar una fase usa `/cerrar-fase` (actualiza docs, CHANGELOG, tag, merge a develop).
4. Si hay decisiones ambiguas, pregunta antes de asumir.

## Estado actual
v1.0.0 publicada (todas las fases cerradas). Ver `docs/PROGRESO.md` y `docs/VERIFICACION.md`.

## Notas para mantenimiento
- La app es **solo en español**: textos de GUI en `gui/strings.py`; CLI y resúmenes de servicios en español; logs y código en inglés.
- Ajustes del usuario: `config.load_settings()/save_settings()` (rangos en `EDITABLE_SETTINGS`). Los tests aíslan todo con `FACE_SORTER_HOME` (fixture `isolated_home`).
- En heredocs de Bash las barras invertidas se alteran: para editar textos con `\n`, escribir un script en un archivo.
