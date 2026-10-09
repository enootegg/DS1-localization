"""Збирає localization\\ds_ua.bin -- архів з усіма зміненими файлами (текст, шрифти, текстури),
який localizer (winhttp.dll) монтує поверх архівів гри.

    python scripts/build_archive.py --edition dc
    python scripts/build_archive.py --edition ds

Гра для збірки не потрібна: оригінали, які доводиться патчити, лежать у gamedata/ (їх знімає
extract_gamedata.py). З --game збірка йде на справжній грі -- так можна звірити результат.

Кроки -- ті самі, що в інсталяторі, лише repack пише не в архів гри, а в новий окремий файл:

  1. Sources + Sources_DSDC_Only копіюються в робочу теку;
  2. fix_types підганяє їх під видання гри;
  3. "decima localization import" патчить текстові .core перекладом і кладе їх туди ж;
  4. "decima repack" пакує теку в архів разом з перебудованим prefetch: у ньому записані
     розміри всіх .core, і без оновлення гра читала б змінені файли зі старими розмірами.
"""
import argparse
import os
import re
import shutil

from common import EDITIONS, GAMEDATA, PATCH_ARCHIVE, ROOT, SOURCE_DIRECTORIES, make_stub_game, run_decima, utf8_output
from fix_types import GameOriginals, ManifestOriginals, fix_types
from packfile import Game

# Рядки з логів Decima, які означають, що в архів потрапило не те, що треба.
DECIMA_FAILURES = re.compile(r"Can't find|Unable to read|Unable to get resource| ERROR ")


def check_log(output, log_path):
    failures = [line for line in output.splitlines() if DECIMA_FAILURES.search(line)]
    if failures:
        for line in failures[:20]:
            print('   ', line)
        raise SystemExit(f'Decima повідомила про проблеми ({len(failures)}), див. {log_path}')


def main():
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--edition', required=True, choices=EDITIONS)
    parser.add_argument('--game', help='корінь справжньої гри з оригінальними файлами (замість gamedata/)')
    parser.add_argument('--resources', default=os.path.join(ROOT, 'resources'), help='тека з Sources, Sources_DSDC_Only і Localization')
    parser.add_argument('--localization', help='файл перекладу (типово -- з <resources>/Localization)')
    parser.add_argument('--out', help='куди покласти архів (типово -- dist/<видання>/localization/ds_ua.bin)')
    arguments = parser.parse_args()

    edition = EDITIONS[arguments.edition]
    work = os.path.join(ROOT, 'work', arguments.edition)
    sources = os.path.join(work, 'Sources')
    localization = arguments.localization or os.path.join(arguments.resources, 'Localization', edition['localization'])
    output = arguments.out or os.path.join(ROOT, 'dist', arguments.edition, 'localization', 'ds_ua.bin')

    print(f'=== {edition["title"]} ===', flush=True)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(sources)
    os.makedirs(os.path.dirname(output), exist_ok=True)

    if arguments.game:
        patch = os.path.join(arguments.game, 'data', PATCH_ARCHIVE)
        if os.path.exists(patch + '.bak') and os.path.getsize(patch) != os.path.getsize(patch + '.bak'):
            raise SystemExit(f'{patch} відрізняється від свого .bak -- гра українізована. Спершу відновіть оригінал.')
        game_root = arguments.game
        originals = GameOriginals(Game(game_root))
    else:
        game_root = make_stub_game(arguments.edition, os.path.join(work, 'game'))
        originals = ManifestOriginals(os.path.join(GAMEDATA, arguments.edition, 'originals.json'))

    for name in SOURCE_DIRECTORIES:
        shutil.copytree(os.path.join(arguments.resources, name), sources, dirs_exist_ok=True)

    fix_types(sources, originals, edition['drop_missing'])

    log = os.path.join(work, 'import.log')
    check_log(run_decima(['localization', 'import', f'--project={game_root}', f'--input={localization}', f'--output={sources}'], log), log)

    if os.path.exists(output):
        os.remove(output)
    log = os.path.join(work, 'repack.log')
    check_log(run_decima(['repack', '--level=NORMAL', f'--project={game_root}', output, sources], log), log)

    count = sum(len(names) for _, _, names in os.walk(sources))
    print(f'Готово: {output} ({os.path.getsize(output) / 2 ** 20:.1f} МБ, файлів: {count})', flush=True)


if __name__ == '__main__':
    main()
