# Imagem para servidor (Fase 4). Localmente use iniciar.bat.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DADOS_DIR=/dados MODO_AUTH=plataforma HOST=0.0.0.0 PORT=8000

WORKDIR /app
COPY requirements.txt requirements-servidor.txt ./
RUN pip install --no-cache-dir -r requirements-servidor.txt

COPY . .
RUN useradd --create-home faturamento && mkdir -p /dados && chown faturamento /dados
USER faturamento
VOLUME ["/dados"]
EXPOSE 8000

# Um processo: as migrações rodam ao subir. As telas (web/out) já vêm compiladas no repositório.
CMD ["uvicorn", "servidor:criar_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
