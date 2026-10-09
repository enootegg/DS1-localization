"""Спільне для скриптів збірки: шляхи репозиторію, видання гри, запуск Decima."""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECIMA = os.path.join(ROOT, 'tools', 'decima', 'decima-cli.exe')
GAMEDATA = os.path.join(ROOT, 'gamedata')
OODLE = 'oo2core_7_win64.dll'

# Архів категорії "Patch": його ім'я гра (і Decima) знає наперед, і він перекриває решту.
PATCH_ARCHIVE = '59b95a781c9170b0d13773766e27ad90.bin'
PREFETCH = 'prefetch/fullgame.prefetch.core'

EDITIONS = {
    'dc': {
        'title': "DEATH STRANDING DIRECTOR'S CUT",
        'localization': 'localization.json',
        # Decima відрізняє Director's Cut від звичайної гри за цим файлом поруч з exe.
        'marker': 'XeFX.dll',
        # Sources зроблено з Director's Cut, тож для неї нічого викидати не треба.
        'drop_missing': False,
    },
    'ds': {
        'title': 'DEATH STRANDING',
        'localization': 'localization_ds_not_dc.json',
        'marker': None,
        'drop_missing': True,
    },
}

SOURCE_DIRECTORIES = ('Sources', 'Sources_DSDC_Only')


def utf8_output():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def run_decima(arguments, log_path):
    """Запускає decima-cli, пише весь вивід у log_path і повертає його текстом."""
    result = subprocess.run([DECIMA, *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode('utf-8', errors='replace')
    with open(log_path, 'w', encoding='utf-8') as file:
        file.write(output)
    if result.returncode != 0:
        raise SystemExit(f'decima-cli {arguments[0]} завершився з кодом {result.returncode}, див. {log_path}')
    return output


def make_stub_game(edition, directory):
    """Збирає "міні-гру", якої досить Decima: exe, Oodle і один архів з оригіналами з gamedata.

    Decima шукає в корені exe (щоб упізнати гру), бере звідти Oodle, а архіви читає з data\\.
    У base.bin лежать лише ті файли, які збірка змінює: текстові .core і prefetch.
    """
    base = os.path.join(GAMEDATA, edition, 'base.bin')
    if not os.path.exists(base):
        raise SystemExit(f'Немає {base} -- запустіть scripts/extract_gamedata.py на справжній грі.')

    shutil.rmtree(directory, ignore_errors=True)
    os.makedirs(os.path.join(directory, 'data'))
    open(os.path.join(directory, 'ds.exe'), 'wb').close()
    if EDITIONS[edition]['marker']:
        open(os.path.join(directory, EDITIONS[edition]['marker']), 'wb').close()
    shutil.copy(os.path.join(GAMEDATA, OODLE), directory)
    shutil.copy(base, os.path.join(directory, 'data', PATCH_ARCHIVE))
    return directory
