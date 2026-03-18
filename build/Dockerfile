FROM python:3.11-slim

WORKDIR /app

# Install platform-commons from pre-built wheel (private repo — can't pip install from git in Docker)
COPY build/wheels/ /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels/

# Install remaining dependencies
COPY requirements.txt .
RUN grep -v "portfolio-platform-commons" requirements.txt > requirements-docker.txt \
    && pip install --no-cache-dir -r requirements-docker.txt \
    && rm requirements-docker.txt

# Copy application code (only what the API needs)
COPY config/ config/
COPY agents/ agents/
COPY utils/ utils/
COPY graph.py .
COPY api.py .

EXPOSE 5001

CMD ["python", "api.py"]
