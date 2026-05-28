#!/usr/bin/env bash
set -euo pipefail

# scripts/load_rag_metrics.sh
# Simule des requêtes RAG pour générer des métriques Prometheus

API_URL="http://127.0.0.1:8080/query"
NUM_REQUESTS=${1:-20}

printf "Running %s requests against %s\n" "$NUM_REQUESTS" "$API_URL"
for i in $(seq 1 "$NUM_REQUESTS"); do
  curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d '{"question":"Test monitoring '"$i"'", "top_k": 5}' > /dev/null &
  sleep 0.1
 done
wait

printf "Requests completed.\n"
printf "Metrics sample:\n"
curl -s http://127.0.0.1:8080/metrics | grep -E 'rag_query_total|rag_embedding_duration_seconds|rag_context_score_avg|rag_llm_latency_seconds|rag_retrieved_docs_count' | head -40
