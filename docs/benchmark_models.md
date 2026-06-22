# Benchmark Gemma3 — latence CPU

_Généré le 2026-06-05T18:14:59.832572+00:00 · Ollama `http://localhost:11434` · num_predict=256_

## Synthèse

| Modèle | N | Médiane | Moyenne | Max | tok/s moyen |
|--------|---|---------|---------|-----|-------------|
| gemma3:1b | 5 | 4.44s | 5.11s | 8.68s | 27.4 |
| gemma3:4b | 5 | 8.3s | 10.7s | 22.95s | 10.2 |

> En CPU, **Gemma3:4b est ~1.9× plus lent que 1b** (médiane). → 1b pour la démo temps réel, 4b réservé aux analyses hors-ligne / rapport.

## Détail par question

### gemma3:1b

| Question | Wall | tok/s | car. réponse |
|----------|------|-------|--------------|
| F1_retards | 8.68s | 27.6 | 96 |
| F2_incidents | 4.44s | 26.0 | 91 |
| F3_restaurant | 4.49s | 28.1 | 113 |
| F4_zone | 4.41s | 26.6 | 93 |
| synthese | 3.52s | 28.8 | 17 |

### gemma3:4b

| Question | Wall | tok/s | car. réponse |
|----------|------|-------|--------------|
| F1_retards | 22.95s | 10.1 | 135 |
| F2_incidents | 9.45s | 10.1 | 136 |
| F3_restaurant | 6.91s | 10.2 | 109 |
| F4_zone | 8.3s | 10.3 | 114 |
| synthese | 5.9s | 10.2 | 62 |

