FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng fonts-hosny-amiri fontconfig \
      libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir 'paddlepaddle==3.2.0' 'paddleocr>=3.2,<4'
COPY . .
# Public OCR weights are downloaded on first run; no invoice bytes are sent
# to a remote inference service. Audit must not convert estimates into approvals.
ENV MDIA_HOST=0.0.0.0 MDIA_PORT=8000 MDIA_DATA_DIR=/data \
    MDIA_OCR_ENGINE=paddle_arabic MDIA_EVIDENCE_RECONCILIATION=1 \
    MDIA_STRICT_INVOICE_REVIEW=1 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "mdia.server"]
