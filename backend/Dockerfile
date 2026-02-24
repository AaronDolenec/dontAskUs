
# Stage 1: Build admin UI
FROM node:20-alpine AS ui-builder

WORKDIR /ui


# Copy only package files first for better cache
COPY admin-ui/package.json admin-ui/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm npm install --legacy-peer-deps

# Copy rest of admin-ui source
COPY admin-ui/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies first
RUN apt-get update && apt-get install -y netcat-traditional curl && rm -rf /var/lib/apt/lists/*


# Copy and install Python dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# Copy backend code (excluding files in .dockerignore)
COPY . .

# Copy built UI from stage 1
COPY --from=ui-builder /ui/dist ./admin_ui_dist

# Make entrypoint executable with explicit chmod after copy
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

CMD ["bash", "./entrypoint.sh"]

