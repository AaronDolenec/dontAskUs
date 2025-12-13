FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --upgrade pip==25.3
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

COPY . .

# Make entrypoint executable with explicit chmod after copy
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

CMD ["bash", "./entrypoint.sh"]

