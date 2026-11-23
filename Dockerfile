#FROM docker.io/python:3.9
FROM docker.io/python:3.13-alpine

RUN apk upgrade --no-cache && apk add --no-cache curl

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip "urllib3>=2.8.0" -r requirements.txt \
    && pip uninstall -y setuptools wheel \
    && python -m pip uninstall -y pip

ADD . /src
WORKDIR /src

# get qudt_units ontology
#RUN curl https://raw.githubusercontent.com/qudt/qudt-public-repo/main/vocab/unit/VOCAB_QUDT-UNITS-ALL-v2.1.ttl > ./ontologies/qudt_unit.ttl
COPY ./ontologies/qudt_unit.ttl ./ontologies/qudt_unit.ttl

ENV PYTHONDONTWRITEBYTECODE 1
# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED 1

# Bake the git release tag into the image so the app can report its version
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "6","--proxy-headers"]
