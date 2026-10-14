# Imagen del servidor web del códec TIC (web/app.py sobre src/tic_codec.py).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    TIC_DATOS=/tmp/tic-web

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 tic

COPY src/ src/
COPY web/ web/
COPY diagrams/tic_codec.architecture.html diagrams/tic_codec.dataflow.html diagrams/tic_codec.teoria.html diagrams/
COPY docs/*.pdf docs/

USER tic
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

# --proxy-headers: detrás de Tailscale Funnel el cliente real llega en X-Forwarded-For.
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
