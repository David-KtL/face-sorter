# ADR 0006: Detección de duplicados con SHA-256 + hash perceptual dHash

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
Se amplía el alcance para detectar y retirar fotos duplicadas (RF-16 a RF-20). Hay dos casos:
- **Exactos:** el mismo archivo copiado varias veces.
- **Casi duplicados:** la misma foto redimensionada, recomprimida o convertida a otro formato (JPG ↔ PNG/HEIC/WEBP). El contenido en bytes difiere, así que un hash criptográfico no basta.

Restricciones: 100 % local, sin dependencias pesadas nuevas, eficiente con decenas de miles de fotos y sin riesgo de perder la única copia de una foto.

## Decisión
- **Exactos:** SHA-256 del archivo. Ya se calcula y guarda en la caché desde la Fase 1 (`images.hash`).
- **Casi duplicados:** **dHash de 64 bits** implementado con Pillow + numpy (`core/hashing.py`). Pasos: se aplica la orientación EXIF, se convierte a gris, se reduce a 9×8 y cada bit indica si un píxel es mayor que su vecino derecho. Dos fotos son casi duplicadas si su **distancia de Hamming ≤ umbral**, configurable (valor inicial a calibrar en la Fase 5 con el dataset sintético).
- **Búsqueda eficiente:** hashes en un array `uint64`. Se hace *bucketing* por bandas (principio del palomar: con `t + 1` bandas, dos hashes a distancia ≤ t comparten al menos una banda) y verificación vectorizada (XOR + `np.bitwise_count`). Nunca O(n²) en Python puro.
- **Copia a conservar** (RF-18): mayor resolución > mayor tamaño > fecha EXIF más antigua > ruta más corta. El usuario puede cambiarla en la GUI.
- **Acción** (RF-19, RF-20): mover a `_duplicados/` vía el `organizer`, con manifiesto y `undo`. Antes de actuar se verifica que cada grupo conserva al menos una copia. Para borrar solo se envía a la papelera (`send2trash`), con confirmación explícita.

## Alternativas consideradas
- **`imagehash` (+ scipy/PyWavelets):** ofrece pHash/wHash ya hechos. Contras: dependencia extra para algo que son ~15 líneas con numpy, y su pHash usa DCT de scipy (más lento). dHash es suficiente para redimensionado y recompresión.
- **Embeddings de imagen (CLIP u otra CNN):** detectan fotos "parecidas" (ráfagas, otro encuadre). Contras: modelo grande y lento, y demasiados falsos positivos para una acción que mueve archivos. Queda como posible mejora futura en un ADR aparte.
- **Solo SHA-256:** simple y sin falsos positivos, pero no detecta la misma foto redimensionada o recomprimida, que es el caso más común (fotos enviadas por mensajería, exportaciones).
- **pHash (DCT) propio con numpy:** algo más robusto a cambios de brillo, pero más costoso. Se puede añadir después tras la misma interfaz si dHash da falsos negativos.

## Consecuencias
- Sin dependencias nuevas para el hashing. `send2trash` solo se usa para la papelera.
- dHash puede dar falsos positivos en imágenes casi uniformes (fondos lisos, capturas en negro) y no detecta recortes ni rotaciones. Por eso la GUI muestra los grupos lado a lado antes de aplicar, y la acción por defecto es reversible.
- La caché necesita la columna `phash` y renombrar `hash` a `sha256`: migración a `schema_version` 2 en la Fase 5, sin perder los embeddings ya calculados.
- `dedupe` es la única operación que mueve archivos dentro de la carpeta original por defecto; es reversible y deja siempre una copia (excepción documentada en CLAUDE.md y RNF-01).
