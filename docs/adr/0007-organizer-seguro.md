# ADR 0007: Organizador seguro: sin sobrescritura, verificación y manifiesto incremental

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
El ADR 0003 fija copiar por defecto, con manifiesto y `undo`. Falta decidir cómo se comporta el organizador en los casos límite: destino ya existente, hardlink imposible, mover con fotos que van a varias carpetas, interrupciones y fallos de disco.

## Decisión
1. **Nunca sobrescribir.** Los destinos se crean en modo exclusivo (`open(..., "xb")` / `os.link`). Si el destino existe:
   - con contenido idéntico (SHA-256) → se omite (`skipped_identical`) y `undo` no lo toca;
   - con otro contenido → se usa el siguiente nombre libre (`foto (2).jpg`).
2. **Verificación.** Cada copia se compara por SHA-256 con el original. Si falla, o si se llena el disco a mitad de una copia, el archivo parcial se borra y la entrada queda como `failed`. Antes de empezar se comprueba el espacio libre (modo copia) y que ningún destino se salga de la carpeta de salida.
3. **Hardlink.** Si no es posible (otra unidad, FAT/exFAT), se **copia** en su lugar y se avisa en el resumen.
4. **Mover.** Requiere confirmación explícita (`s/N` en la CLI o `--yes`; `confirm_move=True` en la API). Funciona en dos fases: primero se crean y verifican todas las copias de cada original (con hardlink si es la misma unidad); después se registra la intención en el manifiesto y solo entonces se borra el original. Un original con alguna copia fallida, o que cambió durante el proceso, se queda en su sitio (`kept`). Una foto con varias personas se mueve a la primera carpeta y se copia a las demás, a efectos prácticos.
5. **Manifiesto incremental** (`manifest_<fecha>.json` en la salida): se guarda al empezar, cada 50 operaciones, al interrumpirse (Ctrl+C) y al terminar, con escritura atómica (archivo temporal + reemplazo). Un apagón puede dejar sin registrar hasta 49 copias, pero nunca un original movido sin registrar.
6. **Undo.** Primero devuelve los originales movidos desde una copia intacta. Después borra solo lo que creó la ejecución y siga igual (mismo hash, o hardlink al original). Por último elimina las carpetas que creó si quedaron vacías. Los archivos modificados después se conservan y se informan. El manifiesto se marca `undone` y se conserva como registro.

## Alternativas consideradas
- **Sobrescribir o preguntar por cada conflicto:** riesgo de pérdida, o un flujo inmanejable con miles de fotos.
- **`shutil.move` directo:** en otra unidad copia y borra sin verificación, y no deja un registro previo de la intención.
- **Guardar el manifiesto tras cada operación:** máxima precisión, pero reescribe el JSON miles de veces (O(n²) en escritura).

## Consecuencias
Cero sobrescrituras y originales recuperables en todos los modos. Coste: cada archivo se lee dos veces (hash de origen y verificación del destino), aceptable frente al riesgo. Con hardlink, editar la copia edita el original (es el mismo archivo); se documenta en la guía de usuario.
