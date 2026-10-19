# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [SemVer](https://semver.org/lang/es/).

## [Unreleased]

## [0.2.0] - 2026-10-19
### Added
- `core/clustering.py`: clustering aglomerativo por distancia coseno; los grupos de 1 rostro van a `_sin_clasificar`; numeración estable por tamaño de grupo.
- `services/pipeline.py`: escaneo completo con caché, progreso por imagen, cancelación reanudable y tolerancia a imágenes rotas.
- `services/plan.py`: plan de organización (qué foto va a qué carpeta), resumen legible y exportación JSON.
- CLI `face-sorter scan <carpeta> --out <salida> --dry-run` con barra de progreso y opciones `--plan`, `--threshold`, `--cache`, `--mode`, `-q`, `-v`.
- ADR 0005: umbral de agrupación por defecto (0,55) y reglas de colocación.

### Changed
- Mensaje más claro para imágenes corruptas.

## [0.1.0] - 2026-10-19
### Added
- `core/scanner.py`: búsqueda recursiva de imágenes soportadas (omite ocultos, no sigue enlaces de carpetas, permite excluir carpetas).
- `core/image_io.py`: carga de imágenes respetando la orientación EXIF, con soporte HEIC; errores de lectura como `ImageLoadError`.
- `core/detector.py`: detector YuNet; reduce fotos grandes para detectar y devuelve coordenadas en la imagen original.
- `core/embedder.py`: interfaz `Embedder` intercambiable e implementación `SFaceEmbedder` (128 dims, normalizado).
- `core/quality.py`: filtro de calidad por tamaño mínimo, confianza y nitidez, con umbrales en `config.py`.
- `core/cache.py`: caché SQLite de rostros y embeddings; no recalcula fotos sin cambios y se invalida si cambia el modelo (ADR 0004).
- `scripts/download_lfw.py` y tests de aceptación sobre LFW.

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
