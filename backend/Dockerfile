# Stage 1: Build admin UI
FROM node:20-alpine AS ui-builder

WORKDIR /ui
COPY admin-ui/package.json admin-ui/package-lock.json* admin-ui/yarn.lock* ./
RUN npm install 2>/dev/null || yarn install

COPY admin-ui .
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade pip==25.3
RUN apt-get update && apt-get install -y netcat-traditional curl && rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY . .

# Copy built UI from stage 1
COPY --from=ui-builder /ui/dist ./admin_ui_dist

# Make entrypoint executable with explicit chmod after copy
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

CMD ["bash", "./entrypoint.sh"]

