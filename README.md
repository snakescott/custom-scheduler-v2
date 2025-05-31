# Custom Scheduler

A simple Python project that demonstrates containerization and Kubernetes integration.

## Development

### Prerequisites

- Python 3.9 or higher
- pip
- Container runtime (e.g., Docker, Podman)

### Setup

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

### Running Tests

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
- `Containerfile`: Container definition 