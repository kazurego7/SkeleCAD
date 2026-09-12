"""A1 mini LAN transport. No print command is retried automatically.

Protocol references: docs/REMOTE_PRINT.md. Credentials stay on the server.
"""
import ftplib
import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
import time
import uuid
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def configuration():
    path = PROJECT / 'config/printer.local.json'
    if not path.exists():
        raise ValueError('プリンターの接続設定が必要です。接続先PCで設定してください。')
    cfg = json.loads(path.read_text(encoding='utf-8-sig'))
    if cfg.get('model') != 'A1 mini':
        raise ValueError('現在の印刷設定に対応するプリンターはA1 miniです。')
    address = ipaddress.ip_address(cfg['host'])
    if not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified:
        raise ValueError('プリンターのLAN内IPアドレスを指定してください。')
    if not re.fullmatch(r'[A-Za-z0-9]{10,24}', cfg.get('serial', '')):
        raise ValueError('プリンターのシリアル番号を設定してください。')
    if cfg.get('use_ams') not in (True, False):
        raise ValueError('フィラメントの供給元を設定してください。')
    if cfg['use_ams'] and (type(cfg.get('ams_slot')) is not int or not 0 <= cfg['ams_slot'] <= 3):
        raise ValueError('AMS Liteの使用スロットを0〜3で設定してください。')
    if not cfg.get('access_code'):
        studio = Path(os.environ.get('APPDATA', '')) / 'BambuStudio/BambuStudio.conf'
        try:
            saved = json.JSONDecoder().raw_decode(studio.read_text(encoding='utf-8-sig'))[0]
            cfg['access_code'] = saved.get('access_code', {}).get(cfg['serial'])
        except (OSError, ValueError):
            pass
    if not re.fullmatch(r'[A-Za-z0-9]{8}', cfg.get('access_code') or ''):
        raise ValueError('プリンターのLANアクセスコードを設定してください。')
    return cfg


def identity(cfg):
    # Include the selected spool and printer, but never return credentials.
    return hashlib.sha256(json.dumps({k: cfg.get(k) for k in
        ('host', 'serial', 'model', 'use_ams', 'ams_slot')}, sort_keys=True).encode()).hexdigest()


class PrinterTLS(ssl.SSLContext):
    """Trust Bambu's installed CA and check the device serial, not its IP."""
    def __new__(cls, serial):
        return super().__new__(cls, ssl.PROTOCOL_TLS_CLIENT)

    def __init__(self, serial):
        from runtime_paths import tool_config
        self.serial = serial
        self.check_hostname = False
        self.verify_mode = ssl.CERT_REQUIRED
        # Printers can have legacy v1 certificates signed by Bambu's CA.
        self.verify_flags &= ~ssl.VERIFY_X509_STRICT
        self.load_verify_locations(str(Path(tool_config()['bambu_studio']['executable']).parent / 'resources/cert/printer.cer'))

    def wrap_socket(self, *args, **kwargs):
        connection = super().wrap_socket(*args, **kwargs)
        names = [value for group in connection.getpeercert().get('subject', ())
                 for key, value in group if key == 'commonName']
        if self.serial not in names:
            connection.close()
            raise ssl.SSLCertVerificationError('Printer identity mismatch')
        return connection


class ImplicitFTP(ftplib.FTP_TLS):
    def connect(self, host='', port=990, timeout=30, source_address=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = self.context.wrap_socket(socket.create_connection((host, port), timeout), server_hostname=host)
        self.af = self.sock.family
        self.file = self.sock.makefile('r', encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        connection, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            connection = self.context.wrap_socket(connection, server_hostname=self.host, session=self.sock.session)
        return connection, size


def upload(cfg, path, name):
    ftp = ImplicitFTP(context=PrinterTLS(cfg['serial']))
    try:
        ftp.connect(cfg['host'])
        ftp.login('bblp', cfg['access_code'])
        ftp.prot_p()
        with path.open('rb') as source:
            ftp.storbinary('STOR /cache/' + name, source)
        # Check stored bytes before a project_file command can be issued.
        checksum = hashlib.sha256()
        ftp.retrbinary('RETR /cache/' + name, checksum.update)
        if checksum.hexdigest() != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('プリンターへ転送したデータの照合に失敗しました。')
    finally:
        ftp.close()


def require_idle(report):
    if report.get('gcode_state') not in ('IDLE', 'FINISH') or report.get('stg_cur') not in (0, 255):
        raise ValueError('プリンターが待機状態ではありません。')
    if report.get('print_error', 0) or report.get('hms'):
        raise ValueError('プリンターにエラーがあります。本体を確認してください。')
    if report.get('sdcard') is not True:
        raise ValueError('プリンターのSDカードを確認してください。')


class Printer:
    def __init__(self, cfg):
        import paho.mqtt.client as mqtt
        self.cfg, self.report, self.acks = cfg, {}, {}
        self.full = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='skelecad-' + uuid.uuid4().hex[:12], reconnect_on_failure=False)
        self.client.connect_timeout = 10
        self.client.username_pw_set('bblp', cfg['access_code'])
        self.client.tls_set_context(PrinterTLS(cfg['serial']))
        # PrinterTLS independently checks CA and serial; the IP is not a SAN.
        self.client.tls_insecure_set(True)
        self.client.on_message = self._message
        self.client.on_connect = lambda c, u, f, rc, p: c.subscribe('device/' + cfg['serial'] + '/report') if rc == 0 else None
        self.client.on_subscribe = lambda *args: self.publish('pushing', {'command': 'pushall'})

    def _message(self, client, userdata, message):
        if message.retain:
            return
        try:
            data = json.loads(message.payload).get('print', {})
            if 'result' in data:
                self.acks[str(data.get('sequence_id'))] = data
            else:
                self.report.update(data)
                self.full |= data.get('msg') == 0
        except (ValueError, AttributeError):
            pass

    def publish(self, category, data):
        sequence = str(uuid.uuid4().int % 2000000000)
        result = self.client.publish('device/' + self.cfg['serial'] + '/request', json.dumps({category: {**data, 'sequence_id': sequence}}), qos=0, retain=False)
        if result.rc != 0:
            raise ValueError('プリンターへの送信に失敗しました。')
        return sequence

    def wait(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.client.loop(timeout=.2) != 0:
                raise ValueError('プリンターとの接続が切れました。')
        raise ValueError('プリンターから応答がありません。LAN接続と開発者モードを確認してください。')

    def __enter__(self):
        try:
            self.client.connect(self.cfg['host'], 8883, 60)
            self.wait(lambda: self.full)
            return self
        except Exception:
            self.client.disconnect()
            raise

    def __exit__(self, *args):
        self.client.disconnect()

    def start(self, name):
        require_idle(self.report)
        sequence = self.publish('print', {
            'command': 'project_file', 'param': 'Metadata/plate_1.gcode',
            'url': 'ftp:///cache/' + name, 'subtask_name': name.removesuffix('.gcode.3mf'),
            'project_id': '0', 'profile_id': '0', 'task_id': '0', 'subtask_id': '0',
            'md5': '', 'timelapse': False, 'bed_leveling': True,
            'flow_cali': True, 'vibration_cali': True, 'layer_inspect': False,
            'use_ams': self.cfg['use_ams'],
            'ams_mapping': [self.cfg['ams_slot']] if self.cfg['use_ams'] else [],
        })
        def confirmed():
            ack = self.acks.get(sequence, {})
            if ack and ack.get('result') != 'success':
                raise ValueError('プリンターが開始要求を拒否しました。')
            if self.report.get('print_error', 0):
                raise ValueError('プリンターがエラーを返しました。')
            return (ack.get('result') == 'success' and self.report.get('gcode_state') in ('PREPARE', 'RUNNING')
                    and self.report.get('subtask_name') == name.removesuffix('.gcode.3mf'))
        self.wait(confirmed, 30)
