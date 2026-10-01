# MangaBinder web interface in a container.
#   docker run -d -p 8765:8765 -v ~/Manga:/library ghcr.io/preygle/mangabinder
# CLI commands work too:
#   docker run --rm -v ~/Manga:/library -w /library ghcr.io/preygle/mangabinder download URL --volumes
FROM python:3.12-slim

LABEL org.opencontainers.image.title="MangaBinder" \
      org.opencontainers.image.description="Download manga chapters, convert them to PDF, bind volumes and export CBZ" \
      org.opencontainers.image.source="https://github.com/Preygle/manga-downloader" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY . /src
RUN pip install /src && rm -rf /src \
    && useradd --create-home --uid 1000 manga \
    && mkdir /library && chown manga:manga /library

USER manga
VOLUME /library
EXPOSE 8765
ENTRYPOINT ["mangabinder"]
CMD ["web", "--host", "0.0.0.0", "--library", "/library", "--no-browser"]
