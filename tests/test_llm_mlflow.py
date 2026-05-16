"""
test_llm_mlflow.py — MLOPS-Gemma: Test complet MLflow pour LLM Gemma3
=====================================================================
Démonstration du tracking MLflow complet pour le modèle LLM:
- Génération simple avec logging
- Chat avec historique
- Comparaison de performance
- Métriques d'évaluation
"""

import asyncio
import sys
from pathlib import Path

# Ajouter le projet au PYTHONPATH
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import structlog
from src.llm.llm_with_mlflow import LLMWithMLflow
from config.settings import get_settings

log = structlog.get_logger()


async def test_simple_generation():
    """Test 1: Génération simple avec logging MLflow."""
    print("\n" + "=" * 80)
    print("TEST 1: Simple Generation avec MLflow")
    print("=" * 80)

    settings = get_settings()
    llm = LLMWithMLflow(
        host=settings.ollama_host,
        port=settings.ollama_port,
        model=settings.ollama_model,
        mlflow_tracking_uri=settings.mlflow_tracking_uri,
        experiment_name="gemma_simple_generation",
    )

    # Test case 1
    context1 = """
    La livraison #001 est en retard depuis 30 minutes. Le chauffeur signale un embouteillage
    sur la route principale. Le client a déjà contacté le support 2 fois.
    Le restaurant attend également sa confirmation.
    """

    question1 = "Quel est le statut actuel et quelles actions recommandez-vous?"

    print(f"\n📋 Question: {question1}")
    print(f"📋 Context (extrait): {context1[:100]}...")

    result = await llm.generate(context1, question1, run_name="test_generate_1")

    print(f"\n✅ Réponse: {result['response'][:150]}...")
    print(f"⏱️  Latency: {result['latency_ms']:.1f}ms")
    print(f"📊 Run ID: {result['run_id'][:8]}...")

    # Test case 2
    context2 = """
    Zone Alger Centre: 15 livraisons en cours, 3 retardées (> 15min).
    Restaurants impliqués: Restaurant X (2 retards), Restaurant Y (1 retard).
    Chauffeurs: Ahmed (1 retard), Fatima (2 retards).
    """

    question2 = "Quelle zone a le plus d'incidents?"

    print(f"\n\n📋 Question 2: {question2}")
    result2 = await llm.generate(context2, question2, run_name="test_generate_2")

    print(f"✅ Réponse: {result2['response'][:150]}...")
    print(f"⏱️  Latency: {result2['latency_ms']:.1f}ms")


async def test_chat_with_history():
    """Test 2: Chat avec historique."""
    print("\n" + "=" * 80)
    print("TEST 2: Chat avec Historique")
    print("=" * 80)

    settings = get_settings()
    llm = LLMWithMLflow(
        host=settings.ollama_host,
        port=settings.ollama_port,
        model=settings.ollama_model,
        mlflow_tracking_uri=settings.mlflow_tracking_uri,
        experiment_name="gemma_chat",
    )

    context = """
    Incident #123: Livraison retardée de 45 minutes.
    Client: Karim (Alger)
    Restaurant: Restaurant Hassan
    Chauffeur: Youcef (expérience 2 ans)
    Montant: 3500 DA
    """

    # Message 1
    messages = [
        {"role": "user", "content": "Quelle est la situation avec la livraison #123?"}
    ]

    print(f"\n📱 Message 1: {messages[0]['content']}")
    result1 = await llm.chat(messages, context, run_name="chat_turn_1")
    print(f"✅ Réponse 1: {result1['response'][:150]}...")
    print(f"⏱️  Latency: {result1['latency_ms']:.1f}ms")

    # Ajouter la réponse à l'historique
    messages.append({"role": "assistant", "content": result1["response"]})

    # Message 2
    messages.append(
        {"role": "user", "content": "Quelles actions devrais-je prendre immédiatement?"}
    )

    print(f"\n📱 Message 2: {messages[-1]['content']}")
    result2 = await llm.chat(messages, context, run_name="chat_turn_2")
    print(f"✅ Réponse 2: {result2['response'][:150]}...")
    print(f"⏱️  Latency: {result2['latency_ms']:.1f}ms")


async def test_model_comparison():
    """Test 3: Comparaison de performance."""
    print("\n" + "=" * 80)
    print("TEST 3: Comparaison de Performance")
    print("=" * 80)

    settings = get_settings()
    llm = LLMWithMLflow(
        host=settings.ollama_host,
        port=settings.ollama_port,
        model=settings.ollama_model,
        mlflow_tracking_uri=settings.mlflow_tracking_uri,
        experiment_name="gemma_performance",
    )

    test_cases = [
        {
            "context": "Incident restaurant: Retard de 20 min, 5 clients affectés, compensation proposée",
            "question": "Résumez l'incident",
        },
        {
            "context": "Zone Oran: 20 livraisons, 2 retards, 1 incident. Chauffeur Ahmed très chargé.",
            "question": "Quelles actions recommandez-vous pour cette zone?",
        },
        {
            "context": "Tendance: Augmentation 15% des retards le weekend. Restaurants fermés lundi cause fermeture.",
            "question": "Qu'indiquent ces tendances?",
        },
    ]

    print(f"\n📊 Lancement de {len(test_cases)} test cases...")
    comparison = await llm.compare_models(
        test_cases=test_cases, experiment_name="gemma_comparison"
    )

    print("\n✅ Résultats:")
    print(
        f"   Tests réussis: {comparison['test_cases_passed']}/{comparison['total_runs']}"
    )
    print(f"   Latency moyenne: {comparison['avg_latency_ms']:.1f}ms")
    print(f"   Expérience: {comparison['experiment_name']}")

    for result in comparison["test_results"]:
        if "error" not in result:
            print(f"\n   Test {result['test_id']}: {result['latency_ms']:.1f}ms")
            print(f"      Question: {result['question'][:60]}...")


async def main():
    """Lancer tous les tests."""
    print("\n" + "╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print(
        "║" + "  🎯 MLFLOW TRACKING POUR GEMMA3:270M - TESTS COMPLETS".center(78) + "║"
    )
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")

    try:
        # Test 1: Génération simple
        await test_simple_generation()

        # Test 2: Chat avec historique
        await test_chat_with_history()

        # Test 3: Comparaison de performance
        await test_model_comparison()

        print("\n" + "=" * 80)
        print("✅ TOUS LES TESTS COMPLÉTÉS AVEC SUCCÈS")
        print("=" * 80)
        print("\n📊 Résultats disponibles dans MLflow:")
        print("   ➡️  http://localhost:5000")
        print("\n   Expériences tracées:")
        print("      • gemma_simple_generation (2 runs)")
        print("      • gemma_chat (2 runs)")
        print("      • gemma_performance (3 runs)")
        print("\n" + "=" * 80)

    except Exception as e:
        log.error(f"Erreur test: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
