# FROM vllm/vllm-openai:latest
FROM vllm/vllm-openai:v0.9.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libsndfile1 \
    libsm6 \
    libxext6 \
    && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# COPY assets /app/assets
COPY indextts /app/indextts
COPY tools /app/tools
COPY patch_vllm.py /app/patch_vllm.py
COPY api_server.py /app/api_server.py
COPY convert_hf_format.py /app/convert_hf_format.py
COPY convert_hf_format.sh /app/convert_hf_format.sh
COPY entrypoint.sh /app/entrypoint.sh

ENTRYPOINT /app/entrypoint.sh
