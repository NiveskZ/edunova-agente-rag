"""Interface Streamlit do agente EduNova (Passo 6).

Campo de pergunta + historico de conversa na sessao, aviso fixo de agente de
IA, fontes citadas por resposta e feedback (like/dislike) gravado em log.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# Streamlit executa o script com o diretorio `app/` no sys.path (nao a raiz
# do projeto), entao o pacote `app` precisa ser exposto manualmente aqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import criar_grafo  # noqa: E402

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "interacoes.jsonl"

st.set_page_config(page_title="EduNova - Assistente Virtual", page_icon="🎓")


@st.cache_resource
def carregar_grafo():
    return criar_grafo()


def registrar_interacao(pergunta: str, resposta: str, fontes: list[str], feedback: str | None) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    registro = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pergunta": pergunta,
        "resposta": resposta,
        "fontes": fontes,
        "feedback": feedback,
    }
    with LOG_PATH.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


def registrar_feedback(indice: int, feedback: str) -> None:
    mensagem = st.session_state.historico[indice]
    mensagem["feedback"] = feedback
    registrar_interacao(mensagem["pergunta"], mensagem["resposta"], mensagem["fontes"], feedback)


st.title("🎓 Assistente Virtual EduNova")
st.info(
    "Este é um agente de IA. As respostas são geradas automaticamente com base "
    "nos documentos internos da EduNova e podem conter imprecisões.",
    icon="🤖",
)

nome_estudante = st.text_input(
    "Seu nome completo (opcional, necessário só para consultar dados do seu "
    "próprio certificado)",
    key="nome_estudante",
)

if "historico" not in st.session_state:
    st.session_state.historico = []

for indice, mensagem in enumerate(st.session_state.historico):
    with st.chat_message("user"):
        st.write(mensagem["pergunta"])
    with st.chat_message("assistant"):
        st.write(mensagem["resposta"])
        if mensagem["fontes"]:
            st.caption("Fontes: " + ", ".join(mensagem["fontes"]))
        col_like, col_dislike, _ = st.columns([1, 1, 8])
        feedback_atual = mensagem["feedback"]
        with col_like:
            if st.button("👍", key=f"like_{indice}", disabled=feedback_atual is not None):
                registrar_feedback(indice, "positivo")
                st.rerun()
        with col_dislike:
            if st.button("👎", key=f"dislike_{indice}", disabled=feedback_atual is not None):
                registrar_feedback(indice, "negativo")
                st.rerun()
        if feedback_atual is not None:
            st.caption("Feedback registrado: " + ("👍" if feedback_atual == "positivo" else "👎"))

pergunta = st.chat_input("Digite sua pergunta sobre a EduNova...")
if pergunta:
    with st.chat_message("user"):
        st.write(pergunta)
    with st.chat_message("assistant"), st.spinner("Consultando os documentos..."):
        grafo = carregar_grafo()
        resultado = grafo.invoke(
            {"pergunta": pergunta, "estudante_identificado": nome_estudante or None}
        )
        resposta = resultado["resposta"]
        fontes = resultado["fontes"]
        st.write(resposta)
        if fontes:
            st.caption("Fontes: " + ", ".join(fontes))

    st.session_state.historico.append(
        {"pergunta": pergunta, "resposta": resposta, "fontes": fontes, "feedback": None}
    )
    registrar_interacao(pergunta, resposta, fontes, None)
    st.rerun()
