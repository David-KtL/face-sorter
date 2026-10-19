# Requisitos

## Alcance
Agrupar por persona las fotos de una carpeta y organizarlas en subcarpetas, y detectar y retirar de forma segura las fotos duplicadas. **Fuera de alcance:** nube, redes sociales, análisis de emociones/edad/género, edición de fotos, reconocimiento en video.

## Requisitos funcionales
| ID | Requisito | Prioridad |
|---|---|---|
| RF-01 | Escanear una carpeta de forma recursiva (JPG, PNG, WEBP, HEIC) | Alta |
| RF-02 | Respetar la orientación EXIF al leer imágenes | Alta |
| RF-03 | Detectar todos los rostros por imagen | Alta |
| RF-04 | Filtrar rostros de baja calidad (tamaño mínimo, nitidez, confianza) | Alta |
| RF-05 | Calcular un embedding por rostro y cachearlo en SQLite (no recalcular si la foto no cambió) | Alta |
| RF-06 | Agrupar embeddings por similitud (clustering) con umbral configurable | Alta |
| RF-07 | Una foto con varias personas se copia a la carpeta de cada una | Alta |
| RF-08 | Carpetas especiales: `_sin_rostro/`, `_baja_calidad/`, `_sin_clasificar/` | Alta |
| RF-09 | GUI de revisión: ver grupos, renombrar, unir, separar, excluir fotos o rostros | Alta |
| RF-10 | Aplicar la organización: copiar (defecto), hardlink o mover (con confirmación) | Alta |
| RF-11 | Modo `--dry-run` que muestra qué se haría sin tocar archivos | Alta |
| RF-12 | Manifiesto de operaciones y comando `undo` para revertir | Alta |
| RF-13 | CLI: `scan`, `gui`, `undo` | Media |
| RF-14 | Ajustes: umbral de agrupación, calidad mínima, modo de salida, idioma | Media |
| RF-15 | Exportar un reporte CSV (foto, grupo, n.º de rostros) | Baja |
| RF-16 | Detectar duplicados exactos por SHA-256 | Alta |
| RF-17 | Detectar casi duplicados (redimensionadas, recomprimidas, otro formato) con hash perceptual dHash (Pillow + numpy, sin dependencias nuevas) y distancia de Hamming configurable | Alta |
| RF-18 | Elegir la copia a conservar por regla configurable (mayor resolución > mayor tamaño > fecha EXIF más antigua > ruta más corta), modificable por el usuario en la GUI | Alta |
| RF-19 | Invariante: siempre queda al menos una copia por grupo de duplicados, verificada antes de actuar | Alta |
| RF-20 | Acción por defecto sobre duplicados: mover a `_duplicados/` con manifiesto y `undo`; `--dry-run` siempre disponible; aplicar pide confirmación (s/N o `--yes`); enviar a la papelera solo con confirmación explícita | Alta |

## Requisitos no funcionales
- **RNF-01 Seguridad de datos:** los originales jamás se modifican ni se borran por defecto. Única excepción: `dedupe` mueve (no borra) los duplicados a `_duplicados/`, de forma reversible (RF-20).
- **RNF-02 Privacidad:** 100 % local; ninguna imagen ni embedding sale del equipo.
- **RNF-03 Rendimiento:** procesar ~5 000 fotos sin congelar la GUI (hilos de trabajo, barra de progreso, cancelable).
- **RNF-04 Reanudable:** si se interrumpe el escaneo, continúa desde la caché.
- **RNF-05 Portabilidad:** Windows (principal), macOS y Linux.
- **RNF-06 Calidad:** cobertura de tests ≥ 80 % en `core/` y `services/`; ruff, black y mypy en verde.
- **RNF-07 Robustez:** imágenes corruptas o ilegibles se registran en el log y no detienen el proceso.

## Criterios de éxito
- En un dataset de prueba etiquetado, pureza de grupos ≥ 95 % con el umbral por defecto.
- Ninguna foto original alterada (verificado con hashes en tests).
- `undo` restaura el estado previo de la carpeta de salida.
- Duplicados: 100 % de los exactos y los casi duplicados de un dataset sintético detectados; nunca se retiran todas las copias de un grupo.
