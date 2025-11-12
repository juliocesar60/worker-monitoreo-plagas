# test_enqueue.py - sube una imagen a 'raw' e inserta fila 'pending' en 'images'
import os, uuid
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BUCKET_RAW = os.getenv("BUCKET_RAW", "raw")
IMAGES_TABLE = os.getenv("IMAGES_TABLE", "images")

assert url and key, "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env"

supa = create_client(url, key)

USER_ID = str(uuid.uuid4())   # usa tu UID real si quieres
SECTION = "CAM"

# usa una imagen real que tengas a mano:
LOCAL_IMG = r"..\runs\detect\train\images\train_batch0.jpg"  # cámbiala si no existe
DST = f"{USER_ID}/demo.jpg"   # ruta dentro del bucket 'raw'

# subir imagen
with open(LOCAL_IMG, "rb") as f:
    supa.storage.from_(BUCKET_RAW).upload(DST, f, file_options={"content-type":"image/jpeg","upsert":True})

# insertar fila en images
row = {
    "user_id": USER_ID,
    "section": SECTION,
    "storage_path": f"raw/{DST}",
    "status": "pending"
}
res = supa.table(IMAGES_TABLE).insert(row).execute()
print("Insert:", res.data)
print("Listo. Deja corriendo detect_supabase.py; debería procesar esta imagen.")
