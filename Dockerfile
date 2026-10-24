FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng fonts-hosny-amiri fontconfig \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV MDIA_HOST=0.0.0.0 MDIA_PORT=8000 MDIA_DATA_DIR=/data
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "mdia.server"]
