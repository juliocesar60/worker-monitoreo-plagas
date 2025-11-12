from supabase_io import upload_bytes, BUCKET_REP
path = upload_bytes(BUCKET_REP, "debug/test.txt", b"hello", "text/plain")
print("OK subido a:", path)
