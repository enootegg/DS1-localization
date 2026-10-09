"""Знімає зі справжньої гри все, що потрібно збірці, щоб далі обходитись без неї.

Запускати на грі з ОРИГІНАЛЬНИМИ файлами (без інсталятора й без нашого архіву в data\\) щоразу,
коли гра оновилась або до Sources додали новий файл:

    python scripts/extract_gamedata.py --edition dc --game "<корінь Director's Cut>"
    python scripts/extract_gamedata.py --edition ds --game "<корінь звичайної гри>"

Результат у gamedata/<видання>/:

  base.bin         архів з оригінальними текстовими .core та prefetch -- їх патчить Decima;
  originals.json   для кожного файлу з Sources: чи є він у грі і які в ньому об'єкти
                   (UUID, хеш типу, розмір) -- цього досить fix_types.py. Сам об'єкт
                   зберігається лише там, де його доведеться брати з гри цілком.

і gamedata/oo2core_7_win64.dll -- бібліотека стиснення Oodle з гри (однакова в обох виданнях).
"""
import argparse
import base64
import json
import os
import re
import shutil
import struct
import tempfile

from common import EDITIONS, GAMEDATA, OODLE, PREFETCH, ROOT, SOURCE_DIRECTORIES, run_decima, utf8_output
from packfile import Game, core_objects


def text_paths(prefetch):
    """Шляхи всіх файлів з текстом. Prefetch перелічує кожен файл гри, тож список беремо з нього."""
    paths = set()
    # Рядок у .core: довжина (4 байти), хеш (4 байти), символи. Довжину беремо звідти, а не
    # вгадуємо кінець шляху: байт довжини наступного рядка сам може виявитись літерою чи цифрою.
    for match in re.finditer(rb'localized/sentences/', prefetch):
        length = struct.unpack_from('<I', prefetch, match.start() - 8)[0]
        path = prefetch[match.start():match.start() + length].decode('ascii', errors='replace')
        if path.rsplit('/', 1)[-1] in ('simpletext', 'sentences'):
            paths.add(path + '.core')
    return sorted(paths)


def build_base(game, root, edition):
    prefetch = game.read(PREFETCH)
    paths = [path for path in text_paths(prefetch) if game.find(path)[0]]

    directory = tempfile.mkdtemp(prefix='ds-gamedata-')
    try:
        for path in [PREFETCH, *paths]:
            target = os.path.join(directory, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as file:
                file.write(game.read(path))

        output = os.path.join(GAMEDATA, edition, 'base.bin')
        if os.path.exists(output):
            os.remove(output)
        log = os.path.join(directory, 'repack.log')
        run_decima(['repack', '--level=BEST', '--no-rebuild-prefetch', f'--project={root}', output, directory], log)
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    print(f'{output}: текстових файлів -- {len(paths)}, {os.path.getsize(output) / 2 ** 20:.1f} МБ')


def build_manifest(game, edition, resources):
    files = {}

    for source in SOURCE_DIRECTORIES:
        base = os.path.join(resources, source)
        for directory, _, names in os.walk(base):
            for name in names:
                path = os.path.join(directory, name)
                relative = os.path.relpath(path, base).replace('\\', '/')

                if game.find(relative)[0] is None:
                    files[relative] = None
                    continue
                if not name.endswith('.core'):
                    files[relative] = []
                    continue

                ours = {uuid: size for _, uuid, size in core_objects(open(path, 'rb').read())}
                original, offset, objects = game.read(relative), 0, []
                for type_hash, uuid, size in core_objects(original):
                    entry = original[offset:offset + 12 + size]
                    offset += 12 + size
                    # Об'єкт іншого розміру, ніж у Sources, не перетипізуєш -- його беруть з гри цілком.
                    keep = uuid in ours and ours[uuid] != size
                    objects.append([uuid, f'{type_hash:016x}', size, base64.b64encode(entry).decode() if keep else None])
                files[relative] = objects

    output = os.path.join(GAMEDATA, edition, 'originals.json')
    with open(output, 'w', encoding='utf-8') as file:
        json.dump({'files': dict(sorted(files.items()))}, file, indent=0)

    missing = sum(1 for value in files.values() if value is None)
    print(f'{output}: файлів -- {len(files)}, з них немає в грі -- {missing}')


def main():
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--edition', required=True, choices=EDITIONS)
    parser.add_argument('--game', required=True, help='корінь гри з оригінальними файлами')
    parser.add_argument('--resources', default=os.path.join(ROOT, 'resources'), help='тека з Sources і Sources_DSDC_Only')
    arguments = parser.parse_args()

    if os.path.exists(os.path.join(arguments.game, 'data', '59b95a781c9170b0d13773766e27ad90.bin.bak')):
        print('УВАГА: у data\\ є .bak від інсталятора. Переконайтесь, що текст у грі оригінальний.')

    os.makedirs(os.path.join(GAMEDATA, arguments.edition), exist_ok=True)
    shutil.copy(os.path.join(arguments.game, OODLE), os.path.join(GAMEDATA, OODLE))

    game = Game(arguments.game)
    build_base(game, arguments.game, arguments.edition)
    build_manifest(game, arguments.edition, arguments.resources)


if __name__ == '__main__':
    main()
