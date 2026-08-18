# EduNova - Agente de IA Corporativo (RAG)

Agente de IA que responde perguntas de estudantes e colaboradores da EduNova (plataforma
educacional fictícia) com base nos documentos internos da empresa, sempre citando a fonte
usada em cada resposta e admitindo quando não sabe algo, em vez de inventar.

Times de suporte recebem repetidamente as mesmas perguntas (política de reembolso, carga
horária de cursos, regras de certificado, uso da plataforma, programa de bolsas), e essas
respostas já existem espalhadas em documentos de formatos diferentes (PDF, Word, Excel,
PowerPoint, Markdown, CSV, JSON, HTML). O agente centraliza essa busca.

## Como funciona

```
Documentos (8 formatos)
        |
   Ingestão (loaders LangChain -> limpeza -> chunking -> metadados)
        |
   Embeddings (HuggingFace, multilingual-e5-small)
        |
   Oracle Database 23ai (AI Vector Search, indice HNSW)
        |
   Retrieval (similaridade + filtro por tema)
        |
   LangGraph: retrieve -> autorizar -> generate (Groq) | fallback
        |
   Interface Streamlit (chat + fontes + feedback)
```

O agente é um grafo (LangGraph) com 4 etapas:

1. **Busca**: procura, por similaridade semântica, os trechos de documentos mais relevantes
   para a pergunta no banco vetorial.
2. **Autorização**: remove da lista qualquer trecho com dado pessoal (ex.: código de
   autenticação de certificado) que não pertença ao estudante identificado na conversa.
3. **Geração**: um LLM responde usando só o que restou depois da busca e da autorização,
   citando o arquivo de origem de cada informação. Se os trechos forem pouco relacionados
   com a pergunta (ou tiverem sido todos removidos na autorização), pula direto para o
   fallback em vez de arriscar uma resposta ruim.
4. **Fallback**: resposta fixa avisando que a informação não foi encontrada nos documentos
   disponíveis, com indicação de contato com a Equipe de Sucesso do Aluno.

A interface (Streamlit) mantém o histórico da conversa na sessão, exibe as fontes de cada
resposta e permite avaliar cada resposta com 👍/👎.

## Stack utilizada

| Camada | Tecnologia |
|---|---|
| Orquestração do agente | LangChain + LangGraph |
| Loaders de documentos | LangChain Community (PDF, Word, Excel, PowerPoint, Markdown, CSV, JSON, HTML) |
| Embeddings | HuggingFace `intfloat/multilingual-e5-small` |
| Banco vetorial | Oracle Database 23ai (Autonomous Database), AI Vector Search com índice HNSW |
| LLM de geração | Groq API, modelo `openai/gpt-oss-120b` |
| Interface | Streamlit |
| Infraestrutura | Oracle Cloud Infrastructure (Always Free) |

## Como rodar localmente

Pré-requisitos: Python 3.13, uma instância Oracle Autonomous Database 23ai com wallet
extraída, e uma chave de API da Groq.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# preencher .env com as credenciais do Oracle Database e a GROQ_API_KEY
```

Processar os documentos e indexar no banco vetorial:

```bash
python -m ingestion.pipeline
python -m ingestion.index
```

Rodar a interface:

```bash
streamlit run app/streamlit_app.py
```

## Deploy na OCI

A cada push em `main`, o GitHub Actions builda a imagem (`docker/Dockerfile`) para
`linux/arm64` (arquitetura da VM A1 Flex Always Free) e publica no GHCR
(`ghcr.io/niveskz/edunova-agente-rag`). O deploy na VM é manual:

```bash
# na VM, num diretorio com docker-compose.yml, .env (permissao 600) e wallet/
docker compose pull
docker compose up -d
```

O container só serve a interface Streamlit (porta 8501); o banco vetorial já populado
(Oracle Autonomous Database) e os documentos originais (OCI Object Storage) são serviços
externos, sem custo de compute adicional. Sem domínio configurado ainda, o acesso é direto
pelo IP público da VM na porta 8501 (HTTP, sem TLS por enquanto).

## Avaliação

A qualidade da busca é medida por Recall@4 sobre um golden set de perguntas anotadas à mão,
cobrindo todos os documentos: **100% de acerto**.
