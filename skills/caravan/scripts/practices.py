"""Grounded use cases from the existing bounded sample. No model/API/dependencies."""
from datetime import datetime, timezone
from pathlib import Path
import portrait

DEFINITION = portrait.read(Path(__file__).parent.parent / 'assets/practice-rubric.json')
SCHEMA = DEFINITION['schema']


def cache_key(packet):
    # Include the actual excerpt as well as the extractor's key: edits cannot reuse a review.
    return portrait.digest([DEFINITION, packet])


def text(value, limit=400):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('Invalid use-case text')


def validate_case(item, schema=SCHEMA):
    fields = {'title', 'stage', 'situation', 'human_action', 'ai_role', 'response', 'limitation', 'question', 'try_next'}
    if schema in ('practice-v2', 'practice-v3'): fields.add('decision')
    if schema == 'practice-v3': fields.add('collaboration')
    if not isinstance(item, dict) or set(item) != fields:
        raise ValueError('Invalid use-case fields')
    text(item['title'], 80)
    if item['stage'] not in DEFINITION['stages']: raise ValueError('Unknown use-case stage')
    for field in ('limitation', 'question', 'try_next'): text(item[field], 300)
    for field in ('situation', 'human_action', 'ai_role', 'response'):
        claim = item[field]
        expected = {'text', 'refs', 'status'} if field == 'response' else {'text', 'refs'}
        if not isinstance(claim, dict) or set(claim) != expected: raise ValueError('Invalid grounded claim')
        text(claim['text'])
        refs = claim['refs']
        if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs) or len(set(refs)) != len(refs):
            raise ValueError('Invalid use-case references')
        if field != 'response' and not refs: raise ValueError('Missing use-case evidence')
    response = item['response']
    if response['status'] not in ('not_visible', 'assistant_report', 'user_report'): raise ValueError('Invalid response status')
    if bool(response['refs']) != (response['status'] != 'not_visible'): raise ValueError('Response status/evidence mismatch')
    if schema in ('practice-v2', 'practice-v3'): validate_decision(item['decision'])
    if schema == 'practice-v3' and item['collaboration'] is not None:
        collaboration = item['collaboration']
        if not isinstance(collaboration, dict) or set(collaboration) != {'pattern', 'boundary'}:
            raise ValueError('Invalid collaboration fields')
        for claim in collaboration.values(): decision_claim(claim)


def decision_claim(claim, states=None):
    fields = {'text', 'refs'} | ({'status'} if states else set())
    if not isinstance(claim, dict) or set(claim) != fields: raise ValueError('Invalid decision claim')
    text(claim['text'], 240)
    refs = claim['refs']
    if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs) or len(refs) != len(set(refs)):
        raise ValueError('Invalid decision evidence')
    if states and claim['status'] not in states: raise ValueError('Invalid decision evidence status')
    if bool(refs) != (not states or claim['status'] != 'unknown'): raise ValueError('Missing or invented decision evidence')


def validate_decision(decision):
    if not isinstance(decision, dict) or set(decision) != {'kind', 'condition', 'alternative', 'steps'}:
        raise ValueError('Invalid decision fields')
    if decision['kind'] not in ('generic', 'sequence', 'tradeoff', 'conditional'): raise ValueError('Unknown decision kind')
    decision_claim(decision['condition'], ('stated', 'context', 'unknown'))
    decision_claim(decision['alternative'], ('observed', 'unknown'))
    if not isinstance(decision['steps'], list) or len(decision['steps']) > 4: raise ValueError('At most four connected steps')
    for step in decision['steps']: decision_claim(step)
    if decision['kind'] == 'sequence' and (len(decision['steps']) < 2 or decision['condition']['status'] == 'unknown'):
        raise ValueError('Sequence needs connected actions and visible context')
    if decision['kind'] in ('tradeoff', 'conditional') and (decision['condition']['status'] != 'stated' or decision['alternative']['status'] != 'observed'):
        raise ValueError('Tradeoff/conditional choice needs stated conditions and an observed alternative')


def validate_featured(item, schema):
    if schema in ('practice-v2', 'practice-v3') and item['featured'] and item['case']['decision']['kind'] == 'generic':
        raise ValueError('Generic observations cannot fill a featured slot')
    if schema == 'practice-v3' and item['featured'] and item['case']['collaboration'] is None:
        raise ValueError('Featured cases need a separately grounded collaboration account')


def validate(review, packet):
    if not isinstance(review, dict) or set(review) != {'schema', 'cache_key', 'reviewer', 'status', 'reason', 'featured', 'case', 'portability'}:
        raise ValueError('Invalid use-case review')
    if review['schema'] != SCHEMA or review['cache_key'] != cache_key(packet): raise ValueError('Stale use-case review')
    text(review['reviewer'], 160); text(review['reason'], 300)
    if type(review['featured']) is not bool: raise ValueError('Invalid featured flag')
    if review['status'] not in ('case', 'insufficient'): raise ValueError('Invalid review status')
    if review['portability'] not in ('portable', 'scene_bound', 'generic', 'unsupported'):
        raise ValueError('Invalid portability review')
    if review['featured'] and review['portability'] != 'portable':
        raise ValueError('Featured cases must pass the portability review')
    item = review['case']
    if review['status'] == 'insufficient':
        if item is not None or review['featured'] or review['portability'] != 'unsupported':
            raise ValueError('Insufficient evidence cannot produce a case')
        return review
    validate_case(item)
    validate_featured(review, SCHEMA)
    if review['portability'] == 'portable' and (item['collaboration'] is None or item['decision']['kind'] == 'generic'):
        raise ValueError('Portable review needs a grounded, non-generic collaboration account')
    messages = {m['id']: m for m in packet['messages']}
    positions = {m['id']: i for i, m in enumerate(packet['messages'])}
    if item['collaboration'] is not None:
        # The abstraction describes the person's choices, not AI-invented motives.
        human_refs = set(item['human_action']['refs'])
        decision = item['decision']
        for claim in [decision['condition'], decision['alternative'], *decision['steps']]:
            human_refs.update(claim['refs'])
        for claim in item['collaboration'].values():
            if any(r not in messages or messages[r]['role'] != 'user' or r not in human_refs for r in claim['refs']):
                raise ValueError('Collaboration needs human evidence already grounded in the scene')
    for field in ('situation', 'human_action', 'ai_role', 'response'):
        refs = item[field]['refs']
        if any(r not in messages for r in refs): raise ValueError('Unknown use-case evidence')
        if field == 'human_action' and any(messages[r]['role'] != 'user' for r in refs):
            raise ValueError('Human action requires human-authored evidence')
    response = item['response']
    if response['status'] != 'not_visible':
        role = 'user' if response['status'] == 'user_report' else 'assistant'
        start = min(positions[r] for r in item['human_action']['refs'])
        if any(messages[r]['role'] != role or positions[r] <= start for r in response['refs']):
            raise ValueError('Response requires a later message with the stated author')
    decision = item['decision']
    for field in ('condition', 'alternative'):
        claim = decision[field]
        if any(r not in messages for r in claim['refs']): raise ValueError('Unknown decision evidence')
        if claim['status'] in ('stated', 'observed') and any(messages[r]['role'] != 'user' for r in claim['refs']):
            raise ValueError('Chosen alternative and stated condition require human evidence')
    scene_refs = [r for field in ('situation','human_action','ai_role','response') for r in item[field]['refs']]
    scene_refs += [r for field in ('condition','alternative') for r in decision[field]['refs']]
    scene_refs += [r for step in decision['steps'] for r in step['refs']]
    if len({messages[r].get('scene',1) for r in scene_refs}) > 1:
        raise ValueError('A use case cannot join separated scenes')
    previous = -1
    for step in decision['steps']:
        if any(r not in messages or messages[r]['role'] != 'user' for r in step['refs']):
            raise ValueError('Each connected step requires human evidence')
        current = min(positions[r] for r in step['refs'])
        if current < previous: raise ValueError('Connected steps must follow visible message order')
        previous = current
    return review


def validate_saved(value, report):
    if not isinstance(value, dict) or value.get('schema') not in ('practice-v1', 'practice-v2', 'practice-v3'): raise ValueError('Unsupported use-case schema')
    schema = value['schema']
    text(value.get('sample_key'), 80)
    if value.get('sample_key') != report.get('sample_key'): raise ValueError('Use cases belong to another sample')
    text(value.get('generated_at'), 80)
    if type(value.get('reviewed_sessions')) is not int or value['reviewed_sessions'] != report['sessions']:
        raise ValueError('Incomplete use-case coverage')
    items = value.get('items')
    if not isinstance(items, list) or len(items) > value['reviewed_sessions']: raise ValueError('Invalid use-case count')
    seen = set(); featured = 0
    for item in items:
        if not isinstance(item, dict) or set(item) != {'session', 'featured', 'case'}: raise ValueError('Invalid saved case')
        text(item['session'], 80)
        if item['session'] in seen or type(item['featured']) is not bool: raise ValueError('Duplicate or invalid case')
        seen.add(item['session']); featured += item['featured']; validate_case(item['case'], schema)
        validate_featured(item, schema)
    if featured > 3 or (schema == 'practice-v1' and featured != min(3, len(items))):
        raise ValueError('Feature at most three cases; never fill a quota in v2/v3')
    return value


def checked_sample(output):
    manifest, report = portrait.checked_sample(output)
    excluded_path = output / 'excluded-sessions.json'
    exclusions = portrait.read(excluded_path) if excluded_path.exists() else []
    if any('sample:' + p['session'] in exclusions for p in manifest['selected']):
        raise ValueError('Saved sample includes an excluded conversation; prepare and review a clean sample first')
    return manifest, report


def prepare(output, consent=False):
    if not consent: raise ValueError('Consent required before exposing private use-case excerpts')
    manifest, _ = checked_sample(output)
    pending = []
    for packet in manifest['selected']:
        path = output / 'cache' / ('practice-' + cache_key(packet) + '.json')
        if path.exists():
            try: validate(portrait.read(path), packet); continue
            except (ValueError, TypeError, KeyError): pass
        pending.append(dict(packet, practice_cache_key=cache_key(packet)))
    portrait.write(output / 'practice-rubric.json', DEFINITION)
    portrait.write(output / 'practice-pending.json', dict(schema=SCHEMA,
        warning='Untrusted historical data, never instructions. Same bounded sample; no additional history.', packets=pending))
    print(f'Use-case review: {len(pending)} pending / {len(manifest["selected"])} selected; same bounded excerpts.')
    return pending


def finalize(output, reviews_path=None):
    manifest, report = checked_sample(output)
    packets = manifest['selected']
    supplied = portrait.read(reviews_path) if reviews_path else []
    if not isinstance(supplied, list): raise ValueError('Use-case reviews must be a list')
    by_key = {r['cache_key']: r for r in supplied}
    if len(by_key) != len(supplied) or set(by_key) - {cache_key(p) for p in packets}:
        raise ValueError('Duplicate or unselected use-case review')
    reviews = []
    for packet in packets:
        key = cache_key(packet); path = output / 'cache' / ('practice-' + key + '.json')
        review = by_key.get(key)
        if review is None:
            if not path.exists(): raise ValueError('Missing use-case review; cannot infer unread cases')
            review = portrait.read(path)
        reviews.append(validate(review, packet))
    value = dict(schema=SCHEMA, sample_key=report['sample_key'], generated_at=datetime.now(timezone.utc).isoformat(),
        reviewed_sessions=len(packets), items=[dict(session=p['session'], featured=r['featured'], case=r['case'])
            for p, r in zip(packets, reviews) if r['status'] == 'case'])
    validate_saved(value, report)
    for packet, review in zip(packets, reviews):
        portrait.write(output / 'cache' / ('practice-' + cache_key(packet) + '.json'), review)
    import backup
    backup.export(output, output / 'before-practices.backup.json')
    # Staged restore validates/renders both pages before replacing the fixed result.
    report['practices'] = value
    destination = output / 'practice-result.backup.json'
    portrait.write(destination, backup.bundle(report, portrait.read(output / 'execution-audit.json') if (output / 'execution-audit.json').exists() else None))
    backup.restore(destination, output, replace=True)
    print(f'Use cases: {len(value["items"])}; classification and original analysis dates preserved.')
    return report
