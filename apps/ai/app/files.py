"""Almacenamiento + lectura/extracción de documentos que el cliente envía por WhatsApp.

El asistente vende seguros; la persona puede mandar su cédula, la tarjeta de
propiedad del vehículo, el RUT, el SOAT o exámenes médicos (PDF, imagen o texto).
Este módulo los guarda de forma estable, extrae el texto y hace una extracción
heurística (regex) de los campos útiles para el intake (número de documento,
nombre, placa, marca, etc.).

Diseño defensivo: extract_text/parse_document nunca lanzan; ante cualquier error
devuelven texto vacío o un dict con lo que se haya podido leer. Las dependencias
pesadas (pdfplumber, PIL, pytesseract) se importan de forma perezosa para que el
simple `import` del módulo no falle si alguna no está instalada.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent  # .../apps/ai/app


# --------------------------------------------------------------------------- #
# 1) Directorio de subidas
# --------------------------------------------------------------------------- #
def _resolve_upload_dir() -> Path:
    """Resuelve el directorio donde se guardan los documentos subidos.

    Prioridad:
      1. Variable de entorno ``SEGURIA_UPLOAD_DIR`` (override explícito).
      2. Convención de ``app.config`` si define ``DOCS_DIR`` (mismo árbol del app).
      3. Fallback: ``app/state/uploads``.
    """
    env = os.getenv("SEGURIA_UPLOAD_DIR")
    if env:
        return Path(env).expanduser()

    # Reutiliza la convención de ubicación de app.config si está disponible.
    # generated_docs (DOCS_DIR) es para PDFs de cotización salientes; los
    # documentos que el cliente sube van a una carpeta dedicada del mismo app.
    try:
        from app import config as app_config  # type: ignore

        docs_dir = getattr(app_config, "DOCS_DIR", None)
        if docs_dir is not None:
            # Path(DOCS_DIR) == apps/ai/generated_docs -> parent == apps/ai
            return Path(docs_dir).parent / "app" / "state" / "uploads"
    except Exception:
        pass

    return BASE_DIR / "state" / "uploads"


UPLOAD_DIR: Path = _resolve_upload_dir()

try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


# Extensiones que tratamos como imágenes (posible OCR).
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
# Extensiones que leemos como texto plano.
_TEXT_EXTS = {".txt", ".csv", ".md", ".log", ".tsv", ".json"}


# --------------------------------------------------------------------------- #
# 2) Guardado
# --------------------------------------------------------------------------- #
def _safe_ext(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    # sólo caracteres seguros para no inventar rutas raras
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", ext or ""):
        return ""
    return ext


def save_upload(filename: str, content: bytes) -> dict:
    """Guarda ``content`` con un ``file_id`` único derivado del hash del contenido.

    No usa aleatoriedad ni marcas de tiempo (evita restricciones del harness): el
    id es determinista (sha256 del contenido + nombre). Guardar dos veces el
    mismo archivo es idempotente.

    Devuelve ``{file_id, path, filename, size, mime}``.
    """
    if content is None:
        content = b""
    if not isinstance(content, (bytes, bytearray)):
        content = str(content).encode("utf-8", errors="ignore")
    content = bytes(content)

    ext = _safe_ext(filename)
    digest = hashlib.sha256(content + b"::" + (filename or "").encode("utf-8", "ignore")).hexdigest()
    file_id = digest[:16]

    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    stored_name = f"{file_id}{ext}"
    dest = UPLOAD_DIR / stored_name

    # Si por alguna razón el id ya existe con distinto contenido, cae a un
    # contador de archivos en el directorio (segunda estrategia permitida).
    try:
        if dest.exists() and dest.read_bytes() != content:
            counter = sum(1 for _ in UPLOAD_DIR.iterdir())
            stored_name = f"{file_id}-{counter}{ext}"
            dest = UPLOAD_DIR / stored_name
    except Exception:
        pass

    try:
        dest.write_bytes(content)
    except Exception:
        # último recurso: no interrumpir el flujo del asistente
        pass

    mime = mimetypes.guess_type(filename or stored_name)[0] or "application/octet-stream"

    return {
        "file_id": file_id,
        "path": str(dest),
        "filename": filename or stored_name,
        "size": len(content),
        "mime": mime,
    }


def path_for(file_id: str) -> str:
    """Resuelve un file_id (o una ruta ya absoluta) a la ruta del archivo guardado."""
    if not file_id:
        return ""
    p = Path(file_id)
    if p.is_file():
        return str(p)
    try:
        matches = sorted(UPLOAD_DIR.glob(f"{file_id}*"))
        return str(matches[0]) if matches else file_id
    except OSError:
        return file_id


# --------------------------------------------------------------------------- #
# 3) Extracción de texto
# --------------------------------------------------------------------------- #
def _extract_pdf(path: str) -> str:
    try:
        import pdfplumber  # import perezoso
    except Exception:
        return ""
    try:
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    txt = ""
                if txt:
                    parts.append(txt)
        return "\n".join(parts)
    except Exception:
        return ""


def _extract_image(path: str) -> str:
    """OCR opcional. Si pytesseract (y Tesseract) no están, devuelve una nota."""
    try:
        import pytesseract  # NO es dependencia declarada; se prueba con try/except
        from PIL import Image

        with Image.open(path) as img:
            text = pytesseract.image_to_string(img, lang=os.getenv("SEGURIA_OCR_LANG", "spa+eng"))
        text = (text or "").strip()
        if text:
            return text
        return "[imagen recibida; OCR no produjo texto]"
    except Exception:
        return "[imagen recibida; OCR no disponible]"


def extract_text(path: str) -> str:
    """Extrae texto de un documento. Nunca lanza; ante error devuelve ``""``.

    - PDF  -> pdfplumber (todas las páginas).
    - DOCX/XLSX/XLS/PPTX -> extractores office (portados de Paloma).
    - .txt/.csv/.md/... -> lectura directa (utf-8 tolerante).
    - imágenes -> OCR si pytesseract está instalado, si no una nota.
    """
    try:
        if not path or not os.path.exists(path):
            return ""
        ext = Path(path).suffix.lower()

        if ext == ".pdf":
            return _extract_pdf(path)

        # Office (Word/Excel/PowerPoint) — extractores portados de Paloma.
        if ext in (".docx", ".doc"):
            from .office_extractors import extract_docx
            return extract_docx(path)
        if ext in (".xlsx", ".xlsm"):
            from .office_extractors import extract_xlsx
            return extract_xlsx(path)
        if ext == ".xls":
            from .office_extractors import extract_xls
            return extract_xls(path)
        if ext == ".pptx":
            from .office_extractors import extract_pptx
            return extract_pptx(path)
        if ext == ".ppt":
            return (f"[Presentación legacy: {Path(path).name} — formato .ppt no "
                    "soportado; pídele al cliente convertirla a .pptx]")

        if ext in _IMAGE_EXTS:
            return _extract_image(path)

        if ext in _TEXT_EXTS or ext == "":
            try:
                return Path(path).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return ""

        # Formato desconocido: intento como texto, si falla vacío.
        try:
            return Path(path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# 4) Detección de tipo + extracción heurística de campos
# --------------------------------------------------------------------------- #
# Palabras clave por tipo (se buscan sobre el texto en minúsculas).
_TIPO_KEYWORDS = [
    ("cedula", (
        "cédula de ciudadanía", "cedula de ciudadania", "identificación personal",
        "identificacion personal", "registraduría", "registraduria", "nuip",
        "número único de identificación", "numero unico de identificacion",
    )),
    ("tarjeta_propiedad", (
        "licencia de tránsito", "licencia de transito", "tarjeta de propiedad",
        "cilindraje", "número de motor", "numero de motor", "vin", "clase de vehículo",
        "clase de vehiculo", "servicio particular",
    )),
    ("rut", (
        "registro único tributario", "registro unico tributario", "rut", "dian",
        "impuestos y aduanas",
    )),
    ("soat", (
        "soat", "seguro obligatorio", "accidentes de tránsito",
        "accidentes de transito",
    )),
    ("examen_medico", (
        "laboratorio clínico", "laboratorio clinico", "hemograma", "resultado de examen",
        "resultados de examen", "glucosa", "colesterol", "historia clínica",
        "historia clinica", "paciente", "diagnóstico", "diagnostico",
    )),
]


def _detect_tipo(text_lower: str) -> str:
    for tipo, kws in _TIPO_KEYWORDS:
        for kw in kws:
            if kw in text_lower:
                return tipo
    return "desconocido"


# ---- extractores de campos (regex tolerantes) ---- #
_RE_NUM_DOTTED = re.compile(r"\b\d{1,3}(?:\.\d{3}){2,3}\b")
_RE_NUM_LABELED = re.compile(
    r"(?:NUIP|N[ÚU]MERO|C[ÉE]DULA|C\.?\s?C\.?|DOCUMENTO)[^\d]{0,15}(\d[\d\.\s]{5,}\d)",
    re.IGNORECASE,
)
_RE_NUM_PLAIN = re.compile(r"\b\d{7,11}\b")


def _find_numero_documento(text: str) -> str | None:
    m = _RE_NUM_DOTTED.search(text)
    if m:
        return m.group(0)
    m = _RE_NUM_LABELED.search(text)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    m = _RE_NUM_PLAIN.search(text)
    if m:
        return m.group(0)
    return None


# placa carro (ABC123 / ABC 123) o moto (ABC12D)
_PLACA_CORE = r"[A-Z]{3}[\s-]?(?:\d{3}|\d{2}[A-Z])"
_RE_PLACA_LABELED = re.compile(r"PLACA[^A-Z0-9]{0,10}(" + _PLACA_CORE + r")", re.IGNORECASE)
_RE_PLACA_STANDALONE = re.compile(r"\b(" + _PLACA_CORE + r")\b")  # sin IGNORECASE: exige mayúsculas
# Prefijos de 3 letras que NO son placa (evita falsos positivos tipo "NIT 900").
_PLACA_STOP_PREFIX = {"NIT", "RUT", "SOA", "VIN", "IVA", "PIN", "REF", "TEL", "FAX"}


def _norm_placa(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw).upper()


def _find_placa_labeled(text: str) -> str | None:
    m = _RE_PLACA_LABELED.search(text)
    return _norm_placa(m.group(1)) if m else None


def _find_placa_standalone(text: str) -> str | None:
    for m in _RE_PLACA_STANDALONE.finditer(text):
        cand = _norm_placa(m.group(1))
        if cand[:3] not in _PLACA_STOP_PREFIX:
            return cand
    return None


def _label_value(label_pattern: str, text: str) -> str | None:
    """Captura el valor que sigue a una etiqueta (misma línea)."""
    rx = re.compile(label_pattern + r"[^A-Za-zÁÉÍÓÚÑ0-9]{0,10}([^\n\r]{1,30})", re.IGNORECASE)
    m = rx.search(text)
    if not m:
        return None
    val = m.group(1).strip(" :.-\t")
    # nos quedamos con las primeras 1-3 palabras razonables
    val = " ".join(val.split()[:3]).strip(" :.-")
    return val or None


def _find_marca(text: str) -> str | None:
    return _label_value(r"MARCA", text)


def _find_linea(text: str) -> str | None:
    return _label_value(r"L[ÍI]NEA", text)


_RE_MODELO = re.compile(r"MODELO[^\d]{0,10}((?:19|20)\d{2})", re.IGNORECASE)
_RE_ANIO = re.compile(r"\b((?:19|20)\d{2})\b")


def _find_modelo_anio(text: str) -> str | None:
    m = _RE_MODELO.search(text)
    if m:
        return m.group(1)
    return None


_RE_NIT_LABELED = re.compile(r"NIT[^\d]{0,10}(\d[\d\.\-]{6,}\d)", re.IGNORECASE)
_RE_NIT_DV = re.compile(r"\b(\d{9})[-\s]?(\d)\b")


def _find_nit(text: str) -> str | None:
    m = _RE_NIT_LABELED.search(text)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    m = _RE_NIT_DV.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


_NOMBRE_STOP = {
    "REPUBLICA", "REPÚBLICA", "DE", "DEL", "COLOMBIA", "CEDULA", "CÉDULA",
    "CIUDADANIA", "CIUDADANÍA", "IDENTIFICACION", "IDENTIFICACIÓN", "PERSONAL",
    "REGISTRADURIA", "REGISTRADURÍA", "NACIONAL", "ESTADO", "CIVIL", "NUIP",
    "NUMERO", "NÚMERO", "DOCUMENTO", "TARJETA", "PROPIEDAD", "PLACA", "MARCA",
    "LINEA", "LÍNEA", "MODELO", "RUT", "NIT", "DIAN", "SOAT", "VEHICULO",
    "VEHÍCULO", "APELLIDOS", "NOMBRES", "FIRMA", "HUELLA",
}
# El valor puede ir en la MISMA línea ("NOMBRES: ANA TORRES") o en la línea
# siguiente (cédula colombiana). Se permite un salto entre etiqueta y valor,
# pero el valor capturado no cruza saltos de línea (clase con espacio literal).
_RE_NOMBRE_LABELED = re.compile(
    r"(?:NOMBRES?|APELLIDOS?)[^A-ZÁÉÍÓÚÑ\n]{0,5}\n?[ ]*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{3,40})",
    re.IGNORECASE,
)
_RE_TOKEN_MAYUS = re.compile(r"^[A-ZÁÉÍÓÚÑ]{2,}$")


def _find_nombre(text: str) -> str | None:
    # 1) por etiqueta
    m = _RE_NOMBRE_LABELED.search(text)
    if m:
        val = " ".join(m.group(1).split()[:4]).strip()
        if val:
            return val
    # 2) heurística: línea de 2-4 palabras en MAYÚSCULAS que no sean encabezado
    for raw in text.splitlines():
        tokens = raw.strip().split()
        if not (2 <= len(tokens) <= 4):
            continue
        if not all(_RE_TOKEN_MAYUS.match(t) for t in tokens):
            continue
        meaningful = [t for t in tokens if t.upper() not in _NOMBRE_STOP]
        if len(meaningful) >= 2:
            return " ".join(tokens)
    return None


def parse_document(path: str, filename: str = "") -> dict:
    """Lee un documento y devuelve tipo detectado + campos extraídos por heurística.

    Return: ``{tipo_detectado, texto, campos_extraidos, resumen}``.
    ``texto`` viene recortado a ~4000 caracteres.
    """
    text = extract_text(path) or ""
    text_lower = text.lower()
    tipo = _detect_tipo(text_lower)

    campos: dict[str, str] = {}

    # Documento de identidad -> número + nombre
    if tipo in ("cedula", "desconocido"):
        num = _find_numero_documento(text)
        if num:
            campos["numero_documento"] = num
        nombre = _find_nombre(text)
        if nombre:
            campos["nombre"] = nombre

    # Tarjeta de propiedad / SOAT -> placa, marca, línea, modelo
    if tipo in ("tarjeta_propiedad", "soat", "desconocido"):
        marca = _find_marca(text)
        if marca:
            campos["marca"] = marca
        linea = _find_linea(text)
        if linea:
            campos["linea"] = linea
        modelo = _find_modelo_anio(text)
        if modelo:
            campos["modelo_anio"] = modelo

    # Placa: la forma etiquetada ("PLACA ABC123") se intenta siempre porque es
    # inequívoca y puede venir junto a la cédula o en cualquier documento. La
    # forma "suelta" (sin etiqueta) sólo se busca en documentos de vehículo o
    # desconocidos, para no confundir p.ej. "NIT 900" con una placa.
    if "placa" not in campos:
        placa = _find_placa_labeled(text)
        if not placa and tipo in ("tarjeta_propiedad", "soat", "desconocido"):
            placa = _find_placa_standalone(text)
        if placa:
            campos["placa"] = placa

    # RUT / PyME -> NIT
    if tipo in ("rut", "pyme", "desconocido"):
        nit = _find_nit(text)
        if nit:
            campos["nit"] = nit

    # Resumen legible
    if not text.strip():
        resumen = "No se pudo extraer texto legible del documento."
    else:
        n = len(text)
        if campos:
            detalle = ", ".join(f"{k}={v}" for k, v in campos.items())
            resumen = (
                f"Se leyó un documento de tipo '{tipo}' ({n} caracteres). "
                f"Campos detectados: {detalle}."
            )
        else:
            resumen = (
                f"Se leyó un documento de tipo '{tipo}' ({n} caracteres), "
                f"pero no se identificaron campos estructurados."
            )

    return {
        "tipo_detectado": tipo,
        "texto": text[:4000],
        "campos_extraidos": campos,
        "resumen": resumen,
    }


# --------------------------------------------------------------------------- #
# 5) Auto-prueba: genera un PDF tipo cédula (con placa) y lo parsea
# --------------------------------------------------------------------------- #
def _demo() -> dict:
    import json
    import tempfile

    # 1) Generar un PDF de prueba con fpdf (ya instalado).
    lines = [
        "REPUBLICA DE COLOMBIA",
        "IDENTIFICACION PERSONAL",
        "CEDULA DE CIUDADANIA",
        "NUIP 1.032.456.789",
        "APELLIDOS",
        "TORRES QUINTERO",
        "NOMBRES",
        "ANA MARIA",
        "ANA TORRES",
        "REGISTRADURIA NACIONAL DEL ESTADO CIVIL",
        "PLACA ABC123",
    ]

    tmp_pdf = os.path.join(tempfile.gettempdir(), "seguria_demo_cedula.pdf")
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=14)
        for ln in lines:
            pdf.cell(w=190, h=10, text=ln, new_x="LMARGIN", new_y="NEXT")
        pdf.output(tmp_pdf)
        print(f"[demo] PDF de prueba generado en: {tmp_pdf}")
    except Exception as exc:  # pragma: no cover
        print(f"[demo] No se pudo generar el PDF con fpdf: {exc}")
        return {}

    # 2) Guardarlo con save_upload (prueba el almacenamiento).
    with open(tmp_pdf, "rb") as fh:
        saved = save_upload("cedula_ana.pdf", fh.read())
    print("[demo] save_upload ->")
    print(json.dumps(saved, indent=2, ensure_ascii=False))

    # 3) Parsearlo.
    result = parse_document(saved["path"], filename=saved["filename"])
    print("\n[demo] parse_document ->")
    printable = {k: v for k, v in result.items() if k != "texto"}
    printable["texto_preview"] = result["texto"][:200].replace("\n", " | ")
    print(json.dumps(printable, indent=2, ensure_ascii=False))

    return result


if __name__ == "__main__":
    res = _demo()
    campos = (res or {}).get("campos_extraidos", {})
    ok = "numero_documento" in campos or "placa" in campos
    print("\n[demo] VERIFICACION:",
          "OK - se extrajo número y/o placa" if ok else "FALLO - no se extrajo número ni placa")
