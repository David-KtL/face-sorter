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

## Línea de comandos
Vista previa sin tocar ningún archivo:
```
face-sorter scan "D:\Fotos" --out "D:\Fotos_Agrupadas" --dry-run
```
Muestra cuántas fotos y rostros irían a cada carpeta. Opciones útiles:
- `--plan plan.json`: guarda el plan completo (cada foto y su destino) para revisarlo.
- `--threshold 0.5`: umbral de agrupación (por defecto 0,55; más bajo = más estricto).
- `-q`: sin barra de progreso · `-v`: más detalle en el registro.

Si interrumpes el escaneo (Ctrl+C), lo ya analizado queda guardado y el siguiente escaneo continúa desde ahí. Aplicar el plan (copiar de verdad) llegará en una próxima versión.

## Carpetas especiales
- `_sin_rostro/`: fotos sin ningún rostro detectado.
- `_baja_calidad/`: rostros demasiado pequeños o borrosos.
- `_sin_clasificar/`: rostros que no encajan con ningún grupo (por ejemplo, alguien que aparece en una sola foto). Una foto de grupo que ya va a la carpeta de alguien no se copia también aquí.

Las fotos que no se pueden leer (archivos dañados) no se copian; aparecen listadas al final del resumen.

## Duplicados (próximamente, Fase 5)
1. Vista previa: `face-sorter dedupe "D:\Fotos" --dry-run`. Muestra cada grupo de duplicados y qué copia se conserva.
   - **Exactos:** mismo contenido byte a byte.
   - **Casi duplicados:** la misma foto redimensionada, recomprimida o en otro formato. La sensibilidad se ajusta con la distancia de Hamming en Ajustes.
2. Revisa los grupos en la GUI, en la pestaña **Duplicados**, que compara las fotos lado a lado. Puedes cambiar qué copia se conserva. Por defecto se conserva la de mayor resolución, luego la de mayor tamaño, luego la de fecha EXIF más antigua y luego la de ruta más corta.
3. Aplica: los duplicados se **mueven** a `_duplicados/` dentro de la carpeta analizada, con la misma estructura de subcarpetas. **Nunca se borran por defecto**, y siempre queda al menos una copia de cada foto.
4. ¿Te arrepientes? `face-sorter undo <manifest.json>` las devuelve a su sitio.
5. Para liberar espacio, puedes enviarlas a la **papelera del sistema**. Esto pide confirmación explícita y se puede recuperar desde la papelera.

## Deshacer
`face-sorter undo <manifest.json>` revierte lo aplicado. También disponible en la GUI.

## Consejos
- Si mezcla personas distintas: baja el umbral de agrupación en Ajustes.
- Si divide a la misma persona en varios grupos: sube el umbral y usa **Unir**.
- Fotos con gafas de sol, perfil extremo o muy pequeñas darán peores resultados.

## Privacidad
Todo se procesa en tu equipo. Los embeddings se guardan en una base local; bórrala desde Ajustes si ya no la necesitas.
