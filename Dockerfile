FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY support_app/ support_app/

USER 10001:10001
EXPOSE 8767
CMD ["uvicorn", "support_app.app:deployment_app", "--factory", "--host", "0.0.0.0", "--port", "8767", "--no-access-log"]
