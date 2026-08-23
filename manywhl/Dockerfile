# Use a stable Ubuntu release as the foundation
FROM ubuntu:24.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install curl to download uv, and ca-certificates for secure downloads
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Astral uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Python versions 3.9 through 3.14
RUN uv python install 3.12 3.13 3.14

# Tell Python, pip, and uv that installing to the system root is allowed and safe inside this container
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV UV_SYSTEM_PYTHON=1
ENV PYTHONUSERBASE=/usr/local

# Symlink uv-managed Pythons AND pips to standard system paths for global usability
RUN ln -s /root/.local/share/uv/python/cpython-3.12.*/bin/python3 /usr/local/bin/python3.12 && \
    ln -s /root/.local/share/uv/python/cpython-3.12.*/bin/pip3 /usr/local/bin/pip3.12 && \
    \
    ln -s /root/.local/share/uv/python/cpython-3.13.*/bin/python3 /usr/local/bin/python3.13 && \
    ln -s /root/.local/share/uv/python/cpython-3.13.*/bin/pip3 /usr/local/bin/pip3.13 && \
    \
    ln -s /root/.local/share/uv/python/cpython-3.14.*/bin/python3 /usr/local/bin/python3.14 && \
    ln -s /root/.local/share/uv/python/cpython-3.14.*/bin/pip3 /usr/local/bin/pip3.14

# Set Python 3.14 as the default interactive interpreter and pip runner
RUN ln -s /usr/local/bin/python3.14 /usr/local/bin/python3 && \
    ln -s /usr/local/bin/pip3.14 /usr/local/bin/pip

# Verify installations upon container startup
CMD ["bash"]