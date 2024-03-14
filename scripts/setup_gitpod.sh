#!/bin/bash
# This script does the setup needed for Gitpod

# Setup pre-commit hooks
pyenv install 3.12 --skip-existing # must match python version in .pre-commit-config.yaml
pyenv global 3.12
sudo python3 -m pip install pre-commit
pre-commit install --install-hooks
