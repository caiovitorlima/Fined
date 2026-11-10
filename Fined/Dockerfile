FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements-prod.txt ./
RUN python -m pip install --no-cache-dir -r requirements-prod.txt
COPY app ./app
COPY deploy/supabase-ca.crt /certs/supabase-ca.crt

USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--workers=1", "--threads=2", "--timeout=30", "--worker-tmp-dir=/tmp", "--forwarded-allow-ips=", "app:create_app()"]
