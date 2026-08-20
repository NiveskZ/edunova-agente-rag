"""Interface Streamlit do agente EduNova (Passo 6 + Passo 8).

Campo de pergunta + historico de conversa na sessao, aviso fixo de agente de
IA, fontes citadas por resposta e feedback (like/dislike) gravado em log.

O registro de execucao de cada interacao (Passo 8) fica em `app/registro.py`.

Limite de perguntas por sessao (Passo 8): controle minimo de uso, protege a
cota da Groq e a VM de um unico usuario abrindo muitas perguntas seguidas.
Conta por `st.session_state` (reseta ao abrir o link numa aba nova; um F5 na
mesma aba normalmente mantem a sessao do Streamlit, entao nao reseta so com
isso).
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import streamlit as st

# Streamlit executa o script com o diretorio `app/` no sys.path (nao a raiz
# do projeto), entao o pacote `app` precisa ser exposto manualmente aqui.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import criar_grafo  # noqa: E402
from app.registro import registrar_feedback, registrar_resposta  # noqa: E402

st.set_page_config(page_title="EduNova - Assistente Virtual", page_icon="🎓")

LIMITE_PERGUNTAS_SESSAO = 15


@st.cache_resource
def carregar_grafo():
    return criar_grafo()


def votar(indice: int, feedback: str) -> None:
    mensagem = st.session_state.historico[indice]
    mensagem["feedback"] = feedback
    registrar_feedback(mensagem["id"], mensagem["pergunta"], feedback)


st.title("🎓 Assistente Virtual EduNova")
st.info(
    "Este é um agente de IA. As respostas são geradas automaticamente com base "
    "nos documentos internos da EduNova e podem conter imprecisões.",
    icon="🤖",
)

nome_estudante = st.text_input(
    "Seu nome completo (opcional, necessário só para consultar dados do seu "
    "próprio certificado ou matrícula)",
    key="nome_estudante",
)
if nome_estudante:
    st.success(f"✅ Identificado como **{nome_estudante}**")

if "historico" not in st.session_state:
    st.session_state.historico = []
if "contador_perguntas" not in st.session_state:
    st.session_state.contador_perguntas = 0

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
                votar(indice, "positivo")
                st.rerun()
        with col_dislike:
            if st.button("👎", key=f"dislike_{indice}", disabled=feedback_atual is not None):
                votar(indice, "negativo")
                st.rerun()
        if feedback_atual is not None:
            st.caption("Feedback registrado: " + ("👍" if feedback_atual == "positivo" else "👎"))

limite_atingido = st.session_state.contador_perguntas >= LIMITE_PERGUNTAS_SESSAO
if limite_atingido:
    st.warning(
        f"Você atingiu o limite de {LIMITE_PERGUNTAS_SESSAO} perguntas desta "
        "sessão. Abra o link em uma nova aba para continuar."
    )

pergunta = st.chat_input(
    "Digite sua pergunta sobre a EduNova...", disabled=limite_atingido
)
if pergunta and not limite_atingido:
    with st.chat_message("user"):
        st.write(pergunta)
    with st.chat_message("assistant"), st.spinner("Consultando os documentos..."):
        grafo = carregar_grafo()
        inicio = time.perf_counter()
        resultado = grafo.invoke(
            {"pergunta": pergunta, "estudante_identificado": nome_estudante or None}
        )
        latencia_s = time.perf_counter() - inicio
        resposta = resultado["resposta"]
        fontes = resultado["fontes"]
        st.write(resposta)
        if fontes:
            st.caption("Fontes: " + ", ".join(fontes))

    st.session_state.contador_perguntas += 1
    interacao_id = str(uuid.uuid4())
    st.session_state.historico.append(
        {
            "id": interacao_id,
            "pergunta": pergunta,
            "resposta": resposta,
            "fontes": fontes,
            "feedback": None,
        }
    )
    registrar_resposta(
        interacao_id, pergunta, nome_estudante or None, resultado, latencia_s
    )
    st.rerun()
