FROM docker.io/python:3.8

RUN apt-get -y update && apt-get install -y apt-utils gcc g++
RUN apt-get -y upgrade
#RUN git clone https://github.com/Mat-O-Lab/CSVtoCSVW.git /src
ADD . /src
RUN pip install --no-cache-dir -r /src/requirements.txt
WORKDIR /src
# get qudt_units ontology
RUN curl https://raw.githubusercontent.com/qudt/qudt-public-repo/main/vocab/unit/VOCAB_QUDT-UNITS-ALL-v2.1.ttl > ./ontologies/qudt_unit.ttl
ENV PYTHONDONTWRITEBYTECODE 1
# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED 1
ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "6","--proxy-headers"]
