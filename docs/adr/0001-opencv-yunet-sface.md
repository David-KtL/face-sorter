# ADR 0001: Detección y embeddings con OpenCV YuNet + SFace

- **Estado:** Aceptado
- **Fecha:** 2026-10-19

## Contexto
Se necesita detectar rostros y generar embeddings localmente, con instalación simple en Windows.

## Decisión
Usar `cv2.FaceDetectorYN` (YuNet) y `cv2.FaceRecognizerSF` (SFace) con modelos ONNX descargados por script. El embedder se define tras una interfaz `Embedder` para poder cambiarlo.

## Alternativas consideradas
- **face_recognition / dlib:** compilación problemática en Windows; modelo más antiguo.
- **InsightFace (ArcFace):** más preciso, pero dependencias más pesadas (onnxruntime, modelos grandes). Queda como mejora futura gracias a la interfaz.
- **DeepFace:** envuelve varios modelos, pero es más pesado y menos controlable.

## Consecuencias
Instalación ligera y 100 % local. Precisión suficiente para uso personal; si la pureza de grupos no alcanza el objetivo, se evaluará InsightFace en un nuevo ADR.
