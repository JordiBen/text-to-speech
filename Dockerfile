FROM apify/actor-python:3.13
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /models && chown myuser:myuser /models
USER myuser
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Bake Kokoro-82M v1.0 int8 (Apache-2.0, ONNX export by kokoro-onnx, MIT) into the image so runs never download models.
RUN curl -fsSL -o /models/kokoro-v1.0.int8.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx \
 && curl -fsSL -o /models/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin \
 && echo "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb  /models/kokoro-v1.0.int8.onnx" > /tmp/sums \
 && echo "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d  /models/voices-v1.0.bin" >> /tmp/sums \
 && sha256sum -c /tmp/sums
ENV KOKORO_MODEL_DIR=/models
COPY --chown=myuser:myuser . ./
RUN python -m compileall -q src/ && python -c "import src.main"
CMD ["python3", "-m", "src"]
