# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [SemVer](https://semver.org/lang/es/).

## [Unreleased]

## [0.0.1] - 2026-10-19
### Added
- Scaffold inicial del proyecto, documentación y configuración de Claude Code.
- Estructura del paquete `src/face_sorter/` (`core`, `services`, `gui`) y `config.py` con rutas y modo de salida por defecto (copiar).
- CLI con `argparse`: subcomandos `scan`, `gui` y `undo` (aún sin lógica; devuelven código 2).
- Tests de humo (importación del paquete, defaults seguros, CLI).
- `.gitattributes` para finales de línea LF.

### Changed
- `requirements.txt` y `requirements-dev.txt` con versiones exactas (`pip freeze`).
- `scripts/download_models.py` verifica el SHA-256 de cada modelo y descarga a un archivo temporal antes de reemplazar.
