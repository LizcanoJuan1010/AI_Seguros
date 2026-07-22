"""Generación de la cotización formal en PDF (fpdf2, puro Python).

Patrón de identidad de marca tomado de reference/paloma_docx_builder.py
(portada con color corporativo, pie con aviso legal), simplificado a PDF
para no depender de WeasyPrint/pango.
"""
from datetime import datetime

from fpdf import FPDF

from .config import BRAND_COLOR, BRAND_NAME, BRAND_TAGLINE, DOCS_DIR


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _latin(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


def build_quote_pdf(quote: dict, lead: dict | None = None) -> str:
    """Genera el PDF de una cotización y devuelve la ruta del archivo."""
    r, g, b = _hex_rgb(BRAND_COLOR)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Encabezado de marca
    pdf.set_fill_color(r, g, b)
    pdf.rect(0, 0, 210, 34, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_xy(12, 8)
    pdf.cell(0, 10, _latin(BRAND_NAME))
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(12, 19)
    pdf.cell(0, 6, _latin(BRAND_TAGLINE))
    pdf.set_xy(12, 40)

    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, _latin(f"Cotización de seguro - {quote['producto']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    fecha = datetime.now().strftime("%d/%m/%Y")
    cliente = (lead or {}).get("name") or "Cliente interesado"
    pdf.cell(0, 6, _latin(f"Preparada para {cliente} - {quote['pais']} - {fecha}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Bloque de prima
    pdf.set_fill_color(240, 245, 250)
    pdf.set_text_color(r, g, b)
    pdf.set_font("Helvetica", "B", 13)
    prima_local = f"{quote['prima_mensual_local']:,.2f} {quote['moneda']}"
    prima_usd = f"(USD {quote['prima_mensual_usd']:,.2f})"
    pdf.cell(0, 12, _latin(f"  Prima {quote['periodicidad']}: {prima_local} {prima_usd}"),
             fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ("Aseguradora", quote["aseguradora"]),
        ("Tipo de seguro", quote["tipo"].capitalize()),
        ("Suma asegurada", f"USD {quote['suma_asegurada_usd']:,.0f}"),
        ("Moneda de pago", quote["moneda"]),
        ("Tasa de cambio aplicada", f"{quote['tasa_fx']:,.4f} {quote['moneda']}/USD"),
    ]
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(60, 7, _latin(label))
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, _latin(str(value)), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _latin("Coberturas incluidas"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for c in quote["coberturas"]:
        pdf.cell(6, 6, "-")
        pdf.multi_cell(0, 6, _latin(c), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 4.5, _latin(
        "Cotización referencial de pre-venta generada por el asistente digital. No constituye "
        "emisión de póliza ni oferta vinculante. La contratación final se realiza con un asesor "
        "licenciado de la aseguradora, sujeta a suscripción, exclusiones y condiciones del país."))

    filename = f"cotizacion_{quote['product_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = DOCS_DIR / filename
    pdf.output(str(path))
    return str(path)
