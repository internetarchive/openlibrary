#!/bin/bash

# Watch JS/CSS/Vue files for changes and auto rebuild

# check if websocket already installed
if [ -d node_modules/websocket ]; then
  echo "websocket already installed"
else
  echo "installing websocket"
  npm install --no-save websocket
fi

npx concurrently npm:watch npm:watch-css npm:watch-autoreload 'node scripts/auto-reload-server.js'
