#!/usr/bin/env python3
#
# Copyright (c) 2024, Antonie Blom
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import logging
import os
import asyncio
import time
from dsmr_parser.clients.protocol import create_dsmr_reader
import paho.mqtt.client as mqtt
from config import Config
from schema import Schema


class AsyncTelegramPublisher:
    def __init__(self, cfg, client):
        self.cfg = cfg
        self.client = client
        self.schema = None

        self.latest_telegram = None
        self.has_new_data = False
        self.has_mqtt_trigger = False
        self.missed_trigger = True

        asyncio.create_task(self.run_timer_loop())

    def handle_telegram(self, telegram):
        logging.debug('Received DSMR telegram')

        # Initialize schema and Home Assistant discovery with the very first telegram
        if self.schema is None:
            self.schema = Schema(telegram, self.cfg.MQTT_TOPIC_PREFIX)
            if self.cfg.HA_DEVICE_ID != '':
                self.schema.publish_ha_discovery(
                    self.client,
                    self.cfg.HA_DISCOVERY_PREFIX,
                    self.cfg.HA_DEVICE_ID,
                    f'{self.cfg.MQTT_TOPIC_PREFIX}/status'
                )

        self.latest_telegram = telegram
        self.has_new_data = True

        # TRIGGER 1: Publish immediately if the interval is 0 and there is no sync topic, or missed trigger
        if (self.cfg.MESSAGE_INTERVAL == 0 and not self.cfg.MQTT_SYNC_TOPIC) or self.missed_trigger:
            self.publish_now()

    def handle_mqtt_sync_trigger(self):
        # TRIGGER 2: Called from MQTT thread on a message in MQTT_SYNC_TOPIC.
        logging.debug('MQTT Sync Trigger Received')
        self.has_mqtt_trigger = True
        self.publish_now()

    def publish_now(self):
        if self.has_new_data and self.latest_telegram and self.schema:
            self.schema.publish(self.client, self.latest_telegram)
            self.missed_trigger = False
            self.has_new_data = False
        else:
            self.missed_trigger = True
            logging.warning('Ready to publish data, but no telegram queued')

    async def run_timer_loop(self):
        # TRIGGER 3: Fixed interval / Fallback timer loop
        if self.cfg.MESSAGE_INTERVAL <= 0:
            return

        interval = self.cfg.MESSAGE_INTERVAL
        logging.info(f'Timer loop started (interval: {interval}s)')

        next_ts = time.monotonic() + 0.1

        while True:
            sleep_t = next_ts - time.monotonic()
            if sleep_t > 0:
                logging.debug(f'Rate limiter delay: {sleep_t:.4f} s')
                await asyncio.sleep(sleep_t)

            if not self.has_mqtt_trigger:
                self.publish_now()

            self.has_mqtt_trigger = False

            next_ts += interval

async def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)
    version = os.getenv('MQTT4DSMR_VERSION', 'unknown')
    logging.info(f'Using mqtt4dsmr {version}')

    cfg = Config()
    loop = asyncio.get_running_loop()

    # Initialize MQTT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    publisher = AsyncTelegramPublisher(cfg, client)

    def on_connect(client, userdata, flags, rc, properties):
        if rc == 0:
            logging.info('Connected to MQTT broker')
            client.publish(avail_topic, 'online', retain=True)
            if cfg.MQTT_SYNC_TOPIC:
                logging.info(f'Subscribing to sync topic: {cfg.MQTT_SYNC_TOPIC}')
                client.subscribe(cfg.MQTT_SYNC_TOPIC)
        else:
            logging.error('MQTT broker connection failed')

    def on_message(client, userdata, msg):
        if cfg.MQTT_SYNC_TOPIC and msg.topic == cfg.MQTT_SYNC_TOPIC:
            loop.call_soon_threadsafe(publisher.handle_mqtt_sync_trigger)

    def on_disconnect(client, userdata, disconnect_flags, rc, properties):
        logging.error('Disconnected from broker')

    if cfg.MQTT_TLS:
        logging.info('Using MQTT over TLS')
        client.tls_set(
            ca_certs=cfg.MQTT_CA_CERTS,
            certfile=cfg.MQTT_CERTFILE,
            keyfile=cfg.MQTT_KEYFILE
        )
        client.tls_insecure_set(cfg.MQTT_TLS_INSECURE)
    else:
        logging.warning('Not using MQTT over TLS; set MQTT_PORT=8883 or MQTT_TLS=1 to enable TLS')

    if cfg.MQTT_USERNAME:
        logging.info('Using MQTT username/password authentication')
        client.username_pw_set(cfg.MQTT_USERNAME, cfg.MQTT_PASSWORD)
    else:
        logging.info('No MQTT username/password provided')

    logging.info(f'Connecting to {cfg.MQTT_HOST}:{cfg.MQTT_PORT}')

    avail_topic = f'{cfg.MQTT_TOPIC_PREFIX}/status'    
    logging.debug(f'Availibility topic: {avail_topic}')
    client.will_set(avail_topic, 'offline', retain=True)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.connect_async(cfg.MQTT_HOST, cfg.MQTT_PORT)
    client.loop_start()

    # Initialize DSMR Reader
    if cfg.DSMR_INTERFACE == 'tcp':
        port = f'socket://{cfg.DSMR_TCP_HOST}:{cfg.DSMR_TCP_PORT}'
    else:
        port = cfg.SERIAL_DEVICE

    try:
        while True:
            disconnected_event = asyncio.Event()
            transport = None

            try:
                logging.info(f'Connecting to DSMR interface on {port}...')

                transport, protocol = await create_dsmr_reader(
                    port=port,
                    dsmr_version=cfg.DSMR_VERSION,
                    telegram_callback=publisher.handle_telegram,
                    keep_alive_interval=cfg.DSMR_KEEP_ALIVE_INTERVAL,
                    encryption_key=cfg.DSMR_ENCRYPTION_KEY,
                    authentication_key=cfg.DSMR_AUTHENTICATION_KEY
                )

                logging.info('Successfully connected to DSMR interface')

                # Wait as long as the connection is active
                await protocol.wait_closed()
                logging.warning(f'DSMR connection lost. Reconnect in {cfg.DSMR_RECONNECT_DELAY} seconds...')

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f'Error connecting to DSMR ({e}). Retry in {cfg.DSMR_RECONNECT_DELAY} seconds...')

            finally:
                if transport and not transport.is_closing():
                    transport.close()

            await asyncio.sleep(cfg.DSMR_RECONNECT_DELAY)

    finally:
        client.loop_stop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Stopping mqtt4dsmr...")
        exit(0)
    exit(1)
