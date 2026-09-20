FROM python:3.12-slim

WORKDIR /srv
COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

COPY app app
COPY data data

ENV PORT=8000
EXPOSE 8000
# The graph is built once at startup (engine.warm), so keep a single worker.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
