FROM python:3.8

RUN mkdir /config
ADD /requirements.txt /config

RUN pip install -r config/requirements.txt

WORKDIR /src

COPY . .

CMD ["gunicorn", "-b", "0.0.0.0:5000", "wsgi:app", "--workers=3"]
