FROM python:3.9-slim-buster

WORKDIR /app

ADD . /app
COPY ./web_app/ .

COPY /requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["python", "-m", "web_app.app"]
