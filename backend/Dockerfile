FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ffmpeg lets librosa decode non-WAV containers. The frontend already sends
# 16 kHz mono PCM WAV, so this is a convenience rather than a requirement.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt ./
# Lean set first so the layer caches independently of the heavy ML extras.
RUN pip install -r requirements.txt
ARG WITH_ML=1
RUN if [ "$WITH_ML" = "1" ]; then pip install -r requirements-ml.txt; fi

COPY . .
RUN mkdir -p /app/uploads/audio

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
