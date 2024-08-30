# just manual: https://github.com/casey/just#readme

_default:
    just --list

# Create a virtual environment and install dependencies
bootstrap default="3.12":
    uv venv --python {{default}}

# Build the project as a package
build *args:
    uv run python -m build {{args}}

# Update the lock file
lock:
    uv lock

# Make sure all dependencies are up to date in env
sync *args:
    uv sync {{args}}

# Release this project to PyPI
release:
    #!/bin/bash -eux
    uv run python -m build
    uv run python -m twine check dist/*
    uv run python -m twine upload dist/*

# Run the formatter (`ruff`)
format:
    uv run ruff format simple_salesforce tests

# Run code quality checks
check:
    #!/bin/bash -eux
    uv run ruff check simple_salesforce tests

# Run mypy checks
check-types:
    #!/bin/bash -eux
    uv run mypy simple_salesforce

# Run all tests locally
test *args:
    #!/bin/bash -eux
    uv run pytest {{args}}

# Run all tests locally
ci-test coverage_dir='./coverage':
    #!/bin/bash -eux
    uv run pytest --cov-report xml --junitxml={{coverage_dir}}/unittest.junit.xml
