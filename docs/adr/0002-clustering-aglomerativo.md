# ADR 0002: Clustering aglomerativo con distancia coseno

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
No se conoce de antemano el número de personas en la colección.

## Decisión
`AgglomerativeClustering(n_clusters=None, distance_threshold=T, metric="cosine", linkage="average")`. El umbral `T` es configurable. HDBSCAN queda como opción experimental.

## Alternativas consideradas
- **K-Means:** exige conocer K.
- **DBSCAN/HDBSCAN:** maneja ruido, pero es más sensible a parámetros y a densidades distintas.

## Consecuencias
El usuario ajusta un solo umbral y corrige con la GUI (unir/separar). Complejidad O(n²) en memoria: suficiente para decenas de miles de rostros; si crece, evaluar clustering incremental.
