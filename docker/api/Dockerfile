# ── Étape build : installe les dépendances dans un préfixe isolé (MLOPS-119) ──
FROM python:3.11-slim AS builder
WORKDIR /app
COPY docker/api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Étape runtime : image minimale, sans cache pip ni outils de build ─────────
FROM python:3.11-slim
WORKDIR /app
# Copie uniquement les paquets installés (pas le cache, pas de compilateurs).
COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY config/ ./config/
# Utilisateur non-root dédié.
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --uid 1000 apiuser \
    && chown -R apiuser:appgroup /app
USER apiuser
EXPOSE 8080
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
