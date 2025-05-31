# Custom Scheduler

A simple Python project that demonstrates containerization and Kubernetes integration.

## Development

### Prerequisites

- Python 3.9 or higher
- Container runtime (e.g., Docker, Podman)
- Either:
  - pip (for traditional Python package management)
  - uv (recommended, for faster package management)

### Setup

#### Using uv (Recommended)

1. Install uv if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Install dependencies:
```bash
uv sync
```

3. Run tests:
```bash
uv run pytest
```

#### Using pip

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Unix/macOS
# or
.\venv\Scripts\activate  # On Windows
```

2. Install dependencies:
```bash
pip install -e ".[test]"
```

3. Run tests:
```bash
pytest
```

### Building and Running the Container

Build the container:
```bash
podman build -t custom-scheduler -f Containerfile .
```

Run the container:
```bash
podman run custom-scheduler
```

## Project Structure

- `src/main.py`: Main application code
- `tests/`: Test files
- `pyproject.toml`: Project configuration and dependencies
- `requirements.txt`: Main dependencies for uv
- `requirements-test.txt`: Test dependencies for uv
- `Containerfile`: Container definition 