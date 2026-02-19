FROM openclaw/openclaw:latest

# Install Python + council skill dependencies
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
    && pip3 install --break-system-packages \
        httpx \
        reportlab \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Pre-warm pip cache so first council run is instant
RUN python3 -c "import httpx; import reportlab; print('Council deps ready')"
