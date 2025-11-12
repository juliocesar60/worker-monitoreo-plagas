# list_storage.py
from supabase_io import get_client, BUCKET_RAW

c = get_client()

def ls(prefix=""):
    try:
        items = c.storage.from_(BUCKET_RAW).list(
            prefix,
            {"limit": 200, "offset": 0, "sortBy": {"column": "name", "order": "asc"}},
        )
        print(f"\n== LIST '{prefix or '/'}' ({BUCKET_RAW}) ==")
        if not items:
            print("(vacío)")
        for it in items:
            name = it.get("name")
            print("-", name)
    except Exception as e:
        print("List error:", e)

if __name__ == "__main__":
    # raíz y candidatos típicos
    ls("")  # raíz del bucket
    ls("public")
    ls("images")
    ls("raw")
    # 👉 añade aquí prefijos que te interesen ver:
    ls("12af3da2-1423-48ab-bd8f-d07963755d13")
    ls("12af3da2-1423-48ab-bd8f-d07963755d13/C")
