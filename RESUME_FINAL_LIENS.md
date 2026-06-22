# 🎯 RÉSUMÉ FINAL — Tous les liens d'accès

**Date** : 2026-06-06 (jour 2 après implémentation capteur C5.2)  
**Utilisateur** : merrad feriel (merradferiel8@gmail.com)  
**Projet** : mlops-rag-delivery (PFE Master 1 MLops)

---

## 🌐 LIENS DIRECTS — Accès Web

### **[1] INTERFACE UTILISATEUR**
```
🔗 Open WebUI — Chat RAG
   URL: http://localhost:3001
   Modèle: Assistant Intelligent (Gemma3:1b v2.0 Production)
   Auth: None (public)
```

---

### **[2] DASHBOARDS (Grafana)**
```
🔗 Accueil Grafana
   URL: http://localhost:3002
   Credentials: admin / admin

   📊 Dashboard 1 — Santé des composants
   URL: http://localhost:3002/d/rag_backend_health
   Affiche: API, Qdrant, Ollama, PostgreSQL, Elasticsearch, Kafka (status UP/DOWN)

   📊 Dashboard 2 — Alertes RAG
   URL: http://localhost:3002/d/rag_alerts
   Affiche: Latence LLM p95, taux erreur, score contexte, seuils

   📊 Dashboard 3 — Cache Redis
   URL: http://localhost:3002/d/rag_cache_detail
   Affiche: Hit ratio embeddings + réponses, latence p50/p95

   📊 Dashboard 4 — Qdrant (Vector Store)
   URL: http://localhost:3002/d/rag_qdrant_detail
   Affiche: Points indexés, optimisations, CPU Qdrant, version

   📊 Dashboard 5 — Infrastructure Docker
   URL: http://localhost:3002/d/rag_docker_infra
   Affiche: Mémoire Docker, CPU, réseau (via cAdvisor)
```

---

### **[3] MONITORING TEMPS RÉEL**

#### **Prometheus — Métriques**
```
🔗 Prometheus UI
   URL: http://localhost:9090
   
   Requêtes clés à tester:
   • mlflow_production_model_healthy          [Capteur C5.2]
   • rag_query_total{status="error"}          [Erreurs RAG]
   • histogram_quantile(0.95, rag_llm_latency_seconds_bucket) [Latence p95]
   • rag_context_score_avg                    [Qualité retrieval]
   • rag_embedding_cache_hits_total           [Cache hits]
   • up{job="rag-api"}                        [API status]
   
   Jobs scrapés:
   ✓ rag-api (8080/metrics)
   ✓ simulator (8090/metrics)
   ✓ qdrant (6333/metrics)
   ✓ cadvisor (8082/metrics)
   ✓ pushgateway (9091/metrics)
   ✓ prometheus (9090/metrics)
   ✓ alertmanager (9093/metrics)
```

#### **Pushgateway — Capteur C5.2**
```
🔗 Pushgateway
   URL: http://localhost:9091
   
   Métrique: mlflow_production_model_healthy
   • Valeur 1 = Modèle Production accessible ✅
   • Valeur 0 = Modèle injoignable ❌
   
   Job: mlflow-healthcheck
   Exécution: DAG Airflow toutes les heures (0 * * * *)
```

#### **Alertmanager — Alertes**
```
🔗 Alertmanager UI
   URL: http://localhost:9093
   
   Alertes définies (4):
   1. HighLLMLatency (warning)
      └─ Si: histogram_quantile(0.95, rag_llm_latency) > 10s pendant 2min
   
   2. HighErrorRate (critical)
      └─ Si: taux_erreur > 5% pendant 1min
   
   3. LowContextScore (warning)
      └─ Si: score_contexte < 0.25 pendant 5min
   
   4. MLflowProductionModelUnhealthy (P0) ⭐ NOUVEAU
      └─ Si: mlflow_production_model_healthy == 0 pendant 5min
      └─ Description: "Modèle MLflow en production non sain"
```

---

### **[4] ML TRACKING & REGISTRY**

#### **MLflow — Model Registry**
```
🔗 MLflow Tracking Server
   URL: http://localhost:5000
   Auth: None
   
   Model Registry:
   📦 rag-llm-model
      ├─ v1: Archived
      └─ v2: PRODUCTION ⭐ (Gemma3:1b actuel)
   
   Experiments:
   • rag-evaluation    — Métriques RAGAS (F1-F4 families)
   • rag-etl           — Logs ETL runs
```

---

### **[5] ORCHESTRATION**

#### **Airflow — DAGs & Workflows**
```
🔗 Airflow UI
   URL: http://localhost:8081
   Credentials: admin / admin
   
   DAGs disponibles (3):
   
   1️⃣ rag_etl
      Schedule: Toutes les 15 min (*/15 * * * *)
      Tâche: Extract → Chunk → Embed → Qdrant upsert
      Status: Active
   
   2️⃣ rag_evaluation (futur)
      Schedule: TBD
      Tâche: RAGAS metrics → MLflow
   
   3️⃣ mlflow_healthcheck ⭐ NOUVEAU (C5.2)
      Schedule: Toutes les heures (0 * * * *)
      Tâche: check_production_model
      └─ 1. Récupère version Production MLflow
         2. Test API avec question "Dis OK"
         3. Pousse métrique mlflow_production_model_healthy
      Status: Active
```

---

### **[6] LOGS & TRACES**

#### **Kibana — Logs structurés**
```
🔗 Kibana UI
   URL: http://localhost:5601
   
   Data views:
   • rag-logs-* (index pattern)
   
   Dashboards:
   • RAG Logs         — Logs structurés (JSON)
   • Error Analysis   — Erreurs par endpoint
   • Performance      — Latence, throughput
   
   Champs disponibles:
   - @timestamp
   - query (question utilisateur)
   - latency_ms (temps réponse)
   - status (success/error)
   - user_id (audit)
   - model_version (v2.0)
```

#### **Elasticsearch — Index**
```
🔗 Elasticsearch REST
   URL: http://localhost:9200
   Endpoint: /_cluster/health
   
   Index: rag-logs-2026-06-*
   Source: Logstash ← API logs (structlog format)
```

---

### **[7] VECTOR STORE & DONNÉES**

#### **Qdrant — Vector Database**
```
🔗 Qdrant UI (interne, via Kibana/Grafana)
   API: http://localhost:6335
   
   Collection: livraison_rag
   Embedding: paraphrase-multilingual-MiniLM-L12-v2 (384 dims)
   Documents: ~200 (restaurants, zones, livraison)
   
   Métriques Prometheus:
   • collection_points                    [Vecteurs indexés]
   • collection_running_optimizations     [Optimisations]
   • collection_hardware_metric_cpu       [CPU Qdrant]
```

---

### **[8] CACHE & PERFORMANCE**

#### **Redis — Cache distributeur**
```
🔗 Redis CLI
   Host: localhost:6379
   Auth: None
   
   Caches:
   1. Embedding Cache
      └─ Key pattern: rag:embedding:*
      └─ TTL: 3600s (1h)
      └─ Source: Questions utilisateur
   
   2. Answer Cache
      └─ Key pattern: rag:answer:*
      └─ TTL: 300s (5 min)
      └─ Source: (Question, Contexte) → Réponse complète
   
   CLI commands:
   $ docker compose exec redis redis-cli
   > KEYS rag:*              # Voir keys
   > INFO stats              # Stats (hits, misses)
   > TTL <key>              # Voir TTL restant
   > FLUSHDB                # Clear cache (⚠️ produit uniquement)
```

---

### **[9] API BACKEND (Internal)**

#### **FastAPI — RAG API**
```
🔗 API REST
   URL: http://localhost:8080 (interne au réseau Docker)
   Accessible via: Open WebUI, tests, DAGs
   
   Endpoints:
   POST /v1/chat/completions
      └─ Chat RAG compatible OpenAI
      └─ Auth: JWT + X-API-Key header
   
   GET /health
      └─ Statut basic
   
   GET /v1/models
      └─ Lister modèles disponibles
   
   POST /rag/query
      └─ RAG direct (prompt v2.0)
   
   GET /metrics
      └─ Prometheus metrics
   
   POST /monitoring/health
      └─ Dépendances (Qdrant, Ollama, Redis status)
   
   Prompt: v2.0 (Factuel, concis, jamais auto-présentation)
   Temperature: 0.1 (faible créativité)
   Max tokens: 256 (concision forcée)
```

---

## 📋 FICHIERS DE CONFIGURATION CLÉS

```
📁 Project root: mlops-rag-delivery/

├─ docker-compose.yml
│  └─ Services: API, Qdrant, Redis, MLflow, Airflow, Prometheus,
│     Grafana, Alertmanager, Pushgateway, Elasticsearch, Kibana, etc.
│
├─ .env
│  ├─ MLFLOW_TRACKING_URI=http://mlflow:5000
│  ├─ PUSHGATEWAY_URL=http://pushgateway:9091  [NEW]
│  ├─ AUTH_ENABLED=true
│  ├─ REDIS_TTL_ANSWER_SEC=300  [Cache réponses]
│  └─ OLLAMA_MODEL=gemma3:1b
│
├─ prometheus/
│  ├─ prometheus.yml         — Jobs à scraper (7 jobs)
│  ├─ alerts.yml            — 4 règles d'alerte
│  └─ alertmanager.yml      — Config alertes
│
├─ grafana/
│  └─ dashboards/
│     ├─ rag_backend_health.json      — Santé composants
│     ├─ rag_alerts.json              — Alertes
│     ├─ rag_cache_detail.json        — Cache Redis
│     ├─ rag_qdrant_detail.json       — Qdrant stats
│     └─ rag_docker_infra.json        — Infrastructure cAdvisor
│
├─ dags/
│  ├─ rag_etl_dag.py                 — ETL 15 min
│  └─ mlflow_healthcheck_dag.py      — Capteur C5.2 [NEW]
│
├─ src/
│  ├─ api/
│  │  ├─ main.py                     — FastAPI app
│  │  └─ openai_compat.py            — Endpoints /v1/*
│  │
│  ├─ rag/
│  │  ├─ prompt_builder.py           — SYSTEM_PROMPT v2.0 [SOURCE OF TRUTH]
│  │  └─ guardrails.py               — Anti-hallucination
│  │
│  ├─ llm/
│  │  └─ llm_service.py              — Ollama client (imports prompt_builder)
│  │
│  └─ monitoring/
│     ├─ mlflow_healthcheck.py       — Capteur C5.2 [NEW]
│     ├─ prometheus_metrics.py       — Metrics export
│     └─ mlflow_tracker.py           — MLflow integration
│
└─ README.md                          — Docs projet
```

---

## 🎯 ÉTAPES POUR CAPTURES D'ÉCRAN

### **TIER 1 — Obligatoires**

1. **Open WebUI**
   ```
   Ouvrir: http://localhost:3001
   Faire: Chat "Quel est le taux de retard?"
   Attendre: Réponse structurée
   Capturer: Écran complet
   ```

2. **Grafana Dashboard Santé**
   ```
   Ouvrir: http://localhost:3002/d/rag_backend_health
   Voir: 6 composants (API, Qdrant, Ollama, PostgreSQL, Elasticsearch, Kafka) en vert
   Capturer: Écran complet
   ```

3. **Prometheus Métrique C5.2**
   ```
   Ouvrir: http://localhost:9090
   Chercher: mlflow_production_model_healthy
   Exécuter: La requête
   Voir: Graphe + valeur (doit être 1)
   Capturer: Écran avec requête + résultat
   ```

4. **MLflow Model Registry**
   ```
   Ouvrir: http://localhost:5000
   Aller à: Models section
   Voir: rag-llm-model v2 avec stage "Production"
   Capturer: Écran Model Registry
   ```

5. **Alertmanager**
   ```
   Ouvrir: http://localhost:9093
   Voir: Tableau d'alertes (4 alertes)
   Capturer: Écran tableau
   ```

### **TIER 2 — Recommandés**

6. **Airflow DAG mlflow_healthcheck**
   ```
   Ouvrir: http://localhost:8081
   Chercher: mlflow_healthcheck
   Voir: Schedule 0 * * * *, task graph
   Capturer: DAG + schedule
   ```

7. **Grafana Cache Redis**
   ```
   Ouvrir: http://localhost:3002/d/rag_cache_detail
   Voir: Hit ratio gauges + timeseries
   Capturer: Écran complet
   ```

8. **Kibana Logs**
   ```
   Ouvrir: http://localhost:5601
   Voir: Data view rag-logs-*
   Capturer: Quelques logs structurés
   ```

9. **Grafana Qdrant**
   ```
   Ouvrir: http://localhost:3002/d/rag_qdrant_detail
   Voir: Vecteurs indexés, version
   Capturer: Écran complet
   ```

10. **Grafana Infrastructure Docker**
    ```
    Ouvrir: http://localhost:3002/d/rag_docker_infra
    Voir: Mémoire, CPU, réseau totaux
    Capturer: Écran complet
    ```

---

## ✅ CHECKLIST FINAL

- [ ] Docker compose up -d (tous services verts)
- [ ] Open WebUI répond et chat fonctionne
- [ ] Grafana dashboards 5 visibles et actifs
- [ ] Prometheus scrape 7 jobs (voir targets)
- [ ] MLflow Registry affiche rag-llm-model v2 Production
- [ ] Airflow DAG mlflow_healthcheck visible
- [ ] Alertmanager tableau d'alertes visible
- [ ] Pushgateway en ligne (port 9091)
- [ ] Kibana logs structurés visibles
- [ ] Redis cache a des keys rag:*

---

## 📚 DOCUMENTATION ASSOCIÉE

| Document | Contenu |
|----------|---------|
| `DOCUMENTATION_LIENS_ACCES.md` | Détail complet de tous les services |
| `GUIDE_CAPTURES_SCREENSHOTS.md` | Instructions pas à pas pour captures |
| `RESUME_FINAL_LIENS.md` | Ce fichier — résumé liens |

---

**Généré le** : 2026-06-06  
**État** : ✅ Prêt pour rédaction  
**Statut services** : 12/12 services actifs

