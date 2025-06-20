#!/bin/bash
set -euo pipefail

# Check if git is installed
if ! command -v git &> /dev/null; then
  echo "Error: git is not installed. Please install git first." >&2
  exit 1
fi

if ! command -v npm &> /dev/null; then
  echo "Error: npm is not installed. Please install Node.js and npm first." >&2
  exit 1
fi

# Clean or update /tmp/olsystem folder
if [ -d /tmp/olsystem ]; then
  echo "Updating olsystem repo..."
  cd /tmp/olsystem
  git pull origin master
  cd -
else
  echo "Cloning olsystem repo..."
  git clone git@github.com:internetarchive/olsystem.git /tmp/olsystem
fi

# Install bubblewrap if missing
if ! command -v bubblewrap &> /dev/null; then
  echo "bubblewrap not found. Installing..."
  npm install -g @bubblewrap/cli
fi

# Run bubblewrap build command from the project root
bubblewrap build
