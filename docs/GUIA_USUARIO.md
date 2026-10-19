# Guía de usuario

## Flujo básico
1. Abre la app: `face-sorter gui`.
2. **Elige la carpeta de fotos** y la **carpeta de salida** (distinta de la de origen).
3. Pulsa **Escanear**. Verás una barra de progreso; puedes cancelar y reanudar después.
4. **Revisa los grupos**:
   - Renombra (`Persona_001` → `Ana`).
   - Une dos grupos que son la misma persona.
   - Separa o excluye fotos mal asignadas.
5. Pulsa **Vista previa (dry-run)** para ver qué se copiará.
6. Pulsa **Aplicar**. Por defecto se **copia**; tus originales no se tocan.

## Carpetas especiales
- `_sin_rostro/`: fotos sin ningún rostro detectado.
- `_baja_calidad/`: rostros demasiado pequeños o borrosos.
- `_sin_clasificar/`: rostros que no encajan con ningún grupo.

## Deshacer
`face-sorter undo <manifest.json>` revierte lo aplicado. También disponible en la GUI.

## Consejos
- Si mezcla personas distintas: baja el umbral de agrupación en Ajustes.
- Si divide a la misma persona en varios grupos: sube el umbral y usa **Unir**.
- Fotos con gafas de sol, perfil extremo o muy pequeñas darán peores resultados.

## Privacidad
Todo se procesa en tu equipo. Los embeddings se guardan en una base local; bórrala desde Ajustes si ya no la necesitas.
