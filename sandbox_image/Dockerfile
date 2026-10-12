FROM python:3.12-slim

RUN pip install --no-cache-dir pandas numpy scipy scikit-learn matplotlib

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp \
    HOME=/tmp

WORKDIR /output