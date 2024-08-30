# just manual: https://github.com/casey/just#readme

_default:
    just --list

# Install cargo plugins used by this project
bootstrap:
    uv venv --python 3.12

# Build the project as a package (poetry build)
build *args:
    uv run python -m build {{args}}

lock:
    uv lock

update *args:
    uv sync {{args}}

release:
    #!/bin/bash -eux
    uv run python -m build
    uv run python -m twine check dist/*
    uv run python -m twine upload dist/*

format:
    uv run ruff format simple_salesforce tests

# Run code quality checks
check:
    #!/bin/bash -eux
    uv run ruff check simple_salesforce tests

# Run all tests locally
test *args:
    #!/bin/bash -eux
    uv run pytest {{args}}

# Run all tests locally
ci-test coverage_dir='./coverage':
    #!/bin/bash -eux
    uv run pytest --cov-report xml --junitxml={{coverage_dir}}/unittest.junit.xml
