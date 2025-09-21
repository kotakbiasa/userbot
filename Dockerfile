FROM python:3.13-alpine AS build

ENV VENV="/opt/venv"
ENV PATH="$VENV/bin:$PATH"

WORKDIR /app

RUN apk add --no-cache build-base git \
    && python -m venv $VENV \
    && pip install --upgrade pip

COPY . .
RUN pip install .


FROM python:3.13-alpine

ENV VENV="/opt/venv"
ENV PATH="$VENV/bin:$PATH" \
    TZ="Asia/Jakarta"

WORKDIR /app

RUN apk add --no-cache git

COPY --from=build $VENV $VENV
COPY --from=build /app /app

CMD ["selfbot"]
