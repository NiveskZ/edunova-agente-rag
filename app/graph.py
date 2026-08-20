"""Grafo LangGraph de geracao e validacao de respostas (Passo 5 + Passo 7 + Passo 8).

6 nos: `retrieve` -> `autorizar` -> `personalizar_reembolso` -> `generate` |
`fallback` | `fallback_privacidade`, roteados por um limiar de distancia
cosseno sobre o melhor resultado recuperado (apos o filtro de autorizacao).
Sem no extra de grounding check pos-geracao: o prompt (citar `arquivo`,
admitir desconhecimento) + o limiar abaixo cobrem o essencial sem mais uma
chamada de LLM por pergunta.

O no `autorizar` existe por causa da pendencia registrada no Passo 6:
`certificados_emitidos.csv` (e, desde o Passo 8, `matriculas_alunos.csv`)
sao os documentos do corpus com dado pessoal identificavel. Sem esse no,
qualquer pessoa podia pedir o dado de outro estudante e o agente respondia
normalmente.

O no `personalizar_reembolso` calcula deterministicamente (nunca deixando o
LLM calcular datas sozinho, o que arrisca alucinacao) a banda de reembolso
aplicavel a um estudante identificado especifico, a partir do registro dele
em `matriculas_alunos.csv`. Sem isso, o agente so citava as regras gerais da
politica, o que podia induzir a erro um aluno perto do prazo (ex.: dizer
"ate 7 dias" pra quem ja passou desse prazo).
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from functools import lru_cache
from typing import TypedDict

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph

from app.retriever import buscar_com_score, buscar_registros_arquivo

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

RESPOSTA_FALLBACK_PRIVACIDADE = (
    "Essa informação é pessoal e só é liberada para o próprio estudante. "
    "Confira se o campo \"Seu nome completo\" acima está preenchido com o "
    "nome exato do cadastro e repita a pergunta."
)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Você é o assistente de suporte da EduNova. Responda a pergunta do "
            "estudante usando apenas as informações do CONTEXTO abaixo. Cite o "
            "arquivo de origem (entre colchetes antes de cada trecho) de cada "
            "informação que usar na resposta, exceto o trecho marcado como "
            "'[cálculo específico para este estudante]': esse já é a conclusão "
            "aplicável a esse aluno em particular, apresente-a diretamente, sem "
            "citar arquivo. Se o contexto não tiver a resposta, diga claramente "
            "que não encontrou a informação nos documentos disponíveis, sem "
            "inventar.\n\nCONTEXTO:\n{contexto}",
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
    bloqueado_por_privacidade: bool
    fato_personalizado: str | None
    resposta: str
    fontes: list[str]


@lru_cache(maxsize=1)
def _obter_llm() -> ChatGroq:
    return ChatGroq(model=MODELO_LLM, temperature=0)


def _formatar_contexto(documentos: list[Document], fato_personalizado: str | None) -> str:
    partes = [
        f"[{doc.metadata.get('arquivo')}] {doc.page_content}" for doc in documentos
    ]
    if fato_personalizado:
        partes.insert(0, f"[cálculo específico para este estudante] {fato_personalizado}")
    return "\n\n".join(partes)


def _normalizar_nome(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def _dias_desde(data_str: str) -> int:
    data_matricula = datetime.strptime(data_str, "%Y-%m-%d").date()
    return (date.today() - data_matricula).days


def _classificar_reembolso(dias: int, percentual_concluido: float) -> str:
    """Aplica a Politica de Reembolso de Matriculas (banda de dias corridos
    desde a compra, depois banda de percentual do curso concluido) e
    devolve o texto explicativo ja com a conclusao para o LLM usar."""
    if dias <= 7:
        return (
            f"comprou há {dias} dia(s), dentro dos 7 dias corridos de direito de "
            "arrependimento: reembolso integral (100%), independentemente do "
            "quanto do curso já foi acessado."
        )
    if percentual_concluido < 25:
        return (
            f"comprou há {dias} dia(s) (fora dos 7 dias) e concluiu "
            f"{percentual_concluido:.0f}% do curso (abaixo de 25%): direito a "
            "reembolso de 50%, descontada a taxa de processamento de pagamento."
        )
    return (
        f"comprou há {dias} dia(s) e já concluiu {percentual_concluido:.0f}% do "
        "curso (25% ou mais): sem direito a reembolso, salvo comprovado "
        "problema técnico da plataforma, mediante análise da Equipe de Sucesso "
        "do Aluno."
    )


def retrieve(estado: EstadoGrafo) -> dict:
    resultados = buscar_com_score(estado["pergunta"])
    return {"resultados": resultados}


def autorizar(estado: EstadoGrafo) -> dict:
    """Remove chunks com dado pessoal (metadata `dono`) que nao pertencem ao
    estudante identificado. Sem identificacao, todo chunk com `dono` e
    removido (dado pessoal so e liberado pro proprio dono, nunca por
    padrao). Registra tambem se algum chunk relevante foi removido por
    privacidade, pra rotear pra uma mensagem especifica em vez do fallback
    generico."""
    identificado = _normalizar_nome(estado.get("estudante_identificado") or "")
    autorizados = []
    bloqueados = []
    for doc, score in estado["resultados"]:
        dono = doc.metadata.get("dono")
        if not dono or _normalizar_nome(dono) == identificado:
            autorizados.append((doc, score))
        else:
            bloqueados.append((doc, score))

    documentos = [doc for doc, _ in autorizados]
    melhor_distancia = min((score for _, score in autorizados), default=1.0)
    melhor_distancia_bloqueada = min((score for _, score in bloqueados), default=1.0)
    return {
        "documentos": documentos,
        "melhor_distancia": melhor_distancia,
        "bloqueado_por_privacidade": bool(bloqueados)
        and melhor_distancia_bloqueada <= LIMIAR_DISTANCIA,
    }


def personalizar_reembolso(estado: EstadoGrafo) -> dict:
    """No opcional: so age quando a pergunta menciona reembolso e o
    estudante esta identificado. Busca o registro de matricula dele (lookup
    exato por `dono`, nao por relevancia semantica) e calcula a banda de
    reembolso aplicavel com data real, em vez de deixar o LLM estimar."""
    pergunta = estado["pergunta"].lower()
    identificado = estado.get("estudante_identificado")
    if "reembolso" not in pergunta or not identificado:
        return {"fato_personalizado": None}

    identificado_norm = _normalizar_nome(identificado)
    registros = buscar_registros_arquivo("matriculas_alunos.csv")
    registro = next(
        (
            doc
            for doc in registros
            if _normalizar_nome(doc.metadata.get("dono", "")) == identificado_norm
        ),
        None,
    )
    if registro is None:
        return {"fato_personalizado": None}

    dias = _dias_desde(registro.metadata["data_matricula"])
    percentual = float(registro.metadata["percentual_concluido"])
    explicacao = _classificar_reembolso(dias, percentual)
    fato = f"Para {identificado}: {explicacao}"
    return {"fato_personalizado": fato}


def rotear_apos_autorizar(estado: EstadoGrafo) -> str:
    if estado["documentos"] and estado["melhor_distancia"] <= LIMIAR_DISTANCIA:
        return "generate"
    if estado.get("bloqueado_por_privacidade"):
        return "fallback_privacidade"
    return "fallback"


def generate(estado: EstadoGrafo) -> dict:
    llm = _obter_llm()
    contexto = _formatar_contexto(estado["documentos"], estado.get("fato_personalizado"))
    mensagem = _PROMPT.invoke({"contexto": contexto, "pergunta": estado["pergunta"]})
    resposta = llm.invoke(mensagem)
    fontes = sorted({doc.metadata.get("arquivo") for doc in estado["documentos"]})
    return {"resposta": resposta.content, "fontes": fontes}


def fallback(estado: EstadoGrafo) -> dict:
    return {"resposta": RESPOSTA_FALLBACK, "fontes": []}


def fallback_privacidade(estado: EstadoGrafo) -> dict:
    return {"resposta": RESPOSTA_FALLBACK_PRIVACIDADE, "fontes": []}


def criar_grafo():
    grafo = StateGraph(EstadoGrafo)
    grafo.add_node("retrieve", retrieve)
    grafo.add_node("autorizar", autorizar)
    grafo.add_node("personalizar_reembolso", personalizar_reembolso)
    grafo.add_node("generate", generate)
    grafo.add_node("fallback", fallback)
    grafo.add_node("fallback_privacidade", fallback_privacidade)

    grafo.add_edge(START, "retrieve")
    grafo.add_edge("retrieve", "autorizar")
    grafo.add_edge("autorizar", "personalizar_reembolso")
    grafo.add_conditional_edges(
        "personalizar_reembolso",
        rotear_apos_autorizar,
        {
            "generate": "generate",
            "fallback": "fallback",
            "fallback_privacidade": "fallback_privacidade",
        },
    )
    grafo.add_edge("generate", END)
    grafo.add_edge("fallback", END)
    grafo.add_edge("fallback_privacidade", END)

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
        # Personalizacao do reembolso (Passo 8): mesma pergunta, 3 alunos em
        # bandas diferentes da politica + 1 caso sem identificacao.
        ("Ainda tenho direito a reembolso da minha matrícula?", None),
        ("Ainda tenho direito a reembolso da minha matrícula?", "Bruna Andrade Lima"),
        ("Ainda tenho direito a reembolso da minha matrícula?", "Rafael Souza Lima"),
        ("Ainda tenho direito a reembolso da minha matrícula?", "Diego Martins Rocha"),
        ("Ainda tenho direito a reembolso da minha matrícula?", "Camila Nogueira Prado"),
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
