FROM openclaw/openclaw:latest

# Install Python + council skill dependencies
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
    && python3 -m venv /opt/council-venv \
    && /opt/council-venv/bin/pip install --no-cache-dir \
        httpx \
        reportlab \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add venv to PATH so council scripts use it
ENV PATH="/opt/council-venv/bin:$PATH"

# Pre-warm so first council run is instant
RUN python3 -c "import httpx; import reportlab; print('Council deps ready')"
