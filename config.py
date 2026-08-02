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


def get_env_opt(name, ty, required, default=None):
    if name in os.environ:
        value = os.environ[name]
    else:
        if required:
            raise LookupError(f'{name} not set in environment')
        return default

    if type(ty) != type:
        # Must be a collection of permissible values
        if value not in ty:
            values = ', '.join(str(t) for t in ty)
            raise ValueError(f'{name} must be one of {values}')
        return value

    if ty == bool:
        if value.lower() in ('true', 'yes', 'y', '1'):
            return True
        if value.lower() in ('false', 'no', 'n', '0', ''):
            return False
        raise ValueError(f'{name} must be boolean')

    return ty(value)


class Config:
    def __init__(self):
        self.LOG_LEVEL = get_env_opt('LOG_LEVEL', str, False, 'INFO')
        logging.getLogger().setLevel(self.LOG_LEVEL)

        self.DSMR_LOG_LEVEL = get_env_opt('DSMR_LOG_LEVEL', str, False, 'INFO')
        logging.getLogger('dsmr_parser.clients.protocol').setLevel(self.DSMR_LOG_LEVEL)


        dsmr_versions = ['2.2', '4', '4+', '5', '5B', '5L', '5S', 'Q3D', 'ISKRA_IE', '5EONHU', 'MSn', 'SAGEMCOM_T210_D_R']
        logging.debug(f'Possible values for DSMR_VERSION: {dsmr_versions}')

        self.DSMR_VERSION = get_env_opt('DSMR_VERSION', dsmr_versions, False, '4')
        self.DSMR_INTERFACE = get_env_opt('DSMR_INTERFACE', ['serial', 'tcp'], False, 'serial')
        self.SERIAL_DEVICE = get_env_opt('SERIAL_DEVICE', str, self.DSMR_INTERFACE == 'serial', '/dev/ttyDSMR')
        self.DSMR_TCP_HOST = get_env_opt('DSMR_TCP_HOST', str, self.DSMR_INTERFACE == 'tcp', None)
        self.DSMR_TCP_PORT = get_env_opt('DSMR_TCP_PORT', int, False, 23)
        self.DSMR_ENCRYPTION_KEY = get_env_opt('DSMR_ENCRYPTION_KEY', str, False, '')
        self.DSMR_AUTHENTICATION_KEY = get_env_opt('DSMR_AUTHENTICATION_KEY', str, False, '')
        self.DSMR_KEEP_ALIVE_INTERVAL = get_env_opt('DSMR_KEEP_ALIVE', int, False, 30)
        self.DSMR_RECONNECT_DELAY = get_env_opt('DSMR_RECONNECT_DELAY', int, False, 5)

        self.MQTT_HOST = get_env_opt('MQTT_HOST', str, True)
        self.MQTT_PORT = get_env_opt('MQTT_PORT', int, False, None)
        self.MQTT_TLS = get_env_opt('MQTT_TLS', bool, False, None)
        self.MQTT_TLS_INSECURE = get_env_opt('MQTT_TLS_INSECURE', bool, False, False)
        self.MQTT_CA_CERTS = get_env_opt('MQTT_CA_CERTS', str, False)
        self.MQTT_CERTFILE = get_env_opt('MQTT_CERTFILE', str, False)
        self.MQTT_KEYFILE = get_env_opt('MQTT_KEYFILE',  str, False)
        self.MQTT_USERNAME = get_env_opt('MQTT_USERNAME', str, False)
        self.MQTT_PASSWORD = get_env_opt('MQTT_PASSWORD', str, self.MQTT_USERNAME is not None)
        self.MQTT_TOPIC_PREFIX = get_env_opt('MQTT_TOPIC_PREFIX', str, False, 'dsmr')
        self.MQTT_SYNC_TOPIC = get_env_opt('MQTT_SYNC_TOPIC', str, False, None)

        self.HA_DEVICE_ID = get_env_opt('HA_DEVICE_ID', str, False, 'dsmr')
        self.HA_DISCOVERY_PREFIX = get_env_opt('HA_DISCOVERY_PREFIX', str, False, 'homeassistant')

        self.MESSAGE_INTERVAL = get_env_opt('MESSAGE_INTERVAL', int, False, 0)
        

        # Make sure MQTT_PORT has a valid value
        if self.MQTT_PORT is None:
            if self.MQTT_TLS is not None and self.MQTT_TLS:
                self.MQTT_PORT = 8883
            else:
                self.MQTT_PORT = 1883

        # Make sure MQTT_TLS has a valid value
        if self.MQTT_TLS is None:
            self.MQTT_TLS = self.MQTT_PORT == 8883
