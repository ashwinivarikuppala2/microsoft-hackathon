FROM node:22-slim AS frontend-build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
RUN npm run build

FROM python:3.12-slim AS app

WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY dealmind ./dealmind
COPY --from=frontend-build /app/web-dist ./web-dist

EXPOSE 10000
CMD ["sh", "-c", "uvicorn dealmind.api:app --host 0.0.0.0 --port ${PORT:-10000}"]