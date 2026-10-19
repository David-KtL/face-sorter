# ADR 0008: GUI: hilos de trabajo, servicio de revisión y nombres de carpeta

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
La Fase 4 añade la GUI (PySide6). Requisitos: no congelarse con miles de fotos (RNF-03), poder cancelar, revisar grupos (RF-09: renombrar, unir, separar, excluir) y aplicar o deshacer desde la interfaz, todo con tests automáticos.

## Decisión
1. **Lógica de revisión fuera de Qt** (`services/review.py`, `ReviewSession`): renombrar, unir, separar, mover, excluir y restaurar operan sobre el `ScanResult` y producen el plan con `build_plan(names=…, excluded_faces=…, excluded_images=…)`. La GUI solo llama y redibuja. Se prueba sin pantalla.
2. **Trabajo pesado en `QThread`** (`gui/workers.py`): escaneo, aplicar y deshacer. Cada worker es un `QObject` movido a su hilo; la cancelación es un `threading.Event` que se revisa entre fotos o archivos. Las miniaturas se decodifican en un `QThreadPool` y llegan como `QImage` (los `QPixmap` solo se crean en el hilo de la GUI).
3. **Reglas de hilos aprendidas en la implementación:**
   - Las señales de un worker se conectan solo a **métodos de la ventana**, nunca a `lambda`. En PySide6 una `lambda` se ejecuta en el hilo que emite la señal; eso provocó un interbloqueo (el worker esperándose a sí mismo) y accesos a la GUI desde fuera de su hilo.
   - `worker.done → thread.quit` usa conexión **directa**. Encolada, se bloquea al cerrar la ventana durante un escaneo, porque el hilo de la GUI está esperando en `thread.wait()`.
4. **Diálogos detrás de una clase `Dialogs`** sustituible en los tests (`pytest-qt`, `QT_QPA_PLATFORM=offscreen`), para que nunca se abran ventanas modales que bloqueen la ejecución.
5. **Nombres de carpeta:** al renombrar se sustituyen los caracteres no válidos en Windows (`\ / : * ? " < > |`, caracteres de control) por `_`. También se quitan puntos y espacios finales, los nombres reservados (`CON`, `COM1`…) reciben un `_` final y se limita la longitud a 100 caracteres. No se admiten los nombres de las carpetas especiales. Si el nombre ya lo usa otro grupo (sin distinguir mayúsculas), se rechaza y se sugiere unir los grupos; nunca se unen sin preguntar.
6. **Textos en español** en `gui/strings.py`, para facilitar el selector de idioma (RF-14).

## Alternativas consideradas
- **`QtConcurrent` / `concurrent.futures` para todo:** menos código, pero la cancelación y el progreso con señales son más torpes, y PySide6 no expone bien `QtConcurrent`.
- **Lógica de revisión dentro de los widgets:** más rápido de escribir, pero difícil de probar y de reutilizar en una futura vista de duplicados.

## Consecuencias
La GUI no se congela y el flujo completo (escanear → revisar → aplicar → deshacer) tiene tests automáticos. Hay una regla de código que cumplir siempre: nada de `lambda` en señales de workers. Queda escrita en el código y en este ADR.
