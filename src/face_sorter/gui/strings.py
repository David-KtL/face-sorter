"""User-visible GUI texts (Spanish). Kept in one place to ease translation (RF-14)."""

APP_TITLE = "face-sorter: agrupar fotos por persona"

# Setup page
SOURCE_LABEL = "Carpeta de fotos:"
OUTPUT_LABEL = "Carpeta de salida:"
MODE_LABEL = "Modo:"
BROWSE = "Elegir…"
CHOOSE_SOURCE = "Elige la carpeta con tus fotos"
CHOOSE_OUTPUT = "Elige la carpeta donde se crearán los grupos"
MODE_COPY = "Copiar (recomendado: los originales no se tocan)"
MODE_HARDLINK = "Enlace duro (sin ocupar espacio extra; mismo disco)"
MODE_MOVE = "Mover (retira los originales; pide confirmación)"
SCAN = "Escanear"
CANCEL = "Cancelar"
SETUP_HINT = (
    "Todo se procesa en tu equipo. El escaneo no modifica tus fotos y se puede "
    "interrumpir: lo ya analizado queda guardado."
)
NEED_FOLDERS = "Elige la carpeta de fotos y la carpeta de salida."
SOURCE_MISSING = "La carpeta de fotos no existe."
SAME_FOLDERS = "La carpeta de salida debe ser distinta de la carpeta de fotos."
SCANNING = "Analizando {done} de {total} fotos…"
SCAN_STARTING = "Preparando…"
SCAN_CANCELLED = "Escaneo cancelado. Lo analizado queda guardado para la próxima vez."
SCAN_FAILED = "No se pudo completar el escaneo"

# Review page
GROUPS = "Grupos"
PERSON_ITEM = "{name}  ({faces} rostros · {images} fotos)"
UNCLASSIFIED_ITEM = "Sin clasificar ({n})"
LOW_QUALITY_ITEM = "Baja calidad ({n})"
EXCLUDED_ITEM = "Excluidos ({n})"
NO_FACE_ITEM = "Sin rostro ({n} fotos)"
RENAME = "Renombrar…"
MERGE = "Unir grupos seleccionados"
SPLIT = "Separar en grupo nuevo"
MOVE_TO = "Mover a grupo…"
EXCLUDE_FACES = "Excluir rostro"
EXCLUDE_PHOTOS = "Excluir foto"
RESTORE = "Restaurar"
PREVIEW = "Vista previa"
APPLY = "Aplicar"
BACK = "Volver"
RENAME_TITLE = "Renombrar grupo"
RENAME_PROMPT = "Nombre de la persona (será el nombre de la carpeta):"
RENAMED_SANITIZED = "Se usará «{name}» (se quitaron caracteres no válidos)."
MERGE_NEED_TWO = "Selecciona al menos dos grupos en la lista (Ctrl+clic)."
MOVE_TITLE = "Mover rostros"
MOVE_PROMPT = "Grupo de destino:"
UNCLASSIFIED_TARGET = "(Sin clasificar)"
SELECT_FACES = "Selecciona uno o más rostros."
REVIEW_HINT = (
    "Revisa los grupos: renombra, une, separa o excluye rostros. "
    "Nada se copia hasta que pulses «Aplicar»."
)
EDIT_ERROR = "No se puede hacer"
PREVIEW_TITLE = "Vista previa (no se ha tocado ningún archivo)"

# Apply / result / undo
CONFIRM_MOVE_TITLE = "¿Mover los originales?"
CONFIRM_MOVE = (
    "Se moverán {n} fotos originales fuera de la carpeta de fotos.\n"
    "Podrás devolverlas con «Deshacer». ¿Continuar?"
)
APPLYING = "Organizando fotos…"
APPLY_FAILED = "No se pudo aplicar"
RESULT_TITLE = "Resultado"
UNDO = "Deshacer"
NEW_SCAN = "Nuevo escaneo"
OPEN_OUTPUT = "Abrir carpeta de salida"
CONFIRM_UNDO_TITLE = "¿Deshacer?"
CONFIRM_UNDO = "Esto es lo que se hará:\n\n{summary}\n\n¿Continuar?"
UNDO_DONE = "Deshecho"
UNDO_FAILED = "No se pudo deshacer"
MENU_FILE = "&Archivo"
MENU_UNDO_MANIFEST = "Deshacer desde un manifiesto…"
MENU_QUIT = "Salir"
CHOOSE_MANIFEST = "Elige el manifiesto (manifest_*.json)"
MANIFEST_FILTER = "Manifiestos (manifest_*.json);;JSON (*.json)"

# Duplicates (phase 5)
FIND_DUPLICATES = "Buscar duplicados"
DUP_NEED_SOURCE = "Elige la carpeta de fotos donde buscar duplicados."
DUP_SCANNING = "Buscando duplicados: {done} de {total} fotos…"
DUP_TITLE = "Duplicados en {folder}"
DUP_HINT = (
    "Marca los grupos que quieres limpiar. Los exactos vienen marcados; revisa los casi "
    "duplicados antes de marcarlos. De cada grupo siempre se conserva una copia "
    "(«CONSERVAR»), y nunca se borra nada: se mueven a «_duplicados»."
)
DUP_NONE = "No se encontraron duplicados."
DUP_EXACT_ITEM = "Exacto · {n} copias"
DUP_NEAR_ITEM = "Casi duplicado · {n} fotos (distancia ≤ {d})"
DUP_KEEP_MARK = "✔ CONSERVAR"
DUP_KEEP_THIS = "Conservar esta"
DUP_MOVE = "Mover duplicados a _duplicados"
DUP_TRASH = "Enviar a la papelera…"
DUP_NOTHING_SELECTED = "No hay ningún grupo marcado."
DUP_CONFIRM_MOVE_TITLE = "¿Mover duplicados?"
DUP_CONFIRM_MOVE = (
    "Se moverán {n} fotos duplicadas a:\n{folder}\n\n"
    "De cada grupo se conserva una copia. Podrás devolverlas con «Deshacer». ¿Continuar?"
)
DUP_CONFIRM_TRASH_TITLE = "¿Enviar a la papelera?"
DUP_CONFIRM_TRASH = (
    "Se enviarán {n} fotos duplicadas a la PAPELERA del sistema.\n"
    "De cada grupo se conserva una copia. Podrás recuperarlas desde la papelera, "
    "pero no con «Deshacer». ¿Continuar?"
)
DUP_FAILED = "No se pudo completar la operación de duplicados"

# Settings, CSV, errors (phase 6)
MENU_SETTINGS = "Ajustes…"
SETTINGS_TITLE = "Ajustes"
SET_THRESHOLD = "Umbral de agrupación:"
SET_THRESHOLD_TIP = (
    "Distancia máxima para considerar dos rostros la misma persona. Más bajo = más "
    "estricto (puede partir a una persona en varios grupos); más alto = puede mezclar "
    "personas. Recomendado: 0,55."
)
SET_MIN_GROUP = "Mínimo de rostros por grupo:"
SET_MIN_GROUP_TIP = "Los grupos más pequeños van a «_sin_clasificar»."
SET_MIN_FACE = "Tamaño mínimo de rostro (px):"
SET_MIN_FACE_TIP = "Rostros más pequeños van a «_baja_calidad»."
SET_MIN_SCORE = "Confianza mínima de detección:"
SET_MIN_SCORE_TIP = "Detecciones con menos confianza van a «_baja_calidad»."
SET_MIN_SHARP = "Nitidez mínima:"
SET_MIN_SHARP_TIP = "Rostros más borrosos van a «_baja_calidad». Más alto = más exigente."
SET_DUP_DISTANCE = "Sensibilidad de casi duplicados:"
SET_DUP_DISTANCE_TIP = (
    "Diferencia máxima (de 0 a 20) entre dos fotos para considerarlas casi duplicadas. "
    "Más bajo = más estricto. Recomendado: 6."
)
SET_MODE = "Modo por defecto:"
SET_DEFAULTS = "Restaurar valores por defecto"
SET_DELETE_DATA = "Borrar datos locales…"
SET_SAVED = (
    "Ajustes guardados. Se aplicarán en el próximo escaneo, que será rápido gracias a la " "caché."
)
CONFIRM_DELETE_DATA_TITLE = "¿Borrar datos locales?"
CONFIRM_DELETE_DATA = (
    "Se borrará la base de datos local con los rostros y huellas calculados:\n{path}\n\n"
    "Tus fotos no se tocan. El próximo escaneo tendrá que analizarlas de nuevo. ¿Continuar?"
)
DATA_DELETED = "Datos locales borrados."
BUSY = "Espera a que termine la tarea en curso."
EXPORT_CSV = "Exportar CSV…"
EXPORT_CSV_TITLE = "Guardar reporte CSV"
CSV_FILTER = "CSV (*.csv)"
CSV_SAVED = "Reporte guardado ({n} filas):\n{path}"
UNEXPECTED_ERROR = "Error inesperado"
UNEXPECTED_ERROR_TEXT = (
    "Ha ocurrido un error inesperado. Tus fotos no se han modificado.\n\n{error}\n\n"
    "Detalles en el registro:\n{log}"
)
ERR_PERMISSION = "Permiso denegado: {path}"
ERR_DISK_FULL = "No queda espacio en el disco."
ERR_MEMORY = "Memoria insuficiente. Prueba con una carpeta más pequeña."
