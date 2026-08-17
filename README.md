# EduNova - Agente de IA Corporativo (RAG)

Agente de IA que responde perguntas de estudantes/colaboradores com base em documentos
internos de uma plataforma educacional fictícia, a EduNova, sempre citando a fonte usada
na resposta. Projeto desenvolvido para o desafio Alura "Agentes".

## O problema

Times de suporte e sucesso do aluno recebem repetidamente as mesmas perguntas (política de
reembolso, carga horária de cursos, regras de certificado, uso da plataforma, programa de
bolsas). Esses documentos existem, mas estão espalhados em formatos diferentes (PDF, Word,
Excel, PowerPoint, Markdown, CSV, JSON, HTML) e ninguém quer procurar manualmente. O agente
busca a resposta nesses documentos e responde citando de onde tirou a informação, admitindo
quando não sabe em vez de inventar.

## Arquitetura

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
   LangGraph: retrieve -> generate (Groq) | fallback
        |
   Interface Streamlit (chat + fontes + feedback)
```

Grafo do agente (LangGraph), 3 nós:
1. `retrieve`: busca por similaridade no Oracle Database 23ai.
2. `generate`: LLM (Groq) responde só com base no contexto recuperado, citando o arquivo de
   origem. Antes de gerar, checa um limiar de similaridade; se o melhor resultado for pouco
   relacionado com a pergunta, pula direto pro fallback.
3. `fallback`: resposta fixa avisando que a informação não foi encontrada, sugerindo contato
   com a Equipe de Sucesso do Aluno.

## Stack utilizada

| Camada | Tecnologia |
|---|---|
| Orquestração do agente | LangChain + LangGraph |
| Loaders de documentos | LangChain Community (PDF, Word, Excel, PowerPoint, Markdown, CSV, JSON, HTML) |
| Embeddings | HuggingFace `intfloat/multilingual-e5-small` (local, sem custo de API) |
| Banco vetorial | Oracle Database 23ai (Autonomous Database, Always Free) via `langchain-oracledb`, distância cosseno, índice HNSW |
| LLM de geração | Groq API (`langchain-groq`), modelo `openai/gpt-oss-120b` |
| Interface | Streamlit |
| Avaliação de retrieval | Script próprio de Recall@k sobre golden set anotado à mão |
| Infraestrutura (planejada) | Oracle Cloud Infrastructure (Always Free): Autonomous Database, Object Storage, VM A1 Flex já existente |

## Estrutura do repositório

```
app/         agente (grafo LangGraph, retriever, interface Streamlit)
ingestion/   pipeline de ingestão (loaders, chunking) e indexação vetorial
eval/        golden set e script de avaliação de Recall@k
docs/        catálogo de documentos e cópia local dos documentos fictícios
docker/      Dockerfile / docker-compose (deploy, próximo passo)
logs/        log JSONL de interações (gerado em runtime, não versionado)
```

## Como rodar localmente

Pré-requisitos: Python 3.13, uma instância Oracle Autonomous Database 23ai (Always Free)
com wallet extraída, uma chave de API da Groq.

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

## Avaliação

`eval/avaliacao_retrieval.py` mede Recall@4 sobre um golden set de 12 perguntas anotadas à
mão (uma ou mais por documento). Resultado atual: **Recall@4: 100% (12/12)**.

```bash
python -m eval.avaliacao_retrieval
```

## Status do projeto

Concluído até aqui: ingestão e chunking dos 8 documentos, indexação vetorial no Oracle
Database 23ai, camada de recuperação com filtro por tema, grafo de geração com fallback via
LangGraph, e interface Streamlit com histórico de conversa e feedback.

Em aberto:
- **Deploy na OCI**: containerização e publicação na VM A1 Flex já existente (Always Free).
- **Autenticação do estudante**: hoje qualquer pessoa que pergunte pelo certificado de outra
  pessoa recebe a resposta (ex.: código de autenticação de certificado de um estudante
  específico), sem verificar se quem pergunta é o próprio dono do dado. É a única informação
  pessoal identificável do corpus atual e precisa de um controle de acesso antes do agente
  ficar acessível publicamente.
- **Log estruturado completo**: hoje o log de interações grava pergunta, resposta, fontes e
  feedback; falta registrar os chunks recuperados e a latência de cada resposta.

## Limitações conhecidas

- Sem reranker: a busca usa similaridade simples (top-k), sem uma segunda etapa de
  reordenação dos resultados.
- Sem verificação de grounding pós-geração: a citação de fonte depende do prompt do LLM, não
  há uma checagem automática posterior de que a resposta realmente veio do contexto.
- Corpus pequeno (8 documentos fictícios), criado para fins de demonstração do desafio.
