FROM python:3.12-slim

# W7 prints the aggregated record — don't let it sit in a buffer.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install the QF framework wheel first (its transitive deps rarely change),
# then the pipeline-specific requirements — maximises Docker layer caching.
COPY dist/ ./dist/
RUN pip install --no-cache-dir ./dist/qf-1.0.5-py3-none-any.whl

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY src/ ./src/
COPY maps/ ./maps/
COPY tools/ ./tools/
COPY main.py app.py ./

EXPOSE 5000

CMD ["python", "app.py"]
