# worker/fix_paths.py
# -*- coding: utf-8 -*-

import os
import re
from typing import List, Optional

from dotenv import load_dotenv, find_dotenv
from supabase import create_client, Client

# ==========================================================
# CARGA VARIABLES .env
# ==========================================================
load_dotenv(find_dotenv(), override=False)

SUPABASE_URL = os.getenv("SUPABASE_URL") or ""
SERVICE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or ""
)
IMAGES_TABLE = os.getenv("IMAGES_TABLE", "images")
BUCKET_RAW = os.getenv("BUCKET_RAW", "raw")

# Flags de ejecución
APPLY = os.getenv("APPLY", "0") in ("1", "true", "TRUE")           # si 1, escribe cambios en BD
MOVE_TO_STANDARD = os.getenv("MOVE_TO_STANDARD", "0") in ("1","true","TRUE")  # si 1, mueve/copias archivos a img/<SECC>/...
LIMIT = int(os.getenv("LIMIT", "50"))
DEBUG = os.getenv("FIX_DEBUG", "0") in ("1", "true", "TRUE")

UUID_RE = re.compile(r"^[0-9a-fA-F-]{32,36}$")

# ==========================================================
# HELPERS
# ==========================================================
def client() -> Client:
    if not SUPABASE_URL or not SERVICE_KEY:
        raise RuntimeError("Faltan SUPABASE_URL o SERVICE_KEY en .env")
    return create_client(SUPABASE_URL, SERVICE_KEY)

def norm(p: str) -> str:
    return (p or "").replace("\\", "/").lstrip("/")

def looks_uuid(seg: str) -> bool:
    return bool(UUID_RE.match((seg or "").strip()))

def section_of_path(p: str) -> Optional[str]:
    p = norm(p)
    m = re.match(r"^img/([A-Ha-h])/", p)
    if m:
        return m.group(1).upper()
    m = re.match(r"^([A-Ha-h])/", p)
    if m:
        return m.group(1).upper()
    m = re.match(r"^[0-9a-fA-F-]{32,36}/([A-Ha-h])/", p)
    if m:
        return m.group(1).upper()
    return None

def filename_of_path(p: str) -> str:
    return norm(p).split("/")[-1]

def std_path(section: str, filename: str) -> str:
    return f"img/{section.upper()}/{filename}"

def raw_exists(c: Client, path: str) -> bool:
    """Verifica existencia listando el directorio padre y comparando el nombre."""
    path = norm(path)
    try:
        parent = "/".join(path.split("/")[:-1])
        name = path.split("/")[-1]
        items = c.storage.from_(BUCKET_RAW).list(parent or "")
        return any((it.get("name") == name) for it in (items or []))
    except Exception as e:
        if DEBUG:
            print(f"[raw_exists] {path=} err={e}")
        return False

def try_candidates(db_path: str) -> List[str]:
    """Genera candidatos típicos para localizar un archivo perdido en RAW."""
    p = norm(db_path)
    cands = set()

    def add(x: str):
        x = norm(x)
        if x:
            cands.add(x)

    # tal cual + con raw/ delante
    add(p); add(f"raw/{p}")

    # si empieza con raw/
    if p.startswith("raw/"):
        add(p[len("raw/"):])

    # raw/<uuid>/
    parts = p.split("/", 2)
    if len(parts) >= 3 and parts[0] == "raw" and looks_uuid(parts[1]):
        add(parts[2])

    # <uuid>/SECC/...
    parts = p.split("/", 1)
    if len(parts) == 2 and looks_uuid(parts[0]):
        add(parts[1]); add(f"raw/{parts[1]}")

    # SECC/archivo -> img/SECC/archivo
    m = re.match(r"^([A-Ha-h])/(.+)$", p)
    if m:
        sec, tail = m.group(1).upper(), m.group(2)
        add(f"img/{sec}/{tail}"); add(f"raw/img/{sec}/{tail}")

    # <uuid>/SECC/archivo -> img/SECC/archivo
    m2 = re.match(r"^([0-9a-fA-F-]{32,36})/([A-Ha-h])/(.+)$", p)
    if m2:
        sec, tail = m2.group(2).upper(), m2.group(3)
        add(f"img/{sec}/{tail}"); add(f"raw/img/{sec}/{tail}")

    # variantes en minúsculas
    for cand in list(cands):
        add(cand.lower())

    return list(cands)

# ==========================================================
# MAIN: ESCANEA FILAS PENDING Y CORRIGE
# ==========================================================
def scan_and_fix():
    c = client()

    # Traer pendientes (ajusta si quieres revisar todas)
    res = (
        c.table(IMAGES_TABLE)
        .select("id, storage_path, status")
        .eq("status", "pending")
        .limit(LIMIT)
        .execute()
    )
    rows = res.data or []
    print(f"[INFO] Revisando {len(rows)} filas pending (LIMIT={LIMIT}, APPLY={APPLY}, MOVE_TO_STANDARD={MOVE_TO_STANDARD})")

    for r in rows:
        img_id = r["id"]
        db_path = norm(r.get("storage_path") or "")
        sec = section_of_path(db_path) or "A"
        fname = filename_of_path(db_path)
        std = std_path(sec, fname)

        current_exists = raw_exists(c, db_path) or raw_exists(c, f"raw/{db_path}")
        if current_exists:
            print(f"[OK] {img_id} :: existe raw/{db_path}")
            continue

        print(f"[MISS] {img_id} :: NO existe raw/{db_path} — buscando alternativas...")
        found: Optional[str] = None
        for cand in try_candidates(db_path):
            if raw_exists(c, cand):
                found = cand
                break

        if not found:
            print(f"  -> No encontrado en alternativas. Sube el archivo a raw/{db_path}")
            continue

        print(f"  -> Encontrado en: {found}")

        # Decidir nueva ruta BD
        if MOVE_TO_STANDARD:
            # mover/copiAR al estándar img/SECC/ y borrar viejo
            new_path = std
            if found != new_path:
                try:
                    c.storage.from_(BUCKET_RAW).copy(found, new_path)
                    c.storage.from_(BUCKET_RAW).remove([found])
                    print(f"  -> Movido {found} -> {new_path}")
                except Exception as e:
                    print(f"  !! Error moviendo {found} -> {new_path}: {e}")
                    new_path = found  # fallback: mantenemos la ruta encontrada
        else:
            # sólo alinear BD con la ruta encontrada
            new_path = found

        if APPLY:
            c.table(IMAGES_TABLE).update({"storage_path": new_path}).eq("id", img_id).execute()
            print(f"  -> BD actualizada: storage_path='{new_path}'")
        else:
            print(f"  -> (DRY-RUN) se actualizaría BD a storage_path='{new_path}'")

# ==========================================================
if __name__ == "__main__":
    scan_and_fix()
