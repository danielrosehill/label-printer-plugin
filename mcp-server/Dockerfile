FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fonts/ /app/fonts/
COPY server.py .

ENV MCP_TRANSPORT=streamable_http \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=3000

EXPOSE 3000

ENTRYPOINT ["python", "/app/server.py"]
