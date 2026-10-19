# face-sorter — Contexto del proyecto para Claude Code

## Objetivo
Aplicación de escritorio en Python que **agrupa por persona** las fotos de una carpeta: detecta rostros, calcula embeddings, los agrupa (clustering) y organiza las imágenes en carpetas (`Persona_001/`, `Persona_002/`, ...). El usuario revisa y nombra los grupos en una GUI antes de aplicar cambios.

**Alcance:** SOLO agrupación de rostros en carpetas. No agregues redes sociales, nube, análisis de emociones/edad/género, ni nada fuera de `docs/REQUISITOS.md`.

## Regla de oro (seguridad de datos)
**Nunca modificar, mover ni borrar las fotos originales por defecto.** El modo por defecto es COPIAR (o hardlink) a una carpeta de salida. Mover solo con confirmación explícita del usuario. Toda operación sobre archivos debe poder deshacerse mediante un manifiesto (`manifest_*.json`) y tener modo `--dry-run`.

## Stack
- Python 3.11+, `.venv`, `pyproject.toml`
- Detección + embedding: OpenCV `FaceDetectorYN` (YuNet) + `FaceRecognizerSF` (SFace), modelos ONNX. Embedder **intercambiable** (interfaz `Embedder`) para poder añadir InsightFace/ArcFace después.
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
  core/      scanner, detector, embedder, quality, clustering, cache
  services/  pipeline, organizer (copiar/enlazar/mover + manifiesto + undo)
  gui/       main_window, vistas, workers (QThread), widgets
  config.py  __main__.py (CLI)
tests/  docs/  docs/adr/  scripts/  models/  .claude/
```

## Comandos
```
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements-dev.txt && pip install -e .
python scripts/download_models.py                  # descarga modelos ONNX
face-sorter scan <carpeta> --out <salida> --dry-run
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
- Tareas pesadas SIEMPRE fuera del hilo de la GUI.
- Tests: nunca commitear fotos reales de personas. Usar fixtures sintéticos o un dataset público descargado por script (ignorado en git).

## Flujo de trabajo
1. Lee `docs/PROGRESO.md` para saber la fase actual.
2. Trabaja una fase a la vez; no avances si los tests fallan.
3. Al terminar una fase usa `/cerrar-fase` (actualiza docs, CHANGELOG, tag, merge a develop).
4. Si hay decisiones ambiguas, pregunta antes de asumir.

## Estado actual
Ver `docs/PROGRESO.md` (fuente de verdad del avance).
