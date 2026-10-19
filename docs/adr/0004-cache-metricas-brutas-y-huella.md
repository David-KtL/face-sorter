# ADR 0004: Caché con métricas brutas de calidad y huella de modelo

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
La caché SQLite (RF-05, RNF-04) evita recalcular fotos que no cambiaron. Hay que decidir qué guardar de cada rostro y cuándo la caché deja de ser válida. Los umbrales de calidad (RF-04) son ajustables por el usuario (RF-14).

## Decisión
- Se detectan rostros con un umbral de YuNet permisivo (0,6) y se calcula el embedding de **todos** ellos.
- Por rostro se guardan **métricas brutas**: lado menor de la caja, confianza del detector y nitidez (varianza del Laplaciano del recorte alineado de 112×112). El veredicto de calidad (`quality.assess`) se aplica después, con los umbrales vigentes.
- La caché guarda una **huella** (`embedder.name` + parámetros del detector). Si cambia, la caché se vacía al abrirse.
- Una foto se considera sin cambios si coinciden tamaño y mtime; si cambió el mtime pero el SHA-256 es igual, también.
- Se guarda la ruta original (para copiar) y una clave normalizada (insensible a mayúsculas en Windows) para buscar.

## Alternativas consideradas
- **Guardar solo rostros que pasan el filtro:** menos datos, pero cambiar un umbral obligaría a reescanear.
- **Nitidez normalizada por contraste** (`var(Laplaciano(gris/σ))`): medida en ~1 500 rostros de LFW, separa peor las fotos nítidas de las desenfocadas que la varianza del Laplaciano sin normalizar.

## Consecuencias
Cambiar umbrales de calidad es instantáneo. El coste es calcular embeddings también para rostros que luego irán a `_baja_calidad/` (despreciable). Con el umbral por defecto (25) ~1-2 % de los rostros de LFW se marcan como borrosos, y al revisarlos son fotos realmente blandas.
