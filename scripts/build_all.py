"""Повна збірка українізатора для обох видань гри -- одна команда і локально, і в CI.

    python scripts/build_all.py

  1. set-version.js          версія з відсотка затверджених рядків у Crowdin
  2. build-localization.js   свіжий переклад з Crowdin -> resources/Localization/*.json
  3. cmake                   localizer -> winhttp.dll
  4. build_archive.py        localization\\ds_ua.bin для Director's Cut і для звичайної гри
  5. пакування               dist/Death.Stranding*.UA.<версія>.zip -- вміст кладуть у корінь гри
  6. verify_text.py          звірка: увесь текст гри є в перекладі й потрапив в архіви

Потрібні: CROWDIN_TOKEN (змінна середовища або .env), тека resources/ з Sources і
Sources_DSDC_Only, CMake з MSVC, Node.js, Python з пакетом mmh3.

З --csv переклад береться з локального CSV-експорту Crowdin, без звернень до мережі.
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile

from common import EDITIONS, ROOT, utf8_output

SCRIPTS = os.path.join(ROOT, 'scripts')
LOCALIZER = os.path.join(ROOT, 'localizer')
DIST = os.path.join(ROOT, 'dist')

PACKAGES = {
    'dc': 'Death.Stranding.Directors.Cut.UA',
    'ds': 'Death.Stranding.UA',
}

INSTALL_NOTES = """Українізатор {title}
Для вас переклали: Спільнота Єнота
Версія перекладу: {version}

ВСТАНОВЛЕННЯ
Скопіюйте вміст архіву у теку з грою:

    winhttp.dll
    localization\\ds_ua.bin

Файли гри не змінюються. Якщо раніше ставили українізатор через інсталятор, спершу
видаліть його (він повертає оригінальний архів гри).

ВИДАЛЕННЯ
Видаліть winhttp.dll і теку localization.

ЯКЩО ПЕРЕКЛАДУ НЕМАЄ
Поруч з exe після запуску з'являється ds1_localizer.log. У робочому стані в ньому є
рядок "Mounted source:localization/ds_ua.bin".

Цей архів підходить лише до {title}, для іншого видання гри потрібен інший.

Наш телеграм - https://t.me/spilnota_enota
"""


def run(command, **options):
    print('>', ' '.join(command), flush=True)
    subprocess.run(command, check=True, **options)


def read_version():
    path = os.path.join(ROOT, 'version-info', 'version.txt')
    return open(path, encoding='utf-8').read().strip() if os.path.exists(path) else 'dev'


def build_localizer():
    build = os.path.join(LOCALIZER, 'build')
    run(['cmake', '-S', LOCALIZER, '-B', build, '-A', 'x64'])
    run(['cmake', '--build', build, '--config', 'Release'])
    return os.path.join(build, 'Release', 'ds1_localizer.dll')


def package(edition, library, version):
    directory = os.path.join(DIST, edition)
    shutil.copy(library, os.path.join(directory, 'winhttp.dll'))
    with open(os.path.join(directory, 'README.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as file:
        file.write(INSTALL_NOTES.format(title=EDITIONS[edition]['title'], version=version))

    archive = os.path.join(DIST, f'{PACKAGES[edition]}.{version}.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for folder, _, names in os.walk(directory):
            for name in names:
                path = os.path.join(folder, name)
                output.write(path, os.path.relpath(path, directory))
    print(f'Пакет: {archive} ({os.path.getsize(archive) / 2 ** 20:.1f} МБ)', flush=True)


def main():
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--resources', default=os.path.join(ROOT, 'resources'), help='тека з Sources і Sources_DSDC_Only')
    parser.add_argument('--csv', help='локальний CSV-експорт Crowdin замість звернення до Crowdin')
    arguments = parser.parse_args()

    shutil.rmtree(DIST, ignore_errors=True)

    if arguments.csv:
        run(['node', os.path.join(SCRIPTS, 'build-localization.js'), os.path.abspath(arguments.csv)])
    else:
        run(['node', os.path.join(SCRIPTS, 'set-version.js')])
        run(['node', os.path.join(SCRIPTS, 'build-localization.js')])
    version = read_version()

    library = build_localizer()

    for edition in EDITIONS:
        localization = os.path.join(ROOT, 'resources', 'Localization', EDITIONS[edition]['localization'])
        run([sys.executable, os.path.join(SCRIPTS, 'build_archive.py'), '--edition', edition,
             '--resources', arguments.resources, '--localization', localization])
        package(edition, library, version)

    # Останній запобіжник перед релізом: кожен рядок гри є в перекладі й справді лежить в архіві.
    run([sys.executable, os.path.join(SCRIPTS, 'verify_text.py')])


if __name__ == '__main__':
    main()
