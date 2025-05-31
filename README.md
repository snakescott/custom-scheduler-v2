# Custom Scheduler

A toy kubernetes scheduler. You may be interested in [devlog.md](devlog.md)

## Functionality, installation, and usage
TBD https://github.com/snakescott/custom-scheduler-v2/issues/8

## Development
**WIP**, the below has a lot of AI-generated text that has not been carefully scrutinized (https://github.com/snakescott/custom-scheduler-v2/issues/7 covers reviewing).

### Prerequisites

- Python 3.12 or higher
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

2. Install the package in development mode:
```bash
# First, make sure you're in the project root directory
cd /path/to/custom-scheduler

# Install the package in development mode with all dependencies
uv pip install -e ".[dev]"
```

3. Install pre-commit hooks:
```bash
# Install the git hooks (using uv run since pre-commit is in the virtual env)
uv run pre-commit install
```

4. Run tests:
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

2. Install the package in development mode:
```bash
# Make sure you're in the project root directory
cd /path/to/custom-scheduler
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

- `src/custom_scheduler/`:
  - `core.py`: Core scheduling logic and data structures
  - `api_components.py`: Kubernetes API integration
  - `driver.py`: Main program entry point and loop driver
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
