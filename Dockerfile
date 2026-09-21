FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser gunicorn.conf.py ./gunicorn.conf.py

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)"

STOPSIGNAL SIGTERM

CMD ["gunicorn", "--config", "gunicorn.conf.py", "mariner_genai_dbx.web:create_app()"]
