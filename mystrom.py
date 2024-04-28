import json
import os
import time
from dataclasses import dataclass
from datetime import datetime

import psycopg2
import requests
import pytz
from dotenv import load_dotenv
from schedule import every, repeat, run_pending


def create_schema():
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS bkw_mystrom (
            timestamp TIMESTAMP,
            boot_id TEXT,
            power TEXT,
            ws TEXT,
            temperature TEXT
        )
    ''')

    conn.commit()


@repeat(every(5).seconds)
def request_mystrom_and_store():
    TZ = os.getenv("MYSTROM_SERVER_TZ", "Europe/Berlin")
    timezone = pytz.timezone(TZ)
    now = datetime.now(timezone)
    if now.hour > 22 or now.hour < 6:
        return
    device_ip = os.getenv('MYSTROM_SERVER_ADDRESS')
    request_mystrom_data_and_store(device_ip, TZ)


def request_mystrom_data_and_store(device_ip: str, tz: str):
    try:
        # noinspection HttpUrlsUsage
        response = requests.get(f'http://{device_ip}/report')
    except requests.ConnectionError:
        print(f'Device with ip address {device_ip} seems to be '
              f'not reachable.')
        return
    except requests.Timeout:
        print(f'Request to device with ip address {device_ip} '
              f'timed out.')
        return
    except requests.RequestException:
        print(f'Request to device with ip address {device_ip} '
              f'failed.')
        return

    try:
        response = json.loads(response.text)
    except json.decoder.JSONDecodeError:
        print(f'Request to device with ip address {device_ip} '
              f'returns invalid JSON response.')
        return

    store(response, tz)


@dataclass
class MyStrom:
    timestamp: datetime
    boot_id: str
    power: str
    ws: str
    temperature: str


def store(response: dict, tz: str):
    timezone = pytz.timezone(tz)
    current_time = datetime.now(timezone)
    mystrom = MyStrom(
        current_time,
        response["boot_id"],
        response["power"],
        response["Ws"],
        response["temperature"])

    try:
        with conn.cursor() as cur:
            data_list = [
                mystrom.timestamp,
                mystrom.boot_id,
                mystrom.power,
                mystrom.ws,
                mystrom.temperature
                ]
            cur.execute('''
                 INSERT INTO bkw_mystrom (
                     timestamp,
                     boot_id, 
                     power,
                     ws,
                     temperature
                 ) VALUES (
                     %s, %s, %s, %s, %s);
                 ''', data_list)

            conn.commit()

    except IndexError as e:
        print("IndexError:", e)
        print("Überprüfe die Länge und Inhalte der Datenliste.")
        # Weitere Debug-Informationen ausgeben
        print("Datenliste enthält:", len(data_list), "Elemente.")
        print(data_list)
    except psycopg2.Error as e:
        print("Database error:", e)
        conn.rollback()


if __name__ == '__main__':
    load_dotenv()

    # Umgebungsvariablen lesen
    DB_HOST = os.getenv("DB_HOST")
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_PORT = os.getenv("DB_PORT", "5432")  # Standard-Port für PostgreSQL

    # Datenbankverbindung aufbauen
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
        )
    conn.autocommit = True

    create_schema()

    try:
        while True:
            run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped.")
        conn.close()
