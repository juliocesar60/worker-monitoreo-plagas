# supabase_io.py
# -*- coding: utf-8 -*-

import os
from typing import Optional
from supabase import create_client, Client
from storage3.utils import StorageException
from dotenv import load_dotenv

# Carga variables del entorno (.env)
load_dotenv()

# ==========================================================
# CREDENCIALES
# ==========================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")

# Acepta ambos nombres por compatibilidad
SUPABASE_SERVICE_ROLE = (
    os.getenv("SUPABASE_SERVICE_ROLE") or
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE:
    raise RuntimeError("❌ Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE en el archivo .env")

# ==========================================================
# CONFIGURACIÓN DE BUCKETS
# ==========================================================
BUCKET_RAW = os.getenv("BUCKET_RAW", "raw")
BUCKET_REP = os.getenv("BUCKET_REP", "reports")

# ==========================================================
# CLIENTE
# ==========================================================
def get_client() -> Client:
    """Devuelve el cliente autenticado de Supabase."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

# ==========================================================
# HELPERS DE STORAGE
# ==========================================================
def _normalize_rel(path_rel: str) -> str:
    """Asegura que el path sea relativo dentro del bucket (sin 'raw/' inicial, sin '/')."""
    p = (path_rel or "").strip().lstrip("/")
    if p.lower().startswith("raw/"):
        p = p[4:]
    return p


def download_from_raw(path_rel: str) -> bytes:
    """Descarga bytes desde el bucket 'raw'. Lanza excepción si no existe."""
    supa = get_client()
    rel = _normalize_rel(path_rel)
    try:
        return supa.storage.from_(BUCKET_RAW).download(rel)
    except Exception as e:
        raise FileNotFoundError(f"raw://{rel} -> {e}")


def upload_to_reports(path_rel: str, data: bytes, mime_type: str = "application/octet-stream"):
    """
    Sube un archivo al bucket 'reports'. Si ya existe, lo reemplaza (update).
    Retorna el path relativo dentro del bucket.
    """
    supa = get_client()
    rel = (path_rel or "").strip().lstrip("/")

    # Opciones de cabecera válidas
    opts = {"content-type": mime_type}

    try:
        # Intentar subir normalmente
        supa.storage.from_(BUCKET_REP).upload(rel, data, opts)
        return rel
    except Exception as e:
        # Si existe conflicto, reemplazar (update)
        msg = str(e).lower()
        if any(k in msg for k in ["exist", "dup", "conflict", "409"]):
            supa.storage.from_(BUCKET_REP).update(rel, data, opts)
            return rel
        raise




def signed_url(bucket: str, path_rel: str, expires_in: int = 3600) -> str:
    """Crea una URL firmada temporal para mostrar o descargar archivos."""
    supa = get_client()
    rel = (path_rel or "").strip().lstrip("/")
    try:
        res = supa.storage.from_(bucket).create_signed_url(rel, expires_in=expires_in)
        # Compatibilidad con diferentes SDKs
        if isinstance(res, dict):
            return res.get("signedURL") or res.get("signed_url") or ""
        if hasattr(res, "get"):
            return res.get("signedURL") or res.get("signed_url") or ""
        if isinstance(res, str):
            return res
        return ""
    except Exception as e:
        print(f"[WARN] signed_url error: {e}")
        return ""
