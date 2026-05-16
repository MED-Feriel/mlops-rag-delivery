.PHONY: up down reset generate etl simulate stop-sim test eval query status ports build-sim

up:
	docker compose up -d
	@echo "Attente 30s..."
	sleep 30

down:
	docker compose down -v

build-sim:
	docker compose build simulator

generate:
	docker compose run --rm simulator python -m simulator.static_generator

etl:
	docker compose exec api python -m src.ingestion.run_etl

simulate:
	curl -X POST http://localhost:8090/start

stop-sim:
	curl -X POST http://localhost:8090/stop

reset:
	curl -X POST http://localhost:8090/reset

test:
	docker compose exec api pytest tests/ -v --tb=short --cov=src

eval:
	docker compose exec api python -c \
	"import asyncio; from src.evaluation.ragas_evaluator import RAGASEvaluator; print('RAGAS OK')"

query:
	curl -X POST http://localhost:8080/query \
	  -H "Content-Type: application/json" \
	  -d '{"question": "Quelles commandes sont en retard en ce moment ?"}'

status:
	@echo "Qdrant:" && curl -s http://localhost:6335/health
	@echo "\nOllama models:" && curl -s http://localhost:11434/api/tags | python3 -c \
	  "import sys,json; print([m['name'] for m in json.load(sys.stdin).get('models',[])])"
	@echo "\nSimulator:" && curl -s http://localhost:8090/status
	@echo "\nAPI RAG:" && curl -s http://localhost:8080/health

ports:
	@echo "Open WebUI     : http://localhost:3001"
	@echo "API RAG docs   : http://localhost:8080/docs"
	@echo "Simulator ctrl : http://localhost:8090"
	@echo "Qdrant UI      : http://localhost:6335/dashboard"
	@echo "Airflow UI     : http://localhost:8081"
	@echo "Kibana         : http://localhost:5601"
	@echo "Grafana        : http://localhost:3000"
	@echo "MLflow         : http://localhost:5000"
	@echo "Prometheus     : http://localhost:9090"
