"""Travel names and embedded artwork: a presentation layer, never diagnostic evidence."""
import base64
import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / 'assets'


def catalog():
    return json.loads((ASSETS / 'journey-types.json').read_text(encoding='utf-8'))['types']


def presentation(report):
    if report.get('portrait', {}).get('schema') not in ('portrait-v1', 'portrait-v2'):
        return None
    types = []
    for item in catalog():
        entry = {key: item[key] for key in ('code', 'name', 'summary', 'alt')}
        image = ASSETS / 'journey' / (item['code'] + '.jpg')
        if image.exists():
            entry['image'] = 'data:image/jpeg;base64,' + base64.b64encode(image.read_bytes()).decode('ascii')
        types.append(entry)
    return dict(version='journey-v1', types=types)
