"""Рядки, які є лише у звичайній DEATH STRANDING і досі не перекладені, -- у JSON і назад.

У Crowdin цих рядків немає (там лише Director's Cut), тож їх перекладають окремо:

    python scripts/ds_only_json.py export     # -> ds_untranslated.json у корені репозиторію
    ... заповнити поля "translation" ...
    python scripts/ds_only_json.py import     # -> scripts/data/ds_only_strings.json

Список береться з resources/Localization/ds_untranslated.txt, який пише
build-localization.js, тому спершу має пройти збірка перекладу. У файл потрапляє лише те, що
гравець бачить: без налагоджувального меню розробників (ds_prototype) і рядків з самої
пунктуації.

Описи вантажів, що відрізняються лише розміром партії ("A small batch of ...",
"A large batch of ..."), зведено до одного запису з {size} на місці розміру. У перекладі
{size} теж має стояти: при імпорті на його місце стає слово з SIZES -- те саме, яким цей
розмір уже перекладено в Director's Cut.
"""
import json
import os
import re
import sys

from common import ROOT, utf8_output

JSON_PATH = os.path.join(ROOT, 'ds_untranslated.json')
REPORT_PATH = os.path.join(ROOT, 'resources', 'Localization', 'ds_untranslated.txt')
DATA_PATH = os.path.join(ROOT, 'scripts', 'data', 'ds_only_strings.json')

SIZES = {
    'A small': 'Мала',
    'A medium-sized': 'Середньорозмірна',
    'A large': 'Велика',
    'A very large': 'Дуже велика',
}
SIZE_PATTERN = re.compile('^(' + '|'.join(map(re.escape, SIZES)) + ') batch ')


def is_visible(path, source):
    return '/ds_prototype/' not in path and any(character.isalnum() for character in source)


def template_of(source):
    return SIZE_PATTERN.sub('{size} batch ', source)


def untranslated():
    """[(ключ, англійський текст)] для видимих гравцеві рядків."""
    result = []
    for line in open(REPORT_PATH, encoding='utf-8'):
        if line.strip():
            key, source = line.rstrip('\n').split(': ', 1)
            source = json.loads(source)
            if is_visible(key, source):
                result.append((key, source))
    return result


def export():
    entries = {}
    for _, source in untranslated():
        entries.setdefault(template_of(source), {'source': template_of(source), 'translation': ''})

    with open(JSON_PATH, 'w', encoding='utf-8') as file:
        json.dump(list(entries.values()), file, ensure_ascii=False, indent=2)
    print(f'{JSON_PATH}: унікальних рядків -- {len(entries)}')


def import_():
    translations = {entry['source']: entry['translation'] for entry in json.load(open(JSON_PATH, encoding='utf-8'))}
    data = json.load(open(DATA_PATH, encoding='utf-8'))
    applied = empty = 0

    for key, source in untranslated():
        template = template_of(source)
        translation = translations.get(template, '')
        if not translation.strip():
            empty += 1
            continue

        if template != source:
            if '{size}' not in translation:
                raise SystemExit(f'У перекладі немає {{size}}: {translation!r}')
            translation = translation.replace('{size}', SIZES[SIZE_PATTERN.match(source).group(1)])

        path, uuid = key.rsplit('@@@@', 1)
        data['files'][path][uuid]['target'] = translation
        applied += 1

    with open(DATA_PATH, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    print(f'{DATA_PATH}: перенесено перекладів -- {applied}, лишилось без перекладу -- {empty}')


if __name__ == '__main__':
    utf8_output()
    if len(sys.argv) != 2 or sys.argv[1] not in ('export', 'import'):
        raise SystemExit(__doc__)
    export() if sys.argv[1] == 'export' else import_()
