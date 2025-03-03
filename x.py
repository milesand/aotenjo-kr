import argparse
import datetime
import json
import shutil
import subprocess
import sys
import zipfile

from collections import OrderedDict
from pathlib import Path

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

def ensure_dir_exists(path: Path):
    path.mkdir(parents=True, exist_ok=True)

BASE_PATH = Path(__file__).parent

FILES = [
    'BossInfo',
    'GameTable',
    'TutorialTable',
    'UIMainMenuTable',
    'YakuInfo',
]

def extract(version, prev_version, gamedir, errstream):
    game_path = Path(gamedir)
    tl_assets_path = game_path / 'Aotenjo_Data' / 'StreamingAssets' / 'aa' / 'StandaloneWindows64'
    assetfiles = {
        'shareddata': 'localization-assets-shared_assets_all.bundle',
        'zh-Hans': 'localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle',
        'en': 'localization-string-tables-english(en)_assets_all.bundle',
        'ja': 'localization-string-tables-japanese(ja)_assets_all.bundle'
    }

    extract_dir = BASE_PATH / 'assets'
    tl_dir = extract_dir / version / 'Translation'
    if prev_version is not None:
        prev_tl_dir = extract_dir / prev_version / 'Translation'
        if not prev_tl_dir.is_dir():
            prev_version = None
            if errstream is not None:
                errstream.write("Translation directory for previous game version missing, skipping\n")

    generator = None
    tl_files = set(FILES)
    tl_dicts = {}

    for (lang, assetfile) in assetfiles.items():
        env = UnityPy.load(str(tl_assets_path / assetfile))
        if generator is None:
            if len(env.objects) == 0:
                continue
            unity_version = env.objects[0].assets_file.unity_version
            generator = TypeTreeGenerator(unity_version)
            generator.load_local_game(str(game_path))
        env.typetree_generator = generator

        obj_name_suffix = ' Shared Data' if lang == 'shareddata' else ('_' + lang)
        data_field = 'm_Entries' if lang == 'shareddata' else 'm_TableData'
        val_field = 'm_Key' if lang == 'shareddata' else 'm_Localized'

        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            name = obj.read().m_Name
            if not name.endswith(obj_name_suffix):
                continue
            tl_filename = name[:-len(obj_name_suffix)]
            if tl_filename not in tl_files:
                continue
            if tl_filename not in tl_dicts:
                tl_dicts[tl_filename] = OrderedDict()
            
            tl = tl_dicts[tl_filename]
            prev_tl = None
            if prev_version is not None:
                prev_tl_path = prev_tl_dir / (tl_filename+'.json')
                if not prev_tl_path.is_file():
                    if errstream is not None:
                        errstream.write("Translation file" + (tl_filename+'.json') + " for previous game version missing, skipping\n")
                else:
                    with prev_tl_path.open('r', encoding='utf-8') as f:
                        prev_tl = json.load(f)
            
            tree = obj.read_typetree()
            for entry in tree[data_field]:
                m_id = entry['m_Id']
                m_val = entry[val_field]
                
                if m_id not in tl:
                    tl[m_id] = OrderedDict()
                    tl[m_id]['value'] = None
                tl[m_id][lang] = m_val

                if prev_tl is not None:
                    prev_entry = prev_tl.get(str(m_id))
                    if prev_entry is not None:
                        # Check if translation of this string in this language has changed.
                        # If it hasn't, reuse previous value.
                        # If it has, make note and set current value to None.
                        prev_lang_val = prev_entry.get(lang)
                        prev_val = prev_entry.get('value')
                        if prev_val is not None:
                            if prev_lang_val is not None and prev_lang_val != m_val:
                                # Translation of this string in this language has changed.
                                tl[m_id]['prev_'+lang] = prev_lang_val
                                tl[m_id].move_to_end(lang)
                                # Maybe we already checked that tl in other language has also changed.
                                # In that case, no need to do this again.
                                if 'prev_value' not in tl[m_id]:
                                    tl[m_id]['prev_value'] = prev_val
                                    tl[m_id]['value'] = None
                            # 'prev_value' in tl[m_id] => we already checked that tl in other language has changed
                            # then we can't reuse prev_val
                            # so we check for *not* in tl[m_id] for reuse
                            elif 'prev_value' not in tl[m_id]:
                                tl[m_id]['value'] = prev_val
                
                if 'prev_value' in tl[m_id]:
                    tl[m_id].move_to_end('prev_value')
                tl[m_id].move_to_end('value')
    
    tl_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = None
    for filename in FILES:
        tl_path = tl_dir / (filename + '.json')
        if tl_path.exists():
            if backup_dir is None:
                backup_dir = tl_dir / 'BACKUP' / datetime.datetime.now().strftime('%Y-%m-%d %H.%M.%S')
                backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tl_path, backup_dir)
            
        with tl_path.open('w', encoding='utf-8') as outfile:
            json.dump(tl_dicts[filename], outfile, indent=4, ensure_ascii=False)

def make_charset(version):
    tl_dir = BASE_PATH / 'assets' / version / 'Translation'
    charset = set("0123456789한국어")
    for fname in FILES:
        tl_file_path = tl_dir / (fname + '.json')
        with tl_file_path.open('r', encoding='utf-8') as f:
            tl = json.load(f)
        for entry in tl.values():
            charset.update(entry['value'])
    out_path = BASE_PATH / 'font-generation-unity' / 'Assets' / 'Resources' / 'charset.txt'
    charset = sorted(charset)
    with out_path.open('w', encoding='utf-8') as f:
        for char in charset:
            f.write(char)

def make_zip(version, gamedir, patchcrc, errstream):
    game_path = Path(gamedir)
    out_path = BASE_PATH / 'output' / version
    ensure_dir_exists(out_path)
    tmp_path = BASE_PATH / 'tmp'
    ensure_dir_exists(tmp_path)
    out_zip = zipfile.ZipFile(out_path / 'Aotenjo_Data.zip', 'w', compression=zipfile.ZIP_DEFLATED)

    catalog_path = game_path / 'Aotenjo_Data' / 'StreamingAssets' / 'aa' / 'catalog.json'
    shutil.copy2(catalog_path, tmp_path)
    catalog_path = tmp_path / 'catalog.json'
    subprocess.run([patchcrc, 'patchcrc', str(catalog_path)])
    out_zip.write(tmp_path / 'catalog.json.patched', 'Aotenjo_Data/StreamingAssets/aa/catalog.json')

    tl_asset_path = game_path / 'Aotenjo_Data' / 'StreamingAssets' / 'aa' / 'StandaloneWindows64' / 'localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle'
    tl_env = UnityPy.load(str(tl_asset_path))
    unity_version = tl_env.objects[0].assets_file.unity_version
    generator = TypeTreeGenerator(unity_version)
    generator.load_local_game(str(game_path))
    tl_env.typetree_generator = generator

    filenames = set(FILES)

    tl_json_dir_path = BASE_PATH / 'assets' / version / 'Translation'
    if not tl_json_dir_path.is_dir():
        if errstream is not None:
            errstream.write('Translation JSON file directory not found')
        return

    for obj in tl_env.objects:
        if obj.type.name == 'MonoBehaviour':
            obj_name = obj.read().m_Name
            suffix = "_zh-Hans"
            if not (obj_name.endswith(suffix) and obj_name[:-len(suffix)] in filenames):
                continue
            tree = obj.read_typetree()
            tl_json_path = tl_json_dir_path / (obj_name[:-len(suffix)] + '.json')
            with tl_json_path.open('r', encoding='utf-8') as f:
                tl = json.load(f)
            for data in tree['m_TableData']:
                m_Id = data['m_Id']
                data['m_Localized'] = tl[str(m_Id)]['value']
            obj.save_typetree(tree)
    out_zip.writestr('Aotenjo_Data/StreamingAssets/aa/StandaloneWindows64/localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle', tl_env.file.save())

    font_src_path = BASE_PATH / 'font-generation-unity' / 'Build' / 'font-generation-unity_Data' / 'sharedassets0.assets'
    font_env = UnityPy.load(str(font_src_path))
    font_generator = TypeTreeGenerator(unity_version)
    font_generator.load_local_game(str(BASE_PATH / 'font-generation-unity' / 'Build'))
    font_env.typetree_generator = font_generator

    font_monobhv_tree = next(filter(lambda obj: obj.type.name == 'MonoBehaviour' and obj.read().m_Name == 'MaruBuri-Regular SDF', font_env.objects)).read_typetree()
    font_texture_id = font_monobhv_tree['m_AtlasTextures'][0]['m_PathID']
    font_texture = font_env.assets[0][font_texture_id].read()

    sharedassets0 = UnityPy.load(str(game_path / 'Aotenjo_Data' / 'sharedassets0.assets'))
    sharedassets0.typetree_generator = generator

    orig_font_monobhv = next(filter(lambda obj: obj.type.name == 'MonoBehaviour' and obj.read().m_Name == 'chinese_general', sharedassets0.objects))
    orig_font_monobhv_tree = orig_font_monobhv.read_typetree()

    for field in ['m_Name', 'm_Script', 'material', 'm_AtlasTextures']:
        font_monobhv_tree[field] = orig_font_monobhv_tree[field]
    orig_font_monobhv.save_typetree(font_monobhv_tree)

    font_texture_id = orig_font_monobhv_tree['m_AtlasTextures'][0]['m_PathID']
    orig_font_texture = sharedassets0.assets[0][font_texture_id].read()
    orig_font_texture.image = font_texture.image
    orig_font_texture.save()

    out_zip.writestr('Aotenjo_Data/sharedassets0.assets', sharedassets0.file.save())

    level0 = UnityPy.load(str(game_path / 'Aotenjo_Data' / 'level0'))
    level0.typetree_generator = generator

    chinese_button_data = next(
        filter(
            lambda data: data.m_Name == 'ChineseButton',
            map(lambda obj: obj.read(), filter(lambda obj: obj.type.name == 'GameObject', level0.objects))
        )
    )

    chinese_button_components = map(lambda pair: pair.component.m_PathID, chinese_button_data.m_Component)
    chinese_button_rect = next(filter(lambda obj: obj.type.name == 'RectTransform', map(lambda path_id: level0.assets[0][path_id], chinese_button_components))).read()
    chinese_button_children = map(lambda pptr: level0.assets[0][pptr.m_PathID].read().m_GameObject.m_PathID, chinese_button_rect.m_Children)
    chinese_button_label = next(filter(lambda obj: obj.m_Name == 'Text (TMP)', map(lambda path_id: level0.assets[0][path_id].read(), chinese_button_children)))
    chinese_button_label_monobhv = next(filter(lambda obj: obj.type.name == 'MonoBehaviour', map(lambda pair: level0.assets[0][pair.component.m_PathID], chinese_button_label.m_Component)))
    chinese_button_label_monobhv_tree = chinese_button_label_monobhv.read_typetree()
    chinese_button_label_monobhv_tree['m_text'] = '한국어'
    chinese_button_label_monobhv.save_typetree(chinese_button_label_monobhv_tree)
    out_zip.writestr('Aotenjo_Data/level0', level0.file.save())

    # TODO: script unity side to auto-build the font project with proper charset
    # TODO: replace QQ logo with discord logo

    out_zip.close()


def main():
    parser = argparse.ArgumentParser(
        prog='x.py',
        description='handle game assets'
    )
    subparsers = parser.add_subparsers(dest='subcommand', title='subcommands')

    parser_extract = subparsers.add_parser('extract', help='extract relevant game assets')
    parser_extract.add_argument('-v', '--version', required=True, help='version of game being extracted')
    parser_extract.add_argument('-p', '--prev_version', help='previous version of game that has been extracted (Optional, Used in generation of translation json files)')
    parser_extract.add_argument('--dir', default=r"D:\Program Files (x86)\Steam\steamapps\common\Aotenjo", help='base directory of game (default: %(default)s)')

    parser_make_charset = subparsers.add_parser('make-charset', help='generate character set file')
    parser_make_charset.add_argument('-v', '--version', required=True, help='version of game')

    parser_make_patch = subparsers.add_parser('make-zip', help='generate patch')
    parser_make_patch.add_argument('-v', '--version', required=True, help='version of game')
    parser_make_patch.add_argument('-a', '--addressablestools', required=True, help='path to Example.exe from nesrak\'s AddressablesTools')
    parser_make_patch.add_argument('--dir', default=r"D:\Program Files (x86)\Steam\steamapps\common\Aotenjo", help='base directory of game (default: %(default)s)')

    args = parser.parse_args()

    if args.subcommand == 'extract':
        extract(args.version, args.prev_version, args.dir, errstream=sys.stderr)
    elif args.subcommand == 'make-charset':
        make_charset(args.version)
    elif args.subcommand == 'make-zip':
        make_zip(args.version, args.dir, args.addressablestools, errstream=sys.stderr)

if __name__ == '__main__':
    main()