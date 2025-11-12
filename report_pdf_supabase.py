# worker/report_pdf_supabase.py
import os
from datetime import datetime
from fpdf import FPDF
from supabase_io import upload_to_reports, signed_url, BUCKET_REP


# ========= Normalización y nombres bonitos =========
# Claves canónicas en minúsculas
CANON_KEYS = {
    "bacterias": "bacterias",
    "bacteria": "bacterias",
    "gorgojo": "gorgojo",
    "hongo": "hongo",
    "hongos": "hongo",
    "nematodo": "nematodo",
    "nematodos": "nematodo",
    "minadores": "minadores",
    "minador": "minadores",
    "phytophthora": "phytophthora",
    "tizon": "phytophthora",
    "tizón": "phytophthora",
    "saludable": "saludable",
    "healthy": "saludable",
}

DISPLAY_NAME = {
    "bacterias": "Bacterias",
    "gorgojo": "Gorgojo",
    "hongo": "Hongo",
    "nematodo": "Nematodo",
    "minadores": "Minadores",
    "phytophthora": "Phytophthora (Tizón)",
    "saludable": "Saludable",
}

def _canon(s: str | None) -> str:
    if not s:
        return ""
    k = s.strip().lower()
    return CANON_KEYS.get(k, k)

def _sev_rgb(sev: str):
    s = (sev or "").lower()
    if "crít" in s or "crit" in s:  # crítico
        return (231, 76, 60)
    if "lev" in s:                  # leve
        return (255, 193, 7)
    return (88, 204, 2)             # sano

def _percent(p01: float | None) -> str:
    if p01 is None: return "—"
    return f"{max(0.0, min(1.0, p01))*100:.1f}%"

def _pretty_name(raw_label: str | None) -> str:
    if not raw_label:
        return "—"
    c = _canon(raw_label)
    return DISPLAY_NAME.get(c, raw_label)

def _guess_type(per_class: dict | None) -> str:
    if not per_class or not isinstance(per_class, dict) or len(per_class) == 0:
        return "Plaga / Enfermedad"
    names = " ".join([str(k).lower() for k in per_class.keys()])
    if any(x in names for x in ["phytophthora", "tizón", "tizon", "hongo", "roya", "oidio", "mildiu", "botrytis"]):
        return "Enfermedad"
    return "Plaga"

def _main_label(per_class: dict | None) -> str:
    """
    Devuelve la clase principal para el texto explicativo:
    1) ordena por conteo desc
    2) intenta ignorar 'saludable' si hay otra clase con conteo > 0
    """
    if not per_class or not isinstance(per_class, dict) or len(per_class) == 0:
        return "—"
    # lista [(canon, display, count)]
    entries = []
    for k, v in per_class.items():
        try:
            cnt = float(v) if isinstance(v, (int, float, str)) else 0.0
        except Exception:
            cnt = 0.0
        ck = _canon(str(k))
        entries.append((ck, _pretty_name(str(k)), cnt))
    # orden por conteo desc
    entries.sort(key=lambda t: -t[2])
    if not entries:
        return "—"
    # si el top es saludable pero hay otra con conteo > 0, elige la otra
    top = entries[0]
    if top[0] == "saludable":
        for e in entries[1:]:
            if e[2] > 0:
                return e[1]
    return top[1]

# ========= Textos por clase =========
WHY_TXT = {
    "bacterias": (
        "Las bacteriosis suelen asociarse a heridas, salpicaduras de agua y alta humedad. "
        "Herramientas y manejo pueden favorecer la diseminación."
    ),
    "gorgojo": (
        "El gorgojo se favorece con suelos agrietados y manejo deficiente de residuos. "
        "Las larvas dañan raíces y tubérculos."
    ),
    "hongo": (
        "Las enfermedades fúngicas prosperan con humedad alta, mojado foliar prolongado y ventilación deficiente."
    ),
    "nematodo": (
        "Los nematodos proliferan en suelos infestados y rotaciones inadecuadas; dañan raíces afectando vigor y rendimiento."
    ),
    "minadores": (
        "El minador prolifera con clima templado y follaje denso; las larvas excavan galerías cuando no hay control temprano."
    ),
    "phytophthora": (
        "El tizón tardío (Phytophthora) aparece con alta humedad, rocío nocturno y temperaturas frescas; "
        "la densidad y falta de ventilación agravan la severidad."
    ),
    "saludable": (
        "No se observan signos relevantes de plaga o enfermedad."
    ),
}
RECO_TXT_CRIT = {
    "phytophthora": (
        "• Fungicida activo para Phytophthora (p. ej., metalaxil-M + mancozeb / cimoxanilo), rotando FRAC.\n"
        "• Mejorar ventilación, evitar riegos nocturnos, retirar focos.\n"
        "• Monitoreo cada 3–5 días y registro fotográfico."
    ),
    "gorgojo": (
        "• Insecticida de suelo conforme etiqueta (p. ej., cipermetrina/granular) y sellado de grietas.\n"
        "• Eliminar residuos y malezas; rotar cultivo.\n"
        "• Considerar trampas/feromonas y evaluación semanal."
    ),
    "minadores": (
        "• Insecticida sistémico registrado (abamectina/spinosad), rotando modos de acción.\n"
        "• Remover hojas muy dañadas y malezas hospederas.\n"
        "• Monitorear cada 3–5 días y ajustar dosis por etiqueta."
    ),
    "hongo": (
        "• Aplicar fungicida según etiqueta (rotar FRAC), evitar mojado foliar prolongado.\n"
        "• Mejorar ventilación y espaciamiento; retirar focos.\n"
        "• Monitoreo cercano (48–72 h)."
    ),
    "bacterias": (
        "• Manejo sanitario estricto: evitar heridas y salpicaduras; desinfectar herramientas.\n"
        "• Retirar tejidos muy afectados.\n"
        "• Consultar producto permitido localmente y monitorear 48–72 h."
    ),
    "nematodo": (
        "• Enfoque integrado: rotación de cultivos no hospederos, materia orgánica, solarización.\n"
        "• En casos severos, considerar nematicidas autorizados.\n"
        "• Muestreo de suelo y seguimiento técnico."
    ),
}
RECO_TXT_LEVE_GENERIC = (
    "• Control cultural y saneamiento (ventilación, densidad, riego oportuno).\n"
    "• Tratamientos biológicos/preventivos si corresponde.\n"
    "• Seguimiento cada 3–5 días."
)
RECO_TXT_SANO = (
    "• Mantener buenas prácticas de manejo y monitoreo preventivo.\n"
    "• Registrar condiciones ambientales y rotación de cultivos."
)

def _why_for_label(label_display: str) -> str:
    # convertir display → canon para buscar
    c = _canon(label_display)
    # fallback: si display venía “Phytophthora (Tizón)”
    if c == "" and "phytophthora" in (label_display or "").lower():
        c = "phytophthora"
    return WHY_TXT.get(c, (
        "Las condiciones ambientales (humedad/temperatura) y el manejo del cultivo "
        "(densidad, ventilación, riego) favorecen la incidencia."
    ))

def _reco_for(severity: str, label_display: str) -> str:
    s = (severity or "").lower()
    c = _canon(label_display)
    if "crít" in s or "crit" in s:
        return RECO_TXT_CRIT.get(c, (
            "• Aplicar control químico/biológico específico (seguir etiqueta y EPP).\n"
            "• Reducir humedad y hojarasca; mejorar ventilación.\n"
            "• Monitoreo cercano (48–72 h)."
        ))
    if "lev" in s:
        return RECO_TXT_LEVE_GENERIC
    return RECO_TXT_SANO

# ========= plantilla FPDF =========
class ReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 8, "Monitoreo Aéreo – Informe", ln=1)
        self.ln(1)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110,110,110)
        self.cell(0, 6,
                  f"Generado automáticamente • Página {self.page_no()}",
                  align="C")
        self.set_text_color(0,0,0)

# ========= constructor principal =========
def build_and_upload_pdf(
    user_id: str,
    section: str,
    filename: str,           # se usa para nombre del archivo
    annotated_bytes: bytes,  # PNG anotada
    severity: str,
    recommendation: str | None,
    counts: dict | None,
    per_class: dict | None,
    damage_pct01: float | None,   # 0..1
):
    # normaliza insumos
    per_class = per_class or counts or {}
    # construir un dict {DisplayName: conteo} ya mapeado
    mapped_counts = {}
    for k, v in (per_class.items() if isinstance(per_class, dict) else []):
        name = _pretty_name(str(k))
        try:
            cnt = float(v) if isinstance(v, (int, float, str)) else 0.0
        except Exception:
            cnt = 0.0
        mapped_counts[name] = mapped_counts.get(name, 0.0) + cnt

    main_lbl  = _main_label(mapped_counts)
    tipo      = _guess_type(mapped_counts)
    sev_rgb   = _sev_rgb(severity)

    # heurística si no llega porcentaje
    if damage_pct01 is None:
        s = (severity or "").lower()
        damage_pct01 = 0.30 if "crít" in s or "crit" in s else (0.12 if "lev" in s else 0.02)

    why_txt  = _why_for_label(main_lbl)
    reco_txt = recommendation or _reco_for(severity, main_lbl)

    # ==== PDF
    pdf = ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    # — Resumen (banda compacta)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Resumen", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(95, 6, f"Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    pdf.cell(95, 6, f"Sección: {section}", ln=1)
    pdf.cell(95, 6, f"Tipo: {tipo}")
    # Severidad con color
    r,g,b = sev_rgb
    pdf.set_text_color(r,g,b)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(95, 6, f"Severidad: {severity}", ln=1, align="R")
    pdf.set_text_color(0,0,0)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(95, 6, f"Afectación estimada: {_percent(damage_pct01)}", ln=1)
    # Principal identificado
    pdf.cell(0, 6, f"Principal identificado: {main_lbl}", ln=1)
    pdf.ln(2)

    # — Tabla de detecciones
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Detecciones", ln=1)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(110, 7, "Clase", border=1)
    pdf.cell(30, 7, "Conteo", border=1, ln=1, align="C")
    pdf.set_font("Helvetica", "", 11)
    if mapped_counts:
        for k, v in sorted(mapped_counts.items(), key=lambda kv: -float(kv[1])):
            pdf.cell(110, 7, str(k), border=1)
            pdf.cell(30, 7, str(int(v) if float(v).is_integer() else v), border=1, ln=1, align="C")
    else:
        pdf.cell(140, 7, "Sin detecciones relevantes", border=1, ln=1)
    pdf.ln(2)

    # — Imagen (compacta, centrada) — ancho máx 120 mm
    img_tmp = f"/tmp/{filename}_annot.png"
    try:
        with open(img_tmp, "wb") as f:
            f.write(annotated_bytes)
        max_w = 120
        x_left = (210 - max_w) / 2.0  # centra en A4 (210mm ancho)
        pdf.image(img_tmp, x=x_left, w=max_w)
    except Exception:
        pass
    finally:
        try: os.remove(img_tmp)
        except Exception: pass

    pdf.ln(3)

    # — Diagnóstico / ¿Por qué aparece?
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "¿Por qué aparece?", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 5.5, why_txt)

    # — Recomendaciones
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Recomendaciones", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 5.5, reco_txt)

    # ==== Exportar y subir (misma ruta/contrato que ya usa tu app)
    pdf_bytes = pdf.output(dest="S").encode("latin1")
    storage_path = f"reports/pdf/{filename}_report.pdf"
    upload_to_reports(storage_path, pdf_bytes, "application/pdf")
    pdf_url = signed_url(BUCKET_REP, storage_path, 3600 * 24 * 7)

    return storage_path, pdf_url, None, None
