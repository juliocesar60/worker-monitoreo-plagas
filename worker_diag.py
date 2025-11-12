# worker/worker_diag.py
import sys, os, traceback
from supabase_io import (
    get_client, download_from_raw, lock_pending, mark_error, IMAGES_TABLE,
    BUCKET_RAW
)

def main():
    print("== DIAG ==")
    print("CWD:", os.getcwd())
    print("SUPABASE_URL set:", bool(os.getenv("SUPABASE_URL")))
    print("SERVICE_ROLE set:", bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")))
    print("BUCKET_RAW:", BUCKET_RAW)
    supa = get_client()

    # 1) listar pending
    res = supa.table(IMAGES_TABLE)\
        .select("id, storage_path, status")\
        .eq("status","pending")\
        .order("created_at")\
        .limit(1).execute()
    rows = res.data or []
    if not rows:
        print("No hay filas pending.")
        return 0

    row = rows[0]
    iid = row["id"]
    spath = row.get("storage_path") or ""
    print(f"Fila pending: id={iid} storage_path='{spath}'")

    # 2) lock
    print("Bloqueando -> processing...")
    supa.table(IMAGES_TABLE).update({"status":"processing"})\
        .eq("id", iid).eq("status","pending").execute()

    # Verificar que cambió
    st = supa.table(IMAGES_TABLE).select("status").eq("id", iid).single().execute().data["status"]
    print("Status tras lock:", st)

    # 3) descarga del raw
    try:
        print("Descargando desde bucket 'raw' ...")
        b = download_from_raw(spath)
        print("Bytes descargados:", len(b))
        print("OK: descarga y lock funcionan. El problema NO es Storage/DB.")
        return 0
    except Exception as e:
        msg = f"DownloadError: {e}\n{traceback.format_exc(limit=2)}"
        print(msg)
        mark_error(iid, msg)
        return 1

if __name__ == "__main__":
    sys.exit(main())
