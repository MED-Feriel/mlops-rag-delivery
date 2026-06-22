# ── Étape build : dépendances légères du simulateur (MLOPS-119) ──────────────
FROM python:3.11-slim AS builder
WORKDIR /app
COPY docker/simulator/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Étape runtime : image minimale ───────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
# UNIQUEMENT le code simulateur — pas langchain, pas ragas.
COPY src/simulator/ ./simulator/
COPY simulation_config.yaml .
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --uid 1000 simulator \
    && chown -R simulator:appgroup /app
USER simulator
EXPOSE 8090
CMD ["uvicorn", "simulator.main:app", "--host", "0.0.0.0", "--port", "8090"]
