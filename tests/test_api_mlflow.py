"""
test_api_mlflow.py — Test complet de l'API RAG avec MLflow Tracking
===================================================================
Tests les 4 endpoints avec MLflow tracking:
- POST /query — RAG simple
- POST /query/stream — RAG streaming
- POST /chat — Chat RAG
- POST /chat/stream — Chat streaming
"""

import asyncio
import sys
from pathlib import Path
import httpx
import json

# Ajouter le projet au PYTHONPATH
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import structlog

log = structlog.get_logger()


async def test_query():
    """Test 1: Requête simple /query."""
    print("\n" + "=" * 80)
    print("TEST 1: POST /query — Requête RAG simple")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            payload = {
                "question": "Quels sont les incidents critiques de livraison?",
                "top_k": 5,
            }

            print(f"\n📋 Payload: {json.dumps(payload, indent=2)}")

            response = await client.post("http://localhost:8000/query", json=payload)

            if response.status_code == 200:
                result = response.json()
                print(f"\n✅ Status: {response.status_code}")
                print(f"📝 Réponse: {result['answer'][:150]}...")
                print(f"📊 Chunks: {len(result.get('contexts', []))}")
                print("⏱️  Latency: Vérifie MLflow pour les détails")
                return True
            else:
                print(f"\n❌ Status: {response.status_code}")
                print(f"❌ Erreur: {response.text}")
                return False

        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            return False


async def test_query_stream():
    """Test 2: Requête streaming /query/stream."""
    print("\n" + "=" * 80)
    print("TEST 2: POST /query/stream — RAG avec streaming")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            payload = {"question": "Quel restaurant a le plus d'incidents?", "top_k": 3}

            print(f"\n📋 Payload: {json.dumps(payload, indent=2)}")
            print("\n📡 Tokens streamés:")

            async with client.stream(
                "POST", "http://localhost:8000/query/stream", json=payload
            ) as response:
                if response.status_code == 200:
                    token_count = 0
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            token = line[6:]  # Enlever "data: "
                            print(f"   {token}", end="", flush=True)
                            token_count += len(token)
                    print(f"\n\n✅ Status: {response.status_code}")
                    print(f"📊 Tokens: {token_count}")
                    return True
                else:
                    print(f"\n❌ Status: {response.status_code}")
                    return False

        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            return False


async def test_chat():
    """Test 3: Chat /chat."""
    print("\n" + "=" * 80)
    print("TEST 3: POST /chat — Chat RAG avec historique")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # Message 1
            payload1 = {
                "messages": [
                    {
                        "role": "user",
                        "content": "Quels sont les problèmes de livraison actuels?",
                    }
                ],
                "top_k": 5,
            }

            print(f"\n📱 Turn 1: {payload1['messages'][0]['content']}")

            response1 = await client.post("http://localhost:8000/chat", json=payload1)

            if response1.status_code != 200:
                print(f"❌ Erreur Turn 1: {response1.status_code}")
                return False

            result1 = response1.json()
            answer1 = result1["answer"]
            print(f"✅ Réponse 1: {answer1[:100]}...")

            # Message 2 (avec historique)
            payload2 = {
                "messages": [
                    {
                        "role": "user",
                        "content": "Quels sont les problèmes de livraison actuels?",
                    },
                    {"role": "assistant", "content": answer1},
                    {
                        "role": "user",
                        "content": "Comment puis-je améliorer la situation?",
                    },
                ],
                "top_k": 5,
            }

            print("\n📱 Turn 2: Comment puis-je améliorer la situation?")

            response2 = await client.post("http://localhost:8000/chat", json=payload2)

            if response2.status_code == 200:
                result2 = response2.json()
                print(f"✅ Réponse 2: {result2['answer'][:100]}...")
                print(f"📊 Messages tracés: {len(payload2['messages'])}")
                return True
            else:
                print(f"❌ Erreur Turn 2: {response2.status_code}")
                return False

        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            return False


async def test_chat_stream():
    """Test 4: Chat streaming /chat/stream."""
    print("\n" + "=" * 80)
    print("TEST 4: POST /chat/stream — Chat streaming")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            payload = {
                "messages": [
                    {"role": "user", "content": "Quelle est la tendance des incidents?"}
                ],
                "top_k": 3,
            }

            print(f"\n📱 Message: {payload['messages'][0]['content']}")
            print("\n📡 Tokens streamés:")

            async with client.stream(
                "POST", "http://localhost:8000/chat/stream", json=payload
            ) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            token = line[6:]
                            print(f"   {token}", end="", flush=True)
                    print(f"\n\n✅ Status: {response.status_code}")
                    return True
                else:
                    print(f"\n❌ Status: {response.status_code}")
                    return False

        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            return False


async def main():
    """Lancer tous les tests."""
    print("\n" + "╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  🎯 TESTS API RAG AVEC MLFLOW TRACKING".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")

    # Vérifier que l'API est disponible
    print("\n🔍 Vérification de l'API...")
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            health = await client.get("http://localhost:8000/health")
            if health.status_code == 200:
                print(f"✅ API disponible: {health.json()}")
            else:
                print("❌ API non disponible")
                return
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            print("\nLance d'abord l'API:")
            print("  uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000")
            return

    # Lancer les tests
    results = []

    results.append(("Query simple", await test_query()))
    results.append(("Query stream", await test_query_stream()))
    results.append(("Chat", await test_chat()))
    results.append(("Chat stream", await test_chat_stream()))

    # Résumé
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ DES TESTS")
    print("=" * 80)

    for name, success in results:
        status = "✅ OK" if success else "❌ FAILED"
        print(f"  {name:30s} {status}")

    total = len(results)
    passed = sum(1 for _, s in results if s)

    print(f"\n  Total: {passed}/{total} tests réussis")

    print("\n" + "=" * 80)
    print("📊 RÉSULTATS MLFLOW")
    print("=" * 80)
    print(
        """
  Ouvre dans le navigateur:
  ➡️  http://localhost:5000

  Expériences tracées:
  • rag_inference (API requests)
  • gemma_simple_generation (LLM calls)
  • gemma_chat (Chat calls)

  Métriques disponibles:
  • retrieve_time_ms
  • context_build_time_ms
  • llm_latency_ms
  • total_pipeline_time_ms
  • chunks_retrieved
  • answer_length
"""
    )
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
