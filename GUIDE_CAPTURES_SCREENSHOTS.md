# 📸 Guide — Captures d'écran pour la rédaction du PFE

**Date** : 2026-06-06  
**Projet** : mlops-rag-delivery (Master 1 MLops)  
**Auteur** : merrad feriel

---

## ✅ Status des services (à 21:57)

| Service | Port | Status | Accessible |
|---------|------|--------|-----------|
| **Open WebUI** | 3001 | ✅ UP | http://localhost:3001 |
| **Grafana** | 3002 | ✅ UP | http://localhost:3002 |
| **Prometheus** | 9090 | ✅ UP | http://localhost:9090 |
| **Alertmanager** | 9093 | ✅ UP | http://localhost:9093 |
| **Airflow** | 8081 | ✅ UP | http://localhost:8081 |
| **Kibana** | 5601 | ✅ UP | http://localhost:5601 |
| API (FastAPI) | 8080 | ✅ UP* | Internal (requis JWT/API-Key) |
| MLflow | 5000 | ✅ UP* | Internal (accessible via Airflow) |
| Qdrant | 6335 | ✅ UP* | Internal (requis Bearer token) |
| Elasticsearch | 9200 | ✅ UP* | Internal (accès Kibana) |
| Redis | 6379 | ✅ UP* | Internal (CLI dans container) |

*Services internes accessibles via interfaces web ou Airflow

---

## 🎯 Captures obligatoires (Tier 1)

### 1️⃣ **Open WebUI — Chat RAG v2.0 (page principale)**

**URL** : http://localhost:3001

**Étapes** :
1. Ouvrir http://localhost:3001
2. ✅ Vérifier que le modèle "Assistant Intelligent" est sélectionné
3. ✅ Poser une question : `Quel est le taux de retard?`
4. ✅ Attendre la réponse structurée (format: `Valeur: X`)
5. 📸 **Capturer** l'écran avec question + réponse

**Ce qu'il doit montrer** :
- Interface Clean OpenWebUI
- Model selector affichant "Assistant Intelligent"
- Réponse facile structurée (ne pas "Je suis un assistant")
- Cache activé (réponse rapide < 3s)
- Prompt v2.0 en action ✅

---

### 2️⃣ **Grafana — Dashboard "Santé des composants backend"**

**URL** : http://localhost:3002/d/rag_backend_health

**Credentials** : admin / admin (si demandé)

**Étapes** :
1. Ouvrir http://localhost:3002
2. Login : admin / admin
3. Menu → Dashboards
4. Rechercher "RAG — Santé des composants"
5. 📸 **Capturer** l'écran avec les 6 composants (API, Qdrant, Ollama, PostgreSQL, Elasticsearch, Kafka)

**Ce qu'il doit montrer** :
- 6 boxes avec status couleur (vert = UP)
- Dernière mise à jour
- Design clean Grafana
- Proof de monitoring en place ✅

---

### 3️⃣ **Prometheus — Requête "mlflow_production_model_healthy"**

**URL** : http://localhost:9090

**Étapes** :
1. Ouvrir http://localhost:9090
2. Aller à l'onglet "Graph"
3. Entrer en search box : `mlflow_production_model_healthy`
4. Cliquer "Execute"
5. Regarder le graphe et la valeur (doit être 1 si tout OK)
6. 📸 **Capturer** l'écran avec la requête et le résultat

**Ce qu'il doit montrer** :
- Requête PromQL visible
- Graphe dans le temps
- Valeur actuelle (1 = healthy)
- Capteur C5.2 fonctionnel ✅

---

### 4️⃣ **MLflow — Model Registry (rag-llm-model v2 Production)**

**URL** : http://localhost:5000

**Étapes** :
1. Ouvrir http://localhost:5000 (pas besoin login)
2. Menu gauche → "Models"
3. Cliquer sur "rag-llm-model"
4. Vérifier que v2 a le tag "Production" (badge orange/vert)
5. 📸 **Capturer** l'écran du Model Registry

**Ce qu'il doit montrer** :
- Model name: rag-llm-model
- v2 avec stage: Production (badge)
- v1 avec stage: Archived
- Timestamps versions
- Proof du model registry ✅

---

### 5️⃣ **Alertmanager — Tableau d'alertes**

**URL** : http://localhost:9093

**Étapes** :
1. Ouvrir http://localhost:9093
2. Regarder le tableau principal (liste des alertes)
3. Attendre 5 sec pour voir le refresh
4. 📸 **Capturer** l'écran du tableau d'alertes

**Ce qu'il doit montrer** :
- Liste des alertes (4 alertes définies dans alerts.yml)
- Colonnes : Alertname, Severity, State, Last update
- Sévérité P0 pour MLflowProductionModelUnhealthy
- Interface Alertmanager ✅

---

## 📋 Captures recommandées (Tier 2)

### 6️⃣ **Airflow — DAG "mlflow_healthcheck"**

**URL** : http://localhost:8081

**Étapes** :
1. Ouvrir http://localhost:8081
2. Login : admin / admin
3. Chercher DAG "mlflow_healthcheck"
4. Cliquer dessus
5. Voir :
   - Schedule : 0 * * * * (toutes les heures)
   - Graph view
   - Recent runs
6. 📸 **Capturer** DAG + schedule + graph

**Ce qu'il doit montrer** :
- DAG mlflow_healthcheck
- Task: check_production_model
- Schedule: Hourly (0 * * * *)
- Orchestration en place ✅

---

### 7️⃣ **Grafana — Cache Redis (hit ratio)**

**URL** : http://localhost:3002/d/rag_cache_detail

**Étapes** :
1. Ouvrir http://localhost:3002/d/rag_cache_detail
2. Regarder les gauges :
   - "Hit ratio — cache embeddings"
   - "Hit ratio — cache réponses"
3. Voir les timeseries
4. 📸 **Capturer** le dashboard entier

**Ce qu'il doit montrer** :
- Cache hits vs misses
- Latence p50/p95 embeddings
- Proof du cache Redis B.2 ✅

---

### 8️⃣ **Kibana — Logs RAG**

**URL** : http://localhost:5601

**Étapes** :
1. Ouvrir http://localhost:5601
2. Menu → Discover
3. Sélectionner data view: rag-logs-*
4. Regarder les logs structurés
5. Filtrer par @timestamp recent
6. 📸 **Capturer** quelques logs

**Ce qu'il doit montrer** :
- Logs structurés (JSON)
- Champs: query, latency, status, user_id
- Kibana UI
- Logging structuré en place ✅

---

### 9️⃣ **Grafana — Qdrant Stats**

**URL** : http://localhost:3002/d/rag_qdrant_detail

**Étapes** :
1. Ouvrir http://localhost:3002/d/rag_qdrant_detail
2. Voir :
   - "Vecteurs indexés (collection_points)"
   - "Optimisations en cours"
   - Table version Qdrant
3. 📸 **Capturer** le dashboard

**Ce qu'il doit montrer** :
- Points indexés (nombre)
- CPU Qdrant
- Version Qdrant info
- Vector store en action ✅

---

### 🔟 **Grafana — Infrastructure Docker**

**URL** : http://localhost:3002/d/rag_docker_infra

**Étapes** :
1. Ouvrir http://localhost:3002/d/rag_docker_infra
2. Voir :
   - "Mémoire totale — tous les conteneurs"
   - "CPU — taux d'utilisation"
   - Note plateforme (WSL2 limitation)
3. 📸 **Capturer** le dashboard

**Ce qu'il doit montrer** :
- Mémoire Docker totale (MB/GB)
- CPU utilisation (%)
- Réseau reçu (B/s)
- Proof de cAdvisor + Prometheus ✅

---

## 💡 Captures optionnelles (Tier 3)

- [ ] **Elasticsearch** cluster status : http://localhost:9200/_cluster/health
- [ ] **Redis CLI** : `docker compose exec redis redis-cli INFO stats`
- [ ] **Prometheus targets** : http://localhost:9090/targets
- [ ] **Airflow task logs** : Log d'exécution mlflow_healthcheck
- [ ] **API health** : Curl depuis terminal (montre JSON response)

---

## 🎬 Conseils pour les captures

### **Format recommandé** :
- **Résolution** : 1920×1080 ou native
- **Format** : PNG (meilleure compression)
- **Nommage** : `1_openwebui_chat.png`, `2_grafana_health.png`, etc.
- **Annotations** : Ajouter des flèches/cercles rouges pour souligner points clés

### **Points clés à souligner** :
1. **Prompt v2.0** : Question → Réponse structurée (pas d'auto-présentation)
2. **Cache Redis** : Hit ratio > 50% = performance
3. **MLflow v2 Production** : Modèle actuellement déployé
4. **Capteur C5.2** : mlflow_production_model_healthy = 1 (healthy)
5. **DAG Airflow** : Exécution horaire du capteur
6. **Alertes P0** : Système d'alerte en place

---

## 📊 Résumé structure des captures

```
Chapitre 1 : Interface utilisateur
  └─ Screenshot 1: Open WebUI chat RAG

Chapitre 2 : Monitoring & Observabilité
  ├─ Screenshot 2: Grafana dashboard santé
  ├─ Screenshot 3: Prometheus mlflow_production_model_healthy
  ├─ Screenshot 4: Alertmanager alertes
  ├─ Screenshot 5: Kibana logs
  └─ Screenshot 6: Grafana infrastructure Docker

Chapitre 3 : ML Tracking & Orchestration
  ├─ Screenshot 7: MLflow Model Registry (v2 Production)
  ├─ Screenshot 8: Airflow DAG mlflow_healthcheck
  └─ Screenshot 9: Grafana Qdrant stats

Chapitre 4 : Performance & Cache
  └─ Screenshot 10: Grafana Redis cache detail
```

---

## 🚀 Commandes utiles pour terminal

### **Tester le capteur C5.2 manuellement**
```bash
# Exécuter le script directement
docker compose exec airflow python /opt/airflow/src/monitoring/mlflow_healthcheck.py

# Voir les logs
docker compose logs -f airflow | grep mlflow_healthcheck
```

### **Vérifier MLflow API**
```bash
# Voir modèles registrés
curl http://localhost:5000/api/2.0/mlflow/registered-models/list

# Voir versions du modèle
curl http://localhost:5000/api/2.0/mlflow/registered-models/get?name=rag-llm-model
```

### **Vérifier Prometheus scrape**
```bash
# Voir tous les jobs scrapés
curl http://localhost:9090/api/v1/targets

# Requête métrique spécifique
curl 'http://localhost:9090/api/v1/query?query=mlflow_production_model_healthy'
```

### **Vérifier Redis cache**
```bash
docker compose exec redis redis-cli
> KEYS rag:*           # Voir les keys
> INFO stats           # Stats cache
> TTL <key>           # Voir TTL
> FLUSHDB             # Clear cache (si besoin)
```

### **Voir logs structurés API**
```bash
docker compose logs -f api | grep -E "query|status|latency"
```

---

## ✅ Checklist avant rédaction

- [ ] Tous les services Docker up (`docker compose ps`)
- [ ] Prometheus scrape 7 jobs (api, simulator, qdrant, cadvisor, pushgateway, alertmanager, prometheus)
- [ ] MLflow Registry affiche rag-llm-model v2 Production
- [ ] Airflow DAG mlflow_healthcheck visible avec schedule
- [ ] Grafana 5 dashboards visibles et actifs
- [ ] Kibana index pattern rag-logs-* visible
- [ ] Redis cache a des keys rag:*
- [ ] Alertmanager tableau d'alertes visible
- [ ] Open WebUI chat répond correctement

---

## 📝 Notes pour la rédaction

**Section 1 — Introduction RAG** :
- Montrer Open WebUI (UX utilisateur)
- Expliquer prompt v2.0 (factuel, concis)

**Section 2 — Architecture techniques** :
- Montrer Grafana santé + infrastructure
- Montrer Qdrant stats + embeddings

**Section 3 — ML Operations** :
- MLflow Model Registry (v2 Production)
- Prometheus + metrics
- Alertmanager + alertes P0

**Section 4 — Observabilité** :
- Kibana logs structurés
- Prometheus + Grafana dashboards
- cAdvisor infrastructure

**Section 5 — Automation** :
- Airflow DAG mlflow_healthcheck
- Capteur C5.2 + Pushgateway
- Schedule toutes les heures

**Section 6 — Cache & Performance** :
- Grafana cache detail
- Redis hit ratio
- Answer cache 300s TTL

---

**Généré le** : 2026-06-06  
**Par** : Claude Code  
**Prêt pour rédaction** : ✅

