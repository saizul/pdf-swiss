FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[compress]" \
    && useradd --system --uid 10001 --create-home app \
    && rm -rf /app/build
USER app
# Mount the folder with your PDFs at /work: docker run --rm -v "$PWD:/work" ghcr.io/saizul/pdf-swiss info file.pdf
WORKDIR /work
ENTRYPOINT ["pdf-swiss"]
CMD ["--help"]
