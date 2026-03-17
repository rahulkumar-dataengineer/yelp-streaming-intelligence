FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (only what the API needs)
COPY config/ config/
COPY agents/ agents/
COPY utils/ utils/
COPY graph.py .
COPY api.py .

EXPOSE 5001

CMD ["python", "api.py"]
