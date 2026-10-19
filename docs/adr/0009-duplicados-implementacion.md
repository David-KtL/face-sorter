# ADR 0009: Implementación de duplicados: tabla de hashes, umbral y selección por defecto

- **Estado:** Aceptado (complementa al ADR 0006)
- **Fecha:** 2026-10-19

## Contexto
El ADR 0006 fija SHA-256 + dHash. Al implementarlo hubo que decidir dónde guardar los hashes, qué umbral usar, qué se aplica por defecto y cómo evitar que dos grupos se pisen.

## Decisión
1. **Tabla `image_hashes` aparte** (sha256, phash, ancho, alto, fecha EXIF; clave = ruta normalizada + tamaño + mtime), en lugar de columnas nuevas en `images` como proponía ARQUITECTURA. Motivos:
   - En `images`, que exista una fila significa "rostros analizados". Si `dedupe` insertara filas ahí, el análisis de rostros creería que esas fotos no tienen caras.
   - Cambiar de modelo de rostros vacía `images` y `faces`, pero los hashes no dependen del modelo y deben sobrevivir.

   El esquema pasa a la versión 2. Una caché v1 se actualiza en el sitio (solo se crea la tabla), sin perder los embeddings. El pipeline de rostros guarda los hashes de paso (ya tiene la imagen decodificada), así que un `dedupe` posterior no vuelve a leer esas fotos. El dHash (64 bits sin signo) se guarda en complemento a dos porque SQLite usa enteros con signo.
2. **Umbral de Hamming por defecto = 6.** Medido con 300 fotos de LFW:

   | Transformación | Distancia máx. | p99 |
   |---|---|---|
   | PNG (sin pérdida) | 0 | 0 |
   | Ampliar ×2 | 5 | 4 |
   | Reducir al 50 % | 8 | 4 |
   | JPEG calidad 30 | 9 | 5 |
   | WEBP calidad 50 | 8 | 5 |
   | Brillo +10 % | 9 | 6 |
   | Reducir al 25 % (miniatura) | 10 | 8 |

   Entre 44 850 pares de fotos distintas, el mínimo fue 5. Ese par resultó ser la misma escena (dos fotos consecutivas, etiquetadas con dos nombres en LFW), es decir, un casi duplicado legítimo. A distancia 7-8 aparecen retratos distintos con la misma composición. Se configura con `--max-distance` o `DedupeSettings`.
3. **Por defecto solo se actúa sobre duplicados exactos.** Los casi duplicados se listan; se aplican con `--near` en la CLI o marcándolos en la GUI tras revisarlos lado a lado.
4. **Un grupo "casi duplicado" absorbe las copias exactas de sus miembros**, y al aplicarlo se descartan los grupos exactos que contiene (`effective_selection`). Así cada foto pertenece como mucho a un grupo aplicado y nunca se retira la copia que otro grupo conserva.
5. **Verificación antes de actuar (RF-19):** para cada grupo, la copia a conservar existe, su SHA-256 no cambió desde el escaneo y ningún otro grupo la retira. Si algo falla no se toca nada. Con la papelera, además, se vuelve a comprobar el hash de cada archivo justo antes de enviarlo.
6. **Mover** usa el organizador (modo mover, dos fases, manifiesto, `undo`) con salida `<carpeta>/_duplicados/`, conservando las rutas relativas. El escáner ignora siempre `_duplicados/`. **Papelera:** `send2trash`, con confirmación explícita y un registro `trash_<fecha>.json`; no se puede deshacer con `undo` (se recupera desde la papelera del sistema).

## Alternativas consideradas
- **Columnas en `images`** (propuesta original): mezcla "analizado para rostros" con "hasheado", y los hashes se perderían al cambiar de modelo.
- **Aplicar casi duplicados por defecto:** más cómodo, pero las ráfagas y los fondos lisos pueden dar falsos positivos.
- **Umbral 8-10:** detectaría también las miniaturas muy reducidas, a costa de agrupar retratos distintos.

## Consecuencias
- **Comportamiento a vigilar en la regla RF-18:** con la misma resolución gana el archivo más grande, así que una conversión a PNG (más pesada) se conserva frente a su JPEG original. Si molesta en la práctica, se puede ajustar la regla (por ejemplo, preferir el formato original o la fecha EXIF antes que el tamaño). Se puede cambiar a mano en la GUI con "Conservar esta".
