"""Official Connect transport configuration and a metadata-only delivery copy."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
OPTIONS = {'Timelapse': 'Off', 'Bed leveling': 'On', 'Flow dynamic calibration': 'On'}


def validate_profile(cfg):
    if (cfg.get('model') != 'A1 mini' or cfg.get('use_ams') is not False
            or cfg.get('material') != 'PLA' or cfg.get('spool') != 'external'
            or cfg.get('options') != OPTIONS
            or not re.fullmatch(r'3DP-\d{3}-\d{3}', cfg.get('printer_label', ''))):
        raise ValueError('Connectの設定はA1 mini・外部スプールPLAに対応しています。設定を確認してください。')
    return cfg


def configuration():
    from bambu_lan import configuration as lan_configuration
    path = PROJECT / 'config/printer.local.json'
    if path.exists():
        cfg = json.loads(path.read_text(encoding='utf-8-sig'))
        if cfg.get('transport') == 'bambu_connect':
            validate_profile(cfg)
            if not (PROJECT / '.runtime/connect-rpa-venv/Scripts/python.exe').is_file():
                raise ValueError('Connectの印刷用環境を接続先PCに用意してください。')
            return cfg
    return lan_configuration()


def identity(cfg):
    if cfg.get('transport') != 'bambu_connect':
        from bambu_lan import identity as lan_identity
        return lan_identity(cfg)
    return hashlib.sha256(json.dumps(validate_profile(cfg), sort_keys=True).encode()).hexdigest()


def compatible_copy(source, target):
    """Fill omitted CLI metadata only after checking the real machine preset.

    No geometry, G-code, checksums or nonempty incompatible metadata are changed.
    The original source is never overwritten.
    """
    if source.resolve() == target.resolve():
        raise ValueError('Connectへの受け渡しには別ファイルが必要です。')
    with zipfile.ZipFile(source) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('印刷ファイルが破損しています。')
        settings = json.loads(archive.read('Metadata/project_settings.config'))
        if (settings.get('printer_model') != 'Bambu Lab A1 mini'
                or settings.get('printer_settings_id') != 'Bambu Lab A1 mini 0.4 nozzle'
                or settings.get('nozzle_diameter') != ['0.4']
                or settings.get('filament_type') != ['PLA']
                or settings.get('curr_bed_type') != 'Textured PEI Plate'):
            raise ValueError('A1 mini・0.4 mm・PLA・Textured PEIの印刷設定と一致しません。')
        compatible = ['Bambu Lab A1 mini 0.4 nozzle']
        if settings.get('print_compatible_printers') not in (None, [], compatible):
            raise ValueError('別機種用の印刷データは送信できません。')
        info = ET.fromstring(archive.read('Metadata/slice_info.config'))
        plates = info.findall('plate')
        codes = [n for n in archive.namelist() if re.fullmatch(r'Metadata/plate_\d+\.gcode', n)]
        if len(plates) != 1 or codes != ['Metadata/plate_1.gcode']:
            raise ValueError('一度に送信できるのは1プレートです。')
        plate = plates[0]
        metadata = {n.get('key'): n for n in plate.findall('metadata')}
        if (metadata.get('index') is None or metadata['index'].get('value') != '1'
                or metadata['outside'].get('value') != 'false'
                or metadata['nozzle_diameters'].get('value') != '0.4'
                or any(n.get('skipped') != 'false' for n in plate.findall('object'))
                or any(n.get('type') != 'PLA' for n in plate.findall('filament'))):
            raise ValueError('印刷プレートの設定を確認できません。')
        # This warning is irrelevant only with the validated Timelapse=Off profile.
        if any(n.get('msg') != 'not_support_traditional_timelapse' for n in plate.findall('warning')):
            raise ValueError('スライス結果の警告を確認してください。')
        model = metadata.get('printer_model_id')
        if model is not None and model.get('value') not in ('', 'N1'):
            raise ValueError('印刷データの機種IDがA1 miniと一致しません。')
        code = archive.read(codes[0])
        if hashlib.md5(code).hexdigest() != archive.read(codes[0] + '.md5').decode().strip().lower():
            raise ValueError('印刷経路のチェックサムが一致しません。')
        if model is None:
            model = ET.SubElement(plate, 'metadata', key='printer_model_id')
        model.set('value', 'N1')
        settings['print_compatible_printers'] = compatible
        changes = {'Metadata/project_settings.config': json.dumps(settings, ensure_ascii=False).encode(),
                   'Metadata/slice_info.config': ET.tostring(info, encoding='utf-8', xml_declaration=True)}
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, 'x') as destination:
            for entry in archive.infolist():
                destination.writestr(entry, changes.get(entry.filename, archive.read(entry.filename)))
    return target
