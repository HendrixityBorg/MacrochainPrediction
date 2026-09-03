FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.lock.txt
CMD ["python", "-m", "macro_gold_latent.cli", "run", "--offline"]
