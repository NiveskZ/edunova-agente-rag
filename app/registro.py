"""Registro de execucao do agente (Passo 8).

Uma linha JSONL por evento em `logs/interacoes.jsonl`:

- `resposta`: pergunta, estudante identificado, chunks recuperados (com
  distancia e se passaram pelo no `autorizar`), resposta, fontes citadas,
  latencia e timestamp;
- `feedback`: voto do usuario, com o mesmo `id` da interacao.

Fica fora do `streamlit_app.py` para poder ser usado e testado sem o runtime
do Streamlit. Analise sob demanda em `eval/metricas_log.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.graph import RESPOSTA_FALLBACK

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "interacoes.jsonl"
TRECHO_LOG = 200


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def gravar_log(registro: dict, caminho: Path = LOG_PATH) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _chunks_para_log(resultado: dict) -> list[dict]:
    """Todos os chunks recuperados, com a distancia e se sobreviveram ao no
    `autorizar` (so os autorizados foram para o prompt do LLM)."""
    autorizados = {id(doc) for doc in resultado.get("documentos", [])}
    return [
        {
            "arquivo": doc.metadata.get("arquivo"),
            "tema": doc.metadata.get("tema"),
            "distancia": round(float(score), 4),
            "autorizado": id(doc) in autorizados,
            "trecho": doc.page_content[:TRECHO_LOG],
        }
        for doc, score in resultado.get("resultados", [])
    ]


def registrar_resposta(
    interacao_id: str,
    pergunta: str,
    estudante: str | None,
    resultado: dict,
    latencia_s: float,
    caminho: Path = LOG_PATH,
) -> None:
    gravar_log(
        {
            "id": interacao_id,
            "timestamp": _agora(),
            "evento": "resposta",
            "pergunta": pergunta,
            "estudante_identificado": estudante,
            "chunks_recuperados": _chunks_para_log(resultado),
            "melhor_distancia": resultado.get("melhor_distancia"),
            "fallback": resultado["resposta"] == RESPOSTA_FALLBACK,
            "resposta": resultado["resposta"],
            "fontes": resultado["fontes"],
            "latencia_s": round(latencia_s, 3),
            "feedback": None,
        },
        caminho,
    )


def registrar_feedback(
    interacao_id: str, pergunta: str, feedback: str, caminho: Path = LOG_PATH
) -> None:
    gravar_log(
        {
            "id": interacao_id,
            "timestamp": _agora(),
            "evento": "feedback",
            "pergunta": pergunta,
            "feedback": feedback,
        },
        caminho,
    )
