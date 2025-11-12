FROM python:3.10-slim

WORKDIR /app

# instalar dependencias del sistema que ultralytics/torch puedan necesitar
RUN apt-get update && apt-get install -y build-essential libgl1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# crear carpeta models
RUN mkdir -p /app/models

EXPOSE 8001

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
