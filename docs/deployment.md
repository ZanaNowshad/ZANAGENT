# Deployment Guide

This guide describes how to deploy Vortex to a server or developer workstation.

## Prerequisites

- Python 3.11+
- Optional: virtual environment (recommended)
- Network access to AI providers if using external APIs

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[extras]
```

The `extras` extra installs optional integrations such as ChromaDB and FAISS.

## Configuration

1. Copy `config/default.yml` to a writable location.
2. Update provider credentials, memory paths, and security policies.
3. Set `VORTEX_CONFIG` to the configuration file path.

```bash
export VORTEX_CONFIG=/path/to/vortex.yml
```

Secrets should be stored using the CLI or by writing encrypted files into the
credential directory defined in the configuration.

## Running the CLI

```bash
python -m vortex.main run --prompt "Hello Vortex"
```

Other subcommands include `plan`, `analyze`, `plugin`, `config`, `memory`, and
`shell`. Use `--help` for detailed usage information.

## Observability

Logs are written in JSON format to `~/.vortex/logs/vortex.log`. Set the
`VORTEX_LOG_DIR` environment variable to customise the location.

## CI/CD

The repository includes a GitHub Actions workflow executing formatting checks
and unit tests. Integrate the same commands into your deployment pipeline.
