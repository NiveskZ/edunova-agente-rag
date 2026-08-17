"""Avaliacao de retrieval (Passo 4): Recall@k sobre o golden set anotado a mao.

Um numero, sem notebook, sem grafico - so pra saber se k=4 e suficiente.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.retriever import K, buscar

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.jsonl"


def carregar_golden_set() -> list[dict]:
    with GOLDEN_SET_PATH.open(encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def avaliar(k: int = K) -> float:
    casos = carregar_golden_set()
    acertos = 0
    for caso in casos:
        resultados = buscar(caso["pergunta"], k=k)
        arquivos_recuperados = {r.metadata["arquivo"] for r in resultados}
        acertou = caso["arquivo_esperado"] in arquivos_recuperados
        acertos += acertou
        status = "OK " if acertou else "FALHOU"
        print(f"[{status}] {caso['pergunta']} -> esperado: {caso['arquivo_esperado']}"
              f" | recuperados: {sorted(arquivos_recuperados)}")

    recall = acertos / len(casos)
    print(f"\nRecall@{k}: {recall:.2%} ({acertos}/{len(casos)})")
    return recall


if __name__ == "__main__":
    avaliar()
