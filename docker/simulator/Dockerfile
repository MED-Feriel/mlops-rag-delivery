FROM python:3.11-slim
WORKDIR /app
# UNIQUEMENT requirements légers du simulateur
COPY docker/simulator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# UNIQUEMENT le code simulateur — pas langchain, pas ragas
COPY src/simulator/ ./simulator/
COPY simulation_config.yaml .
RUN useradd -m -u 1000 simulator && chown -R simulator /app
USER simulator
EXPOSE 8090
CMD ["uvicorn", "simulator.main:app", "--host", "0.0.0.0", "--port", "8090"]
