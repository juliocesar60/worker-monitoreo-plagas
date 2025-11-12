# worker/test_supabase_conn.py
import os
from dotenv import load_dotenv, find_dotenv
from supabase_io import get_client, IMAGES_TABLE

load_dotenv(find_dotenv(), override=False)

print("🔍 TEST CONEXIÓN SUPABASE")
print("URL =", os.getenv("SUPABASE_URL"))
print("KEY =", "OK" if (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")) else "NO")

try:
    supa = get_client()
    res = supa.table(IMAGES_TABLE).select("id").limit(1).execute()
    print("✅ Conexión correcta, tabla:", IMAGES_TABLE)
    if res.data:
        print(f"Se encontraron {len(res.data)} registros (muestra): {res.data[0]}")
    else:
        print("Tabla vacía pero conexión OK.")
except Exception as e:
    print("❌ Error de conexión o credenciales inválidas:")
    print(e)
