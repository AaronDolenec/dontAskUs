# Stage 1: Build admin UI
FROM node:20-alpine AS ui-builder

WORKDIR /ui

# Copy all admin-ui files first
COPY admin-ui/ ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Build
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies first
RUN apt-get update && apt-get install -y netcat-traditional curl && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (excluding files in .dockerignore)
COPY . .

# Copy built UI from stage 1
COPY --from=ui-builder /ui/dist ./admin_ui_dist

# Make entrypoint executable with explicit chmod after copy
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

CMD ["bash", "./entrypoint.sh"]

