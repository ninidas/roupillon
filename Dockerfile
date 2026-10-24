# Écrans React compilés, puis servis par le serveur FastAPI : une seule image
FROM node:20-alpine AS front
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /backend
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt
COPY backend/app/ ./app/
COPY backend/tests/ ./tests/
COPY backend/pytest.ini .
COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY --from=front /app/dist ./frontend_dist
ENV TZ=Europe/Paris APP_TZ=Europe/Paris
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
