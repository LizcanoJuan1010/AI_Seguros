"""Generación de documentos de marca en PDF (fpdf2, puro Python).

Identidad Tequendama: banda verde bosque con el logo en tarjeta blanca,
filete ámbar, marca de agua sutil, tarjetas redondeadas, tabla zebra,
coberturas con vistos y pie con folio + paginación en todas las páginas.
"""
import re
from datetime import datetime

from fpdf import FPDF

from .config import (
    BRAND_ACCENT_COLOR,
    BRAND_COLOR,
    BRAND_LOGO,
    BRAND_NAME,
    BRAND_TAGLINE,
    DOCS_DIR,
)


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _latin(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


# Paleta del documento (alineada con el frontend)
GREEN = _hex_rgb(BRAND_COLOR)          # banda y acentos principales
AMBER = _hex_rgb(BRAND_ACCENT_COLOR)   # filete/detalles dorados
INK = (23, 33, 26)                     # texto principal
MUTED = (100, 110, 102)                # texto secundario
LINE = (200, 212, 200)                 # bordes suaves
CARD = (233, 243, 233)                 # tarjetas verde niebla
ZEBRA = (246, 250, 246)                # filas alternas

PAGE_W = 210
MARGIN = 16
CONTENT_W = PAGE_W - 2 * MARGIN

# Marca de agua: versión del logo con fondo transparente (solo trazos)
WATERMARK = BRAND_LOGO.with_name("watermark.png")

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _fecha_larga(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    return f"{dt.day} de {MESES[dt.month - 1]} de {dt.year}"


class BrandPDF(FPDF):
    """Plantilla de marca: encabezado, marca de agua y pie en cada página."""

    def __init__(self, doc_type: str, folio: str):
        super().__init__(format="A4")
        self.doc_type = doc_type
        self.folio = folio
        self.set_title(f"{BRAND_NAME} · {doc_type}")
        self.set_author(BRAND_NAME)
        self.set_creator(f"{BRAND_NAME} AI")
        self.set_margins(MARGIN, 14, MARGIN)
        self.set_auto_page_break(auto=True, margin=26)
        self.alias_nb_pages()

    # -- encabezado -----------------------------------------------------
    def header(self):
        first = self.page_no() == 1
        band_h = 40 if first else 15

        self.set_fill_color(*GREEN)
        self.rect(0, 0, PAGE_W, band_h, style="F")
        self.set_fill_color(*AMBER)
        self.rect(0, band_h, PAGE_W, 1.4, style="F")

        # Marca de agua sutil bajo el contenido (solo trazos, sin fondo)
        if WATERMARK.exists():
            try:
                with self.local_context(fill_opacity=0.06):
                    self.image(str(WATERMARK), x=(PAGE_W - 110) / 2, y=105, w=110)
            except Exception:
                pass

        if first:
            text_x = MARGIN
            if BRAND_LOGO.exists():
                self.set_fill_color(255, 255, 255)
                self.rect(14, 7, 26, 26, style="F", round_corners=True, corner_radius=5)
                self.image(str(BRAND_LOGO), x=15.2, y=8.2, w=23.6)
                text_x = 46

            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 23)
            self.set_xy(text_x, 10)
            self.cell(0, 10, _latin(BRAND_NAME))
            self.set_font("Helvetica", "", 9.5)
            self.set_text_color(197, 224, 199)
            self.set_xy(text_x, 20.5)
            self.cell(0, 5, _latin(BRAND_TAGLINE))

            # Chip del tipo de documento (borde ámbar) + folio y fecha
            self.set_font("Helvetica", "B", 10)
            chip_w = self.get_string_width(_latin(self.doc_type.upper())) + 12
            chip_x = PAGE_W - MARGIN - chip_w
            self.set_draw_color(*AMBER)
            self.set_line_width(0.5)
            self.rect(chip_x, 8.5, chip_w, 9, style="D", round_corners=True, corner_radius=4.5)
            self.set_text_color(255, 214, 92)
            self.set_xy(chip_x, 8.5)
            self.cell(chip_w, 9, _latin(self.doc_type.upper()), align="C")

            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(210, 228, 211)
            self.set_xy(PAGE_W / 2, 21)
            self.cell(PAGE_W / 2 - MARGIN, 4.5, _latin(f"Folio {self.folio}"), align="R")
            self.set_xy(PAGE_W / 2, 26)
            self.cell(PAGE_W / 2 - MARGIN, 4.5, _latin(_fecha_larga()), align="R")

            self.set_y(50)
        else:
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 11)
            self.set_xy(MARGIN, 3.5)
            self.cell(60, 8, _latin(BRAND_NAME))
            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(207, 226, 208)
            self.set_xy(MARGIN, 3.5)
            self.cell(CONTENT_W, 8, _latin(f"{self.doc_type} · Folio {self.folio}"), align="R")
            self.set_y(24)

    # -- pie ------------------------------------------------------------
    def footer(self):
        self.set_y(-19)
        y = self.get_y()
        self.set_draw_color(*LINE)
        self.set_line_width(0.3)
        self.line(MARGIN, y, PAGE_W - MARGIN, y)
        self.set_fill_color(*AMBER)
        self.rect(MARGIN, y - 0.7, 9, 1.4, style="F")

        self.set_y(y + 2.5)
        self.set_font("Helvetica", "", 7.8)
        self.set_text_color(*MUTED)
        self.cell(CONTENT_W / 2, 5, _latin(f"{BRAND_NAME} · {BRAND_TAGLINE}"))
        self.cell(CONTENT_W / 2, 5,
                  _latin(f"Folio {self.folio} · Página {self.page_no()} de {{nb}}"),
                  align="R")


# -- piezas reutilizables ---------------------------------------------------

def _doc_title(pdf: FPDF, kicker: str, title: str, subtitle: str) -> None:
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(139, 106, 0)  # ámbar oscuro legible sobre blanco
    pdf.set_char_spacing(0.9)
    pdf.cell(0, 5, _latin(kicker.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.set_char_spacing(0)
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*INK)
    pdf.cell(0, 9, _latin(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, _latin(subtitle), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


def _section(pdf: FPDF, title: str) -> None:
    pdf.ln(2)
    y = pdf.get_y()
    pdf.set_fill_color(*AMBER)
    pdf.rect(MARGIN, y + 1.6, 3, 3, style="F")
    pdf.set_xy(MARGIN + 5.5, y)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*GREEN)
    pdf.set_char_spacing(0.7)
    pdf.cell(0, 6.2, _latin(title.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.set_char_spacing(0)
    pdf.ln(1.5)


def _kv_table(pdf: FPDF, rows: list[tuple[str, str]]) -> None:
    row_h = 8
    y0 = pdf.get_y()
    for i, (label, value) in enumerate(rows):
        y = pdf.get_y()
        if i % 2 == 0:
            pdf.set_fill_color(*ZEBRA)
            pdf.rect(MARGIN, y, CONTENT_W, row_h, style="F")
        pdf.set_xy(MARGIN + 4, y)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*GREEN)
        pdf.cell(62, row_h, _latin(label))
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*INK)
        pdf.cell(0, row_h, _latin(str(value)), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.3)
    pdf.rect(MARGIN, y0, CONTENT_W, len(rows) * row_h, style="D",
             round_corners=True, corner_radius=2.5)
    pdf.ln(2)


def _check_bullet(pdf: FPDF, x: float, y: float) -> None:
    pdf.set_fill_color(*GREEN)
    pdf.ellipse(x, y, 4.6, 4.6, style="F")
    pdf.set_draw_color(255, 255, 255)
    pdf.set_line_width(0.7)
    pdf.line(x + 1.15, y + 2.35, x + 1.95, y + 3.25)
    pdf.line(x + 1.95, y + 3.25, x + 3.55, y + 1.35)


def _coverage_list(pdf: FPDF, items: list) -> None:
    for item in items:
        y = pdf.get_y()
        _check_bullet(pdf, MARGIN + 1, y + 0.8)
        pdf.set_xy(MARGIN + 8.5, y)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*INK)
        pdf.multi_cell(CONTENT_W - 8.5, 6.2, _latin(item), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.8)


def _legal_box(pdf: FPDF, text: str) -> None:
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 7.8)
    lines = pdf.multi_cell(CONTENT_W - 8, 4.3, _latin(text), dry_run=True, output="LINES")
    box_h = len(lines) * 4.3 + 8
    if pdf.get_y() + box_h > 297 - 28:
        pdf.add_page()
    y = pdf.get_y()
    pdf.set_fill_color(246, 248, 246)
    pdf.rect(MARGIN, y, CONTENT_W, box_h, style="F", round_corners=True, corner_radius=3)
    pdf.set_xy(MARGIN + 4, y + 4)
    pdf.set_font("Helvetica", "I", 7.8)
    pdf.set_text_color(122, 130, 122)
    pdf.multi_cell(CONTENT_W - 8, 4.3, _latin(text))
    pdf.set_y(y + box_h)


def _highlight_card(pdf: FPDF, left_kicker: str, left_big: str, left_small: str,
                    right_kicker: str, right_big: str, right_small: str) -> None:
    """Tarjeta destacada de dos columnas con barra de acento ámbar."""
    h = 25
    y = pdf.get_y()
    pdf.set_fill_color(*CARD)
    pdf.rect(MARGIN, y, CONTENT_W, h, style="F", round_corners=True, corner_radius=4)
    pdf.set_fill_color(*AMBER)
    pdf.rect(MARGIN, y + 3, 2.2, h - 6, style="F", round_corners=True, corner_radius=1.1)

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*MUTED)
    pdf.set_char_spacing(0.7)
    pdf.set_xy(MARGIN + 7, y + 4)
    pdf.cell(90, 4, _latin(left_kicker.upper()))
    pdf.set_xy(PAGE_W / 2, y + 4)
    pdf.cell(PAGE_W / 2 - MARGIN - 5, 4, _latin(right_kicker.upper()), align="R")
    pdf.set_char_spacing(0)

    pdf.set_font("Helvetica", "B", 19)
    pdf.set_text_color(*GREEN)
    pdf.set_xy(MARGIN + 7, y + 9.5)
    pdf.cell(100, 9, _latin(left_big))
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_xy(PAGE_W / 2, y + 11)
    pdf.cell(PAGE_W / 2 - MARGIN - 5, 8, _latin(right_big), align="R")

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.set_xy(MARGIN + 7, y + 18.5)
    pdf.cell(100, 4.5, _latin(left_small))
    pdf.set_xy(PAGE_W / 2, y + 18.5)
    pdf.cell(PAGE_W / 2 - MARGIN - 5, 4.5, _latin(right_small), align="R")

    pdf.set_y(y + h + 5)


def _new_folio(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


# -- documentos --------------------------------------------------------------

def build_quote_pdf(quote: dict, lead: dict | None = None) -> str:
    """Genera el PDF de una cotización y devuelve la ruta del archivo."""
    folio = _new_folio("TQ-COT")
    pdf = BrandPDF("Cotización", folio)
    pdf.add_page()

    cliente = (lead or {}).get("name") or "Cliente interesado"
    _doc_title(
        pdf,
        "Cotización de seguro",
        quote["producto"],
        f"Preparada especialmente para {cliente} · {quote['pais']} · {_fecha_larga()}",
    )

    prima_local = f"{quote['prima_mensual_local']:,.2f} {quote['moneda']}"
    prima_usd = f"Equivale a USD {quote['prima_mensual_usd']:,.2f}"
    _highlight_card(
        pdf,
        f"Prima {quote['periodicidad']}", prima_local, prima_usd,
        "Suma asegurada", f"USD {quote['suma_asegurada_usd']:,.0f}",
        f"Respaldada por {quote['aseguradora']}",
    )

    _section(pdf, "Detalle de la propuesta")
    _kv_table(pdf, [
        ("Aseguradora", quote["aseguradora"]),
        ("Tipo de seguro", str(quote["tipo"]).capitalize()),
        ("Suma asegurada", f"USD {quote['suma_asegurada_usd']:,.0f}"),
        ("Moneda de pago", quote["moneda"]),
        ("Tasa de cambio aplicada", f"{quote['tasa_fx']:,.4f} {quote['moneda']}/USD"),
    ])

    _section(pdf, "Coberturas incluidas")
    _coverage_list(pdf, quote["coberturas"])

    _legal_box(pdf, (
        "Cotización referencial de pre-venta generada por el asistente digital de "
        f"{BRAND_NAME}. No constituye emisión de póliza ni oferta vinculante. La "
        "contratación final se realiza con un asesor licenciado de la aseguradora, "
        "sujeta a suscripción, exclusiones y condiciones del país."
    ))

    filename = f"cotizacion_{quote['product_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = DOCS_DIR / filename
    pdf.output(str(path))
    return str(path)


def _fmt_date(value: str) -> str:
    """ISO -> dd/mm/aaaa (tolerante: si no parsea, devuelve el original)."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(value)[:10]


def build_policy_pdf(policy: dict, customer: dict, coverage: dict | None = None) -> str:
    """Genera el certificado/carátula de una póliza EMITIDA y devuelve la ruta.

    `policy`   : {policyNumber, insuranceType, monthlyPremiumCop, startDate, endDate,
                  status, aseguradora?}
    `customer` : {fullName, documentType, documentId, city?, email?, phone?}
    `coverage` : {resumen?, coberturas?: [...], aseguradora?}
    """
    coverage = coverage or {}
    status = str(policy.get("status") or "vigente").upper()
    pol_num = str(policy.get("policyNumber") or "N/D")

    pdf = BrandPDF("Certificado de póliza", pol_num)
    pdf.add_page()

    nombre = customer.get("fullName") or "Cliente"
    _doc_title(
        pdf,
        f"{BRAND_NAME} · Distribuido por Colsubsidio",
        "¡Ya quedaste con protección activa!",
        f"Certificado digital emitido para {nombre} · {_fecha_larga()}",
    )

    # Banda de estado: número de póliza + estado con visto
    y = pdf.get_y()
    pdf.set_fill_color(*CARD)
    pdf.rect(MARGIN, y, CONTENT_W, 13, style="F", round_corners=True, corner_radius=4)
    _check_bullet(pdf, MARGIN + 4, y + 4.2)
    pdf.set_xy(MARGIN + 11, y)
    pdf.set_font("Helvetica", "B", 12.5)
    pdf.set_text_color(*GREEN)
    pdf.cell(110, 13, _latin(f"Póliza N.º {pol_num}"))
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(PAGE_W / 2, y)
    pdf.cell(PAGE_W / 2 - MARGIN - 5, 13, _latin(f"Estado: {status}"), align="R")
    pdf.set_y(y + 17)

    ins_type = str(policy.get("insuranceType") or coverage.get("tipo") or "").capitalize()
    aseguradora = (policy.get("aseguradora") or coverage.get("aseguradora")
                   or "Aseguradora aliada")
    prima = policy.get("monthlyPremiumCop")
    try:
        prima_txt = f"{float(prima):,.0f} COP / mes" if prima is not None else "N/D"
    except (ValueError, TypeError):
        prima_txt = f"{prima} / mes"

    _section(pdf, "Datos de la póliza")
    rows = [
        ("Tomador / Asegurado", nombre),
        ("Documento", f"{customer.get('documentType', 'CC')} {customer.get('documentId', '')}".strip()),
        ("Tipo de seguro", ins_type or "N/D"),
        ("Aseguradora (emisora)", aseguradora),
        ("Prima", prima_txt),
        ("Vigencia desde", _fmt_date(policy.get("startDate")) or datetime.now().strftime("%d/%m/%Y")),
        ("Vigencia hasta", _fmt_date(policy.get("endDate")) or "+1 año"),
    ]
    if customer.get("city"):
        rows.append(("Ciudad", customer["city"]))
    if customer.get("email"):
        rows.append(("Correo", customer["email"]))
    _kv_table(pdf, rows)

    coberturas = coverage.get("coberturas") or []
    if coberturas:
        _section(pdf, "Coberturas incluidas")
        _coverage_list(pdf, coberturas)
    if coverage.get("resumen"):
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(CONTENT_W, 5.6, _latin(str(coverage["resumen"])),
                       new_x="LMARGIN", new_y="NEXT")

    _legal_box(pdf, (
        "Certificado de póliza emitido de forma digital. Colsubsidio actúa como distribuidor; "
        "la aseguradora indicada es la emisora y responsable de la cobertura. El tomador "
        "autorizó el tratamiento de sus datos (Ley 1581/2012) y cuenta con derecho de retracto "
        "dentro de los 5 días hábiles siguientes (Ley 1480/2011). Sujeto a las condiciones, "
        "exclusiones y clausulado de la póliza."
    ))

    safe_num = re.sub(r"[^A-Za-z0-9_-]", "", pol_num) or "poliza"
    filename = f"poliza_{safe_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = DOCS_DIR / filename
    pdf.output(str(path))
    return str(path)
