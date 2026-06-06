#!/bin/bash

# Script de vérification complète du système RAG MLops
# Teste tous les services et affiche les informations pour capture d'écran

set -e

RESET='\033[0m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'

echo -e "${BLUE}════════════════════════════════════════════════════════════════${RESET}"
echo -e "${BLUE}   Vérification complète — mlops-rag-delivery (PFE)${RESET}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${RESET}\n"

# ──────────────────────────────────────────────────────────────────────────
# 1. Vérifier Docker
# ──────────────────────────────────────────────────────────────────────────

echo -e "${YELLOW}[1/10]${RESET} Vérification services Docker..."
docker_check=$(docker compose ps --filter "status=running" 2>/dev/null | wc -l)
if [ "$docker_check" -gt 5 ]; then
    echo -e "${GREEN}✓${RESET} $(docker compose ps --filter "status=running" --quiet | wc -l) services en cours d'exécution"
else
    echo -e "${RED}✗${RESET} Services non disponibles. Démarrer : docker compose up -d"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────
# 2. API Health
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[2/10]${RESET} API RAG (http://localhost:8080)..."
if curl -s http://localhost:8080/health | jq . >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} API online"
    curl -s http://localhost:8080/health | jq '.' | head -20
else
    echo -e "${RED}✗${RESET} API offline"
fi

# ──────────────────────────────────────────────────────────────────────────
# 3. MLflow Models Registry
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[3/10]${RESET} MLflow Registry (http://localhost:5000)..."
if curl -s http://localhost:5000/api/2.0/mlflow/registered-models/list | jq . >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} MLflow online"
    echo "Models registrés :"
    curl -s http://localhost:5000/api/2.0/mlflow/registered-models/list | jq '.registered_models[].name'
else
    echo -e "${RED}✗${RESET} MLflow offline"
fi

# ──────────────────────────────────────────────────────────────────────────
# 4. Prometheus Metrics
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[4/10]${RESET} Prometheus (http://localhost:9090)..."
if curl -s http://localhost:9090/-/healthy >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} Prometheus online"
    echo "Targets scrapés :"
    curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, instance: .labels.instance, state: .health}' | head -30
else
    echo -e "${RED}✗${RESET} Prometheus offline"
fi

# ──────────────────────────────────────────────────────────────────────────
# 5. Pushgateway (C5.2)
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[5/10]${RESET} Pushgateway — Capteur C5.2 (http://localhost:9091)..."
if curl -s http://localhost:9091/-/healthy >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} Pushgateway online"
    echo "Métriques pushées :"
    curl -s http://localhost:9091/metrics | grep mlflow_production || echo "  (aucune métrique encore — attendre 1ère exécution DAG)"
else
    echo -e "${RED}✗${RESET} Pushgateway offline (service à démarrer)"
fi

# ──────────────────────────────────────────────────────────────────────────
# 6. Alertmanager
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[6/10]${RESET} Alertmanager (http://localhost:9093)..."
if curl -s http://localhost:9093/-/healthy >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} Alertmanager online"
    echo "Alertes actuelles :"
    curl -s http://localhost:9093/api/v2/alerts | jq '.[] | {alertname: .labels.alertname, severity: .labels.severity, state: .state}' || echo "  (aucune alerte)"
else
    echo -e "${RED}✗${RESET} Alertmanager offline"
fi

# ──────────────────────────────────────────────────────────────────────────
# 7. Elasticsearch
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[7/10]${RESET} Elasticsearch (http://localhost:9200)..."
if curl -s http://localhost:9200/_cluster/health | jq . >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} Elasticsearch online"
    curl -s http://localhost:9200/_cluster/health | jq '{status, number_of_nodes, active_shards}'
else
    echo -e "${RED}✗${RESET} Elasticsearch offline"
fi

# ──────────────────────────────────────────────────────────────────────────
# 8. Qdrant
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[8/10]${RESET} Qdrant (http://localhost:6335)..."
if curl -s http://localhost:6335/health | jq . >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} Qdrant online"
    curl -s http://localhost:6335/health | jq '.'
else
    echo -e "${RED}✗${RESET} Qdrant offline"
fi

# ──────────────────────────────────────────────────────────────────────────
# 9. Redis
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[9/10]${RESET} Redis (localhost:6379)..."
if redis-cli -p 6379 ping >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} Redis online"
    echo "Stats Redis :"
    redis-cli -p 6379 INFO stats 2>/dev/null | grep -E "total_commands_processed|keyspace_hits|keyspace_misses"
else
    echo -e "${RED}✗${RESET} Redis offline ou non accessible"
fi

# ──────────────────────────────────────────────────────────────────────────
# 10. Test RAG Chat
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${YELLOW}[10/10]${RESET} Test RAG Chat (v2.0 - Prompt Factuel)..."
response=$(curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Dis OK"}],
    "model": "Assistant Intelligent",
    "temperature": 0.1
  }' 2>/dev/null)

if echo "$response" | jq . >/dev/null 2>&1; then
    echo -e "${GREEN}✓${RESET} RAG API responding"
    echo "Réponse test :"
    echo "$response" | jq '.choices[0].message'
else
    echo -e "${RED}✗${RESET} RAG API error"
    echo "$response"
fi

# ──────────────────────────────────────────────────────────────────────────
# URLs pour les captures d'écran
# ──────────────────────────────────────────────────────────────────────────

echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${RESET}"
echo -e "${GREEN}✓ VÉRIFICATION COMPLÈTE${RESET}\n"

echo -e "${YELLOW}URLs pour captures d'écran (TBD):${RESET}\n"

echo "1️⃣  Interface utilisateur"
echo "   🔗 Open WebUI: http://localhost:3001"
echo "   └─ Chat avec Gemma3:1b (v2.0 factuel, concis)\n"

echo "2️⃣  Dashboards (Grafana)"
echo "   🔗 Santé backend: http://localhost:3002/d/rag_backend_health"
echo "   🔗 Alertes RAG: http://localhost:3002/d/rag_alerts"
echo "   🔗 Cache Redis: http://localhost:3002/d/rag_cache_detail"
echo "   🔗 Qdrant stats: http://localhost:3002/d/rag_qdrant_detail"
echo "   🔗 Infrastructure: http://localhost:3002/d/rag_docker_infra\n"

echo "3️⃣  Monitoring"
echo "   🔗 Prometheus: http://localhost:9090"
echo "   └─ Requête: mlflow_production_model_healthy"
echo "   🔗 Alertmanager: http://localhost:9093"
echo "   🔗 Pushgateway (C5.2): http://localhost:9091\n"

echo "4️⃣  MLflow & Orchestration"
echo "   🔗 MLflow Registry: http://localhost:5000"
echo "   └─ Model: rag-llm-model v2 (Production)"
echo "   🔗 Airflow DAGs: http://localhost:8081"
echo "   └─ DAG: mlflow_healthcheck (schedule: 0 * * * *)\n"

echo "5️⃣  Logs & Traces"
echo "   🔗 Kibana: http://localhost:5601"
echo "   🔗 Elasticsearch: http://localhost:9200\n"

echo -e "${BLUE}════════════════════════════════════════════════════════════════${RESET}\n"

echo -e "${YELLOW}Conseils pour la rédaction:${RESET}"
echo "✓ Capturer Open WebUI avec une conversation (ex: 'Taux de retard?')"
echo "✓ Afficher Grafana avec 'Santé des composants' (tous green)"
echo "✓ Montrer Prometheus avec mlflow_production_model_healthy = 1"
echo "✓ Montrer MLflow Registry avec v2 Production"
echo "✓ Montrer Airflow DAG mlflow_healthcheck avec schedule"
echo "✓ Inclure capture Alertmanager (tableau d'alertes)"
echo ""
echo "Pour données brutes: voir DOCUMENTATION_LIENS_ACCES.md"
echo ""
