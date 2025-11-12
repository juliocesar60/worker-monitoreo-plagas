# find_in_storage.py
from supabase_io import get_client, BUCKET_RAW

c = get_client()

def walk(prefix="", depth=0, max_depth=4):
    if depth > max_depth:
        return []
    items = c.storage.from_(BUCKET_RAW).list(prefix, {"limit": 200, "offset": 0})
    out = []
    for it in items:
        name = it.get("name")
        if not name:
            continue
        full = f"{prefix}/{name}" if prefix else name
        out.append(full)
        # si parece carpeta, descender
        if "." not in name or name.endswith("/"):
            out.extend(walk(full, depth + 1, max_depth))
    return out

if __name__ == "__main__":
    target = "6651df69-e3d0-4df8-abb9-5bfb94b89fa7_20230712_114335-640x640.jpg".lower()  # cambia al nombre real que te sale en error
    print(f"Buscando en bucket '{BUCKET_RAW}' el archivo: {target}")
    paths = walk("")
    hits = [p for p in paths if p.lower().endswith(target)]
    if not hits:
        print("No encontrado. Revisa que esté en este bucket o cambia BUCKET_RAW en .env.")
    else:
        print("Coincidencias:")
        for h in hits:
            print(" -", h)
