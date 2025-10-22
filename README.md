# Vortex AI Agent Framework

[![PyPI](https://img.shields.io/pypi/v/vortex-ai.svg)](https://pypi.org/project/vortex-ai/)
[![CI](https://github.com/example/vortex/actions/workflows/ci.yml/badge.svg)](https://github.com/example/vortex/actions/workflows/ci.yml)

Vortex is a production-grade, CLI-first framework for orchestrating multi-modal AI agents. The project emphasises modularity, security, and observability so that teams can safely compose advanced AI workflows.

## Installation

```bash
pip install vortex-ai
```

To install with optional extras:

```bash
pip install "vortex-ai[all,dev]"
```

## Quickstart

```bash
# Inspect available commands
vortex --help

# Execute a task with automatic planning
vortex run --task "Summarise repository changes and draft release notes"

# Explore performance analytics
vortex perf metrics
```

## Development

```bash
python -m pip install -r requirements-dev.txt
pre-commit run --all-files  # if using pre-commit hooks
pytest --cov=vortex --cov-report=term-missing
```

Refer to the documentation in `docs/` for detailed architecture, deployment, release, and development guides.

## Contributing

We welcome issues and pull requests that follow the Conventional Commits specification. Please ensure new contributions include tests and documentation updates where appropriate.

## License

Vortex is released under the MIT License. See [LICENSE](LICENSE) for details.
