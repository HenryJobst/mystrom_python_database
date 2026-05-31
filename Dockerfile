FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY ./mystrom.py ./

ENV DB_HOST=localhost \
    DB_NAME=stiebelwp \
    DB_USER=stiebelwp \
    DB_PORT=5432 \
    MYSTROM_SERVER_ADDRESS=192.168.1.99 \
    MYSTROM_SERVER_TZ=Europe/Berlin

CMD ["python", "./mystrom.py"]
