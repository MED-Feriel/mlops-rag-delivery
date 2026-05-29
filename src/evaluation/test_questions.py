"""
Questions d'évaluation couvrant les 4 familles.
20 questions au total (5 par famille).
Ground truth basée sur les données simulées.
"""

EVAL_QUESTIONS = [
    # ── FAMILLE 1 : Données métier ──────────────────────
    {
        "question": "Quel restaurant a le plus fort taux d'annulation ?",
        "ground_truth": "Le restaurant avec le taux d'annulation le plus élevé "
        "est identifiable dans les documents agrégés top_restaurants.",
        "family": "F1_metier",
        "filters_expected": {},
    },
    {
        "question": "Quelles commandes sont en retard de plus de 30 minutes ?",
        "ground_truth": "Les commandes avec delai_reel_min - delai_estime_min > 30 "
        "et statut en_route ou retard_détecté.",
        "family": "F1_metier",
        "filters_expected": {"criticite": "haute"},
    },
    {
        "question": "Quelle zone géographique a les délais de livraison les plus longs ?",
        "ground_truth": "La zone avec la plus grande moyenne de retard. "
        "Hydra a un délai extra de 12 min (convois présidentiels).",
        "family": "F1_metier",
        "filters_expected": {},
    },
    {
        "question": "Quels livreurs moto ont le plus de livraisons réussies ?",
        "ground_truth": "Livreurs avec vehicule_type=moto et nb_livraisons élevé.",
        "family": "F1_metier",
        "filters_expected": {},
    },
    {
        "question": "Quels restaurants de catégorie fast food ont des retards fréquents ?",
        "ground_truth": "Restaurants avec categorie=Fast Food et taux_annulation élevé.",
        "family": "F1_metier",
        "filters_expected": {"type_event": "restaurant"},
    },
    # ── FAMILLE 2 : Logs applicatifs ─────────────────────
    {
        "question": "Y a-t-il des erreurs récentes dans les logs applicatifs ?",
        "ground_truth": "Les logs ERROR récents sont indexés depuis Elasticsearch "
        "toutes les 2 minutes dans Qdrant.",
        "family": "F2_logs",
        "filters_expected": {"source": "elasticsearch", "type_event": "log_error"},
    },
    {
        "question": "Quel service a généré le plus d'erreurs récemment ?",
        "ground_truth": "Le service avec le plus de logs ERROR dans les dernières minutes.",
        "family": "F2_logs",
        "filters_expected": {"source": "elasticsearch"},
    },
    {
        "question": "Y a-t-il eu une panne DNS en mars 2026 ?",
        "ground_truth": "Oui, panne DNS documentée le 27 mars 2026, sévérité critique, "
        "22 incidents générés sur Dely Ibrahim.",
        "family": "F2_logs",
        "filters_expected": {"criticite": "critique", "type_event": "log_error"},
    },
    {
        "question": "Des erreurs de paiement ont-elles été détectées dans les logs ?",
        "ground_truth": "Les erreurs GATEWAY_TIMEOUT du payment-service sont "
        "visibles dans les logs indexés.",
        "family": "F2_logs",
        "filters_expected": {"source_service": "payment-service"},
    },
    {
        "question": "Quels logs WARNING concernent la zone Hydra ?",
        "ground_truth": "Logs WARN liés aux retards de convois présidentiels à Hydra.",
        "family": "F2_logs",
        "filters_expected": {"zone": "Hydra", "type_event": "log_warn"},
    },
    # ── FAMILLE 3 : Métriques système ────────────────────
    {
        "question": "Quel est l'état de santé de la plateforme en ce moment ?",
        "ground_truth": "Le snapshot Prometheus contient taux succès RAG, "
        "latence p95, score contexte, et état des services.",
        "family": "F3_metriques",
        "filters_expected": {"source": "prometheus"},
    },
    {
        "question": "Le taux de succès des requêtes RAG est-il satisfaisant ?",
        "ground_truth": "Taux succès visible dans le snapshot santé système "
        "(seuil acceptable: >95%).",
        "family": "F3_metriques",
        "filters_expected": {"source": "prometheus"},
    },
    {
        "question": "Quelle est la latence actuelle de l'API RAG ?",
        "ground_truth": "Latence p95 du snapshot Prometheus le plus récent.",
        "family": "F3_metriques",
        "filters_expected": {"source": "prometheus"},
    },
    {
        "question": "Y a-t-il des services en panne actuellement ?",
        "ground_truth": "Le snapshot Prometheus indique le nombre de services UP.",
        "family": "F3_metriques",
        "filters_expected": {"source": "prometheus"},
    },
    {
        "question": "Le score contexte Qdrant est-il dans les normes ?",
        "ground_truth": "Score contexte moyen visible dans le snapshot santé "
        "(seuil: >0.30 acceptable, >0.60 excellent).",
        "family": "F3_metriques",
        "filters_expected": {"source": "prometheus"},
    },
    # ── FAMILLE 4 : Synthèse et diagnostic ───────────────
    {
        "question": "Pourquoi y a-t-il eu une augmentation des annulations "
        "lors de la panne du restaurant en décembre 2025 ?",
        "ground_truth": "Panne restaurant jour 15 (12 décembre 2025) sur Dely Ibrahim, "
        "12 commandes annulées, sévérité haute.",
        "family": "F4_diagnostic",
        "filters_expected": {"type_event": "restaurant_ferme"},
    },
    {
        "question": "Résume les incidents critiques survenus en mars 2026",
        "ground_truth": "Panne DNS critique le 27 mars 2026 sur Dely Ibrahim, "
        "22 incidents, sévérité critique.",
        "family": "F4_diagnostic",
        "filters_expected": {"criticite": "critique"},
    },
    {
        "question": "Donne-moi un état de santé général de la plateforme",
        "ground_truth": "Synthèse combinant métriques Prometheus (snapshot actuel) "
        "et données opérationnelles (commandes, incidents).",
        "family": "F4_diagnostic",
        "filters_expected": {},
    },
    {
        "question": "Quelles sont les causes récurrentes de retard à Hydra ?",
        "ground_truth": "Convois présidentiels (+12 min), documenté dans les incidents "
        "et la configuration des zones.",
        "family": "F4_diagnostic",
        "filters_expected": {"zone": "Hydra"},
    },
    {
        "question": "Le livreur injoignable du 25 février 2026 était-il expérimenté ?",
        "ground_truth": "Incident livreur_bloque jour 90 (25 fév 2026) à Hydra. "
        "Croiser avec les données livreur (annee_experience, note).",
        "family": "F4_diagnostic",
        "filters_expected": {"type_event": "livreur_bloque"},
    },
]
