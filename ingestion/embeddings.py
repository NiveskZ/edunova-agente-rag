"""Embeddings compartilhados entre indexacao (Passo 3) e recuperacao (Passo 4).

Modelos da familia E5 exigem prefixar o texto com "query: " (perguntas) ou
"passage: " (documentos indexados) para ter a qualidade de busca esperada.
"""

from __future__ import annotations

from langchain_huggingface import HuggingFaceEmbeddings

MODELO_EMBEDDINGS = "intfloat/multilingual-e5-small"


class E5Embeddings(HuggingFaceEmbeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return super().embed_documents([f"passage: {texto}" for texto in texts])

    def embed_query(self, text: str) -> list[float]:
        return super().embed_query(f"query: {text}")


def criar_embeddings() -> E5Embeddings:
    return E5Embeddings(
        model_name=MODELO_EMBEDDINGS,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
