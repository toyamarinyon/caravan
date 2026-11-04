"""Versioned private result backups. Standard library only; never restores code/logs."""
import copy
import json
import math
from pathlib import Path
import tempfile

SCHEMA = 'caravan-private-backup-v1'
LIMIT = 8 * 1024 * 1024
METHODS = {'semantic-18-v1', 'semantic-26-v2', 'semantic-38-v3', 'semantic-38-v4'}


def validate(value):
    nodes = 0
    def walk(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 30 or nodes > 150000:
            raise ValueError('Backup is too complex')
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ('__proto__', 'prototype', 'constructor'):
                    raise ValueError('Unsupported object key')
                walk(child, depth + 1)
        elif isinstance(item, list):
            for child in item: walk(child, depth + 1)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError('Non-finite number')
    walk(value)
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError('本人用バックアップではないか、未対応の版です。共有用JSONからは復元できません。')
    if set(value) != {'schema', 'report', 'execution_audit'}:
        raise ValueError('Unexpected backup fields')
    report = value['report']
    if not isinstance(report, dict) or report.get('method') not in METHODS:
        raise ValueError('Unsupported analysis method')
    if not isinstance(report.get('perspectives'), list) or not 18 <= len(report['perspectives']) <= 38:
        raise ValueError('Invalid observations')
    ids = [p.get('id') for p in report['perspectives'] if isinstance(p, dict)]
    import rubric
    known = {p['id'] for p in rubric.PERSPECTIVES}
    if len(ids) != len(report['perspectives']) or any(not isinstance(i,str) for i in ids) or len(set(ids)) != len(ids) or any(i not in known for i in ids):
        raise ValueError('Unknown or duplicate observation')
    for key in ('sessions', 'messages', 'days'):
        if type(report.get(key)) is not int or report[key] < (1 if key == 'days' else 0):
            raise ValueError('Invalid counts')
    if not isinstance(report.get('generated_at'), str): raise ValueError('Missing analysis date')
    if report.get('portrait') and (not isinstance(report['portrait'],dict) or report['portrait'].get('schema') not in ('portrait-v1', 'portrait-v2')):
        raise ValueError('Unsupported portrait method')
    if 'practices' in report:
        import practices
        practices.validate_saved(report['practices'], report)
    audit = value['execution_audit']
    if audit is not None and (not isinstance(audit, dict) or audit.get('schema') != 'execution-events-v1'):
        raise ValueError('Unsupported execution audit')
    # Presentation assets are always from the installed skill, never imported URLs/code.
    if any(k in report for k in ('journey', 'rendered_at', 'private_backup', 'execution_audit', 'material_checks')):
        raise ValueError('Backup must contain the saved analysis, not presentation assets')
    return value


LEGACY_FIELDS = ('type_code', 'type_name', 'profile', 'type_status', 'candidate_codes',
                 'alternatives', 'type_catalog', 'repeated_dimensions', 'evidence_ready')


def current_report(report):
    """Keep evidence intact; export only the active classification and current labels."""
    report = copy.deepcopy(report)
    if report.get('portrait', {}).get('schema') in ('portrait-v1', 'portrait-v2'):
        import journey
        for key in LEGACY_FIELDS:
            report.pop(key, None)
        names = {t['code']: t for t in journey.catalog()}
        style = report['portrait']['classification']
        for item in style.get('type_catalog', []) + style.get('alternatives', []) + ([style['profile']] if style.get('profile') else []):
            if item.get('code') in names:
                entry = names[item['code']]
                item['name'] = entry['name']
                if 'description' in item: item['description'] = entry['summary']
        if style.get('profile') and style['profile']['code'] in names:
            style['type_name'] = names[style['profile']['code']]['name']
    return report


def bundle(report, audit=None):
    return validate(dict(schema=SCHEMA, report=current_report(report), execution_audit=copy.deepcopy(audit)))


def read(path):
    if path.stat().st_size > LIMIT: raise ValueError('Backup exceeds 8 MiB')
    return validate(json.loads(path.read_text(encoding='utf-8')))


def export(output, destination):
    if destination.resolve() in {(output/name).resolve() for name in ('report.json','execution-audit.json','share-profile.json','index.html','developer.html','manifest.json','pending.json')}:
        raise ValueError('Do not overwrite analysis files with a backup')
    report = json.loads((output/'report.json').read_text(encoding='utf-8'))
    audit_path = output/'execution-audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else None
    value = bundle(report, audit)
    payload=json.dumps(value, ensure_ascii=False, indent=2)
    if len(payload.encode('utf-8'))>LIMIT:raise ValueError('Backup exceeds 8 MiB')
    destination.write_text(payload, encoding='utf-8')
    return value


def restore(source, output, replace=False):
    """Render and validate in staging before replacing any of the fixed files."""
    import semantic
    import diagnose
    value = read(source)
    names = ['report.json', 'execution-audit.json', 'share-profile.json', 'index.html', 'developer.html']
    if not replace and any((output/name).exists() for name in names):
        raise ValueError('Output already contains results; use a new output or --replace explicitly')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='caravan-restore-', dir=output.parent) as directory:
        staging = Path(directory)
        if not staging.resolve().is_relative_to(output.parent.resolve()):
            raise ValueError('Restore staging escaped the selected workspace')
        semantic.write(staging/'report.json', value['report'])
        if value['execution_audit'] is not None: semantic.write(staging/'execution-audit.json', value['execution_audit'])
        try:
            semantic.write(staging/'share-profile.json', diagnose.make_share(value['report']))
            semantic.render_pages(staging)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
            raise ValueError('Backup has incomplete or incompatible analysis data') from error
        output.mkdir(parents=True, exist_ok=True)
        previous = {name: (output/name).read_bytes() if (output/name).exists() else None for name in names}
        if (output/'report.json').exists(): export(output, output/'before-restore.backup.json')
        try:
            for name in names:
                target = output/name
                if (staging/name).exists(): target.write_bytes((staging/name).read_bytes())
                elif target.exists(): target.unlink()  # Do not keep another result's execution audit.
        except OSError:
            for name, data in previous.items():
                target = output/name
                if data is not None: target.write_bytes(data)
                elif target.exists(): target.unlink()
            raise
    return value
