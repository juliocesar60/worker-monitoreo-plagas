# inferencia_mejorada.py
# Uso (ejemplos):
#   python inferencia_mejorada.py --model ./best.pt --data ./data.yaml --source "C:/ruta/a/imagenes" --outdir ./salidas_mejoradas
#
# Requisitos:
#   pip install ultralytics python-dotenv pyyaml
#
# Qué hace:
#  - Inferencia con:
#       * NMS por clase (agnostic_nms=False)
#       * Umbrales por clase desde .env (o valor por defecto)
#       * Filtro por tamaño mínimo/máximo y relación de aspecto
#       * TTA opcional
#  - Guarda:
#       * Imágenes anotadas "finales" (solo detecciones que pasaron filtros)
#       * report_inferencia.csv (por imagen)
#       * report_resumen.csv (agregado global)
#       * manifest_inferencia.json (parámetros usados)

import argparse, os, json, csv, time
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple

import yaml
from ultralytics import YOLO

# .env opcional
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key, str(default)).strip().lower()
    return v in ("1", "true", "t", "yes", "y")


def ensure_outdir(outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "imgs").mkdir(parents=True, exist_ok=True)


def build_per_class_thresholds(names: Dict[int, str], default_conf: float) -> Dict[str, float]:
    """Lee umbrales por clase desde .env según nombres de data.yaml."""
    d = {}
    for _, name in names.items():
        env_key = f"YOLO_CONF_{name}"
        try:
            d[name] = float(os.getenv(env_key, default_conf))
        except Exception:
            d[name] = default_conf
    return d


def valid_box(xyxy: List[float], img_hw: Tuple[int, int], min_area: float, max_area_frac: float, ar_min: float, ar_max: float) -> bool:
    H, W = img_hw
    x1, y1, x2, y2 = map(float, xyxy)
    w, h = max(0.0, x2 - x1), max(0.0, y2 - y1)
    area = w * h
    if area < min_area:
        return False
    if area > max_area_frac * (W * H):
        return False
    if w <= 0 or h <= 0:
        return False
    ar = h / max(w, 1e-6)
    return (ar_min <= ar <= ar_max)


def summarize_counts(counts_by_class: Counter) -> str:
    if not counts_by_class:
        return ""
    return "; ".join([f"{k}:{v}" for k, v in sorted(counts_by_class.items())])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Ruta a best.pt")
    ap.add_argument("--data", required=True, help="Ruta a data.yaml (usa nombres correctos)")
    ap.add_argument("--source", required=True, help="Imagen o carpeta de imágenes (jpg/png)")
    ap.add_argument("--outdir", default="./salidas_mejoradas", help="Carpeta de salida")
    ap.add_argument("--save_txt", action="store_true", help="Guardar etiquetas .txt de predicciones finales")
    args = ap.parse_args()

    model_path = Path(args.model)
    data_yaml = Path(args.data)
    source = Path(args.source)
    outdir = Path(args.outdir)

    ensure_outdir(outdir)

    # Cargar nombres de clases
    cfg = load_yaml(data_yaml)
    names_cfg = cfg.get("names", {})
    if isinstance(names_cfg, list):
        names = {i: str(n) for i, n in enumerate(names_cfg)}
    elif isinstance(names_cfg, dict):
        names = {}
        for k, v in names_cfg.items():
            try:
                ki = int(k)
            except Exception:
                ki = len(names)
            names[ki] = str(v)
    else:
        raise SystemExit("[X] 'names' no encontrado en data.yaml")

    # Parámetros de inferencia (con defaults)
    IMGSZ = int(os.getenv("YOLO_IMGSZ", 1024))
    IOU = float(os.getenv("YOLO_IOU", 0.55))
    CONF_DEFAULT = float(os.getenv("YOLO_CONF_DEFAULT", 0.25))
    TTA = get_env_bool("YOLO_AUGMENT", False)

    # Filtros geométricos
    MIN_AREA = float(os.getenv("MIN_AREA", 3000))
    MAX_AREA_FRAC = float(os.getenv("MAX_AREA_FRAC", 0.35))
    AR_MIN = float(os.getenv("AR_MIN", 0.50))
    AR_MAX = float(os.getenv("AR_MAX", 2.50))

    # Umbrales por clase
    per_class_conf = build_per_class_thresholds(names, CONF_DEFAULT)

    # Cargar modelo
    model = YOLO(str(model_path))

    # Listado de imágenes
    if source.is_file():
        img_paths = [source]
    else:
        img_paths = sorted([p for p in source.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    if not img_paths:
        raise SystemExit("[X] No se encontraron imágenes en --source")

    # Reportes
    report_csv = outdir / "report_inferencia.csv"
    resumen_csv = outdir / "report_resumen.csv"
    manifest_json = outdir / "manifest_inferencia.json"

    # Acumuladores globales
    global_raw = Counter()
    global_kept = Counter()
    disc_lowconf_total = 0
    disc_size_total = 0
    disc_aspect_total = 0

    with open(report_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "imagen", "H", "W",
            "raw_total", "kept_total",
            "raw_por_clase", "kept_por_clase",
            "desc_lowconf", "desc_size", "desc_aspect",
            "params_imgsz", "params_conf_default", "params_iou", "params_tta"
        ])

        for img_path in img_paths:
            # Inferencia base
            results = model.predict(
                source=str(img_path),
                imgsz=IMGSZ,
                conf=CONF_DEFAULT,
                iou=IOU,
                augment=TTA,
                agnostic_nms=False,   # NMS por clase
                save=True,            # guarda anotada "raw" en runs
                project=str(outdir / "runs"),
                name="raw",
                exist_ok=True
            )
            r = results[0]
            H, W = r.orig_shape

            # Conteo "raw"
            raw_counts = Counter()
            for i in range(len(r.boxes)):
                cls_id = int(r.boxes.cls[i].item())
                cls_name = names.get(cls_id, str(cls_id))
                raw_counts[cls_name] += 1
                global_raw[cls_name] += 1

            # Filtrado por clase + geometría
            kept_idx = []
            local_disc_lowconf = 0
            local_disc_size = 0
            local_disc_aspect = 0

            for i in range(len(r.boxes)):
                cls_id = int(r.boxes.cls[i].item())
                cls_name = names.get(cls_id, str(cls_id))
                conf = float(r.boxes.conf[i].item())
                thr = per_class_conf.get(cls_name, CONF_DEFAULT)

                if conf < thr:
                    local_disc_lowconf += 1
                    continue

                xyxy = r.boxes.xyxy[i].tolist()
                if not valid_box(xyxy, (H, W), MIN_AREA, MAX_AREA_FRAC, AR_MIN, AR_MAX):
                    # separar razones
                    x1, y1, x2, y2 = map(float, xyxy)
                    w_box, h_box = max(0.0, x2 - x1), max(0.0, y2 - y1)
                    area = w_box * h_box
                    if area < MIN_AREA or area > MAX_AREA_FRAC * (W * H):
                        local_disc_size += 1
                    else:
                        local_disc_aspect += 1
                    continue

                kept_idx.append(i)

            # === DIBUJO MANUAL SOLO DE LAS DETECCIONES ACEPTADAS (kept_idx) ===
            save_dir_final = outdir / "imgs"
            save_dir_final.mkdir(parents=True, exist_ok=True)
            img_bgr = r.orig_img.copy()

            try:
                import cv2

                for i in kept_idx:
                    x1, y1, x2, y2 = map(int, r.boxes.xyxy[i].tolist())
                    cls_id = int(r.boxes.cls[i].item())
                    conf   = float(r.boxes.conf[i].item())
                    cls_name = names.get(cls_id, str(cls_id))
                    label = f"{cls_name} {conf:.2f}"

                    cv2.rectangle(img_bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.rectangle(img_bgr, (x1, y1 - th - 6), (x1 + tw + 4, y1), (0, 255, 0), -1)
                    cv2.putText(img_bgr, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

                out_img_path = save_dir_final / (img_path.stem + "_final.jpg")
                cv2.imwrite(str(out_img_path), img_bgr)

            except Exception:
                from PIL import Image, ImageDraw, ImageFont
                img_rgb = img_bgr[:, :, ::-1]
                pil_im = Image.fromarray(img_rgb)
                draw = ImageDraw.Draw(pil_im)
                try:
                    font = ImageFont.load_default()
                except Exception:
                    font = None

                for i in kept_idx:
                    x1, y1, x2, y2 = map(int, r.boxes.xyxy[i].tolist())
                    cls_id = int(r.boxes.cls[i].item())
                    conf   = float(r.boxes.conf[i].item())
                    cls_name = names.get(cls_id, str(cls_id))
                    label = f"{cls_name} {conf:.2f}"

                    draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0), width=2)
                    tw = draw.textlength(label, font=font)
                    th = 12
                    draw.rectangle([x1, y1 - th - 4, x1 + int(tw) + 4, y1], fill=(0, 255, 0))
                    draw.text((x1 + 2, y1 - th - 2), label, fill=(0, 0, 0), font=font)

                out_img_path = save_dir_final / (img_path.stem + "_final.jpg")
                pil_im.save(str(out_img_path))
            # === FIN DIBUJO MANUAL ===

            # Guardar .txt finales (opcional)
            if args.save_txt and kept_idx:
                labels_dir = outdir / "labels"
                labels_dir.mkdir(parents=True, exist_ok=True)
                txt_path = labels_dir / (img_path.stem + ".txt")
                with open(txt_path, "w", encoding="utf-8") as tf:
                    for i in kept_idx:
                        cls_id = int(r.boxes.cls[i].item())
                        # Convertimos xyxy a xywh normalized
                        x1, y1, x2, y2 = map(float, r.boxes.xyxy[i].tolist())
                        cx = (x1 + x2) / 2.0 / W
                        cy = (y1 + y2) / 2.0 / H
                        bw = (x2 - x1) / W
                        bh = (y2 - y1) / H
                        tf.write(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")

            # Conteo kept
            kept_counts = Counter()
            for i in kept_idx:
                cls_id = int(r.boxes.cls[i].item())
                cls_name = names.get(cls_id, str(cls_id))
                kept_counts[cls_name] += 1
                global_kept[cls_name] += 1

            disc_lowconf_total += local_disc_lowconf
            disc_size_total += local_disc_size
            disc_aspect_total += local_disc_aspect

            # Fila por imagen
            w.writerow([
                str(img_path),
                H, W,
                sum(raw_counts.values()),
                sum(kept_counts.values()),
                summarize_counts(raw_counts),
                summarize_counts(kept_counts),
                local_disc_lowconf,
                local_disc_size,
                local_disc_aspect,
                IMGSZ, CONF_DEFAULT, IOU, TTA
            ])

    # Resumen global
    with open(resumen_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clase", "raw_total", "kept_total"])
        cls_all = sorted(set(global_raw.keys()) | set(global_kept.keys()))
        for c in cls_all:
            w.writerow([c, global_raw.get(c, 0), global_kept.get(c, 0)])
        w.writerow([])
        w.writerow(["descartes_lowconf_total", "descartes_size_total", "descartes_aspect_total"])
        w.writerow([disc_lowconf_total, disc_size_total, disc_aspect_total])

    # Manifest de parámetros
    manifest = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": str(model_path.resolve()),
        "data_yaml": str(data_yaml.resolve()),
        "params": {
            "IMGSZ": IMGSZ,
            "IOU": IOU,
            "CONF_DEFAULT": CONF_DEFAULT,
            "TTA": TTA,
            "MIN_AREA": MIN_AREA,
            "MAX_AREA_FRAC": MAX_AREA_FRAC,
            "AR_MIN": AR_MIN,
            "AR_MAX": AR_MAX
        },
        "per_class_conf": {k: float(v) for k, v in build_per_class_thresholds(names, CONF_DEFAULT).items()},
        "source": str(source.resolve()),
        "outputs": {
            "annotated_images_dir": str((outdir / "imgs").resolve()),
            "report_inferencia_csv": str((outdir / "report_inferencia.csv").resolve()),
            "report_resumen_csv": str((outdir / "report_resumen.csv").resolve())
        }
    }
    with open(manifest_json, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("\n[OK] Inferencia mejorada finalizada.")
    print(f"  - Imágenes anotadas: {manifest['outputs']['annotated_images_dir']}")
    print(f"  - Reporte por imagen: {manifest['outputs']['report_inferencia_csv']}")
    print(f"  - Resumen global:     {manifest['outputs']['report_resumen_csv']}")
    print(f"  - Manifiesto:         {str((outdir / 'manifest_inferencia.json').resolve())}")


if __name__ == "__main__":
    main()
