# peek_images.py
from supabase_io import get_client
c = get_client()

IMAGES_TABLE = "images"  # cambia si tu tabla se llama distinto

res = c.table(IMAGES_TABLE).select("id, storage_path, status, user_id").limit(20).execute()
print("== IMAGES (id | status | storage_path) ==")
for r in (res.data or []):
    print(r["id"], "|", r.get("status"), "|", r.get("storage_path"))
