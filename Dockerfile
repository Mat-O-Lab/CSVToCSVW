FROM python:3.8

RUN mkdir /config
ADD /config/requirements.txt /config

RUN pip install -r config/requirements.txt

WORKDIR /src

COPY /src .

CMD ["gunicorn", "-b", "0.0.0.0:5000", "wsgi:app"]
#CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
