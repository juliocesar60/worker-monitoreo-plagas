# show_training_info.py
# Uso:
#   python show_training_info.py --run "ruta/a/tu_run" --data "data.yaml"
#
# Imprime:
#   - Clases (names) desde data.yaml (soporta lista o dict)
#   - Hiperparámetros desde args.yaml / hyp.yaml si existen en el run
#   - Métricas finales desde results.csv

import argparse
import csv
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

def print_names(names):
    print("== CLASES (data.yaml) ==")
    if isinstance(names, dict):
        # Ordena por clave numérica si es posible (0,1,2,...)
        try:
            for k in sorted(names.keys(), key=lambda x: int(x)):
                print(f"{k}: {names[k]}")
        except Exception:
            for k in sorted(names.keys()):
                print(f"{k}: {names[k]}")
    elif isinstance(names, list):
        for i, n in enumerate(names):
            print(f"{i}: {n}")
    else:
        print("[!] No se encontró 'names' en data.yaml o formato no soportado")
    print()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Carpeta del entrenamiento (debe contener results.csv)")
    ap.add_argument("--data", required=True, help="Ruta a data.yaml (para listar clases)")
    args = ap.parse_args()

    run = Path(args.run)
    data_yaml = Path(args.data)

    results_csv = run / "results.csv"
    if not results_csv.exists():
        print(f"[X] No existe {results_csv}")
        return

    # --- Clases (data.yaml)
    try:
        data_cfg = read_yaml(data_yaml)
        names = data_cfg.get("names", [])
    except Exception as e:
        print(f"[!] Error leyendo data.yaml: {e}")
        names = []
    print_names(names)

    # --- Hiperparámetros (args.yaml / hyp.yaml si existen)
    args_yaml = run / "args.yaml"
    hyp_yaml  = run / "hyp.yaml"

    if args_yaml.exists():
        print("== HIPERPARÁMETROS (args.yaml) ==")
        try:
            ay = read_yaml(args_yaml)
            for k in [
                "model","epochs","batch","imgsz","lr0","optimizer","weight_decay",
                "warmup_epochs","patience","freeze","cos_lr","close_mosaic",
                "mosaic","mixup","copy_paste","hsv_h","hsv_s","hsv_v",
                "degrees","translate","scale","shear"
            ]:
                if k in ay:
                    print(f"{k}: {ay[k]}")
        except Exception as e:
            print(f"[!] Error leyendo args.yaml: {e}")
        print()
    else:
        print("[!] No se encontró args.yaml")

    if hyp_yaml.exists():
        print("== HIPERPARÁMETROS (hyp.yaml) ==")
        try:
            hy = read_yaml(hyp_yaml)
            for k, v in hy.items():
                print(f"{k}: {v}")
        except Exception as e:
            print(f"[!] Error leyendo hyp.yaml: {e}")
        print()
    else:
        print("[!] No se encontró hyp.yaml")

    # --- Métricas finales (última fila de results.csv)
    r = last_row_csv(results_csv)
    if r:
        print("== MÉTRICAS FINALES (results.csv) ==")
        keys = [
            "metrics/precision(B)", "metrics/recall(B)",
            "metrics/mAP50(B)", "metrics/mAP50-95(B)",
            "train/box_loss", "train/cls_loss", "train/dfl_loss",
            "val/box_loss", "val/cls_loss", "val/dfl_loss"
        ]
        for k in keys:
            if k in r:
                print(f"{k}: {r[k]}")
    else:
        print("[!] results.csv vacío")

if __name__ == "__main__":
    main()
