# Verificación de requisitos (v1.0.0)

Estado de cada requisito de `REQUISITOS.md` y la prueba automática que lo respalda. Todos los tests se ejecutan con `pytest` (192 tests, cobertura total 95 %). Los que usan LFW o los modelos se saltan si no están descargados.

## Requisitos funcionales

| ID | Requisito | Estado | Evidencia |
|---|---|---|---|
| RF-01 | Escaneo recursivo JPG, PNG, WEBP, HEIC | ✅ | `test_scanner.py`, `test_image_io.py::test_loads_heic` |
| RF-02 | Orientación EXIF | ✅ | `test_image_io.py::test_respects_exif_orientation` |
| RF-03 | Detectar todos los rostros | ✅ | `test_lfw_core.py::test_detection_rate` (100 % en LFW) |
| RF-04 | Filtro de baja calidad | ✅ | `test_quality.py`, `test_lfw_core.py::test_good_faces_pass_quality_and_blur_is_flagged` |
| RF-05 | Embeddings en caché SQLite, sin recalcular | ✅ | `test_cache.py`, `test_pipeline.py::test_second_run_uses_cache` |
| RF-06 | Clustering con umbral configurable | ✅ | `test_clustering.py`, `test_lfw_clustering.py` |
| RF-07 | Foto con varias personas → una copia por persona | ✅ | `test_plan.py::test_placement_rules` |
| RF-08 | `_sin_rostro`, `_baja_calidad`, `_sin_clasificar` | ✅ | `test_plan.py::test_placement_rules` |
| RF-09 | GUI de revisión: renombrar, unir, separar, excluir | ✅ | `test_review.py`, `test_gui.py::test_merge_split_move_exclude_restore` |
| RF-10 | Copiar (defecto), hardlink, mover con confirmación | ✅ | `test_organizer.py`, `test_cli_scan.py::test_scan_move_asks_and_respects_no` |
| RF-11 | `--dry-run` | ✅ | `test_cli_scan.py::test_scan_dry_run_end_to_end` |
| RF-12 | Manifiesto y `undo` | ✅ | `test_organizer.py::test_undo_restores_previous_state`, `test_move_and_undo` |
| RF-13 | CLI `scan`, `gui`, `undo` (+ `dedupe`) | ✅ | `test_cli_scan.py`, `test_smoke.py` |
| RF-14 | Ajustes: umbral, calidad, modo, idioma | ✅* | `test_settings_report.py`, `test_gui.py::test_open_settings_saves_and_updates_mode`. *Idioma: solo español, por decisión del 2026-10-19 (los textos están centralizados en `gui/strings.py`). |
| RF-15 | Reporte CSV | ✅ | `test_settings_report.py::test_csv_rows`, `test_gui.py::test_export_csv` |
| RF-16 | Duplicados exactos (SHA-256) | ✅ | `test_dedupe.py::test_detects_all_exact_and_near_duplicates` |
| RF-17 | Casi duplicados (dHash, Hamming configurable) | ✅ | `test_hashing.py`, `test_dedupe.py` |
| RF-18 | Copia a conservar por regla, modificable en la GUI | ✅ | `test_dedupe.py::test_keep_rule_resolution_date_size_path`, `test_gui.py::test_change_keep_check_near_and_move_then_undo` |
| RF-19 | Siempre queda ≥ 1 copia, verificado antes de actuar | ✅ | `test_dedupe.py::test_override_keep_and_invariant`, `test_changed_keep_is_refused`, `test_keep_removed_by_other_group_is_refused` |
| RF-20 | Mover a `_duplicados/` + undo; dry-run; papelera con confirmación | ✅ | `test_dedupe.py::test_move_to_duplicates_and_undo`, `test_trash_*`, `test_cli_scan.py::test_dedupe_cli*` |

## Requisitos no funcionales

| ID | Estado | Evidencia / notas |
|---|---|---|
| RNF-01 Seguridad de datos | ✅ | Hashes de los originales antes y después en todos los modos (`test_organizer.py`, `test_pipeline.py::test_originals_are_untouched`, tests de CLI y GUI). No se sobrescribe nunca (`test_never_overwrites_a_different_file`). |
| RNF-02 Privacidad | ✅ | El código de `src/` no hace ningún acceso a red. Solo los scripts de descarga (modelos y LFW) usan internet. "Borrar datos locales" elimina el archivo de caché. |
| RNF-03 Rendimiento | ✅ | Trabajo pesado en `QThread` y `QThreadPool` (`test_gui.py` comprueba que corre fuera del hilo de la GUI); cancelable. Medido: ~0,25-0,5 s por foto de 12 MP en el primer análisis y < 1 ms con caché; clustering de 10 000 rostros ≈ 9 s y ~400 MB. Estimación para 5 000 fotos de móvil: 30-50 min la primera vez y segundos después. |
| RNF-04 Reanudable | ✅ | `test_pipeline.py::test_cancel_keeps_processed_images_cached`, `test_gui.py::test_scan_can_be_cancelled` |
| RNF-05 Portabilidad | ⚠️ | Desarrollado y probado en Windows 10. El código usa `pathlib` y `platformdirs` y evita APIs de un solo sistema, pero **no se ha probado en macOS ni en Linux** (no hay CI). |
| RNF-06 Calidad | ✅ | ruff, black y mypy en verde. Cobertura: `core/` 99-100 %, `services/` 93-100 %. |
| RNF-07 Robustez | ✅ | Imágenes corruptas registradas sin detener el proceso (`test_pipeline.py::test_unexpected_error_in_one_image_does_not_stop_scan`); log rotativo; disco lleno y permisos con mensajes claros (`test_organizer.py::test_disk_full_leaves_no_partial_file`, `test_gui.py::test_friendly_messages`). |

## Criterios de éxito

| Criterio | Resultado |
|---|---|
| Pureza de grupos ≥ 95 % con el umbral por defecto | **99,9 %** en LFW (1 048 rostros, 100 personas + 200 desconocidos), `test_lfw_clustering.py` |
| Ningún original alterado | Verificado con SHA-256 en todos los modos |
| `undo` restaura la carpeta de salida | Verificado (salvo el manifiesto, que se conserva como registro) |
| Duplicados: 100 % exactos y casi duplicados sintéticos; nunca se retiran todas las copias | Verificado con el dataset sintético (`tests/dupdata.py`) |
