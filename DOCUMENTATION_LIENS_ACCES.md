# 📋 Documentation — Liens d'accès au système RAG MLops

**Date** : 2026-06-06  
**Projet** : mlops-rag-delivery (PFE)  
**Utilisateur** : merrad feriel (merradferiel8@gmail.com)

---

## 🔗 Tous les liens disponibles

### **1. Interface Utilisateur — Chat RAG**
- **Nom** : Open WebUI (Assistant Intelligent)
- **URL** : http://localhost:3001
- **Accès** : Public (pas d'authentification)
- **Fonction** : Interface chat pour interroger le modèle Gemma3:1b
- **Modèle** : "Assistant Intelligent" (rag-llm-model v2 en Production)
- **Cache** : Réponses Redis 300s TTL

### **2. Backend API REST**
- **Nom** : RAG API FastAPI
- **URL** : http://localhost:8080
- **Port** : 8080
- **Endpoints clés** :
  - `POST /v1/chat/completions` — Chat RAG (OpenAI compatible)
  - `GET /health` — Statut santé
  - `GET /v1/models` — Liste modèles
  - `POST /rag/query` — RAG direct (prompt v2.0)
  - `POST /monitoring/health` — Dépendances (Qdrant, Ollama, Redis)
  - `GET /metrics` — Métriques Prometheus
- **Auth** : JWT + API Key (X-API-Key header)
- **Rate limiting** : Par rôle (admin/user/service)
- **Prompt** : v2.0 — Factuel, concis, jamais auto-présentation

---

## 📊 Dashboards & Monitoring

### **3. Grafana — Dashboards visuels**
- **Nom** : Grafana
- **URL** : http://localhost:3002
- **Credentials** : admin / admin
- **Dashboards disponibles** (5 dashboards) :
  1. **RAG — Santé des composants backend** (rag_backend_health)
     - Statut API, Qdrant, Ollama, PostgreSQL, Elasticsearch, Kafka
  2. **RAG — Alertes** (rag_alerts)
     - Latence LLM p95, taux erreur, score contexte
  3. **RAG — Cache Redis (détaillé)** (rag_cache_detail)
     - Hit ratio embeddings vs réponses
     - Latence embedding p50/p95
  4. **RAG — Qdrant (détaillé)** (rag_qdrant_detail)
     - Vecteurs indexés, optimisations, CPU matériel
  5. **RAG — Infrastructure Docker (cAdvisor)** (rag_docker_infra)
     - Mémoire totale, CPU Docker, réseau

**Accès direct aux dashboards** :
- Santé backend : http://localhost:3002/d/rag_backend_health
- Alertes : http://localhost:3002/d/rag_alerts
- Cache : http://localhost:3002/d/rag_cache_detail
- Qdrant : http://localhost:3002/d/rag_qdrant_detail
- Infrastructure : http://localhost:3002/d/rag_docker_infra

### **4. Prometheus — Métriques temps réel**
- **Nom** : Prometheus
- **URL** : http://localhost:9090
- **Queries utiles** :
  - `mlflow_production_model_healthy` — Santé capteur C5.2
  - `rag_query_total` — Nombre de requêtes
  - `rag_llm_latency_seconds_bucket` — Latence LLM
  - `rag_context_score_avg` — Qualité retrieval
  - `rag_embedding_cache_hits_total` — Cache hits
  - `container_memory_usage_bytes{id="/docker"}` — Mémoire Docker
  - `up{job="rag-api"}` — Statut API
- **Jobs scrapés** : rag-api, simulator, qdrant, cadvisor, pushgateway, prometheus

### **5. Alertmanager — Alertes & incidents**
- **Nom** : Alertmanager
- **URL** : http://localhost:9093
- **API** :
  - `GET /api/v2/alerts` — Lister alertes actives
  - `POST /api/v1/alerts/grouping` — Groupes d'alertes
- **Alertes** :
  - `HighLLMLatency` (warning) — Latence Gemma3 p95 > 10s
  - `HighErrorRate` (critical) — Taux erreur > 5%
  - `LowContextScore` (warning) — Qualité retrieval < 0.25
  - `MLflowProductionModelUnhealthy` (P0) — Modèle injoignable

---

## 🧠 Models & Expériences

### **6. MLflow — Registry & tracking**
- **Nom** : MLflow Tracking Server
- **URL** : http://localhost:5000
- **Port** : 5000
- **Accès** : Public (pas d'authentification)
- **Fonctionnalités** :
  - **Model Registry** : `rag-llm-model`
    - v1 : Archived
    - v2 : **Production** (Gemma3:1b déployée)
  - **Experiments** :
    - `rag-evaluation` — Métriques RAGAS (F1-F4 per-family)
    - `rag-etl` — Logs des runs ETL
  - **Artifacts** : Modèles, prompts, configurations
- **Capteur C5.2** : Healthcheck toutes les heures (DAG Airflow)

### **7. Ollama — Serveur LLM local**
- **Host** : host.docker.internal (Windows/WSL2)
- **Port** : 11434
- **Modèle** : `gemma3:1b` (CPU-only, ~3-4s/réponse)
- **Alternative** : `gemma3:4b` (CPU ~150s, plus précis pour rapport)
- **URL API** : http://host.docker.internal:11434/api/chat

---

## 🗂️ Données & Ingestion

### **8. Qdrant — Vector Store**
- **Nom** : Qdrant Vector Database
- **URL** : http://localhost:6335
- **Port** : 6335
- **Collection** : `livraison_rag`
- **Embedding** : paraphrase-multilingual-MiniLM-L12-v2 (384 dims)
- **Documents** : ~200 documents (restaurants, zones, livraison)
- **Metrics** :
  - Points indexés : `collection_points`
  - Optimisations en cours : `collection_running_optimizations`

### **9. PostgreSQL — Métadonnées & audit**
- **Host** : localhost:5432
- **DB** : `livraison`
- **User** : postgres / secret
- **Tables** :
  - `audit_logs` — Logs audit JWT/API-Key
  - `user_profiles` — Utilisateurs (admin/user/service roles)
  - `deployments` — Historique déploiements

### **10. Elasticsearch — Logs structurés**
- **URL** : http://localhost:9200
- **Port** : 9200
- **Index pattern** : `rag-logs-*`
- **Source** : Logstash (depuis API logs)
- **Format** : JSON structlog (structlog)

---

## 📈 Observabilité & Workflows

### **11. Kibana — Visualisation logs**
- **Nom** : Kibana
- **URL** : http://localhost:5601
- **Dashboards** :
  - **RAG Logs** — Logs structurés (query, latency, status, user_id)
  - **Error Analysis** — Erreurs par endpoint
  - **Performance** — Latence, throughput
- **Data views** : rag-logs-*

### **12. Airflow — Orchestration & DAGs**
- **Nom** : Apache Airflow (Standalone)
- **URL** : http://localhost:8081
- **Credentials** : admin / admin
- **DAGs** :
  - `rag_etl` — Extract → Chunk → Embed → Qdrant (toutes les 15 min)
  - `rag_evaluation` — RAGAS metrics → MLflow (schedule TBD)
  - `mlflow_healthcheck` — C5.2 Capteur (toutes les heures, `0 * * * *`)
- **Logs** : `/opt/airflow/logs/`
- **Status** : Web UI → DAGs tab

### **13. Redis — Cache**
- **Host** : localhost:6379
- **Caches** :
  - **Embedding cache** : Questions → embeddings (3600s TTL)
  - **Answer cache** : (Q, context) → réponse (300s TTL)
- **Commands** :
  ```bash
  docker compose exec redis redis-cli
  > INFO stats          # Nombre keys/accès
  > KEYS rag:*         # Voir cache keys
  > TTL <key>          # TTL restant
  ```

### **14. cAdvisor — Métriques infrastructure**
- **URL** : http://localhost:8082
- **Expose** : Métriques container (RAM, CPU, réseau)
- **Limitation** : Docker Desktop/WSL2 expose seulement cgroups racine (`/docker`, `/restricted`)
- **Métrique Prometheus** : `container_memory_usage_bytes`, `container_cpu_usage_seconds_total`

### **15. Pushgateway — Push metrics**
- **Nom** : Prometheus Pushgateway
- **URL** : http://localhost:9091
- **Port** : 9091
- **Job** : `mlflow-healthcheck` (C5.2 capteur)
- **Métrique** : `mlflow_production_model_healthy` (1=OK, 0=KO)
- **Scrape par** : Prometheus job `pushgateway`

---

## 🧪 Tests & Simulation

### **16. Simulator — Requêtes synthétiques**
- **URL** : http://localhost:8090
- **Fonction** : Génère des requêtes RAG continues pour tester le système
- **Config** : `simulation_config.yaml`
- **Logs** : Visible dans Kibana

---

## 🔐 Authentification

### **Configuration actuelle** :
```env
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=admin
JWT_SECRET=01bfffdb73193430ce3ac6fe1e717725121fbea1fffc006a90f696c604ff3214
JWT_EXPIRY_MIN=60
API_SERVICE_TOKEN=5fef7c06f3f02045150b50982bbfa35d2f02b37039edea4e
```

### **Endpoints protégés** :
- `POST /auth/login` — Obtenir JWT
- `POST /rag/query` — Requires JWT ou X-API-Key
- `GET /health/dependencies` — Requires JWT

### **Open WebUI** :
- Token service envoyé comme `OPENAI_API_KEY` (rôle "service")

---

## 📋 Checklist — Captures d'écran pour la rédaction

### **Tier 1 — Critical (obligatoires)**
- [ ] Open WebUI : Chat avec Gemma3:1b (réponse structurée)
- [ ] Grafana : Dashboard "Santé des composants"
- [ ] Prometheus : Requête `mlflow_production_model_healthy`
- [ ] MLflow : Model Registry (v2 Production)
- [ ] Alertmanager : Alerte MLflowProductionModelUnhealthy (si KO)

### **Tier 2 — Important (recommandé)**
- [ ] Kibana : Dashboard RAG Logs
- [ ] Airflow : DAG `mlflow_healthcheck` (schedule)
- [ ] Grafana : Cache Redis (hit ratio)
- [ ] Qdrant : Collection stats
- [ ] Prometheus : Alertes actives

### **Tier 3 — Détails (optionnel)**
- [ ] cAdvisor : Mémoire Docker
- [ ] Elasticsearch : Index pattern rag-logs
- [ ] PostgreSQL : Audit logs
- [ ] Redis : CLI stats
- [ ] Ollama : Model list

---

## 🚀 Commandes utiles

### **Démarrer le système**
```bash
docker compose up -d
```

### **Tester le capteur C5.2**
```bash
# Exécution manuelle
docker compose exec airflow python /opt/airflow/src/monitoring/mlflow_healthcheck.py

# Voir métrique Prometheus
curl "http://localhost:9090/api/v1/query?query=mlflow_production_model_healthy"

# Voir alertes Alertmanager
curl http://localhost:9093/api/v2/alerts
```

### **Tester l'API RAG**
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Quel est le taux de retard?"}],
    "model": "Assistant Intelligent"
  }'
```

### **Accéder à Redis CLI**
```bash
docker compose exec redis redis-cli
> KEYS rag:*
> INFO stats
```

### **Voir logs API**
```bash
docker compose logs -f api
```

### **Voir logs Airflow**
```bash
docker compose logs -f airflow
```

---

## 📊 Résumé architecture

```
┌─────────────────────────────────────────────────────────┐
│                   UTILISATEURS                          │
│  Open WebUI (3001) ← Chat RAG ← API (8080)            │
└─────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
    ┌────────┐         ┌────────┐         ┌────────┐
    │ Qdrant │         │ Ollama │         │ Redis  │
    │ (6335) │         │(11434) │         │ (6379) │
    └────────┘         └────────┘         └────────┘
        ↓                                       ↓
    ┌──────────────────────────────────────────────┐
    │         LOGS & METRICS                       │
    │  Elasticsearch (9200) → Kibana (5601)       │
    │  Prometheus (9090) → Grafana (3002)         │
    │  Pushgateway (9091) → Alertmanager (9093)   │
    └──────────────────────────────────────────────┘
        ↓
    ┌──────────────────────────────────────────────┐
    │    ORCHESTRATION & ML TRACKING                │
    │  Airflow (8081) ← DAGs ← MLflow (5000)      │
    │  C5.2: mlflow_healthcheck (DAG toutes les h) │
    └──────────────────────────────────────────────┘
```

---

## ✅ Verification checklist

Avant rédaction du rapport, vérifier :

- [ ] Tous les services Docker en cours d'exécution (`docker compose ps`)
- [ ] API répond sur http://localhost:8080/health
- [ ] Open WebUI accessible et chat fonctionne
- [ ] Grafana avec 5 dashboards visibles
- [ ] Prometheus scrape 6 jobs (api, simulator, qdrant, cadvisor, pushgateway, prometheus)
- [ ] Alertmanager voit les 4 alertes dans rules
- [ ] MLflow Model Registry affiche rag-llm-model v2 en Production
- [ ] Airflow montre 3 DAGs (rag_etl, rag_evaluation, mlflow_healthcheck)
- [ ] Redis cache a des keys `rag:*`
- [ ] Kibana a au moins un index rag-logs-*

---

**Généré le** : 2026-06-06  
**Par** : Claude Code  
**Projet** : mlops-rag-delivery (PFE)
