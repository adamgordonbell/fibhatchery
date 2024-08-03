FROM python:3.9-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy only requirements to cache them in docker layer
COPY pyproject.toml poetry.lock* /app/

# Project initialization:
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi

COPY app/app.py .

EXPOSE 8080

CMD ["python", "app.py"]
