# test_yolo_metrics.py
import os
from pathlib import Path
import numpy as np
import cv2
from ultralytics import YOLO

# ---------- Diagnóstico de rutas ----------
BASE = Path(__file__).parent.resolve()
CWD  = Path.cwd().resolve()
print("BASE (carpeta del script):", BASE)
print("CWD  (carpeta de ejecución):", CWD)

# Nombre base del archivo (sin importar extensión o mayúsculas)
STEM = "test_hongo"  # si tu archivo se llama distinto, cambia este stem

# Busca el archivo en la misma carpeta del script con varias extensiones
CAND_EXT = [".jpg",".jpeg",".png",".JPG",".JPEG",".PNG"]
img_path = None
for ext in CAND_EXT:
    p = BASE / f"{STEM}{ext}"
    if p.exists():
        img_path = p
        break

if not img_path:
    print("\n[ERROR] No encontré la imagen. Revisa lo siguiente:")
    print(f"- Debe estar en: {BASE}")
    print(f"- Debe llamarse: {STEM} + una de estas extensiones: {CAND_EXT}")
    print("\n[Lista de archivos en la carpeta]:")
    for f in sorted(BASE.iterdir()):
        print("  -", f.name)
    raise SystemExit(1)

print("Usando imagen:", img_path)

# ---------- Carga robusta de imagen (soporta rutas con espacios/acentos) ----------
try:
    data = np.fromfile(str(img_path), np.uint8)
    img  = cv2.imdecode(data, cv2.IMREAD_COLOR)
except Exception as e:
    print("[ERROR] Falló imdecode:", e)
    raise SystemExit(1)

if img is None:
    print("[ERROR] OpenCV no pudo decodificar la imagen (archivo corrupto?).")
    raise SystemExit(1)

# ---------- Modelo ----------
weights_path = BASE / "best.pt"
assert weights_path.exists(), f"No encontré pesos en {weights_path}"
print("Cargando modelo:", weights_path)
model = YOLO(str(weights_path))

# ---------- Inferencia ----------
res = model.predict(source=img, imgsz=640, conf=0.25, iou=0.6, device="CPU", verbose=False)[0]

names = res.names
counts = {}
probs  = {}      # probabilidad máxima por clase
sum_conf = 0.0
n = 0

if res.boxes is not None:
    for b in res.boxes:
        cls_id = int(b.cls[0]); conf = float(b.conf[0])
        label = names.get(cls_id, str(cls_id))
        counts[label] = counts.get(label, 0) + 1
        probs[label]  = max(probs.get(label, 0.0), conf)
        sum_conf += conf
        n += 1

avg_conf = (sum_conf / n) if n > 0 else 0.0
max_conf = max(probs.values()) if probs else 0.0

print("\n=== MÉTRICAS POR IMAGEN ===")
print("Detecciones totales:", n)
print("Confianza prom.:     ", f"{avg_conf:.3f}")
print("Confianza máx.:      ", f"{max_conf:.3f}")
print("Conteo por clase:    ", counts)

print("\n=== Probabilidades máx. por clase ===")
if probs:
    for k, v in sorted(probs.items(), key=lambda kv: -kv[1]):
        print(f" - {k:<15} {v:>6.3f}")
else:
    print(" (sin detecciones)")
