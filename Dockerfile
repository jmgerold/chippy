FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
# Provide an empty patents dir so the container still starts if host volume missing
RUN mkdir -p /app/patents
# Expose files in /frontend as static assets via FastAPI
ENV PYTHONPATH="/app"

# at top, after your existing ENVs
ENV XML_STORE_DIR=/app/patents \
    MAX_TABLES_PER_FILE=10 \
    MAX_WORKERS=8


CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]