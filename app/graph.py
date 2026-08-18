"""Grafo LangGraph de geracao e validacao de respostas (Passo 5 + Passo 7).

4 nos: `retrieve` -> `autorizar` -> `generate` | `fallback`, roteados por um
limiar de distancia cosseno sobre o melhor resultado recuperado (apos o
filtro de autorizacao). Sem no extra de grounding check pos-geracao: o
prompt (citar `arquivo`, admitir desconhecimento) + o limiar abaixo cobrem
o essencial sem mais uma chamada de LLM por pergunta.

O no `autorizar` existe por causa da pendencia registrada no Passo 6:
`certificados_emitidos.csv` e o unico documento do corpus com dado pessoal
identificavel (nome + codigo de autenticacao). Sem esse no, qualquer pessoa
podia pedir o codigo de autenticacao de outro estudante e o agente
respondia normalmente.
"""

from __future__ import annotations

import unicodedata
from typing import TypedDict

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph

from app.retriever import buscar_com_score

load_dotenv()

MODELO_LLM = "openai/gpt-oss-120b"

# Distancia cosseno acima disso (documentos pouco relacionados com a
# pergunta) pula direto pro fallback. Calibrado com o golden_set do Passo 4:
# pior caso dentro do escopo ~0.18, melhor caso fora do escopo ~0.20.
LIMIAR_DISTANCIA = 0.18

RESPOSTA_FALLBACK = (
    "Não encontrei essa informação nos documentos disponíveis. "
    "Recomendo entrar em contato com a Equipe de Sucesso do Aluno."
)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Você é o assistente de suporte da EduNova. Responda a pergunta do "
            "estudante usando apenas as informações do CONTEXTO abaixo. Cite o "
            "arquivo de origem (entre colchetes antes de cada trecho) de cada "
            "informação que usar na resposta. Se o contexto não tiver a "
            "resposta, diga claramente que não encontrou a informação nos "
            "documentos disponíveis, sem inventar.\n\nCONTEXTO:\n{contexto}",
        ),
        ("human", "{pergunta}"),
    ]
)


class EstadoGrafo(TypedDict, total=False):
    pergunta: str
    estudante_identificado: str | None
    resultados: list[tuple[Document, float]]
    documentos: list[Document]
    melhor_distancia: float
    resposta: str
    fontes: list[str]


def _formatar_contexto(documentos: list[Document]) -> str:
    return "\n\n".join(
        f"[{doc.metadata.get('arquivo')}] {doc.page_content}" for doc in documentos
    )


def _normalizar_nome(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def retrieve(estado: EstadoGrafo) -> dict:
    resultados = buscar_com_score(estado["pergunta"])
    return {"resultados": resultados}


def autorizar(estado: EstadoGrafo) -> dict:
    """Remove chunks com dado pessoal (metadata `dono`) que nao pertencem ao
    estudante identificado. Sem identificacao, todo chunk com `dono` e
    removido (dado pessoal so e liberado pro proprio dono, nunca por
    padrao)."""
    identificado = _normalizar_nome(estado.get("estudante_identificado") or "")
    resultados_autorizados = [
        (doc, score)
        for doc, score in estado["resultados"]
        if not doc.metadata.get("dono") or _normalizar_nome(doc.metadata["dono"]) == identificado
    ]
    documentos = [doc for doc, _ in resultados_autorizados]
    melhor_distancia = min((score for _, score in resultados_autorizados), default=1.0)
    return {"documentos": documentos, "melhor_distancia": melhor_distancia}


def rotear_apos_autorizar(estado: EstadoGrafo) -> str:
    if not estado["documentos"] or estado["melhor_distancia"] > LIMIAR_DISTANCIA:
        return "fallback"
    return "generate"


def generate(estado: EstadoGrafo) -> dict:
    llm = ChatGroq(model=MODELO_LLM, temperature=0)
    contexto = _formatar_contexto(estado["documentos"])
    mensagem = _PROMPT.invoke({"contexto": contexto, "pergunta": estado["pergunta"]})
    resposta = llm.invoke(mensagem)
    fontes = sorted({doc.metadata.get("arquivo") for doc in estado["documentos"]})
    return {"resposta": resposta.content, "fontes": fontes}


def fallback(estado: EstadoGrafo) -> dict:
    return {"resposta": RESPOSTA_FALLBACK, "fontes": []}


def criar_grafo():
    grafo = StateGraph(EstadoGrafo)
    grafo.add_node("retrieve", retrieve)
    grafo.add_node("autorizar", autorizar)
    grafo.add_node("generate", generate)
    grafo.add_node("fallback", fallback)

    grafo.add_edge(START, "retrieve")
    grafo.add_edge("retrieve", "autorizar")
    grafo.add_conditional_edges(
        "autorizar",
        rotear_apos_autorizar,
        {"generate": "generate", "fallback": "fallback"},
    )
    grafo.add_edge("generate", END)
    grafo.add_edge("fallback", END)

    return grafo.compile()


if __name__ == "__main__":
    app = criar_grafo()
    casos = [
        ("Quantos dias tenho para pedir reembolso integral da matrícula?", None),
        ("Qual a carga horária do curso de Inglês para Negócios?", None),
        ("Posso compartilhar meu login com outra pessoa?", None),
        ("Qual o código de autenticação do certificado da Ana Beatriz Souza?", None),
        ("Qual o código de autenticação do certificado da Ana Beatriz Souza?", "Ana Beatriz Souza"),
        ("Qual a capital da França?", None),
    ]
    for pergunta, estudante_identificado in casos:
        resultado = app.invoke(
            {"pergunta": pergunta, "estudante_identificado": estudante_identificado}
        )
        print("Pergunta:", pergunta)
        print("Identificado como:", estudante_identificado)
        print("Resposta:", resultado["resposta"])
        print("Fontes:", resultado["fontes"])
        print("-" * 60)
