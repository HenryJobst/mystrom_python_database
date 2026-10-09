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


def connect_db(retries=5, delay=2):
    for attempt in range(1, retries + 1):
        try:
            new_conn = psycopg2.connect(
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT
                )
            new_conn.autocommit = True
            return new_conn
        except psycopg2.OperationalError as e:
            print(f"DB-Verbindung fehlgeschlagen (Versuch {attempt}/{retries}): {e}")
            if attempt == retries:
                raise
            time.sleep(delay)


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


_last_error_log = {}
_ERROR_LOG_INTERVAL = 300  # Sekunden: dieselbe Fehlermeldung hoechstens alle 5 Minuten wiederholen


def _log_once_per_interval(device_ip: str, message: str):
    now = time.monotonic()
    last_message, last_time = _last_error_log.get(device_ip, (None, 0))
    if message == last_message and now - last_time < _ERROR_LOG_INTERVAL:
        return
    print(message)
    _last_error_log[device_ip] = (message, now)


def request_mystrom_data_and_store(device_ip: str, tz: str):
    try:
        # noinspection HttpUrlsUsage
        response = requests.get(f'http://{device_ip}/report', timeout=5)
    except requests.ConnectionError:
        _log_once_per_interval(device_ip, f'Device with ip address {device_ip} seems to be '
                                           f'not reachable.')
        return
    except requests.Timeout:
        _log_once_per_interval(device_ip, f'Request to device with ip address {device_ip} '
                                           f'timed out.')
        return
    except requests.RequestException:
        _log_once_per_interval(device_ip, f'Request to device with ip address {device_ip} '
                                           f'failed.')
        return

    try:
        response = json.loads(response.text)
    except json.decoder.JSONDecodeError:
        _log_once_per_interval(device_ip, f'Request to device with ip address {device_ip} '
                                           f'returns invalid JSON response.')
        return

    _last_error_log.pop(device_ip, None)
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

    global conn
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
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        print("Datenbankverbindung verloren, baue sie neu auf:", e)
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn = connect_db()
        except psycopg2.OperationalError as reconnect_error:
            print("Reconnect fehlgeschlagen, naechster Versuch im naechsten Tick:", reconnect_error)
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
    conn = connect_db()

    create_schema()

    try:
        while True:
            run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped.")
        conn.close()
