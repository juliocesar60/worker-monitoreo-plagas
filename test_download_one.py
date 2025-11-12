from supabase_io import download_from_raw
# Pega aquí un storage_path EXACTO que veas en la columna images.storage_path
PATH = "12af3da2-1423-48ab-bd8f-d07963755d13/C/90a007c1-72e5-446b-9dfd-89c28914dc8d_20230712_114335-640x640.jpg"
b = download_from_raw(PATH)
print("OK bytes:", len(b))
