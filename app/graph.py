"""Grafo LangGraph de geracao e validacao de respostas (Passo 5).

3 nos: `retrieve` -> `generate` | `fallback`, roteados por um limiar de
distancia cosseno sobre o melhor resultado recuperado. Sem no extra de
grounding check pos-geracao: o prompt (citar `arquivo`, admitir
desconhecimento) + o limiar abaixo cobrem o essencial sem mais uma chamada
de LLM por pergunta.
"""

from __future__ import annotations

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


class EstadoGrafo(TypedDict):
    pergunta: str
    documentos: list[Document]
    melhor_distancia: float
    resposta: str
    fontes: list[str]


def _formatar_contexto(documentos: list[Document]) -> str:
    return "\n\n".join(
        f"[{doc.metadata.get('arquivo')}] {doc.page_content}" for doc in documentos
    )


def retrieve(estado: EstadoGrafo) -> dict:
    resultados = buscar_com_score(estado["pergunta"])
    documentos = [doc for doc, _ in resultados]
    melhor_distancia = min((score for _, score in resultados), default=1.0)
    return {"documentos": documentos, "melhor_distancia": melhor_distancia}


def rotear_apos_retrieve(estado: EstadoGrafo) -> str:
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
    grafo.add_node("generate", generate)
    grafo.add_node("fallback", fallback)

    grafo.add_edge(START, "retrieve")
    grafo.add_conditional_edges(
        "retrieve",
        rotear_apos_retrieve,
        {"generate": "generate", "fallback": "fallback"},
    )
    grafo.add_edge("generate", END)
    grafo.add_edge("fallback", END)

    return grafo.compile()


if __name__ == "__main__":
    app = criar_grafo()
    perguntas = [
        "Quantos dias tenho para pedir reembolso integral da matrícula?",
        "Qual a carga horária do curso de Inglês para Negócios?",
        "Posso compartilhar meu login com outra pessoa?",
        "Qual o código de autenticação do certificado da Ana Beatriz Souza?",
        "Qual a capital da França?",
    ]
    for pergunta in perguntas:
        resultado = app.invoke({"pergunta": pergunta})
        print("Pergunta:", pergunta)
        print("Resposta:", resultado["resposta"])
        print("Fontes:", resultado["fontes"])
        print("-" * 60)
