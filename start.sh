#!/usr/bin/env bash
# activar virtualenv si lo usas
# . .venv/bin/activate

# exporta variables (o usa .env)
# export SUPABASE_URL=...
# export SUPABASE_KEY=...
# export SUPABASE_BUCKET=models

uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
