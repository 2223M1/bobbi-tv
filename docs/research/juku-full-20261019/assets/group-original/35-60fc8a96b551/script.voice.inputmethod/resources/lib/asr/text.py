"""Text spacing and low-level token validation; no library import or alias rewriting."""
from pathlib import Path
import re

def display_text(text):
    # Vosk inserts token spaces between Chinese words. Keep Latin word spacing.
    return re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])', '', text.strip())

def vocabulary(tokens_path):
    return {line.rsplit(maxsplit=1)[0] for line in Path(tokens_path).read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.startswith('<')}

def validate_hotwords(path, symbols):
    """Upstream calls exit() for an unknown token: reject it safely in Python."""
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('热词文件过大。')
    rows = path.read_text(encoding='utf-8').splitlines()
    for row in rows:
        pieces = row.split()
        if not pieces or any(piece not in symbols for piece in pieces):
            raise ValueError('热词文件含有当前模型不支持的词元，请重新更新词库。')
    return len(rows)
