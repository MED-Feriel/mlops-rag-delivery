FROM python:3.11-slim
WORKDIR /app
COPY docker/etl/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY config/ ./config/
RUN useradd -m -u 1000 etluser && chown -R etluser /app
USER etluser
# run_etl.py orchestre extract → clean → build → embed → upsert.
# (extract.py est une lib async sans __main__, ne pas l'appeler directement.)
CMD ["python", "-m", "src.ingestion.run_etl"]
