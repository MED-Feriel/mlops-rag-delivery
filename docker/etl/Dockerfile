FROM python:3.11-slim
WORKDIR /app
COPY docker/etl/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
RUN useradd -m -u 1000 etluser && chown -R etluser /app
USER etluser
CMD ["python", "-m", "src.ingestion.extract"]
