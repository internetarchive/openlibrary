#!/bin/bash
# This script does the setup needed for gitpod

# Builds the docker images so when user opens env this step is cached
docker-compose up --no-start

# Setup pre-commit hooks
pyenv install
pip install pre-commit
# PIP_USER false because https://github.com/gitpod-io/gitpod/issues/4886#issuecomment-963665656
env PIP_USER=false pre-commit install
