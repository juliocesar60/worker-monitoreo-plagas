# eval_yolo_txt.py
# Uso:
#   python eval_yolo_txt.py --gt "C:/.../Dataset_papa/labels/val" --imgs "C:/.../Dataset_papa/images/val" --pred ".\salidas_base\labels" --data ".\data.yaml"
#   python eval_yolo_txt.py --gt "C:/.../Dataset_papa/labels/val" --imgs "C:/.../Dataset_papa/images/val" --pred ".\salidas_mejoradas\labels" --data ".\data.yaml"

import argparse, os, glob
from pathlib import Path
from collections import defaultdict
import yaml
import math

try:
    from PIL import Image
except Exception:
    Image = None

def load_yaml(p):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def read_yolo_txt(p):
    # line: cls cx cy w h (norm)
    boxes = []
    if not Path(p).exists():
        return boxes
    for line in Path(p).read_text(encoding="utf-8").splitlines():
        s = line.strip().split()
        if len(s) >= 5:
            cls = int(float(s[0]))
            cx, cy, w, h = map(float, s[1:5])
            boxes.append((cls, cx, cy, w, h))
    return boxes

def to_xyxy_norm(cx, cy, w, h):
    x1 = cx - w/2
    y1 = cy - h/2
    x2 = cx + w/2
    y2 = cy + h/2
    return (x1, y1, x2, y2)

def iou_xyxy(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0.0, inter_x2 - inter_x1)
    ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union

def greedy_match(preds, gts, iou_thr=0.5):
    # preds, gts: listas de (xyxy_norm)
    matched_gt = set()
    tp = 0
    for p in preds:
        best_iou = 0.0
        best_j = -1
        for j, g in enumerate(gts):
            if j in matched_gt:
                continue
            i = iou_xyxy(p, g)
            if i > best_iou:
                best_iou = i
                best_j = j
        if best_iou >= iou_thr:
            tp += 1
            matched_gt.add(best_j)
    fp = max(0, len(preds) - tp)
    fn = max(0, len(gts) - tp)
    return tp, fp, fn

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True, help="carpeta de labels GT (YOLO .txt)")
    ap.add_argument("--imgs", required=True, help="carpeta de imagenes (para emparejar extensiones)")
    ap.add_argument("--pred", required=True, help="carpeta de predicciones .txt")
    ap.add_argument("--data", required=True, help="data.yaml para nombres")
    ap.add_argument("--iou", type=float, default=0.5)
    args = ap.parse_args()

    names_cfg = load_yaml(args.data).get("names", {})
    if isinstance(names_cfg, list):
        id2name = {i: str(n) for i, n in enumerate(names_cfg)}
    else:
        id2name = {int(k): str(v) for k, v in names_cfg.items()}

    # indexar imagenes por stem -> extension
    img_index = {}
    for ext in ("*.jpg","*.jpeg","*.png"):
        for p in Path(args.imgs).rglob(ext):
            img_index[Path(p).stem] = str(p)

    # por clase: TP/FP/FN
    metrics = defaultdict(lambda: {"TP":0,"FP":0,"FN":0})

    gt_files = sorted(Path(args.gt).rglob("*.txt"))
    for gt in gt_files:
        stem = gt.stem
        pred = Path(args.pred) / f"{stem}.txt"
        gts = read_yolo_txt(gt)
        prs = read_yolo_txt(pred)

        # separar por clase
        cls_set = set([c for c, *_ in gts] + [c for c, *_ in prs])
        for c in cls_set:
            gtc = [to_xyxy_norm(*coords[1:]) for coords in gts if coords[0]==c]
            prc = [to_xyxy_norm(*coords[1:]) for coords in prs if coords[0]==c]
            tp, fp, fn = greedy_match(prc, gtc, iou_thr=args.iou)
            metrics[c]["TP"] += tp
            metrics[c]["FP"] += fp
            metrics[c]["FN"] += fn

    # imprimir
    print("CLASE, TP, FP, FN, Precision, Recall, F1")
    macro_p = []
    macro_r = []
    macro_f1 = []
    for cid in sorted(metrics.keys()):
        m = metrics[cid]
        P = m["TP"] / (m["TP"] + m["FP"]) if (m["TP"] + m["FP"]) > 0 else 0.0
        R = m["TP"] / (m["TP"] + m["FN"]) if (m["TP"] + m["FN"]) > 0 else 0.0
        F1 = 2*P*R/(P+R) if (P+R) > 0 else 0.0
        macro_p.append(P); macro_r.append(R); macro_f1.append(F1)
        print(f"{id2name.get(cid,str(cid))}, {m['TP']}, {m['FP']}, {m['FN']}, {P:.3f}, {R:.3f}, {F1:.3f}")

    if macro_p:
        print("\nMACRO-AVG, , , , {:.3f}, {:.3f}, {:.3f}".format(
            sum(macro_p)/len(macro_p), sum(macro_r)/len(macro_r), sum(macro_f1)/len(macro_f1)
        ))

if __name__ == "__main__":
    main()
