# explica_entrenamiento_inferencia.py  (ASCII-safe)
# Uso:
#   python explica_entrenamiento_inferencia.py --run "yolov8m_gorgojo_minador" --data "data.yaml" --env ".env"

import argparse, os, csv, textwrap, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("Falta PyYAML. Instala con: pip install pyyaml")

def read_yaml(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def last_row_csv(p: Path):
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None

def print_section(title):
    line = "=" * len(title)
    print("\n" + line)
    print(title)
    print(line)

def print_names(names):
    print_section("1) CLASES (data.yaml)")
    if isinstance(names, dict):
        # ordenar por clave numerica si es posible
        try:
            keys = sorted(names.keys(), key=lambda x: int(x))
        except Exception:
            keys = sorted(names.keys())
        for k in keys:
            print(f"{k}: {names[k]}")
    elif isinstance(names, list):
        for i, n in enumerate(names):
            print(f"{i}: {n}")
    else:
        print("[!] No se encontro 'names' en data.yaml")

def explain_train_hparams(ay: dict):
    print_section("2) HIPERPARAMETROS DE ENTRENAMIENTO (args.yaml) + EFECTO")
    def g(k, default=None):
        return ay.get(k, default)

    items = [
        ("model", "Checkpoint base preentrenado; define arquitectura y pesos iniciales (transfer learning)."),
        ("epochs", "Epocas totales; mas epocas permiten aprender mas, pero si no mejora puede sobreajustar."),
        ("batch", "Tamano de lote; lotes grandes estabilizan el gradiente pero consumen mas VRAM."),
        ("imgsz", "Resolucion de entrada en entrenamiento; mayor imgsz ayuda a objetos pequenos, mas costo."),
        ("lr0", "Learning rate inicial; controla la velocidad de aprendizaje. Alto=rapido pero inestable; bajo=estable pero lento."),
        ("optimizer", "Algoritmo de optimizacion (p.ej. AdamW/SGD); afecta convergencia y estabilidad."),
        ("weight_decay", "Regularizacion L2; reduce sobreajuste penalizando pesos grandes."),
        ("warmup_epochs", "Calentamiento; arranque suave del LR para evitar saltos bruscos."),
        ("patience", "Early stopping; si no mejora, detiene para evitar sobreentrenar y ahorrar tiempo."),
        ("freeze", "Capas congeladas; si >0 usa las capas del backbone fijas (transfer learning estable)."),
        ("cos_lr", "Scheduler coseno; decrece LR suavemente para afinar al final."),
        ("mosaic", "Aumento que mezcla 4 imagenes; aumenta diversidad de escenas/escala."),
        ("mixup", "Aumento que mezcla pixeles/labels de 2 imagenes; regulariza y ayuda con clases desbalanceadas."),
        ("copy_paste", "Aumento de objetos pegados; util para aumentar instancias raras (si hay recortes reales)."),
        ("hsv_h/s/v", "Jitter de color en tono/saturacion/valor; robustez a iluminacion/camara."),
        ("degrees/translate/scale/shear", "Geometrias; mejoran invariancia a rotacion, traslacion y escala."),
        ("close_mosaic", "Desactiva mosaic al final; deja que el modelo vea imagenes reales antes de cerrar.")
    ]
    for key, why in items:
        if "/" in key and key in ("hsv_h/s/v","degrees/translate/scale/shear"):
            if key == "hsv_h/s/v":
                vals = [str(ay.get("hsv_h","N/A")), str(ay.get("hsv_s","N/A")), str(ay.get("hsv_v","N/A"))]
            else:
                vals = [str(ay.get("degrees","N/A")), str(ay.get("translate","N/A")), str(ay.get("scale","N/A")), str(ay.get("shear","N/A"))]
            print(f"{key}: {', '.join(vals)}")
            print("   -", why)
        else:
            print(f"{key}: {g(key, 'N/A')}")
            print("   -", why)

def print_metrics(last: dict):
    print_section("3) METRICAS FINALES (results.csv)")
    keys = [
        ("metrics/precision(B)", "Precision (detecciones correctas / detecciones totales)"),
        ("metrics/recall(B)",    "Recall (objetos detectados / objetos presentes)"),
        ("metrics/mAP50(B)",     "mAP@0.5 (area bajo curva PR con IoU=0.5)"),
        ("metrics/mAP50-95(B)",  "mAP@0.5:0.95 (promedio en IoU 0.5..0.95)"),
        ("train/box_loss",       "Perdida de cajas en entrenamiento"),
        ("train/cls_loss",       "Perdida de clasificacion en entrenamiento"),
        ("train/dfl_loss",       "Perdida DFL (bordes) en entrenamiento"),
        ("val/box_loss",         "Perdida de cajas en validacion"),
        ("val/cls_loss",         "Perdida de clasificacion en validacion"),
        ("val/dfl_loss",         "Perdida DFL en validacion"),
    ]
    for k, desc in keys:
        if k in last:
            print(f"{k}: {last[k]}  - {desc}")

def load_env(env_path: Path):
    env = {}
    if env_path and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, val = s.split("=", 1)
            env[key.strip()] = val.strip()
    else:
        for k in ["YOLO_IMGSZ","YOLO_CONF","YOLO_IOU","YOLO_AUGMENT","YOLO_TILING"]:
            if k in os.environ:
                env[k] = os.environ[k]
    return env

def explain_inference(env):
    print_section("4) PARAMETROS DE INFERENCIA (.env) + EFECTO EN PRODUCCION")
    imgsz   = env.get("YOLO_IMGSZ", "N/A")
    conf    = env.get("YOLO_CONF", "N/A")
    iou     = env.get("YOLO_IOU", "N/A")
    augment = env.get("YOLO_AUGMENT", "N/A")
    tiling  = env.get("YOLO_TILING", "N/A")

    print(f"YOLO_IMGSZ:  {imgsz}")
    print("   - Mayor resolucion en inferencia capta objetos pequenos (minadores/manchas) a costo de tiempo/VRAM.")
    print(f"YOLO_CONF:   {conf}")
    print("   - Umbral de confianza: subirlo aumenta Precision (menos falsos positivos) pero baja Recall.")
    print(f"YOLO_IOU:    {iou}")
    print("   - Umbral de IoU para NMS: mas alto fusiona menos (posibles duplicados); mas bajo fusiona mas.")
    print(f"YOLO_AUGMENT:{augment}")
    print("   - TTA (flip/escala en inferencia): suele subir Recall (detecta mas) a costa de tiempo.")
    print(f"YOLO_TILING: {tiling}")
    print("   - Con tiles (parches) mejora objetos diminutos en fotos de planta completa.")

def print_defense_cheatsheet():
    print_section("5) RESUMEN PARA DEFENSA (GUION BREVE)")
    txt = """
    Flujo de datos:
      - Entrada: imagenes RGB se normalizan y reescalan a imgsz; el backbone extrae caracteristicas (bordes, texturas).
      - Salida: la cabeza de YOLO predice cajas, clases y confianzas; NMS (IoU) filtra solapamientos.

    Por que congelar/descongelar:
      - Etapa 1 (freeze>0): uso el conocimiento general del backbone (transfer learning) y adapto la cabeza a mis clases.
      - Etapa 2 (freeze=0): afino todo el modelo con LR menor para adaptar texturas y colores del cultivo.

    Hiperparametros clave e impacto:
      - lr0 / optimizer / weight_decay / epochs / batch / imgsz / augment (mosaic, mixup).
      - A mayor imgsz: mejor para minadores/manchas pequenas.
      - Aumentos mejoran generalizacion y evitan sobreajuste.

    En produccion (app):
      - Ajusto YOLO_IMGSZ, YOLO_CONF, YOLO_IOU y TTA sin reentrenar para calibrar Precision vs Recall segun necesidad.
      - Si una clase falla (p.ej., Gorgojo), subo imgsz y/o bajo conf, y puedo usar tiles para recuperar casos sutiles.
    """
    print(textwrap.dedent(txt).strip())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Carpeta del entrenamiento (contiene results.csv/args.yaml)")
    ap.add_argument("--data", required=True, help="Ruta al data.yaml (para listar clases)")
    ap.add_argument("--env", default=".env", help="Ruta a archivo .env con parametros de inferencia")
    args = ap.parse_args()

    run_dir = Path(args.run)
    data_yaml = Path(args.data)
    env_path = Path(args.env)

    # 1) Clases
    try:
        data_cfg = read_yaml(data_yaml)
        names = data_cfg.get("names", [])
    except Exception as e:
        names = []
        print(f"[!] Error leyendo data.yaml: {e}")
    print_names(names)

    # 2) Hparams de entrenamiento
    args_yaml = run_dir / "args.yaml"
    if args_yaml.exists():
        try:
            ay = read_yaml(args_yaml)
            explain_train_hparams(ay)
        except Exception as e:
            print(f"[!] Error leyendo args.yaml: {e}")
    else:
        print("[!] No se encontro args.yaml en el run")

    # 3) Metricas
    results_csv = run_dir / "results.csv"
    if results_csv.exists():
        last = last_row_csv(results_csv)
        if last:
            print_metrics(last)
        else:
            print("[!] results.csv vacio")
    else:
        print(f"[!] No existe {results_csv}")

    # 4) Inference params (.env)
    env = load_env(env_path)
    explain_inference(env)

    # 5) Guion de defensa
    print_defense_cheatsheet()

if __name__ == "__main__":
    # Forzar stdout a no cortar por encoding en algunas consolas (mejor usar ASCII)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
