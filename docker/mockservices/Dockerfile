FROM python:3.12-slim

# Install mailpit (SMTP capture + web UI)
ARG MAILPIT_VERSION=1.21.6
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates \
    && wget -q "https://github.com/axllent/mailpit/releases/download/v${MAILPIT_VERSION}/mailpit-linux-amd64.tar.gz" \
       -O /tmp/mailpit.tar.gz \
    && tar -xzf /tmp/mailpit.tar.gz -C /usr/local/bin mailpit \
    && chmod +x /usr/local/bin/mailpit \
    && rm /tmp/mailpit.tar.gz \
    && apt-get purge -y wget \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY start.sh .
RUN chmod +x start.sh

# FastAPI mock on 8090; mailpit SMTP on 1025; mailpit web UI on 8025
EXPOSE 8090 1025 8025

CMD ["/app/start.sh"]
