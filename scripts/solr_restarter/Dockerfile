FROM docker:latest

# Install Node
RUN apk add --update nodejs npm

# Install deps globally for this tiny image; don't create a node_modules folder
RUN npm install --no-audit -g node-fetch@2
ENV NODE_PATH="/usr/local/lib/node_modules:$NODE_PATH"

COPY . /app

# Override default entrypoint, since docker block "sh" as the default entrypoint,
# so we wouldn't be able to run node as the cmd otherwise.
ENTRYPOINT []

CMD ["node", "/app/index.js"]
