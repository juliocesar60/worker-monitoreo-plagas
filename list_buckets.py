# list_buckets.py
from supabase_io import get_client
c = get_client()

buckets = c.storage.list_buckets()
print("== BUCKETS ==")
for b in buckets:
    print("-", b.get("name"))
