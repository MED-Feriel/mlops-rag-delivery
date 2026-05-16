"""
mlflow_docker_config.py — Configuration Docker pour MLflow
==========================================================
Exemple de setup MLflow avec PostgreSQL et S3 en Docker.

À utiliser si vous voulez une setup de production avec persistance.
"""

DOCKER_COMPOSE_MLFLOW = """
version: '3.9'

services:
  mlflow-postgres:
    image: postgres:15-alpine
    container_name: mlflow-postgres
    environment:
      POSTGRES_USER: mlflow
      POSTGRES_PASSWORD: mlflow_secure_password_123
      POSTGRES_DB: mlflow
    volumes:
      - mlflow_db:/var/lib/postgresql/data
    networks:
      - rag-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mlflow"]
      interval: 10s
      timeout: 5s
      retries: 5
    ports:
      - "5432:5432"

  mlflow-minio:
    image: minio/minio:latest
    container_name: mlflow-minio
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin123
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    networks:
      - rag-network
    ports:
      - "9000:9000"
      - "9001:9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  mlflow-server:
    image: ghcr.io/mlflow/mlflow:latest
    container_name: mlflow-server
    environment:
      BACKEND_STORE_URI: postgresql://mlflow:mlflow_secure_password_123@mlflow-postgres:5432/mlflow
      DEFAULT_ARTIFACT_ROOT: s3://mlflow/artifacts
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin123
      MLFLOW_S3_ENDPOINT_URL: http://mlflow-minio:9000
    command: >
      mlflow server
      --backend-store-uri postgresql://mlflow:mlflow_secure_password_123@mlflow-postgres:5432/mlflow
      --default-artifact-root s3://mlflow/artifacts
      --host 0.0.0.0
      --port 5000
    depends_on:
      mlflow-postgres:
        condition: service_healthy
      mlflow-minio:
        condition: service_healthy
    networks:
      - rag-network
    ports:
      - "5000:5000"
    volumes:
      - mlflow_artifacts:/mlflow

networks:
  rag-network:
    driver: bridge

volumes:
  mlflow_db:
  minio_data:
  mlflow_artifacts:
"""

DOCKER_COMPOSE_SIMPLE = """
version: '3.9'

services:
  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    container_name: mlflow
    command: >
      mlflow server
      --backend-store-uri sqlite:////mlflow/mlflow.db
      --default-artifact-root /mlflow/artifacts
      --host 0.0.0.0
      --port 5000
    volumes:
      - mlflow_data:/mlflow
    ports:
      - "5000:5000"
    networks:
      - rag-network

networks:
  rag-network:
    driver: bridge

volumes:
  mlflow_data:
"""

if __name__ == "__main__":
    print("Configuration MLflow Docker Compose\n")
    print("=" * 80)
    print("\n1. SIMPLE (SQLite + Local Storage)")
    print("-" * 80)
    print(DOCKER_COMPOSE_SIMPLE)

    print("\n2. PRODUCTION (PostgreSQL + MinIO S3)")
    print("-" * 80)
    print(DOCKER_COMPOSE_MLFLOW)

    print("\nUsage:")
    print("  docker-compose -f docker-compose.mlflow.yml up -d")
    print("\nAccès:")
    print("  - MLflow UI: http://localhost:5000")
    print("  - MinIO Console: http://localhost:9001")
