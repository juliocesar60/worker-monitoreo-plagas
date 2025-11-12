# worker/worker_loop.py
import io
import os
import time
import json
import traceback
import tempfile
from uuid import uuid4

import numpy as np
from PIL import Image
from fpdf import FPDF
from ultralytics import YOLO

from supabase_io import (
    get_client,
    download_from_raw,
    upload_to_reports,
    lock_pending,
    IMAGES_TABLE,
)

# ==================== Config ====================

WEIGHTS_PATH  = os.getenv("WEIGHTS", "best.pt")
YOLO_CONF     = float(os.getenv("YOLO_CONF", "0.25"))   # confianza de predicción
BATCH_LIMIT   = int(os.getenv("BATCH_LIMIT", "5"))      # cuántas imágenes por iteración
SLEEP_SECONDS = float(os.getenv("SLEEP_SECONDS", "2.0"))
SIMULATE      = os.getenv("SIMULATE", "0") == "1"

REPORTS_TABLE = os.getenv("REPORTS_TABLE", "reports")   # tabla de reportes

print(f"[YOLO] Cargando pesos: {WEIGHTS_PATH}")
model = YOLO(WEIGHTS_PATH)
MODEL_NAMES = model.names if hasattr(model, "names") else {}

# ==================== Utilidades ====================

def fetch_pending(limit=BATCH_LIMIT):
    """Lee filas 'pending' ordenadas por created_at (asc)."""
    supa = get_client()
    res = (
        supa.table(IMAGES_TABLE)
        .select("id, user_id, section, storage_path, status, created_at")
        .eq("status", "pending")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return res.data or []

def image_bytes_to_numpy(img_bytes: bytes) -> np.ndarray:
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(im)

def run_yolo(ori_bytes: bytes):
    """
    Corre YOLOv8 y devuelve:
      annotated_png_bytes, severity ('Sano'|'Leve'|'Crítico'),
      affect_pct (0..100), class_counts (dict),
      avg_conf (0..1), max_conf (0..1), n_boxes (int),
      probs_by_class (dict {clase: prob máx})
    """
    arr = image_bytes_to_numpy(ori_bytes)

    # Inferencia en CPU para evitar errores de CUDA
    results = model.predict(source=arr, conf=YOLO_CONF, verbose=False, device="cpu")
    r = results[0]

    # Imagen anotada (r.plot -> BGR)
    plotted_bgr = r.plot()
    annotated_rgb = plotted_bgr[:, :, ::-1]  # BGR -> RGB
    out_png = io.BytesIO()
    Image.fromarray(annotated_rgb).save(out_png, format="PNG")
    annotated_bytes = out_png.getvalue()

    # Métricas por imagen
    total_area = float(arr.shape[0] * arr.shape[1])
    area_sum = 0.0
    counts = {}
    names = MODEL_NAMES if isinstance(MODEL_NAMES, dict) else {}
    confs = []
    probs_by_class = {}
    n_boxes = len(r.boxes) if r.boxes is not None else 0

    if r.boxes is not None:
        for box in r.boxes:
            cls_id = int(box.cls[0].item()) if hasattr(box.cls[0], "item") else int(box.cls[0])
            label = names.get(cls_id, str(cls_id))
            conf = float(box.conf[0]) if hasattr(box, "conf") else None
            if conf is not None:
                confs.append(conf)
                prev = probs_by_class.get(label, 0.0)
                probs_by_class[label] = max(prev, conf)

            counts[label] = counts.get(label, 0) + 1

            xyxy = box.xyxy[0].tolist()
            w = max(0.0, float(xyxy[2] - xyxy[0]))
            h = max(0.0, float(xyxy[3] - xyxy[1]))
            area_sum += w * h

    affect_pct = round(100.0 * area_sum / total_area, 2) if total_area > 0 else 0.0

    # Severidad por % de área afectada (ajusta si quieres)
    if n_boxes == 0 or affect_pct < 5:
        severity = "Sano"
    elif affect_pct < 25 and n_boxes < 10:
        severity = "Leve"
    else:
        severity = "Crítico"

    avg_conf = round(float(sum(confs) / len(confs)), 3) if confs else 0.0
    max_conf = round(float(max(confs)), 3) if confs else 0.0

    return annotated_bytes, severity, affect_pct, counts, avg_conf, max_conf, n_boxes, probs_by_class

def build_pdf(section: str, severity: str, affect_pct: float, counts: dict, annotated_png_bytes: bytes) -> bytes:
    """Genera un PDF simple con resumen + imagen anotada (sin tocar rutas/estilo externo)."""
    tmp_img = os.path.join(tempfile.gettempdir(), f"annot_{uuid4().hex}.png")
    with open(tmp_img, "wb") as f:
        f.write(annotated_png_bytes)

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=12)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Monitoreo Aéreo - Informe Automático", ln=1)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Sección: {section}", ln=1)
    pdf.cell(0, 7, f"Severidad: {severity}", ln=1)
    pdf.cell(0, 7, f"Afectación estimada: {affect_pct}%", ln=1)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Conteo por clase:", ln=1)
    pdf.set_font("Helvetica", "", 11)
    if counts:
        for k, v in counts.items():
            pdf.cell(0, 6, f"- {k}: {v}", ln=1)
    else:
        pdf.cell(0, 6, "- Sin detecciones", ln=1)

    pdf.ln(4)
    try:
        pdf.image(tmp_img, x=15, w=180)
    except Exception as e:
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 6, f"[Aviso] No se pudo incrustar la imagen: {e}", ln=1)
        pdf.set_text_color(0, 0, 0)

    try:
        pdf_bytes = pdf.output(dest="S").encode("latin-1")
    except Exception:
        pdf_bytes = pdf.output(dest="S").encode("latin-1")

    try:
        os.remove(tmp_img)
    except Exception:
        pass

    return pdf_bytes

# ==================== Proceso por imagen ====================

def process_one(row: dict):
    """Procesa una fila de la tabla images (status='pending')."""
    supa = get_client()

    image_id = row["id"]
    user_id  = row.get("user_id")
    storage_path = (row.get("storage_path") or "").replace("\\", "/")
    section = row.get("section") or "CAM"

    try:
        # 1) Lock (evita dobles procesos)
        lock_pending(image_id)

        # 2) Descargar original
        ori_bytes = download_from_raw(storage_path)

        # 3) YOLO
        if SIMULATE:
            annotated_png_bytes = ori_bytes
            severity, affect_pct, counts = "Sano", 0.0, {}
            avg_conf, max_conf, n_boxes, probs_by_class = 0.0, 0.0, 0, {}
        else:
            (annotated_png_bytes,
             severity,
             affect_pct,
             counts,
             avg_conf,
             max_conf,
             n_boxes,
             probs_by_class) = run_yolo(ori_bytes)

        # 4) PDF
        pdf_bytes = build_pdf(section, severity, affect_pct, counts, annotated_png_bytes)

        # 5) Subir artefactos
        annotated_name = f"{image_id}_annotated.png"
        pdf_name       = f"{image_id}_report.pdf"

        annotated_path = upload_to_reports(annotated_name, annotated_png_bytes, "image/png")
        pdf_path       = upload_to_reports(pdf_name, pdf_bytes, "application/pdf")

        # 6) Armar JSON de métricas para la app (en reports.metrics)
        metrics = {
            "confidence_avg": float(avg_conf),
            "confidence_max": float(max_conf),
            "detections_total": int(n_boxes),
            "per_class_max": probs_by_class,          # dict: {clase: prob_max}
            "affect_pct": float(affect_pct),          # útil tenerlo también aquí
        }

        # 7) Actualizar la fila en images (opcional pero útil para trazabilidad)
        supa.table(IMAGES_TABLE).update({
            "status": "done",
            "severity": severity,
            "counts": counts,                   # <- chips en la app (si leen images)
            "detections": metrics,              # <- antes pusiste 'detections'; ahora metemos mismo dict
            "annotated_path": annotated_path,   # 'reports/<id>_annotated.png'
            "report_pdf_path": pdf_path,        # 'reports/<id>_report.pdf'
            "processed_at": __import__("datetime").datetime.utcnow().isoformat()
        }).eq("id", image_id).execute()

        # 8) Insertar/actualizar en reports (esto es lo que la app lee para NO mostrar ceros)
        #    Usa image_id para enlazar reporte con la imagen original.
        report_row = {
            "user_id": user_id,
            "section": section,
            "severity": severity,
            "image_id": image_id,              # requiere columna image_id uuid en reports
            "counts": counts,                  # jsonb
            "metrics": metrics,                # jsonb (confidence_avg, etc.)
            "annotated_path": annotated_path,
            "report_pdf_path": pdf_path,
        }
        # upsert por (image_id) si definiste unique; si no, inserta nuevas filas
        supa.table(REPORTS_TABLE).insert(report_row).execute()

        print(f"[OK] {image_id} → processed ({severity}, {affect_pct}%)  "
              f"avg={avg_conf} max={max_conf} dets={n_boxes}  classes={counts}")

    except Exception as e:
        msg = f"{e.__class__.__name__}: {e}\n{traceback.format_exc(limit=2)}"
        # Si algo falla, marca error en la fila
        try:
            supa.table(IMAGES_TABLE).update({
                "status": "error",
                "error_msg": (msg or "")[:1000],
            }).eq("id", image_id).execute()
        except Exception:
            pass
        print(f"[ERR] {image_id}: {msg}")

# ==================== Loop ====================

def main():
    print("[WORKER] Iniciado. Buscando imágenes 'pending'...")
    while True:
        try:
            rows = fetch_pending()
            if not rows:
                time.sleep(SLEEP_SECONDS)
                continue
            for r in rows:
                process_one(r)
        except KeyboardInterrupt:
            print("[WORKER] Detenido por usuario.")
            break
        except Exception as e:
            print(f"[WORKER] Error de ciclo: {e}")
            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    main()
