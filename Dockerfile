FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy only the runtime sources needed to build and run Praxis.
COPY pyproject.toml README.md openenv.yaml LICENSE-3rd-party /app/
COPY praxis_env /app/praxis_env
COPY server /app/server
COPY data /app/data
COPY inference.py /app/inference.py

RUN pip install --upgrade pip && pip install .

ENV HOST=0.0.0.0 \
    PORT=7860 \
    LOG_LEVEL=INFO

EXPOSE 7860

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
