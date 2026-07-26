"""Genera el PDF de resumen ejecutivo del plan de beneficios por permanencia
(vesting) + condiciones legales aplicables — documento de referencia interna,
no es un documento transaccional (no lo dispara ninguna tool del agente).

Uso: desde apps/ai, `python scripts/build_benefits_plan_pdf.py`
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.documents import (  # noqa: E402
    BrandPDF, CONTENT_W, MARGIN, _coverage_list, _doc_title, _kv_table,
    _latin, _legal_box, _section,
)
from app.benefits import MILESTONES_AFILIADO, MILESTONES_NO_AFILIADO  # noqa: E402
from app.underwriting import PREMIUM_REFER_COP  # noqa: E402


def build() -> str:
    pdf = BrandPDF("Plan de beneficios", "BEN-2026")
    pdf.add_page()

    _doc_title(
        pdf,
        "Programa de fidelización",
        "Plan de beneficios por permanencia",
        "Pólizas Tequendama × Colsubsidio — vigente desde julio de 2026",
    )

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 68, 62)
    pdf.multi_cell(CONTENT_W, 5.5, _latin(
        "En vez de pagar la adquisición con un descuento al comprar, el beneficio se paga "
        "con la capacidad ociosa que Colsubsidio ya tiene (clubes, hoteles, droguerías): se "
        "libera de forma ESCALONADA por meses de póliza vigente y sin interrupción. Solo se "
        "entrega si la póliza sobrevivió — nunca se adelanta costo de adquisición sobre prima "
        "que no se llegó a cobrar, y cancelar cerca de un hito cuesta algo concreto."
    ), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    _section(pdf, "Cómo funciona")
    _kv_table(pdf, [
        ("Hitos", "Mes 3, mes 6 y mes 12 de póliza vigente CONTINUA"),
        ("Condición", "Se otorga solo si la póliza sigue activa en esa fecha"),
        ("Cálculo", "Meses desde la fecha de inicio de la póliza, mientras status='vigente'"),
        ("Reinicio", "El ciclo se reinicia en cada renovación anual"),
        ("Entrega", "Aviso por WhatsApp con código de reclamo, canjeable en el punto Colsubsidio"),
    ])

    _section(pdf, "Escalera AFILIADOS Colsubsidio (beneficio mayor)")
    _coverage_list(pdf, [f"Mes {mes}: {beneficio}" for mes, beneficio in MILESTONES_AFILIADO])

    _section(pdf, "Escalera NO AFILIADOS")
    _coverage_list(pdf, [f"Mes {mes}: {beneficio}" for mes, beneficio in MILESTONES_NO_AFILIADO])
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(100, 110, 102)
    pdf.multi_cell(CONTENT_W, 4.6, _latin(
        "Misma red Colsubsidio en ambos casos; la diferencia es deliberada: el no afiliado "
        "recibe una versión más pequeña, limitada a los viernes y con descuento (nunca "
        "gratis) — también funciona como incentivo para afiliarse y acceder a la escalera "
        "completa."), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    _section(pdf, "Economía de referencia (cifras ILUSTRATIVAS, no verificadas)")
    _kv_table(pdf, [
        ("Prima mensual de referencia", "$18.000 COP (ejemplo: exequial familiar)"),
        ("Costo de adquisición tradicional", "≈ $70.000 (asesor + call center)"),
        ("Costo de adquisición propuesto", "≈ $12.000 en inventario perecedero"),
        ("Momento en que se causa el costo", "Tradicional: al cerrar. Propuesto: al llegar al mes 3"),
        ("Persistencia a 12 meses (meta)", "≈ 55% tradicional → 80% meta con el plan"),
    ])
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 130, 122)
    pdf.multi_cell(CONTENT_W, 4.2, _latin(
        "Fuente: Nota_estrategica_Seguros_Colsubsidio.pdf §7. Documento de trabajo — no son "
        "datos de mercado verificados, ilustran la estructura del modelo."
    ), new_x="LMARGIN", new_y="NEXT")

    pdf.add_page()
    _section(pdf, "Clasificación de modalidad por tipo de producto")
    _kv_table(pdf, [
        ("Colectiva (aceptación garantizada)", "Exequial, accidentes personales, mascotas, "
         "asistencias médicas, viaje — sin biometría ni declaración de riesgo individual"),
        ("Individual (flujo completo)", "Vida (sin ahorro), salud, hogar, PyME, movilidad, SOAT"),
        ("Asesor (no autogestionable)", "Auto todo riesgo, vida con ahorro/renta protegida — "
         "se deriva a un asesor humano, nunca se ofrece el checklist autogestionado"),
    ])
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*(60, 68, 62))
    umbrales = ", ".join(f"{k.lower()}: {v:,.0f} COP/mes" for k, v in PREMIUM_REFER_COP.items())
    pdf.multi_cell(CONTENT_W, 5, _latin(
        f"Umbral de auto-emisión por prima (por encima pasa a revisión humana, solo aplica a "
        f"modalidad individual): {umbrales}."
    ), new_x="LMARGIN", new_y="NEXT")

    _section(pdf, "Condiciones legales aplicables")
    _kv_table(pdf, [
        ("Ley 2300 de 2023", "Contacto comercial solo lun-vie 7:00-19:00 y sáb 8:00-15:00 "
         "(hora Colombia), nunca domingo — aplicado en el motor de llamadas salientes"),
        ("Ley 1480 de 2011", "Derecho de retracto de 5 días hábiles en venta a distancia"),
        ("Ley 1581 de 2012", "Autorización previa y auditable para tratar datos personales"),
        ("Ley 1328 de 2009", "Protección al consumidor financiero — coberturas y exclusiones "
         "en lenguaje claro antes de aceptar"),
        ("Art. 1058 C. de Comercio", "Declaración del estado del riesgo — neutralizado en "
         "pólizas COLECTIVAS (aceptación garantizada); sigue aplicando en INDIVIDUALES"),
    ])

    _legal_box(pdf, (
        "Los beneficios de este plan son promocionales y de fidelización: están sujetos a "
        "disponibilidad de cupo en cada punto Colsubsidio, no hacen parte de la cobertura "
        "asegurada, no tienen valor de rescate en efectivo y no generan obligación "
        "contractual para la aseguradora emisora de la póliza. Colsubsidio actúa como "
        "distribuidor/operador de estos beneficios, no como asegurador."
    ))

    out = Path(__file__).resolve().parent.parent.parent.parent / \
        "Plan_Beneficios_Permanencia_Colsubsidio.pdf"
    pdf.output(str(out))
    return str(out)


if __name__ == "__main__":
    path = build()
    print(f"PDF generado: {path}")
