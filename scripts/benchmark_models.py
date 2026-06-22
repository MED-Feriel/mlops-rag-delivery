#!/usr/bin/env python3
"""benchmark_models.py — Compare la latence Gemma3:1b vs 4b sur Ollama (CPU).

But : justifier le choix du modèle servi. En CPU pur, les modèles 3-4B sont
nettement plus lents que 1b sur les requêtes lourdes — ce script chiffre l'écart
sur des questions représentatives des 4 familles d'intent (retards, incidents,
restaurants, zones) + une question de synthèse/superlatif.

Aucune dépendance tierce (urllib stdlib) → exécutable depuis l'hôte qui voit
Ollama (Windows ou WSL). Exploite les timings serveur renvoyés par Ollama
(total_duration, eval_count, eval_duration) en plus du wall-clock.

Usage :
  python scripts/benchmark_models.py
  OLLAMA_URL=http://172.x.x.x:11434 python scripts/benchmark_models.py
  python scripts/benchmark_models.py --models gemma3:1b,gemma3:4b --num-predict 256
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONTEXT = (
    "[Contexte supervision livraison]\n"
    "- Zone Bab Ezzouar : 142 commandes, retard moyen 18 min, 7 incidents.\n"
    "- Zone Hydra : 98 commandes, retard moyen 9 min, 2 incidents.\n"
    "- Restaurant 'Le Gourmet' : note 4.6, 3 retards > 30 min aujourd'hui.\n"
    "- Restaurant 'Pizza Express' : note 3.9, 11 retards > 30 min aujourd'hui.\n"
    "- Incident #4521 : livreur bloqué 27 min, zone Bab Ezzouar, statut résolu.\n"
)

SYSTEM = (
    "Tu es un assistant de supervision d'une plateforme de livraison. "
    "Réponds de façon concise et factuelle en t'appuyant sur le contexte."
)

QUESTIONS = [
    ("F1_retards", "Quels sont les retards de livraison aujourd'hui ?"),
    ("F2_incidents", "Combien d'incidents et lesquels sont critiques ?"),
    ("F3_restaurant", "Quel restaurant a le plus de retards et pourquoi ?"),
    ("F4_zone", "Fais une synthèse de la zone Bab Ezzouar."),
    ("synthese", "Quelle est la pire zone en termes de retards ?"),
]


def generate(url: str, model: str, prompt: str, num_predict: int, timeout: int) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0.2},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    wall = time.perf_counter() - start
    eval_count = body.get("eval_count", 0)
    eval_dur_s = (body.get("eval_duration", 0) or 0) / 1e9
    tok_s = (eval_count / eval_dur_s) if eval_dur_s else 0.0
    return {
        "wall_s": round(wall, 2),
        "total_duration_s": round((body.get("total_duration", 0) or 0) / 1e9, 2),
        "eval_count": eval_count,
        "tokens_per_s": round(tok_s, 1),
        "answer_chars": len(body.get("response", "")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--models", default="gemma3:1b,gemma3:4b")
    ap.add_argument("--num-predict", type=int, default=256)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--runs", type=int, default=1, help="garde la meilleure latence sur N essais")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    url = args.url
    print(f"Benchmark Ollama @ {url} — modèles: {', '.join(models)} (num_predict={args.num_predict})")

    summary: dict = {}
    per_question: dict = {}
    for model in models:
        latencies: list[float] = []
        toks: list[float] = []
        rows: list[tuple[str, dict]] = []
        for qid, question in QUESTIONS:
            prompt = f"{SYSTEM}\n\n{CONTEXT}\nQuestion: {question}\nRéponse:"
            best = None
            for _ in range(args.runs):
                try:
                    r = generate(url, model, prompt, args.num_predict, args.timeout)
                except (urllib.error.URLError, TimeoutError) as e:
                    print(f"  x {model} / {qid}: {e}")
                    best = None
                    break
                if best is None or r["wall_s"] < best["wall_s"]:
                    best = r
            if best is None:
                continue
            latencies.append(best["wall_s"])
            toks.append(best["tokens_per_s"])
            rows.append((qid, best))
            print(f"  {model:12s} {qid:14s} {best['wall_s']:7.2f}s  {best['tokens_per_s']:6.1f} tok/s")
        if latencies:
            summary[model] = {
                "n": len(latencies),
                "median_s": round(statistics.median(latencies), 2),
                "mean_s": round(statistics.mean(latencies), 2),
                "max_s": round(max(latencies), 2),
                "mean_tokens_per_s": round(statistics.mean(toks), 1),
            }
            per_question[model] = {qid: r for qid, r in rows}

    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "docs"
    out_dir.mkdir(exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "num_predict": args.num_predict,
        "runs": args.runs,
        "summary": summary,
        "per_question": per_question,
    }
    (out_dir / "benchmark_models.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = [
        "# Benchmark Gemma3 — latence CPU",
        "",
        f"_Généré le {payload['generated_at']} · Ollama `{url}` · num_predict={args.num_predict}_",
        "",
        "## Synthèse",
        "",
        "| Modèle | N | Médiane | Moyenne | Max | tok/s moyen |",
        "|--------|---|---------|---------|-----|-------------|",
    ]
    for model, s in summary.items():
        md.append(
            f"| {model} | {s['n']} | {s['median_s']}s | {s['mean_s']}s | {s['max_s']}s | {s['mean_tokens_per_s']} |"
        )
    if "gemma3:1b" in summary and "gemma3:4b" in summary and summary["gemma3:1b"]["median_s"]:
        ratio = summary["gemma3:4b"]["median_s"] / summary["gemma3:1b"]["median_s"]
        md += [
            "",
            f"> En CPU, **Gemma3:4b est ~{ratio:.1f}× plus lent que 1b** (médiane). "
            "→ 1b pour la démo temps réel, 4b réservé aux analyses hors-ligne / rapport.",
        ]
    md += ["", "## Détail par question", ""]
    for model in summary:
        md += [f"### {model}", "", "| Question | Wall | tok/s | car. réponse |", "|----------|------|-------|--------------|"]
        for qid, r in per_question[model].items():
            md.append(f"| {qid} | {r['wall_s']}s | {r['tokens_per_s']} | {r['answer_chars']} |")
        md.append("")
    (out_dir / "benchmark_models.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("\nRésumé:\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    print("\n-> docs/benchmark_models.md + docs/benchmark_models.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
