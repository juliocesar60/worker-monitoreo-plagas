# worker/api/main.py
import os
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import shutil
from pathlib import Path
import requests
from supabase import create_client  # pip install supabase
import importlib.util

ROOT = Path(__file__).parents[1]
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "best.pt"

# Config via env
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "models")  # nombre del bucket

app = FastAPI(title="Worker - FastAPI")

def ensure_model():
    """
    Si el modelo no existe localmente, intenta descargarlo desde Supabase.
    Requiere SUPABASE_URL y SUPABASE_KEY en variables de entorno.
    """
    MODEL_DIR.mkdir(exist_ok=True)
    if MODEL_PATH.exists():
        return True

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Modelo no encontrado y variables SUPABASE_URL/SUPABASE_KEY no configuradas.")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    bucket = supabase.storage.from_(SUPABASE_BUCKET)

    # Intentamos crear una URL firmada y descargar (algunas versiones devuelven distintas keys)
    signed = bucket.create_signed_url(str(MODEL_PATH.name), 3600)
    url = None
    # compatibilidad con distintas respuestas
    for k in ("signedURL", "signed_url", "signedUrl", "signedurl"):
        url = signed.get(k) if isinstance(signed, dict) else None
        if url:
            break
    if not url:
        # fallback: si create_signed_url devolvió la url en la forma {'signedURL':..., 'error': None}
        try:
            url = signed["signedURL"]
        except Exception:
            pass

    if not url:
        # última opción: intentar descargar directamente (si el archivo es público)
        try:
            data = bucket.download(str(MODEL_PATH.name))
            if data:
                with open(MODEL_PATH, "wb") as f:
                    f.write(data)
                return True
        except Exception:
            pass

    if not url:
        raise RuntimeError("No se pudo obtener URL firmada del modelo desde Supabase. Revisa permisos o la versión del cliente.")

    # descarga por HTTP
    r = requests.get(url, stream=True)
    if r.status_code != 200:
        raise RuntimeError(f"Error descargando modelo: {r.status_code}")

    with open(MODEL_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return True


def run_inference(image_path: Path):
    """
    Llamar a tu script de inferencia local (inferencia_mejorada.py).
    Ajusta el nombre de la función de inferencia si tu script tiene otra firma.
    """
    infer_script = ROOT / "inferencia_mejorada.py"
    if not infer_script.exists():
        raise FileNotFoundError("inferencia_mejorada.py no encontrado en el worker.")

    # Import dinámico del script (para evitar import si se ejecuta desde otro contexto)
    spec = importlib.util.spec_from_file_location("inferencia_mejorada", str(infer_script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Buscamos una función pública para inferir: infer o run_inference o main_infer
    for fn in ("infer", "run_inference", "main"):
        if hasattr(module, fn):
            func = getattr(module, fn)
            return func(str(image_path), model_path=str(MODEL_PATH))
    # si no existe, intentamos llamar al script como proceso (fallback)
    # raise error para que el dev sepa ajustarlo
    raise RuntimeError("No se encontró función de inferencia en inferencia_mejorada.py. Adapta la llamada.")


@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    try:
        ensure_model()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando modelo: {e}")

    tmp_dir = ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    img_path = tmp_dir / file.filename
    with open(img_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = run_inference(img_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en inferencia: {e}")

    return JSONResponse({"status": "ok", "result": result})
