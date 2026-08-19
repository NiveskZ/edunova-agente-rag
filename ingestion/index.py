"""Indexacao vetorial: embeda os chunks do Passo 2 e popula o Oracle Database 26ai.

Script unico e reexecutavel (ver PLANO_DESENVOLVIMENTO.md Passo 3): dropa e recria a
tabela vetorial a cada execucao. Reindexacao completa e aceitavel nesse volume de
documentos (8 arquivos), sem necessidade de logica incremental por hash.
"""

from __future__ import annotations

import os

import oracledb
from dotenv import load_dotenv
from langchain_oracledb.vectorstores.oraclevs import OracleVS, create_index, drop_table_purge
from langchain_oracledb.vectorstores.utils import DistanceStrategy

from ingestion.embeddings import criar_embeddings
from ingestion.pipeline import processar_documentos

load_dotenv()

TABLE_NAME = "edunova_chunks"
INDEX_NAME = "edunova_hnsw_idx"


def conectar() -> oracledb.Connection:
    wallet_dir = os.environ["ORACLE_WALLET_DIR"]
    return oracledb.connect(
        user=os.environ["ORACLE_DB_USER"],
        password=os.environ["ORACLE_DB_PASSWORD"],
        dsn=os.environ["ORACLE_DB_DSN"],
        config_dir=wallet_dir,
        wallet_location=wallet_dir,
        wallet_password=os.environ.get("ORACLE_WALLET_PASSWORD"),
    )


def indexar() -> None:
    documentos = processar_documentos()
    print(f"{len(documentos)} chunks para indexar.")

    embeddings = criar_embeddings()

    with conectar() as connection:
        # Precisa do mesmo quoting de identificador que o OracleVS usa
        # internamente (nome de tabela e case-sensitive, entre aspas duplas);
        # um DROP TABLE sem aspas aqui virava um no-op silencioso (Oracle
        # dobra pra maiusculo e nao acha a tabela real), acumulando linhas
        # duplicadas a cada reindexacao.
        drop_table_purge(connection, TABLE_NAME)

        vector_store = OracleVS(
            client=connection,
            embedding_function=embeddings,
            table_name=TABLE_NAME,
            distance_strategy=DistanceStrategy.COSINE,
        )
        vector_store.add_documents(documentos)

        create_index(
            client=connection,
            vector_store=vector_store,
            params={"idx_name": INDEX_NAME, "idx_type": "HNSW", "parallel": 8},
        )

    print(f"Tabela '{TABLE_NAME}' indexada, com indice HNSW '{INDEX_NAME}'.")


if __name__ == "__main__":
    indexar()
