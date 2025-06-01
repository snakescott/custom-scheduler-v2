FROM python:3.12-slim

WORKDIR /app

# Set Python to run unbuffered
ENV PYTHONUNBUFFERED=1

# Copy only pyproject.toml for installation
COPY pyproject.toml .

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install the package
RUN pip install --no-cache-dir .

# Copy source code after installation for better caching
COPY src/ .

# Set the entrypoint
ENTRYPOINT ["python", "-m", "custom_scheduler.driver"]
