FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    texlive-fonts-recommended \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY build.py pdf_checks.py tailor.py review_flow.py web_server.py ./
COPY config/ ./config/
COPY content/master.yaml ./content/master.yaml
COPY templates/ ./templates/
COPY web/ ./web/

# Generate the reference PDF from the same fonts and tools used at runtime.
RUN python build.py \
    && mkdir -p content/tailored output/tailored \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 10000
CMD ["python", "web_server.py", "--host", "0.0.0.0"]
