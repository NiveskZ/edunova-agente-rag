"""Camada de recuperacao (RAG) sobre o Oracle Database 23ai indexado no Passo 3.

Filtro por tema (Passo 4, item 2): heuristica simples de palavra-chave, sem
classificador extra. So filtra se a pergunta mencionar claramente um dos temas
do catalogo; caso contrario busca sem filtro nas TABLE_NAME inteira.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_oracledb.vectorstores.oraclevs import OracleVS
from langchain_oracledb.vectorstores.utils import DistanceStrategy

from ingestion.embeddings import criar_embeddings
from ingestion.index import TABLE_NAME, conectar

K = 4

# tema -> palavras-chave que, se presentes na pergunta, disparam o filtro.
_PALAVRAS_POR_TEMA = {
    "matricula": ["matricula", "matrícula", "reembolso", "cancelamento", "trancamento", "regimento"],
    "certificados": ["autenticação", "autenticacao", "código de autenticação"],
    "cursos": ["avaliação", "avaliacao", "carga horária", "carga horaria", "preço", "preco", "parcelado", "categoria"],
    "plataforma": ["plataforma", "aplicativo", "site"],
    "bolsas": ["bolsa", "bolsas", "afiliado", "afiliados", "indicação", "indicacao"],
}


def detectar_tema(pergunta: str) -> str | None:
    pergunta_normalizada = pergunta.lower()
    for tema, palavras in _PALAVRAS_POR_TEMA.items():
        if any(palavra in pergunta_normalizada for palavra in palavras):
            return tema
    return None


def criar_vector_store(connection) -> OracleVS:
    return OracleVS(
        client=connection,
        embedding_function=criar_embeddings(),
        table_name=TABLE_NAME,
        distance_strategy=DistanceStrategy.COSINE,
    )


def buscar(pergunta: str, k: int = K) -> list[Document]:
    tema = detectar_tema(pergunta)
    filtro = {"tema": tema} if tema else None
    with conectar() as connection:
        vector_store = criar_vector_store(connection)
        return vector_store.similarity_search(pergunta, k=k, filter=filtro)


def criar_retriever(connection, k: int = K) -> VectorStoreRetriever:
    vector_store = criar_vector_store(connection)
    return vector_store.as_retriever(search_type="similarity", search_kwargs={"k": k})


if __name__ == "__main__":
    for resultado in buscar("como pedir reembolso de matrícula"):
        print(resultado.metadata["arquivo"], "->", resultado.page_content[:80])
