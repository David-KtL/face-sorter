---
description: Cierra la fase actual (tests, docs, changelog, tag, merge a develop)
---

Cierra la fase actual del proyecto siguiendo estos pasos en orden. Detente y repórtame si algo falla.

1. Lee `docs/PROGRESO.md` e identifica la fase en curso y su criterio de aceptación.
2. Ejecuta `ruff check . && black --check . && mypy src && pytest -q --cov=face_sorter`. Si algo falla, corrígelo antes de seguir.
3. Verifica que el criterio de aceptación de la fase se cumple; si no, dime qué falta y para.
4. Actualiza `docs/PROGRESO.md` (estado, fecha, tag) y agrega una fila al registro de sesiones.
5. Actualiza `CHANGELOG.md` moviendo lo de `[Unreleased]` a la nueva versión.
6. Sube la versión en `pyproject.toml` y `src/face_sorter/__init__.py`.
7. Actualiza `CLAUDE.md` y los docs afectados (`ARQUITECTURA.md`, `GUIA_USUARIO.md`).
8. Commit `chore(release): vX.Y.Z`, tag anotado `vX.Y.Z`, merge de la rama feature a `develop`.
9. Resúmeme en 5 líneas lo entregado y propón el plan de la siguiente fase. No la inicies.
