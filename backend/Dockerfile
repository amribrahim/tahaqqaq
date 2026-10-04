FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Tesseract with Arabic + English language packs for OCR; Chromium prints the result page as the review PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng libpq5 curl libglib2.0-0 \
      chromium fonts-hosny-amiri fonts-dejavu-core \
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

# Self-hosted voice for the assistant (Piper, MIT; voices from rhasspy/piper-voices): no quota, no key
ENV TTS_PIPER_DIR=/opt/piper
RUN mkdir -p /opt/piper && cd /opt/piper \
    && for v in ar/ar_JO/kareem/medium/ar_JO-kareem-medium en/en_US/ryan/medium/en_US-ryan-medium; do \
         f=$(basename $v); \
         curl -fsSL -o $f.onnx "https://huggingface.co/rhasspy/piper-voices/resolve/main/$v.onnx"; \
         curl -fsSL -o $f.onnx.json "https://huggingface.co/rhasspy/piper-voices/resolve/main/$v.onnx.json"; \
       done
COPY app ./app
COPY ingest ./ingest
COPY tests ./tests

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
