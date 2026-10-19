# face-sorter

Agrupa automáticamente las fotos de una carpeta por persona y las organiza en subcarpetas. También detecta fotos duplicadas y las retira de forma segura. Funciona 100 % local.

## Cómo funciona
1. **Escanea** la carpeta de fotos (recursivo).
2. **Detecta** rostros y descarta los de baja calidad.
3. **Calcula** un embedding por rostro.
4. **Agrupa** los embeddings (misma persona = mismo grupo).
5. **Revisas** los grupos en la GUI: renombrar, unir, separar, excluir.
6. **Aplica**: copia las fotos a `Salida/<Persona>/` (los originales no se tocan).

Carpetas especiales: `_sin_rostro/`, `_baja_calidad/`, `_sin_clasificar/`.

**Duplicados** (en desarrollo): detecta copias exactas (SHA-256) y casi duplicados (dHash). Los mueve a `_duplicados/`, nunca los borra por defecto, siempre conserva al menos una copia y todo se puede deshacer.
Una foto con varias personas se copia a la carpeta de cada una.

## Requisitos
- Python 3.11+
- Windows / macOS / Linux
- Webcam NO necesaria

## Instalación
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python scripts/download_models.py
```

## Uso
```
face-sorter gui
face-sorter scan "D:\Fotos" --out "D:\Fotos_Agrupadas" --dry-run   # vista previa
face-sorter scan "D:\Fotos" --out "D:\Fotos_Agrupadas"             # copia
face-sorter undo "D:\Fotos_Agrupadas\manifest_<fecha>.json"         # deshacer
face-sorter dedupe "D:\Fotos" --dry-run        # próximamente
```

## Documentación
- [Requisitos](docs/REQUISITOS.md)
- [Arquitectura](docs/ARQUITECTURA.md)
- [Guía de usuario](docs/GUIA_USUARIO.md)
- [Guía de desarrollo](docs/GUIA_DESARROLLO.md)
- [Progreso](docs/PROGRESO.md)
- [Decisiones (ADR)](docs/adr/)

## Privacidad
Las imágenes y los embeddings faciales son datos personales (biométricos). Se procesan y almacenan solo en tu equipo. Úsalo únicamente con fotos propias o con consentimiento de las personas, y cumple la normativa de protección de datos aplicable.
