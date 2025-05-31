FROM python:3.9-slim

WORKDIR /app

# Set Python to run unbuffered
ENV PYTHONUNBUFFERED=1

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN pip install --no-cache-dir .

# Set the entrypoint
ENTRYPOINT ["python", "-m", "src.main"] 