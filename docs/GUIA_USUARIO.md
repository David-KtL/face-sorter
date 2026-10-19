# Guía de usuario

## Flujo básico
1. Abre la app: `face-sorter gui`.
2. **Elige la carpeta de fotos** y la **carpeta de salida** (distinta de la de origen).
   Elige también el **modo**: Copiar (recomendado), Enlace duro o Mover.
3. Pulsa **Escanear**. Verás una barra de progreso. Puedes cancelar: lo analizado se guarda y el próximo escaneo continúa desde ahí.
4. **Revisa los grupos**. A la izquierda está la lista de personas (con la foto de una cara) y, al final, Sin clasificar, Baja calidad, Excluidos y Sin rostro. A la derecha están los rostros del grupo elegido (Ctrl+clic o Mayús+clic para seleccionar varios).
   - **Renombrar…**: `Persona_001` → `Ana`. Será el nombre de la carpeta. Los caracteres no válidos (`\ / : * ? " < > |`) se cambian por `_`, y no se permiten dos grupos con el mismo nombre.
   - **Unir grupos seleccionados**: selecciona dos o más grupos (Ctrl+clic) que sean la misma persona.
   - **Separar en grupo nuevo**: los rostros seleccionados pasan a un grupo nuevo.
   - **Mover a grupo…**: lleva rostros a otro grupo. También sirve para asignar los "Sin clasificar".
   - **Excluir rostro**: ignora una detección errónea o a un desconocido.
   - **Excluir foto**: esa foto no se copiará.
   - **Restaurar**: en "Excluidos", devuelve los rostros seleccionados.
5. Pulsa **Vista previa** para ver qué se copiará, sin tocar nada.
6. Pulsa **Aplicar**. Por defecto se **copia**; tus originales no se tocan. Si elegiste Mover, se pide confirmación.
7. En el resultado puedes **Abrir carpeta de salida** o **Deshacer**. Para deshacer una operación anterior: menú **Archivo → Deshacer desde un manifiesto…**.

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

## Duplicados
**En la GUI:** elige la carpeta de fotos y pulsa **Buscar duplicados**.

1. A la izquierda aparecen los grupos:
   - **Exacto:** el mismo archivo copiado varias veces. Vienen **marcados**.
   - **Casi duplicado:** la misma foto redimensionada, recomprimida o en otro formato. Vienen **sin marcar**: revísalos y márcalos si de verdad son la misma foto.
2. A la derecha ves las copias lado a lado, con su resolución, tamaño y fecha. La marcada **✔ CONSERVAR** es la que se queda. Para cambiarla, selecciona otra y pulsa **Conservar esta**. Por defecto se conserva la de mayor resolución, luego la de mayor tamaño, luego la de fecha EXIF más antigua y luego la de ruta más corta.
3. **Mover duplicados a _duplicados**: los duplicados se **mueven** a `_duplicados/` dentro de la carpeta analizada, con la misma estructura de subcarpetas. **Nunca se borran por defecto**, y siempre queda al menos una copia de cada foto.
4. ¿Te arrepientes? `face-sorter undo <manifest.json>` las devuelve a su sitio.
5. **Enviar a la papelera…**: para liberar espacio. Pide confirmación explícita. Se recuperan desde la papelera del sistema (no con «Deshacer»).

**En la línea de comandos:**
```
face-sorter dedupe "D:\Fotos" --dry-run     # solo lista los grupos (* = se aplicaría)
face-sorter dedupe "D:\Fotos"               # mueve los duplicados EXACTOS (pide s/N)
face-sorter dedupe "D:\Fotos" --near        # incluye también los casi duplicados
face-sorter dedupe "D:\Fotos" --trash       # a la papelera en vez de mover (pide s/N)
```
`--max-distance N` ajusta la sensibilidad de los casi duplicados (por defecto 6; menos = más estricto).

Ten en cuenta: con la misma resolución se conserva el archivo más grande, así que una copia convertida a PNG puede ganar a su JPEG original. Revísalo en la GUI si te importa.

## Deshacer
`face-sorter undo <salida>\manifest_<fecha>.json` revierte lo aplicado (prueba antes con `--dry-run`). En la GUI, antes de deshacer se muestra un resumen de lo que se hará.
- Devuelve a su sitio los originales movidos.
- Borra solo los archivos que creó la aplicación y que no modificaste después; los modificados se conservan y se listan.
- Quita las carpetas que creó si quedaron vacías. El manifiesto se conserva como registro.

## Consejos
- Si mezcla personas distintas: baja el umbral de agrupación en Ajustes.
- Si divide a la misma persona en varios grupos: sube el umbral y usa **Unir**.
- Fotos con gafas de sol, perfil extremo o muy pequeñas darán peores resultados.

## Privacidad
Todo se procesa en tu equipo. Los embeddings se guardan en una base local; bórrala desde Ajustes si ya no la necesitas.
