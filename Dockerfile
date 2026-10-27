# romm_tools - save sync (based on romm_syncthing_sync by amn-96, MIT) + ROM folders (from rom-mapper).
FROM python:3.13-slim

LABEL org.opencontainers.image.title="romm_tools" \
      org.opencontainers.image.description="RomM companion tools: two-way save/state sync with a Syncthing folder, frontend folders of links and RomM platform mapping - one web page" \
      org.opencontainers.image.source="https://github.com/sireteanu/romm_tools" \
      org.opencontainers.image.licenses="MIT"

# tzdata: TZ for log times and the ROM folders schedule
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (src/web_static = save sync pages, src/mapper/static = ROM folders page)
COPY src/ ./src/
RUN rm -rf ./src/experimental
COPY romm_tools.py VERSION platform_mapping.yaml ./

# The release workflow passes the real release number (it auto-bumps the patch beyond the VERSION file).
ARG APP_VERSION=""
RUN if [ -n "$APP_VERSION" ]; then echo "$APP_VERSION" > VERSION; fi
ENV APP_VERSION=${APP_VERSION}

# /data: save sync history, approvals, backups, recycle bin, logs, and the ROM folders mapping/settings.
ENV DATA_DIR=/data \
    WEB_PORT=8080 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data /syncdata /config
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.getenv('WEB_PORT','8080'), timeout=5)" || exit 1

# Web page + save sync + ROM folders scheduler. One-off ROM folders resync without the page:
#   docker exec romm-tools python romm_tools.py --resync
CMD ["python", "romm_tools.py"]
