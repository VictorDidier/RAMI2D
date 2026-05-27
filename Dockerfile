FROM mambaorg/micromamba:latest
LABEL maintainer="Victor Perez"

# define root prefix (using default location for mambauser)
ARG MAMBA_ROOT_PREFIX=/home/mambauser/micromamba

# add micromamba's bin directory to PATH ----
ENV PATH=$MAMBA_ROOT_PREFIX/bin:$PATH

# Temporarily switch to root to install system dependencies
USER root
WORKDIR /tool

RUN apt-get update -qq && apt-get install -y \
    build-essential \
    ffmpeg \
    libsm6 \
    libxext6 \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch back to mambauser for the rest (security)
USER mambauser

# Create environment with conda-forge and bioconda channels
RUN micromamba create --name rami2d-env python=3.11 -c conda-forge -c bioconda -y \
    && micromamba clean --all --yes
# auto-activate the environment by prepending its bin to PATH ----
ENV PATH=$MAMBA_ROOT_PREFIX/envs/rami2d-env/bin:$PATH

# Copy only necessary files (minimal)
COPY --chown=mambauser:mambauser pyproject.toml README.md LICENSE.txt .
COPY --chown=mambauser:mambauser src/ .

# Install your package inside the activated environment
RUN pip install --no-cache-dir .