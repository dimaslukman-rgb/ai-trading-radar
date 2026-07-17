# Linux containers support paper, CCXT, and Alpaca workflows.  MT5's native
# Python bridge remains Windows-only, so do not use this image for MT5 live
# execution without a separately managed Windows MT5 gateway.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY aitrader_bot ./aitrader_bot
COPY run_scalping.py config.example.json ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      requests==2.34.2 \
      ccxt==4.5.64 \
      alpaca-py==0.43.5

EXPOSE 9190
ENTRYPOINT ["python", "run_scalping.py"]
CMD ["--config", "/app/config.json", "--broker", "default", "--no-gui", "--no-tray", "--auto-start"]
