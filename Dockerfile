FROM python:3.8

WORKDIR /app

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY ./app ./app

CMD ["python", "./app/main.py"]