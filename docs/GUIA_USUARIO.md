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

Si interrumpes el escaneo (Ctrl+C), lo ya analizado queda guardado y el siguiente escaneo continúa desde ahí.

Aplicar (copiar de verdad): el mismo comando sin `--dry-run`.
```
face-sorter scan "D:\Fotos" --out "D:\Fotos_Agrupadas"
```
- `--mode copy` (por defecto): copia; los originales no se tocan.
- `--mode hardlink`: no ocupa espacio extra, pero la "copia" es el mismo archivo que el original: si editas una, cambias la otra. Si la salida está en otro disco, se copia en su lugar y se avisa.
- `--mode move`: mueve los originales. Pide confirmación (`s/N`); `--yes` la omite. Un original solo se retira cuando todas sus copias están verificadas.

Nunca se sobrescribe nada: si en la salida ya existe un archivo idéntico se omite, y si existe otro distinto con el mismo nombre se guarda como `foto (2).jpg`. Cada copia se verifica con su huella SHA-256.

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
`face-sorter undo <salida>\manifest_<fecha>.json` revierte lo aplicado (prueba antes con `--dry-run`). También estará disponible en la GUI.
- Devuelve a su sitio los originales movidos.
- Borra solo los archivos que creó la aplicación y que no modificaste después; los modificados se conservan y se listan.
- Quita las carpetas que creó si quedaron vacías. El manifiesto se conserva como registro.

## Consejos
- Si mezcla personas distintas: baja el umbral de agrupación en Ajustes.
- Si divide a la misma persona en varios grupos: sube el umbral y usa **Unir**.
- Fotos con gafas de sol, perfil extremo o muy pequeñas darán peores resultados.

## Privacidad
Todo se procesa en tu equipo. Los embeddings se guardan en una base local; bórrala desde Ajustes si ya no la necesitas.
