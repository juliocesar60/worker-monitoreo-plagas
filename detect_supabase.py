# ================================================================
# Proyecto : Sistema Inteligente de Monitoreo Aéreo EMIE (Papa)
# Archivo  : detect_supabase.py
# Versión  : 1.2 (Producción: JSON + Imagen Anotada + PDF)
# Autor    : [TU NOMBRE]
# Fecha    : Octubre 2025
# Notas    :
#   - Procesa imágenes "pending" de Supabase (tabla: images)
#   - Ejecuta YOLO (best.pt)
#   - Calcula métricas y severidad
#   - Sube anotaciones y JSON/PDF a bucket 'reports'
#   - Actualiza 'images' y opcionalmente inserta en 'reports'
#   - Compatible con tu app Flutter (campos: annotated_path, report_pdf_path, counts, detections/metrics)
# ================================================================

import os
import io
import time
import json
import traceback
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

from supabase_io import (
    get_client,
    download_from_raw,
    upload_to_reports,
    signed_url,
    BUCKET_REP,
)

# =======================
# CONFIGURACIÓN BASE
# =======================
WEIGHTS = os.getenv("WEIGHTS", "best.pt")
DEVICE = os.getenv("YOLO_DEVICE", "cpu")
IMGSZ = int(float(os.getenv("YOLO_IMGSZ", "1024")))
IOU = float(os.getenv("YOLO_IOU", "0.55"))
CONF_DF = float(os.getenv("YOLO_CONF_DEFAULT", "0.25"))
AUGMENT = os.getenv("YOLO_AUGMENT", "false").lower() == "true"
DEBUG = os.getenv("DEBUG", "0") == "1"
FETCH_MODE = os.getenv("FETCH_MODE", "TODAY").upper()  # "TODAY" | "LATEST"

# CLASES Y UMBRALES (coincidir con data.yaml)
CLASS_CONF = {
    "Bacterias": float(os.getenv("YOLO_CONF_Bacterias", str(CONF_DF))),
    "Gorgojo": float(os.getenv("YOLO_CONF_Gorgojo", str(CONF_DF))),
    "Hongo": float(os.getenv("YOLO_CONF_Hongo", str(CONF_DF))),
    "Nematodo": float(os.getenv("YOLO_CONF_Nematodo", str(CONF_DF))),
    "Minadores": float(os.getenv("YOLO_CONF_Minadores", str(CONF_DF))),
    "Phytophthora": float(os.getenv("YOLO_CONF_Phytophthora", str(CONF_DF))),
    # "Saludable" no necesita umbral especial
}

LA_PAZ_TZ = timezone(timedelta(hours=-4))  # America/La_Paz

# =======================
# UTILITARIOS
# =======================
def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()

def start_of_today_utc():
    """00:00 hoy (La Paz) -> UTC ISO para filtrar en DB."""
    today_lp = datetime.now(LA_PAZ_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return today_lp.astimezone(timezone.utc).isoformat()

def today_token_lp():
    """Token 'YYYYMMDD' de HOY (La Paz) para filtrar por nombre en storage_path."""
    d = datetime.now(LA_PAZ_TZ)
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"

def normalize_storage_path(p: str) -> str:
    """Limpia prefijo 'raw/' (en BD guardas 'raw/user/..', aquí queremos relativo al bucket)."""
    p = (p or "").strip().lstrip("/")
    if p.lower().startswith("raw/"):
        p = p[4:]
    return p

def recommend_from_top(counts: dict) -> str:
    """Recomendación basada solo en plagas/enfermedades (excluye 'Saludable')."""
    pests = {k: v for k, v in counts.items() if k.lower() not in ("saludable", "sano", "healthy")}
    if not pests:
        return "Sin detecciones visibles. Monitoreo continuo recomendado."
    top = max(pests.items(), key=lambda kv: kv[1])[0]
    return f"Se recomienda inspección focalizada para: {top}."

def _sev_color_tuple(severity: str) -> tuple[int, int, int]:
    s = (severity or "").lower()
    if "crít" in s or "crit" in s:
        return (230, 57, 53)   # rojo
    if "lev" in s:
        return (255, 193, 7)   # amarillo
    return (46, 204, 113)      # verde

def draw_annotations(img_bytes: bytes, detections: list, severity: str | None = None) -> bytes:
    """Dibuja boxes y etiquetas. El borde de caja se pinta por confianza; se añade una banda de severidad."""
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        font_big = ImageFont.truetype("arial.ttf", 22)
    except:
        font = None
        font_big = None

    # Banda de severidad en la parte superior
    if severity:
        col = _sev_color_tuple(severity)
        W, H = im.size
        band_h = int(H * 0.06)
        draw.rectangle([0, 0, W, band_h], fill=col)
        label = f"Severidad: {severity.upper()}"
        draw.text((12, 8), label, fill=(255, 255, 255), font=font_big or font)

    # Cajas por detección
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        cls = det["class"]; conf = det["conf"]
        label = f"{cls} {conf:.2f}"
        # color por confianza (verde->amarillo->rojo)
        if conf >= 0.70:
            color = (230, 57, 53)   # rojo
        elif conf >= 0.45:
            color = (255, 193, 7)   # amarillo
        else:
            color = (46, 204, 113)  # verde

        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        # etiqueta
        if hasattr(draw, "textbbox"):
            x0, y0, x1t, y1t = draw.textbbox((0, 0), label, font=font)
            tw, th = x1t - x0, y1t - y0
        else:
            tw, th = (draw.textlength(label, font=font) or 80), 16
        draw.rectangle([x1, y1 - th - 6, x1 + tw + 8, y1], fill=color)
        draw.text((x1 + 4, y1 - th - 4), label, fill=(255, 255, 255), font=font)

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()

def build_report_json(meta: dict) -> bytes:
    return json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")

# =======================
# SEVERIDAD Y MÉTRICAS
# =======================
def eval_severity_from_detections(dets: list) -> str:
    """
    Calcula severidad usando SOLO plagas/enfermedades (excluye 'Saludable').
    Reglas combinadas por promedio de confianza y cantidad:
      - crítico: avg_conf >= 0.70 o n >= 5
      - leve   : avg_conf >= 0.45 o n >= 2
      - sano   : otro caso o sin detecciones de plaga
    """
    pest_confs = [float(d["conf"]) for d in dets if d.get("class", "").lower() not in ("saludable", "sano", "healthy")]
    n = len(pest_confs)
    if n == 0:
        return "sano"
    avg = sum(pest_confs) / n
    if avg >= 0.70 or n >= 5:
        return "crítico"
    if avg >= 0.45 or n >= 2:
        return "leve"
    return "sano"

def compute_metrics(dets: list) -> dict:
    """Métricas compactas para UI/PDF y compatibilidad con tu app."""
    if not dets:
        return {"avg_conf": 0.0, "max_conf": 0.0, "n_boxes": 0, "affect_pct": 0.0}
    confs = [float(d["conf"]) for d in dets]
    avg_conf = float(sum(confs) / len(confs))
    max_conf = float(max(confs))
    n_boxes = int(len(dets))
    pest_count = len([1 for d in dets if d["class"].lower() not in ("saludable", "sano", "healthy")])
    affect_pct = (pest_count / n_boxes * 100.0) if n_boxes > 0 else 0.0
    return {
        "avg_conf": round(avg_conf, 4),
        "max_conf": round(max_conf, 4),
        "n_boxes": n_boxes,
        "affect_pct": round(affect_pct, 2),
    }

# =======================
# YOLO
# =======================
def load_model():
    print(f"[CONFIG] WEIGHTS={WEIGHTS}")
    print(f"[CONFIG] DEVICE={DEVICE}  CONF={CONF_DF}  IMGSZ={IMGSZ}  IOU={IOU}")
    print(f"[YOLO] Cargando pesos: {WEIGHTS}")
    return YOLO(WEIGHTS)

def run_yolo(model, img_bytes: bytes):
    """Bytes -> PIL -> numpy -> YOLO. Retorna lista de dicts {class, conf, bbox}."""
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = np.array(im)  # HxWx3
    results = model.predict(
        source=arr,
        imgsz=IMGSZ,
        conf=CONF_DF,
        iou=IOU,
        device=DEVICE,
        verbose=False,
        augment=AUGMENT,
        stream=False,
    )
    out = []
    if not results:
        return out
    r = results[0]
    if r.boxes is None:
        return out
    names = r.names
    for b in r.boxes:
        cls_id = int(b.cls.item())
        conf = float(b.conf.item())
        name = names.get(cls_id, str(cls_id))
        thr = CLASS_CONF.get(name, CONF_DF)
        if conf < thr:
            continue
        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
        out.append({"class": name, "conf": conf, "bbox": [x1, y1, x2, y2]})
    return out

# =======================
# GENERACIÓN DE PDF
# =======================
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Image as RLImage
# import tempfile
# import os as _os

# Reemplaza COMPLETO tu función generar_pdf_informe por esta
def generar_pdf_informe(meta: dict | None = None,
                        annotated_png_bytes: bytes | None = None,
                        report_meta: dict | None = None,
                        **kwargs) -> bytes:
    # compatibilidad: si viene report_meta, úsalo como meta
    if meta is None and report_meta is not None:
        meta = report_meta
    # ... resto de la función tal como la tienes ...

    """
    Genera un PDF con la información del reporte en memoria (BytesIO).
    Si 'annotated_png_bytes' viene, inserta la imagen 400x300 centrada
    justo debajo del subtítulo 'Diagnóstico'.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    flow = []

    # Título
    flow.append(Paragraph("<b>Informe de Monitoreo de Cultivo</b>", styles["Title"]))
    flow.append(Spacer(1, 0.3 * cm))

    # Encabezado de datos
    flow.append(Paragraph(f"ID Imagen: {meta.get('image_id', '-')}", styles["Normal"]))
    flow.append(Paragraph(f"Sección: {meta.get('section', '-')}", styles["Normal"]))
    flow.append(Paragraph(f"Fecha de procesamiento: {meta.get('processed_at', '-')}", styles["Normal"]))
    flow.append(Spacer(1, 0.3 * cm))

    # Diagnóstico
    sev = str(meta.get("severity", "sano")).capitalize()
    flow.append(Paragraph(f"<b>Diagnóstico:</b> {sev}", styles["Heading2"]))
    flow.append(Spacer(1, 0.2 * cm))

    # Imagen anotada (400x300) centrada, debajo de Diagnóstico
    if annotated_png_bytes:
        img_stream = io.BytesIO(annotated_png_bytes)
        img = RLImage(img_stream, width=400, height=300)  # px
        img.hAlign = "CENTER"
        flow.append(img)
        flow.append(Spacer(1, 0.4 * cm))

    # Detecciones
    counts = meta.get("counts") or {}
    if counts:
        flow.append(Paragraph("<b>Detecciones:</b>", styles["Heading3"]))
        for k, v in counts.items():
            flow.append(Paragraph(f"• {k}: {v}", styles["Normal"]))
        flow.append(Spacer(1, 0.2 * cm))

    # Métricas
    metrics = meta.get("metrics") or {}
    if metrics:
        flow.append(Paragraph("<b>Métricas del modelo:</b>", styles["Heading3"]))
        flow.append(Paragraph(f"Confianza promedio: {float(metrics.get('avg_conf', 0)):.2f}", styles["Normal"]))
        flow.append(Paragraph(f"Confianza máxima: {float(metrics.get('max_conf', 0)):.2f}", styles["Normal"]))
        flow.append(Paragraph(f"Detecciones totales: {int(metrics.get('n_boxes', 0))}", styles["Normal"]))
        flow.append(Paragraph(f"Afectación estimada: {float(metrics.get('affect_pct', 0)):.2f}%", styles["Normal"]))
        flow.append(Spacer(1, 0.3 * cm))

    # Recomendación
    rec = meta.get("recommendation")
    if rec:
        flow.append(Paragraph("<b>Recomendación:</b>", styles["Heading3"]))
        flow.append(Paragraph(str(rec), styles["Normal"]))
        flow.append(Spacer(1, 0.3 * cm))

    # Fuente
    flow.append(Paragraph(
        "<b>Fuente:</b> Sistema Monitoreo Aéreo EMIE – Inteligencia Artificial Agrícola",
        styles["Normal"])
    )

    # Construir PDF en memoria
    doc.build(flow)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes




# =======================
# SUPABASE HELPERS (DB)
# =======================
def _fetch_pending_images_today(supa, limit=10):
    """Filtra 'pending' de HOY (>= 00:00 La Paz) y además nombre con _YYYYMMDD_."""
    since_iso = start_of_today_utc()
    tok = today_token_lp()
    rows = (
        supa.table("images")
        .select("id,user_id,section,storage_path,status,created_at")
        .eq("status", "pending")
        .gte("created_at", since_iso)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    ).data or []
    if DEBUG:
        print(f"[DEBUG] pending>=hoy={len(rows)} token=_{tok}_")
    out = []
    for r in rows:
        sp = (r.get("storage_path") or "")
        if f"_{tok}_" in sp:
            out.append(r)
        elif DEBUG:
            print(f"[DEBUG] descartado: no token de hoy: {sp}")
    return out

def _fetch_latest_pending(supa, limit=1):
    """Para pruebas: trae últimos 'pending' sin mirar fecha."""
    rows = (
        supa.table("images")
        .select("id,user_id,section,storage_path,status,created_at")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    if DEBUG:
        print(f"[DEBUG] latest pending: {len(rows)}")
        for r in rows:
            print("   -", r["id"], r["created_at"], r["storage_path"])
    return list(reversed(rows))

def _debug_peek_pending(supa, n=8):
    """Solo debug."""
    tok = today_token_lp()
    rows = (
        supa.table("images")
        .select("id,storage_path,created_at,status")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(n)
        .execute()
    ).data or []
    print("[DEBUG] Peek pendientes recientes:")
    for r in rows:
        sp = r["storage_path"]
        has_today = f"_{tok}_" in (sp or "")
        print(f"  - id={r['id']} created={r['created_at']} today_token={has_today} path={sp}")

def _set_processing(supa, ids: list[str]):
    if not ids:
        return
    res = supa.table("images").update({"status": "processing"}).in_("id", ids).execute()
    print(f"[LOCK] set processing -> {len(res.data or [])} filas")

def _update_image_status(supa, image_id: str, status: str, error_msg: str | None = None):
    patch = {"status": status, "processed_at": utcnow_iso()}
    if error_msg:
        patch["error_message"] = str(error_msg)[:480]
    supa.table("images").update(patch).eq("id", image_id).execute()
    print(f"[UPDATE] image {image_id} -> {status}")
# ================================================================
# INSERCIÓN Y ACTUALIZACIÓN EN SUPABASE
# ================================================================
def _insert_report(
    supa,
    user_id: str,
    section: str,
    annotated_path: str | None,
    json_path: str | None,
    detections: list,
    counts: dict,
    severity: str,
    recommendation: str,
    image_id: str,
    metrics: dict | None = None,
    pdf_path: str | None = None,
):
    """
    Inserta un registro en la tabla 'reports'.
    Devuelve el id del reporte si la inserción fue exitosa.
    """
    payload = {
        "user_id": user_id,
        "section": section,
        "status": "done",
        "created_at": utcnow_iso(),
        "annotated_path": annotated_path,
        "report_json_path": json_path,
        "report_pdf_path": pdf_path,
        "detections": detections,
        "counts": counts,
        "severity": severity,
        "recommendation": recommendation,
        "image_id": image_id,
        "metrics": metrics or {},
    }

    try:
        res = supa.table("reports").insert(payload).execute()
        data = getattr(res, "data", None) or (res.get("data") if isinstance(res, dict) else None)
        if data and len(data) > 0 and isinstance(data[0], dict) and "id" in data[0]:
            print(f"[INSERT] Reporte insertado en 'reports' :: id={data[0]['id']}")
            return data[0]["id"]
    except Exception as e:
        print(f"[WARN] Error insertando en reports: {e}")

    # fallback: buscar por image_id
    try:
        res2 = (
            supa.table("reports")
            .select("id")
            .eq("image_id", image_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        data2 = getattr(res2, "data", None) or (res2.get("data") if isinstance(res2, dict) else None)
        if data2 and len(data2) > 0:
            return data2[0]["id"]
    except Exception:
        pass
    return None


# ================================================================
# PROCESAMIENTO INDIVIDUAL DE IMAGEN
# ================================================================
def process_one(supa, model, row: dict):
    """
    Procesa una imagen:
      - Descarga desde bucket 'raw'
      - Detecta con YOLO
      - Dibuja anotaciones
      - Calcula métricas y severidad
      - Genera JSON + PDF
      - Sube a bucket 'reports'
      - Actualiza registros en 'images' y 'reports'
    """
    image_id = row["id"]
    user_id = row["user_id"]
    section = (row.get("section") or "").upper()
    storage_path_raw = normalize_storage_path(row["storage_path"])

    print(f"[START] {image_id} :: {storage_path_raw}")
    try:
        ori_bytes = download_from_raw(storage_path_raw)
    except Exception as e:
        _update_image_status(supa, image_id, "error", error_msg=f"download-missing: {e}")
        print(f"[SKIP] {image_id} :: archivo no encontrado.")
        return

    # --- detección ---
    dets = run_yolo(model, ori_bytes)
    counts = defaultdict(int)
    for d in dets:
        counts[d["class"]] += 1
    counts = dict(counts)
    metrics = compute_metrics(dets)
    severity = eval_severity_from_detections(dets)
    recommendation = recommend_from_top(counts)

    # --- anotación visual ---
    annotated_png_bytes = draw_annotations(ori_bytes, dets, severity)

    # --- paths dentro de bucket 'reports' ---
    base_dir = f"{user_id}/{image_id}"
    annotated_name = f"{base_dir}/annotated.png"
    json_name = f"{base_dir}/report.json"
    pdf_name = f"{base_dir}/report.pdf"

    # --- subidas ---
    annotated_path = upload_to_reports(annotated_name, annotated_png_bytes, "image/png")

    report_meta = {
        "image_id": image_id,
        "user_id": user_id,
        "section": section,
        "storage_path_raw": storage_path_raw,
        "processed_at": utcnow_iso(),
        "detections": dets,
        "counts": counts,
        "metrics": metrics,
        "severity": severity,
        "recommendation": recommendation,
        "annotated_path": annotated_path,
    }
    json_bytes = build_report_json(report_meta)
    json_path = upload_to_reports(json_name, json_bytes, "application/json")

    # --- generar PDF con datos ---
      # --- generar PDF con datos ---
    pdf_bytes = generar_pdf_informe(
        report_meta=report_meta,
        annotated_png_bytes=annotated_png_bytes
    )
    pdf_path = upload_to_reports(f"{base_dir}/report.pdf", pdf_bytes, "application/pdf")

    # --- insertar reporte en 'reports' ---
    rpt_id = _insert_report(
        supa=supa,
        user_id=user_id,
        section=section,
        annotated_path=annotated_path,
        json_path=json_path,
        detections=dets,
        counts=counts,
        severity=severity,
        recommendation=recommendation,
        image_id=image_id,
        metrics=metrics,
    )

    # --- actualizar tabla 'images' ---
    supa.table("images").update({
        "annotated_path": annotated_path,
        "report_json_path": json_path,
        "report_pdf_path": pdf_path,
        "severity": severity,
        "counts": counts,
        "detections": metrics,
        "recommendation": recommendation,
        "status": "done",
        "processed_at": utcnow_iso()
    }).eq("id", image_id).execute()

    _update_image_status(supa, image_id, "done")
    print(f"[OK] image_id={image_id} -> report_id={rpt_id}  severity={severity}")
    print(f"[URL] annotated={signed_url(BUCKET_REP, annotated_path)}")
    print(f"[URL] json={signed_url(BUCKET_REP, json_path)}")
    print(f"[URL] pdf={signed_url(BUCKET_REP, pdf_path)}")



# ================================================================
# BUCLE PRINCIPAL
# ================================================================
def main():
    supa = get_client()
    model = load_model()
    print("[INFO] Worker YOLO (Supabase) iniciado correctamente.")
    print("[INFO] Modo FETCH:", FETCH_MODE)

    SLEEP_SEC_EMPTY = 8
    BATCH_SIZE = 6

    while True:
        try:
            if FETCH_MODE == "LATEST":
                rows = _fetch_latest_pending(supa, limit=BATCH_SIZE)
            else:
                rows = _fetch_pending_images_today(supa, limit=BATCH_SIZE)

            if not rows:
                if DEBUG:
                    print("[DEBUG] No hay imágenes pendientes. Reintentando...")
                time.sleep(SLEEP_SEC_EMPTY)
                continue

            _set_processing(supa, [r["id"] for r in rows])

            for row in rows:
                process_one(supa, model, row)

        except KeyboardInterrupt:
            print("[INFO] Detenido por usuario (Ctrl+C).")
            break
        except Exception as e:
            print(f"[LOOP ERROR] {e}")
            traceback.print_exc()
            time.sleep(SLEEP_SEC_EMPTY)


if __name__ == "__main__":
    main()
