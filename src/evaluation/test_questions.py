"""Questions de référence pour l'évaluation RAGAS — 10 questions par catégorie"""

EVAL_QUESTIONS = [
    {
        "question": "Quelles commandes sont actuellement en retard de plus de 30 minutes ?",
        "ground_truth": "Les commandes en retard ont delai_reel_min - delai_estime_min > 30, statut en_route ou retard_détecté.",  # noqa: E501
        "category": "temps_reel",
    },
    {
        "question": "Y a-t-il des incidents critiques actifs en ce moment ?",
        "ground_truth": "Incidents avec severite='critique' ou 'haute' et resolu=false.",
        "category": "temps_reel",
    },
    {
        "question": "Quel livreur est actuellement bloqué ?",
        "ground_truth": "Livreur avec incident de type livreur_bloque non résolu.",
        "category": "temps_reel",
    },
    {
        "question": "Quel restaurant a le plus fort taux d'annulation ce mois-ci ?",
        "ground_truth": "Restaurant avec le plus de commandes annulées sur les 30 derniers jours.",
        "category": "analyse",
    },
    {
        "question": "Quelle zone géographique a les délais de livraison les plus longs ?",
        "ground_truth": "Zone avec la plus grande moyenne de (delai_reel_min - delai_estime_min).",
        "category": "analyse",
    },
    {
        "question": "Quelles sont les causes les plus fréquentes de retard ?",
        "ground_truth": "Types d'incidents par fréquence : retard, restaurant_ferme, livreur_bloque.",
        "category": "diagnostic",
    },
    {
        "question": "Comment s'est comporté le service de paiement ces dernières heures ?",
        "ground_truth": "Incidents paiement_echoue et logs ERROR du payment-service.",
        "category": "diagnostic",
    },
    {
        "question": "Le volume de commandes est-il en hausse ou en baisse aujourd'hui ?",
        "ground_truth": "Comparaison du compte de commandes aujourd'hui vs moyenne des 7 derniers jours.",
        "category": "tendance",
    },
    {
        "question": "Les notes clients se sont-elles améliorées récemment ?",
        "ground_truth": "Évolution de la note moyenne des commentaires clients dans le temps.",
        "category": "tendance",
    },
    {
        "question": "Décris les 3 incidents les plus critiques survenus aujourd'hui.",
        "ground_truth": "3 incidents avec severite='critique' triés par created_at décroissant.",
        "category": "complexe",
    },
]
