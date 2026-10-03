FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Tesseract with Arabic + English language packs for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng libpq5 curl libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# Higher-accuracy LSTM models (tessdata_best) replace the fast ones shipped by Debian
RUN d=$(dirname "$(find / -name ara.traineddata 2>/dev/null | head -1)") \
    && curl -fsSL -o "$d/ara.traineddata" https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata \
    && curl -fsSL -o "$d/eng.traineddata" https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Bake the local embedding model into the image so the API serves immediately after start
# (no download at boot). The same path is also a named volume in docker-compose.
ENV FASTEMBED_CACHE_PATH=/root/.cache/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/root/.cache/fastembed')"

COPY app ./app
COPY ingest ./ingest
COPY tests ./tests

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
