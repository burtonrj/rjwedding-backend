FROM python:3.11

LABEL wedding.api.version="0.0.1"

ENV POETRY_VERSION=1.3.1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip
RUN pip install "poetry==$POETRY_VERSION"

COPY ./pyproject.toml ./pyproject.toml
COPY ./src ./src

RUN poetry install

EXPOSE 8000

CMD ["poetry", "run", "hypercorn", "src.app:app", "--bind", "0.0.0.0:8000"]
