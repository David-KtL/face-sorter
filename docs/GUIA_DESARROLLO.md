# Guía de desarrollo

## Setup
```
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
pip install -e .
python scripts/download_models.py   # verifica el SHA-256 de cada modelo
```

Para actualizar dependencias: cambia los rangos en `pyproject.toml`, reinstala en un `.venv` limpio y regenera `requirements.txt` (solo runtime) y `requirements-dev.txt` con `pip freeze`.

## Calidad (antes de cada commit)
```
ruff check . && black --check . && mypy src
pytest -q --cov=face_sorter
```

## Git
- Ramas: `main` (estable) · `develop` (integración) · `feature/<fase>-<nombre>`.
- Commits **Conventional Commits**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Tags **SemVer** anotados al cerrar cada fase: `git tag -a v0.1.0 -m "Fase 1: core"`.
- `main` solo recibe merges desde `develop` en releases.

## Cerrar una fase
Usa el comando `/cerrar-fase` de Claude Code. Hace: tests y lint, actualiza `PROGRESO.md` y `CHANGELOG.md`, sube versión en `pyproject.toml` y `__init__.py`, tag y merge a `develop`.

## ADRs
Toda decisión técnica relevante va en `docs/adr/NNNN-titulo.md` copiando `0000-plantilla.md`.

## Datos de prueba
Nunca commitear fotos reales. Usa fixtures sintéticos o el dataset público LFW: `python scripts/download_lfw.py` lo descarga a `data/lfw` (ignorado en git). Los tests que usan LFW o los modelos se saltan si no están descargados; sin ellos la cobertura de `core/` baja.

## Convenciones
Código y commits en inglés; documentación en español; type hints y docstrings en API pública; sin rutas ni umbrales hardcodeados (usar `config.py`).
