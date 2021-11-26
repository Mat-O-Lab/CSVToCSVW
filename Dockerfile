FROM python:3.8

WORKDIR /app

COPY config/requirements.txt .

RUN pip3 install -r requirements.txt

COPY . .

CMD ["gunicorn", "-b", "0.0.0.0:5000", "src.app:flaskapp"]
#CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
