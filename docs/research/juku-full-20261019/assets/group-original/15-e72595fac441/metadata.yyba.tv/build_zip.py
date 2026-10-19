# -*- coding: utf-8 -*-

"""打包 metadata.yyba.tv 插件安装 zip。"""



import os

import zipfile



ADDON_ID = 'metadata.yyba.tv'

ROOT = os.path.dirname(os.path.abspath(__file__))

PARENT = os.path.dirname(ROOT)

OUTPUT = os.path.join(PARENT, f'{ADDON_ID}-install.zip')



SKIP_DIRS = {'__pycache__', '.git', '.idea'}

SKIP_EXT = {'.pyc', '.pyo'}





def should_skip(path):

    parts = set(path.replace('\\', '/').split('/'))

    if parts & SKIP_DIRS:

        return True

    return os.path.splitext(path)[1].lower() in SKIP_EXT





def main():

    if os.path.isfile(OUTPUT):

        os.remove(OUTPUT)

    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as zf:

        for dirpath, dirnames, filenames in os.walk(ROOT):

            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for name in filenames:

                full = os.path.join(dirpath, name)

                rel = os.path.relpath(full, PARENT)

                if should_skip(rel):

                    continue

                zf.write(full, rel.replace('\\', '/'))

    print('Created', OUTPUT)





if __name__ == '__main__':

    main()

