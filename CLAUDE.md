# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is HAP (Hierarchical Pangenome toolkit), a Python bioinformatics tool for building and manipulating hierarchical pangenomes from GFA files. The toolkit provides CLI commands for converting GFA files into hierarchical pangenome representations stored in PostgreSQL databases.

## Development Commands

### Poetry Package Management
- `poetry install` - Install dependencies and development tools
- `poetry shell` - Activate virtual environment
- `poetry add <package>` - Add new dependency

### Testing and Quality Assurance
- `nox` - Run all default sessions (pre-commit, safety, mypy, tests, typeguard, xdoctest, docs-build)
- `nox -s tests` - Run test suite with coverage
- `nox -s mypy` - Run type checking with mypy
- `nox -s pre-commit` - Run all pre-commit hooks
- `nox -s safety` - Check dependencies for security vulnerabilities
- `nox -s coverage` - Generate coverage report
- `nox -s typeguard` - Runtime type checking
- `nox -s xdoctest` - Run docstring examples

### Code Formatting and Linting
- `black .` - Format code with Black
- `isort .` - Sort imports
- `flake8` - Lint code
- `pre-commit run --all-files` - Run all pre-commit hooks

### Documentation
- `nox -s docs-build` - Build documentation
- `nox -s docs` - Build and serve docs with live reloading

## Code Architecture

### Core Structure
- `src/hap/__main__.py` - CLI entry point using Click framework
- `src/hap/commands/` - Command implementations (build, config, sequence)
- `src/hap/lib/` - Core library modules

### Key Modules
- **Database Layer** (`lib/database.py`): PostgreSQL connection management and HAP data storage
- **GFA Processing** (`lib/gfa.py`): GFA file parsing and manipulation 
- **Configuration** (`lib/config.py`): Application configuration management
- **Sequence Handling** (`lib/sequence.py`): Biological sequence processing
- **File Utilities** (`lib/fileutil.py`): File system operations
- **Core Elements** (`lib/elements.py`): Data structure definitions

### Command Structure
Commands are auto-registered from the `commands` module. Main commands:
- `build` - Build hierarchical pangenome from GFA files
- `config` - Manage database and application configuration  
- `sequence` - Sequence-related operations

### Database Integration
The application uses PostgreSQL to store hierarchical pangenome data. Database connection configured via:
- Environment variables: `HAP_DB_USER`, `HAP_DB_PASSWORD`
- Config commands: `hap config set db.user <username>`

## Development Environment Setup

1. Install PostgreSQL and configure database credentials
2. Install Poetry: `pip install poetry`
3. Install dependencies: `poetry install`
4. Install pre-commit hooks: `pre-commit install`
5. Run tests to verify setup: `nox -s tests`

## Code Quality Standards

- **Code Style**: Black formatting with line length 88, isort for imports
- **Type Checking**: Full mypy coverage required
- **Testing**: pytest with 100% coverage requirement
- **Security**: Safety checks for dependency vulnerabilities
- **Docstring Testing**: xdoctest validates code examples in docstrings
- **Pre-commit**: Automated formatting and linting on commits