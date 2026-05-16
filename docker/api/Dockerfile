FROM python:3.11-slim
WORKDIR /app
COPY docker/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY config/ ./config/
RUN useradd -m -u 1000 apiuser && chown -R apiuser /app
USER apiuser
EXPOSE 8080
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
