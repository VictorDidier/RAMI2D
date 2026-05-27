# Use the official micromamba image as a base
FROM mambaorg/micromamba:2.0.8
LABEL maintainer="Victor Perez"

# Set the base layer for micromamba
USER root

# Update package manager and install essential build tools
RUN apt-get update -qq && apt-get install -y \
    build-essential \
    ffmpeg \
    libsm6 \
    libxext6 \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the environment variable for the root prefix
ARG MAMBA_ROOT_PREFIX=/opt/conda

# Add /opt/conda/bin to the PATH
ENV PATH=$MAMBA_ROOT_PREFIX/bin:$PATH

# Install dependencies with micromamba, clean afterwards
RUN micromamba create --name rami2d-env python=3.11 -c conda-forge -c bioconda -y \
    && micromamba clean --all --yes
# auto-activate the environment by pre

# Add environment to PATH
ENV PATH="/opt/conda/envs/rami2d-env/bin:$PATH"

# Set the working directory
WORKDIR /app

# Copy contents of the folder to the working directory
COPY ./src .
COPY pyproject.toml .
COPY LICENSE.txt .
COPY README.md .
#COPY . .
#RUN pip install --no-cache-dir -e .
RUN PYTHONPATH="/app/src" pip install --no-cache-dir --no-build-isolation -e .