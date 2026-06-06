# ==========================================
# Stage 1: Build the Vite React Frontend
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy frontend packages and install
COPY frontend/package.json ./
RUN npm install

# Copy all frontend source files and build
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Build the Python FastAPI Backend
# ==========================================
FROM python:3.11-slim AS backend-runner
WORKDIR /app

# Install dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source
COPY backend/ ./backend

# Copy built frontend assets from Stage 1 to serve statically
COPY --from=frontend-builder /app/frontend/dist ./static

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

# Run FastAPI app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
