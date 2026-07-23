FROM python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /opt/faultwitness
COPY deploy/control-api/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps . && \
    useradd --system --uid 10001 --no-create-home faultwitness
USER 10001:10001
EXPOSE 8001
CMD ["uvicorn", "faultwitness.observability.server:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
