FROM python:3.13-alpine AS builder

RUN apk add --no-cache gcc musl-dev libffi-dev curl git

ENV POETRY_HOME="/opt/poetry"
RUN curl -sSL https://install.python-poetry.org | python3 - \
    ; ln -s $POETRY_HOME/bin/poetry /usr/local/bin/poetry

RUN poetry config virtualenvs.create false

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry install --no-interaction --no-ansi --only main


FROM python:3.13-alpine

RUN apk add --no-cache libffi git

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages \
    /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

CMD ["poetry", "run", "selfbot"]
