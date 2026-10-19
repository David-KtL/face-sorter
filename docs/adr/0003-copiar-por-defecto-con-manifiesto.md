# ADR 0003: Copiar por defecto, con manifiesto y undo

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
Mover o borrar fotos originales por error es irreversible y de alto costo para el usuario.

## Decisión
El modo por defecto es **copiar** a una carpeta de salida. Hardlink y mover son opcionales (mover requiere confirmación). Toda aplicación escribe `manifest_<fecha>.json` y existe `undo`. Siempre hay `--dry-run`.

## Consecuencias
Usa más disco en modo copia (mitigable con hardlinks en el mismo volumen). A cambio, cero riesgo sobre los originales.
