"""Підганяє замінні .core файли під ту гру, для якої збирається архів.

Файли в Sources і Sources_DSDC_Only зроблено з Director's Cut. У звичайній DEATH STRANDING
частина типів має інший хеш, а TextureSet ще й на одне поле коротший. Гра, зустрівши
невідомий хеш, не створює об'єкт, і перше ж посилання на нього закінчується вильотом
"Failed to resolve link ... (Failed to find the target object)".

Для кожного .core, який є і в теці, і в грі, об'єкти зіставляються з оригіналом за UUID:

  - тип інший, розмір той самий (Texture): будова та сама, тож лишається наш об'єкт із
    перекладеним зображенням, а хеш типу підставляється з гри;
  - тип інший і розмір інший (TextureSet): будова відрізняється, тож об'єкт цілком береться
    з гри. Це лише опис набору -- самі зображення лежать у сусідніх Texture.

Відомості про оригінали беруться або зі справжньої гри (GameOriginals), або з маніфесту
gamedata/<видання>/originals.json, який extract_gamedata.py знімає з гри заздалегідь, щоб
збірка в CI обходилась без неї (ManifestOriginals).
"""
import base64
import json
import os
import struct

from packfile import core_objects


class GameOriginals:
    def __init__(self, game):
        self.game = game

    def exists(self, path):
        return self.game.find(path)[0] is not None

    def objects(self, path):
        data = self.game.read(path)
        result, offset = {}, 0
        for type_hash, uuid, size in core_objects(data):
            result[uuid] = (type_hash, data[offset:offset + 12 + size])
            offset += 12 + size
        return result


class ManifestOriginals:
    def __init__(self, path):
        self.path = path
        self.files = json.load(open(path, encoding='utf-8'))['files']

    def exists(self, path):
        if path not in self.files:
            raise SystemExit(f'{path}: файлу немає в {self.path}. Його додали до Sources після того, як '
                             f'знімали маніфест -- запустіть scripts/extract_gamedata.py на справжній грі.')
        return self.files[path] is not None

    def objects(self, path):
        result = {}
        for uuid, type_hash, size, data in self.files[path]:
            entry = base64.b64decode(data) if data else None
            result[uuid] = (int(type_hash, 16), entry, size)
        return result


def convert(data, expected, path):
    """Повертає (нові байти файлу, скільки хешів підставлено, скільки об'єктів узято з гри)."""
    result, offset, retyped, replaced = bytearray(), 0, 0, 0

    for type_hash, uuid, size in core_objects(data):
        entry = data[offset:offset + 12 + size]
        offset += 12 + size

        if uuid in expected and expected[uuid][0] != type_hash:
            game_type, game_entry = expected[uuid][0], expected[uuid][1]
            game_size = expected[uuid][2] if len(expected[uuid]) > 2 else len(game_entry) - 12

            if game_size == size:
                entry = struct.pack('<Q', game_type) + entry[8:]
                retyped += 1
            elif game_entry is not None:
                entry = game_entry
                replaced += 1
            else:
                raise SystemExit(f'{path}: об\'єкт {uuid} треба взяти з гри, але в маніфесті його немає. '
                                 f'Запустіть scripts/extract_gamedata.py на справжній грі.')

        result += entry

    return bytes(result), retyped, replaced


def fix_types(sources, originals, drop_missing):
    files = retyped = replaced = dropped = 0

    for directory, _, names in os.walk(sources):
        for name in names:
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, sources).replace('\\', '/')

            if not originals.exists(relative):
                if drop_missing:
                    os.remove(path)
                    dropped += 1
                continue

            if not name.endswith('.core'):
                continue

            data = open(path, 'rb').read()
            converted, a, b = convert(data, originals.objects(relative), relative)
            if converted != data:
                open(path, 'wb').write(converted)
                files += 1
                retyped += a
                replaced += b

    print(f'Підгонка під гру: змінено файлів -- {files} (хешів типів підставлено -- {retyped}, '
          f'об\'єктів узято з гри -- {replaced}), видалено відсутніх у грі -- {dropped}', flush=True)
