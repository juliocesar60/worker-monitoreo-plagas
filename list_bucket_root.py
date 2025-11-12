# list_bucket_root.py
from supabase_io import get_client

c = get_client()
buckets = [b.get("name") for b in c.storage.list_buckets()]

def ls(bucket: str, prefix: str = ""):
    try:
        items = c.storage.from_(bucket).list(prefix, {"limit": 200, "offset": 0})
        print(f"\n== {bucket} / {prefix or '(root)'} ==")
        if not items:
            print("(vacío)")
        for it in items:
            print("-", it.get("name"))
    except Exception as e:
        print(f"[{bucket}] List error:", e)

if __name__ == "__main__":
    for b in buckets:
        ls(b, "")
    