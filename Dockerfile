# Imagen de la interfaz gráfica del códec TIC (src/app.py, Flask) servida con gunicorn.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 tic \
 && mkdir -p /app/data/gui && chown -R tic:tic /app/data

COPY src/ src/

USER tic
# Lo que se sube o genera queda en data/gui/<id>/ (volumen en compose.yaml).
VOLUME ["/app/data"]
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/', timeout=4)"

# Solo es alcanzable desde 127.0.0.1 del LXC (Tailscale Funnel), por eso se confía en X-Forwarded-*.
# Un solo proceso (el códec usa mucha RAM) con hilos para atender varias peticiones;
# timeout alto porque codificar un archivo grande con k grande tarda minutos.
CMD ["gunicorn", "--chdir", "src", "app:app", \
     "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", \
     "--timeout", "900", "--forwarded-allow-ips", "*", "--access-logfile", "-"]
