# ADR 0005: Umbral de agrupación por defecto y reglas de colocación

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
El ADR 0002 fija el clustering aglomerativo con umbral configurable, pero no su valor. Además hay que decidir a qué carpeta va cada foto cuando tiene varias caras, caras de baja calidad o desconocidos.

## Decisión
**Umbral:** `distance_threshold = 0.55` (distancia coseno, enlace `average`), `min_cluster_size = 2`. Calibrado en LFW (1 048 rostros: 100 personas con ≥ 6 fotos + 200 personas con 1 foto):

| Umbral | Pureza | Rostros agrupados | Desconocidos sin clasificar | Grupos por persona |
|---|---|---|---|---|
| 0,50 | 99,9 % | 97,5 % | 99,0 % | 1,08 |
| **0,55** | **99,9 %** | **99,2 %** | **99,0 %** | **1,03** |
| 0,60 | 99,8 % | 99,6 % | 98,0 % | 1,01 |
| 0,65 | 97,1 % | 99,8 % | 81,8 % | 1,00 |
| 0,70 | 89,1 % | 99,9 % | 40,9 % | 1,00 |

Se elige 0,55 y no 0,60 para dejar margen antes de 0,65, donde empieza a mezclar personas. El enlace `complete` fragmenta más (1,13 grupos/persona a 0,60).

**Reglas de colocación** (por foto):
1. Ilegible → no se copia; se lista en `errors` del plan.
2. Sin rostros → `_sin_rostro/`.
3. Con rostros pero ninguno usable → `_baja_calidad/`.
4. Cada rostro usable en un grupo → una copia en la carpeta de esa persona (RF-07).
5. Rostros usables pero ninguno en un grupo → `_sin_clasificar/`.

Un desconocido que aparece en una foto que ya va a la carpeta de alguna persona **no** genera copia en `_sin_clasificar/`, pero ese rostro sí figura en ese grupo lógico del plan, para revisarlo en la GUI. Los nombres repetidos dentro de una carpeta se resuelven como `foto (2).jpg`, sin distinguir mayúsculas.

## Alternativas consideradas
- **Umbral 0,60:** agrupa algo más, pero queda pegado al punto de quiebre.
- **Copiar también a `_sin_clasificar/` las fotos de grupo con desconocidos:** llenaría esa carpeta de fotos ya organizadas.

## Consecuencias
Con datos de LFW (fotos de prensa) los resultados son muy buenos. Las fotos personales (niños que crecen, perfiles) pueden necesitar un umbral distinto: se ajusta con `--threshold` o en Ajustes, y se corrige en la GUI (unir/separar).
