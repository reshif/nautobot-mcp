FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV NAUTOBOT_MCP_TRANSPORT=streamable-http \
    NAUTOBOT_MCP_HOST=0.0.0.0 \
    NAUTOBOT_MCP_PORT=8000 \
    NAUTOBOT_MCP_STREAMABLE_HTTP_PATH=/mcp
EXPOSE 8000
# Provide NAUTOBOT_URL + NAUTOBOT_TOKEN at run time (never bake secrets in).
CMD ["nautobot-mcp"]
