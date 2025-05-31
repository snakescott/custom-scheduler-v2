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
# Install main dependencies
uv pip install -e .

# Install development dependencies (including pytest)
uv pip install -e ".[dev]"
```

3. Run tests:
```bash
# Run all tests
uv run pytest

# Run only unit tests
uv run pytest -m unit

# Run only system tests
uv run pytest -m system
```

4. Run linting and formatting:
```bash
# Run ruff linter
uv run ruff check .

# Run ruff formatter
uv run ruff format .
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
pip install -e ".[dev]"
```

3. Run tests and linting (same commands as above, but without `uv run`)

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

## Development Tools

The project uses several development tools configured in `pyproject.toml`:

- **pytest**: Testing framework with markers for unit and system tests
- **ruff**: Fast Python linter and formatter
  - Configured with common rules for code style and quality
  - Auto-fix enabled for many common issues
  - 120 character line length
  - Double quotes for strings
  - Spaces for indentation 