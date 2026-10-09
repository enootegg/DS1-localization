"""Наскрізна перевірка тексту: чи кожен рядок гри є в перекладі й чи він справді в архіві.

    python scripts/verify_text.py

Гра не потрібна. Для кожного видання читає:

  - gamedata/<видання>/base.bin -- усі текстові файли гри в оригіналі: рядок, якого немає в
    перекладі, видно тут;
  - dist/<видання>/localization/ds_ua.bin -- щойно зібраний архів: файл з нього перекриває
    оригінал так само, як у грі, тож прочитаний текст -- це те, що побачить гравець;

і порівнює з resources/Localization/*.json. Запускати після build_all.py. Завершується з
помилкою, якщо щось не збігається.

Текст читається напряму з .core, без Decima: об'єкт LocalizedTextResource -- це UUID і далі
для кожної мови "довжина (2 байти) + текст, довжина + примітка, режим показу (1 байт)".
Англійська йде першою, і саме її слот українізатор переписує.
"""
import json
import os
import re
import struct
import sys

from common import EDITIONS, GAMEDATA, OODLE, PREFETCH, ROOT, utf8_output
from extract_gamedata import text_paths
from packfile import Oodle, Packfile, core_objects, path_hash

SHOW = {0: 'auto', 1: 'always', 2: 'never'}
# Те саме, що Decima вважає порожнім рядком і не експортує.
EMPTY = ('', '(none)', '(did not translate)', '<ignoresub>')


def uuid_text(raw):
    """UUID так, як його пише Decima (і ключі Crowdin): перші три групи -- little-endian."""
    return f'{raw[3::-1].hex()}-{raw[5:3:-1].hex()}-{raw[7:5:-1].hex()}-{raw[8:10].hex()}-{raw[10:].hex()}'


def english(data, offset):
    """Англійський слот об'єкта: (текст, режим показу)."""
    length = struct.unpack_from('<H', data, offset)[0]
    text = data[offset + 2:offset + 2 + length].decode('utf-8')
    offset += 2 + length
    offset += 2 + struct.unpack_from('<H', data, offset)[0]
    return text, SHOW[data[offset]]


def read_strings(archives, paths, known):
    """{(файл, UUID): (текст, режим)} для всіх LocalizedTextResource у переліку файлів.

    Тип упізнається за об'єктами, UUID яких є в перекладі (known): хеш типу той самий у всіх.
    """
    files = {}
    for path in paths:
        for archive in archives:
            if path_hash(path) in archive.files:
                files[path] = archive.read(path_hash(path))
                break

    text_types = set()
    for path, data in files.items():
        offset = 0
        for type_hash, uuid, size in core_objects(data):
            if (path, uuid_text(bytes.fromhex(uuid))) in known:
                text_types.add(type_hash)
            offset += 12 + size

    result = {}
    for path, data in files.items():
        offset = 0
        for type_hash, uuid, size in core_objects(data):
            if type_hash in text_types:
                result[(path, uuid_text(bytes.fromhex(uuid)))] = english(data, offset + 12 + 16)
            offset += 12 + size
    return result


def verify(edition, oodle):
    info = EDITIONS[edition]
    localization = json.load(open(os.path.join(ROOT, 'resources', 'Localization', info['localization']), encoding='utf-8'))
    wanted = {(file, uuid): text for file, strings in localization['files'].items() for uuid, text in strings.items()}

    base = Packfile(os.path.join(GAMEDATA, edition, 'base.bin'), oodle)
    built = Packfile(os.path.join(ROOT, 'dist', edition, 'localization', 'ds_ua.bin'), oodle)
    paths = text_paths(base.read(path_hash(PREFETCH)))

    original = {key: value for key, value in read_strings([base], paths, wanted).items() if value[0].strip() not in EMPTY}
    result = read_strings([built, base], paths, wanted)

    not_covered = [key for key in original if key not in wanted]
    unknown = [key for key in wanted if key not in original]
    wrong_source = [key for key in wanted if key in original and original[key][0] != wanted[key]['source']]
    wrong_text = [key for key in wanted if key in result and result[key][0] != wanted[key]['target']]
    wrong_show = [key for key in wanted if key in result and result[key][1] != wanted[key]['show']]
    same = [key for key in wanted if wanted[key]['target'] == wanted[key]['source']]
    words = [key for key in same if re.search('[A-Za-z]{2,}', wanted[key]['source'])]

    print(f'=== {info["title"]} ===')
    print(f'  текстових файлів у грі: {len(paths)}, рядків у грі: {len(original)}, у перекладі: {len(wanted)}')
    print(f'  є в грі, немає в перекладі: {len(not_covered)}; є в перекладі, немає в грі: {len(unknown)}; '
          f'англійський текст у перекладі не той, що в грі: {len(wrong_source)}')
    print(f'  в архіві не той текст: {len(wrong_text)}; не той режим показу: {len(wrong_show)}')
    print(f'  переклад дорівнює оригіналу: {len(same)}, з них зі словами латиницею: {len(words)}')

    for title, keys in (('немає в перекладі', not_covered), ('немає в грі', unknown), ('не той текст в архіві', wrong_text)):
        for file, uuid in keys[:5]:
            print(f'    {title}: {file} {uuid}')

    return not (not_covered or unknown or wrong_source or wrong_text or wrong_show)


if __name__ == '__main__':
    utf8_output()
    oodle = Oodle(os.path.join(GAMEDATA, OODLE))
    results = [verify(edition, oodle) for edition in EDITIONS]
    if not all(results):
        sys.exit('Текст в архівах не збігається з перекладом.')
    print('Увесь текст обох видань є в перекладі й потрапив в архіви.')
