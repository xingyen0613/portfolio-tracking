FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# fubon-neo 不在 PyPI，官方 binary whl 放 vendor/（Linux x86_64）
COPY vendor/ vendor/
RUN pip install --no-cache-dir vendor/fubon_neo-*.whl

COPY . .

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
