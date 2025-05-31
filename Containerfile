FROM python:3.9-slim

WORKDIR /app

# Set Python to run unbuffered
ENV PYTHONUNBUFFERED=1

# Copy project files
COPY pyproject.toml .

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies in virtual environment
RUN pip install --no-cache-dir .

# Copy source last to get better caching perf
COPY src/ src/

# Set the entrypoint
ENTRYPOINT ["python", "-m", "custom_scheduler.main"] 