"""Embeddings compartilhados entre indexacao (Passo 3) e recuperacao (Passo 4).

Modelos da familia E5 exigem prefixar o texto com "query: " (perguntas) ou
"passage: " (documentos indexados) para ter a qualidade de busca esperada.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

MODELO_EMBEDDINGS = "intfloat/multilingual-e5-small"


class E5Embeddings(HuggingFaceEmbeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return super().embed_documents([f"passage: {texto}" for texto in texts])

    def embed_query(self, text: str) -> list[float]:
        return super().embed_query(f"query: {text}")


@lru_cache(maxsize=1)
def criar_embeddings() -> E5Embeddings:
    """Cacheada (1 instancia por processo): sem isso, cada busca no app
    Streamlit recarregava o modelo do zero (visivel como "Loading weights"
    no log), derrubando o container por OOM (exit 137) apos poucas perguntas
    seguidas com o mem_limit de 1g do docker-compose.yml."""
    return E5Embeddings(
        model_name=MODELO_EMBEDDINGS,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
