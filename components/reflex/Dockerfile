# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set the working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
COPY pyproject.toml .python-version uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
COPY . .
RUN uv sync --frozen --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Run the app
CMD ["python", "main.py"]
