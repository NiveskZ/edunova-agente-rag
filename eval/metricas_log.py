"""Metricas do registro de execucao (Passo 8), sob demanda a partir do JSONL.

Le `logs/interacoes.jsonl` com pandas e imprime taxa de fallback, feedback,
latencia e documentos mais citados. Sem dashboard e sem servico de
observabilidade: para o volume deste projeto, ler o log direto e suficiente.

Uso:
    python -m eval.metricas_log [caminho_do_log]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

LOG_PADRAO = Path(__file__).resolve().parent.parent / "logs" / "interacoes.jsonl"


def carregar(caminho: Path) -> pd.DataFrame:
    df = pd.read_json(caminho, lines=True)
    # Linhas gravadas antes do Passo 8 nao tem a coluna `evento`; sao respostas.
    if "evento" not in df.columns:
        df["evento"] = "resposta"
    df["evento"] = df["evento"].fillna("resposta")
    return df


def consolidar(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por interacao, com o feedback (gravado depois, em linha
    separada com o mesmo `id`) trazido para a linha da resposta."""
    respostas = df[df["evento"] == "resposta"].copy()
    votos = df[df["evento"] == "feedback"]
    if "id" in df.columns and not votos.empty:
        ultimo_voto = votos.dropna(subset=["id"]).groupby("id")["feedback"].last()
        respostas["feedback"] = respostas["id"].map(ultimo_voto).fillna(respostas["feedback"])
    return respostas


def relatorio(respostas: pd.DataFrame) -> None:
    total = len(respostas)
    print(f"Interacoes registradas: {total}")
    if total == 0:
        return

    if "fallback" in respostas.columns:
        fallbacks = respostas["fallback"].fillna(False).astype(bool)
        print(f"Taxa de fallback: {fallbacks.mean():.1%} ({int(fallbacks.sum())}/{total})")

    if "latencia_s" in respostas.columns:
        latencias = respostas["latencia_s"].dropna()
        if not latencias.empty:
            print(
                f"Latencia (s): media {latencias.mean():.2f} | "
                f"mediana {latencias.median():.2f} | p95 {latencias.quantile(0.95):.2f}"
            )

    votos = respostas["feedback"].value_counts()
    positivos, negativos = int(votos.get("positivo", 0)), int(votos.get("negativo", 0))
    avaliadas = positivos + negativos
    print(f"Feedback: {positivos} positivo(s), {negativos} negativo(s), "
          f"{total - avaliadas} sem avaliacao")
    if avaliadas:
        print(f"Aprovacao entre as avaliadas: {positivos / avaliadas:.1%}")

    citados = respostas["fontes"].explode().dropna()
    if not citados.empty:
        print("\nDocumentos mais citados:")
        for arquivo, quantidade in citados.value_counts().head(5).items():
            print(f"  {quantidade:>3}x  {arquivo}")

    if "fallback" in respostas.columns:
        sem_resposta = respostas[respostas["fallback"].fillna(False).astype(bool)]["pergunta"]
        if not sem_resposta.empty:
            print("\nPerguntas sem resposta na base (candidatas a novo documento):")
            for pergunta in sem_resposta.tail(10):
                print(f"  - {pergunta}")


if __name__ == "__main__":
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else LOG_PADRAO
    if not caminho.exists():
        sys.exit(f"Log nao encontrado: {caminho}")
    relatorio(consolidar(carregar(caminho)))
