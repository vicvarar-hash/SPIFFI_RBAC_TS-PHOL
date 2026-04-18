FROM python:3.10-slim

WORKDIR /app

# System dependencies for gRPC or other python packages if needed
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "streamlit run main.py --server.port $PORT --server.address 0.0.0.0"]
