# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [SemVer](https://semver.org/lang/es/).

## [Unreleased]

## [1.0.1] - 2026-10-19
### Added
- Lanzador para Windows `Iniciar face-sorter.bat`: con doble clic prepara el entorno y descarga los modelos la primera vez, y luego abre la GUI sin ventana de consola.

### Fixed
- Guía de usuario: la regla de la copia a conservar entre duplicados estaba desactualizada.

## [1.0.0] - 2026-10-19
### Added
- Ajustes persistentes (RF-14): umbral de agrupación, mínimo de rostros por grupo, calidad mínima (tamaño, confianza, nitidez), sensibilidad de casi duplicados y modo por defecto. Se guardan en un JSON de usuario con validación de rangos; un archivo dañado nunca impide arrancar. La CLI y la GUI los usan.
- GUI: diálogo **Archivo → Ajustes…** con «Restaurar valores por defecto» y «Borrar datos locales…» (elimina el archivo de caché por completo).
- Reporte CSV (RF-15): `face-sorter scan … --csv reporte.csv` y botón «Exportar CSV…» en la revisión. Separador `;` y UTF-8 con BOM para Excel en español.
- Registro en archivo rotativo (carpeta de logs del usuario) y capturador global de errores en la GUI.
- Mensajes claros para permisos denegados, disco lleno y memoria insuficiente.
- Variable `FACE_SORTER_HOME` para guardar ajustes, caché y logs en una carpeta concreta (instalación portátil y tests aislados).
- `docs/VERIFICACION.md`: estado de cada requisito y su evidencia.

### Changed
- Todos los textos para el usuario (CLI, resúmenes, errores) están en español, incluidas las frases de ayuda de argparse.
- `--mode` toma por defecto el modo de los ajustes del usuario.
- Regla de la copia a conservar entre duplicados: mayor resolución > **fecha EXIF más antigua** > mayor tamaño > ruta más corta. Una conversión más pesada (p. ej. a PNG) ya no gana a su JPEG original.

## [0.5.0] - 2026-10-19
### Added
- Detección de duplicados: exactos (SHA-256) y casi duplicados (dHash de 64 bits + distancia de Hamming, umbral 6 calibrado en LFW), con búsqueda vectorizada y por bandas (`core/hashing.py`).
- `services/dedupe.py`: grupos, copia a conservar (mayor resolución > mayor tamaño > fecha EXIF más antigua > ruta más corta; se puede cambiar), verificación de que siempre queda una copia intacta, mover a `_duplicados/` con manifiesto y `undo`, o enviar a la papelera (`send2trash`) con confirmación.
- `face-sorter dedupe <carpeta> [--dry-run] [--near] [--max-distance N] [--trash] [--yes]`. Por defecto solo actúa sobre duplicados exactos.
- GUI: botón "Buscar duplicados" y página con grupos marcables y fotos lado a lado (resolución, tamaño, fecha), "Conservar esta", vista previa, mover y papelera.
- Caché: tabla `image_hashes` (esquema v2); una caché v1 se actualiza sin perder los rostros. El análisis de rostros guarda los hashes de paso.
- ADR 0009.

### Changed
- El escáner ignora siempre la carpeta `_duplicados/`.

## [0.4.0] - 2026-10-19
### Added
- GUI (`face-sorter gui`): elegir carpetas y modo; escaneo en segundo plano con barra de progreso y botón Cancelar; revisión de grupos con miniaturas de rostros (renombrar, unir, separar en grupo nuevo, mover a otro grupo, excluir rostro o foto, restaurar); vista previa; aplicar (pide confirmación para mover); deshacer la última operación o cualquier manifiesto (menú Archivo).
- `services/review.py`: lógica de revisión sin Qt. Nombres de carpeta saneados (caracteres no válidos, nombres reservados de Windows) y sin duplicados.
- `build_plan` admite nombres de grupo, rostros y fotos excluidos; el resumen cuenta las fotos excluidas.
- Textos de la interfaz en español en `gui/strings.py`.
- Tests de GUI con `pytest-qt` (sin pantalla). ADR 0008.

## [0.3.0] - 2026-10-19
### Added
- `services/organizer.py`: aplica el plan en modo copiar (por defecto), hardlink o mover. Nunca sobrescribe (si el destino es idéntico lo omite, si no usa `foto (2).jpg`), verifica cada copia por SHA-256, comprueba espacio libre y rutas antes de empezar, y cambia hardlink por copia si el destino está en otra unidad.
- Modo mover en dos fases: el original solo se borra tras verificar todas sus copias y registrar la intención; requiere confirmación (`s/N` o `--yes`).
- Manifiesto `manifest_<fecha>.json` incremental y atómico (también al interrumpir).
- `face-sorter undo <manifest> [--dry-run]`: devuelve los originales movidos, borra solo lo creado que no se modificó y quita las carpetas vacías creadas.
- `face-sorter scan` sin `--dry-run` aplica el plan; opción `--yes`.
- ADR 0007: organizador seguro.
- Documentación de la nueva Fase 5 "Duplicados": requisitos RF-16 a RF-20, arquitectura (`core/hashing.py`, `services/dedupe.py`, columnas `sha256` y `phash`), ADR 0006 y flujo en la guía de usuario.
- Dependencia `send2trash` (papelera del sistema; se usará en la Fase 5).

### Changed
- Alcance ampliado: agrupación por persona + detección y retiro seguro de duplicados. La antigua Fase 5 pasa a ser la Fase 6 (v1.0.0).

### Fixed
- `docs/PROGRESO.md`: las filas del registro de sesiones estaban dentro de la tabla de fases.

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
