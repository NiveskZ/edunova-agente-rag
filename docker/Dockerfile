FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
# torch so roda embeddings em CPU nessa VM (A1 Flex, sem GPU); instalar antes
# via indice CPU-only evita puxar os pacotes nvidia-cu* (build com CUDA e
# imagem final saltando de ~1.5GB pra ~9GB, inviavel na VM Always Free ja
# saturada de storage).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY ingestion/ ingestion/
COPY .streamlit/ .streamlit/

EXPOSE 8501

CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
