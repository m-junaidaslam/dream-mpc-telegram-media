FROM python:3.12-alpine
WORKDIR /app
COPY . /app
RUN mkdir -p /app/state /app/logs
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 CMD test -f /app/state/healthy || exit 1
CMD ["python", "-u", "/app/bot.py"]
