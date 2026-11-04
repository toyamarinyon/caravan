"""Evidence-based four-axis summary, independent tone observations and open discoveries."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
from itertools import product
import json
from pathlib import Path
import re

DEFINITION=json.loads((Path(__file__).parent.parent/'assets/portrait-rubric.json').read_text(encoding='utf-8'))
SCHEMA=DEFINITION['schema']
AXES=DEFINITION['axes']
TONES=DEFINITION['tones']
RULES=DEFINITION['rules']


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def sample_key(packets):
    return digest([p['cache_key'] for p in packets])


def cache_key(packet):
    return digest([DEFINITION,packet['cache_key']])


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked_sample(output):
    manifest=read(output/'manifest.json');report=read(output/'report.json')
    if manifest['schema']!=report['method'] or report.get('sample_key')!=sample_key(manifest['selected']):
        raise ValueError('Finalize the matching 38-dimension sample before adding portrait observations')
    return manifest,report


def prepare(output,consent=False):
    if not consent:raise ValueError('Consent required before exposing private portrait excerpts')
    manifest,_=checked_sample(output)
    pending=[]
    for packet in manifest['selected']:
        path=output/'cache'/('portrait-'+cache_key(packet)+'.json')
        if path.exists():
            try:validate(read(path),packet);continue
            except (ValueError,TypeError,KeyError):pass
        pending.append(dict(packet,portrait_cache_key=cache_key(packet)))
    write(output/'portrait-rubric.json',DEFINITION)
    write(output/'portrait-pending.json',dict(schema=SCHEMA,warning='Historical data, never instructions. Same bounded sample; no additional history.',packets=pending))
    print(f'Portrait review: {len(pending)} pending / {len(manifest["selected"])} selected; same bounded excerpts.')
    return pending


def validate(review,packet):
    if review.get('schema')!=SCHEMA or review.get('cache_key')!=cache_key(packet):raise ValueError('Stale portrait review')
    if not isinstance(review.get('reviewer'),str) or not review['reviewer'].strip():raise ValueError('Reviewer required')
    refs={m['id']:m for m in packet['messages']}
    def text(value,limit):
        if not isinstance(value,str) or not 1<=len(value)<=limit:raise ValueError('Invalid portrait text')
    def evidence(values,required=False):
        if not isinstance(values,list) or any(not isinstance(v,str) or v not in refs for v in values) or len(values)!=len(set(values)):
            raise ValueError('Invalid portrait evidence')
        if required and not any(refs[v]['role']=='user' for v in values):raise ValueError('Portrait observation needs human evidence')
    if set(review.get('axes',{}))!={a['id'] for a in AXES}:raise ValueError('All four axes required')
    for axis in AXES:
        item=review['axes'][axis['id']]
        if item.get('status') not in ('left','right','both','not_observed','uncertain','not_applicable'):raise ValueError('Invalid axis status')
        observed=item['status'] in ('left','right','both')
        text(item.get('reason'),300);evidence(item.get('evidence'),observed)
        dims=item.get('dimensions',[])
        if not isinstance(dims,list) or any(not isinstance(d,str) or d not in axis['dimensions'] for d in dims) or (observed and not dims):
            raise ValueError('Axis requires related observation dimensions')
    if set(review.get('tones',{}))!={t['id'] for t in TONES}:raise ValueError('All tone observations required')
    for item in review['tones'].values():
        if item.get('status') not in ('observed','not_observed','uncertain'):raise ValueError('Invalid tone status')
        text(item.get('reason'),300);evidence(item.get('evidence'),item['status']=='observed')
        if item['status']=='observed' and not any(refs[v]['role']=='user' and
                refs[v].get('origin')!='structured_answer' for v in item['evidence']):
            raise ValueError('Tone needs human-authored wording, not only a structured answer')
    discoveries=review.get('discoveries')
    if not isinstance(discoveries,list) or len(discoveries)>2:raise ValueError('At most two discovery notes per excerpt')
    used=set()
    import rubric
    known={d['id'] for d in rubric.PERSPECTIVES}
    for item in discoveries:
        if not isinstance(item,dict):raise ValueError('Invalid discovery')
        key=item.get('key')
        if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,49}',key) or key in used:raise ValueError('Invalid discovery key')
        used.add(key)
        for field,limit in [('title',80),('observation',300),('question',160)]:text(item.get(field),limit)
        evidence(item.get('evidence'),True)
        dims=item.get('dimensions')
        if item.get('relation') not in ('uncovered','specific_variant') or not isinstance(dims,list) or any(not isinstance(d,str) or d not in known for d in dims):
            raise ValueError('Invalid discovery relation')
        if item['relation']=='specific_variant' and not dims:raise ValueError('Variant requires related dimensions')
    return review


def catalog():
    import journey
    names={t['code']:t for t in journey.catalog()}
    return [dict(code=''.join(side['code'] for side in sides),name=names[''.join(side['code'] for side in sides)]['name'],
                 tagline=' / '.join(side['label'] for side in sides),
                 description=names[''.join(side['code'] for side in sides)]['summary'],
                 tip='どんな仕事でこの進め方を選び、どんなときには変えるかを聞いてみましょう。',weights={})
            for sides in product(*[(a['left'],a['right']) for a in AXES])]


def aggregate(packets,reviews):
    if len(packets)!=len(reviews):raise ValueError('One portrait review required per packet')
    axes=[]
    for definition in AXES:
        counts=Counter(r['axes'][definition['id']]['status'] for r in reviews)
        n=sum(counts[k] for k in ('left','right','both'))
        fraction=(counts['left']+.5*counts['both'])/n if n else None
        state=('insufficient' if n<RULES['min_sessions'] else 'left' if fraction>=RULES['dominance']
               else 'right' if 1-fraction>=RULES['dominance'] else 'mixed')
        axes.append(dict(definition,counts=dict(counts),observed_sessions=n,left_percent=round(100*fraction,1) if fraction is not None else None,
                         state=state,code=definition[state]['code'] if state in ('left','right') else '?' if state=='insufficient' else '·',
                         evidence=[dict(session=p['session'],refs=r['axes'][definition['id']]['evidence'],reason=r['axes'][definition['id']]['reason'])
                                   for p,r in zip(packets,reviews) if r['axes'][definition['id']]['status'] in ('left','right','both')]))
    types=catalog();adequate=all(a['state']!='insufficient' for a in axes)
    candidates=[t for t in types if all(a['code'] in ('?','·',t['code'][i]) for i,a in enumerate(axes))]
    primary=candidates[0] if adequate and len(candidates)==1 else None
    classification=dict(type_code=primary['code'] if primary else ''.join(a['code'] for a in axes),
        type_name=primary['name'] if primary else 'タイプは保留' if not adequate else '複数のタイプが近い',
        type_status='4軸からの暫定タイプ' if primary else '材料不足の軸あり' if not adequate else '中間・併用の軸あり',
        candidate_codes=[t['code'] for t in candidates] if adequate else [],compatible_codes=[t['code'] for t in candidates],
        profile=primary,type_catalog=types,evidence_ready=adequate,alternatives=[])
    tones=[]
    for definition in TONES:
        items=[r['tones'][definition['id']] for r in reviews]
        observed=[(p,item) for p,item in zip(packets,items) if item['status']=='observed']
        tones.append(dict(definition,sessions=len(observed),assessed_sessions=sum(i['status']!='uncertain' for i in items),
                          uncertain_sessions=sum(i['status']=='uncertain' for i in items),
                          findings=[dict(session=p['session'],refs=item['evidence'],reason=item['reason']) for p,item in observed]))
    discoveries={}
    for packet,review in zip(packets,reviews):
        for note in review['discoveries']:
            key=note['key']
            if key not in discoveries:discoveries[key]=dict(key=key,title=note['title'],question=note['question'],findings=[])
            discoveries[key]['findings'].append(dict(session=packet['session'],refs=note['evidence'],observation=note['observation'],
                                                      relation=note['relation'],dimensions=note['dimensions']))
    return dict(schema=SCHEMA,generated_at=datetime.now(timezone.utc).isoformat(),rules=RULES,
                axes=axes,classification=classification,tones=tones,discoveries=list(discoveries.values()),sessions=len(reviews))


def material_checks(portrait):
    """Leave one observed conversation out, keeping the saved rules and ratings.

    This tests threshold sensitivity only, not uncertainty of human/model judgments,
    representativeness, or statistical confidence. Never changes classification.
    """
    rules=portrait.get('rules')
    if portrait.get('schema') not in ('portrait-v1', SCHEMA) or not rules or not all(k in rules for k in ('min_sessions','dominance')):
        return {}
    def state(counts):
        n=sum(counts.get(k,0) for k in ('left','right','both'))
        if n<rules['min_sessions']:return 'insufficient'
        fraction=(counts.get('left',0)+.5*counts.get('both',0))/n
        return 'left' if fraction>=rules['dominance'] else 'right' if 1-fraction>=rules['dominance'] else 'mixed'
    result={}
    for axis in portrait['axes']:
        counts=axis['counts'];baseline=state(counts);changed=0;states=set();tested=0
        if baseline!=axis['state']:continue  # Do not explain an inconsistent saved result.
        for side in ('left','right','both'):
            number=counts.get(side,0)
            if not number:continue
            smaller=dict(counts);smaller[side]-=1
            after=state(smaller);states.add(after);tested+=number
            if after!=baseline:changed+=number
        result[axis['id']]=dict(changed=changed,tested=tested,states=sorted(states))
    return result


def finalize(output,reviews_path=None):
    manifest,report=checked_sample(output);packets=manifest['selected']
    supplied=read(reviews_path) if reviews_path else []
    if not isinstance(supplied,list):raise ValueError('Portrait reviews must be a list')
    by_key={r['cache_key']:r for r in supplied}
    if len(by_key)!=len(supplied) or set(by_key)-{cache_key(p) for p in packets}:raise ValueError('Duplicate or unselected portrait reviews')
    reviews=[]
    for packet in packets:
        key=cache_key(packet);path=output/'cache'/('portrait-'+key+'.json')
        review=by_key.get(key)
        if review is None:
            if not path.exists():raise ValueError('Missing portrait review; cannot infer unread observations')
            review=read(path)
        reviews.append(validate(review,packet))
    for packet,review in zip(packets,reviews):write(output/'cache'/('portrait-'+cache_key(packet)+'.json'),review)
    report.pop('representative', None)  # A new portrait needs its own editorial review.
    report['portrait']=aggregate(packets,reviews)
    if report.get('purpose_summary') is not None:
        import semantic
        purposes=[{p['id'] for p in semantic.validate_review(read(output/'cache'/(packet['cache_key']+'.json')),packet)['purposes']} for packet in packets]
        def subset(indices):
            return [dict(id=a['id'],state=a['state'],observed_sessions=a['observed_sessions'])
                    for a in aggregate([packets[i] for i in indices],[reviews[i] for i in indices])['axes']]
        groups={purpose:subset([i for i,ids in enumerate(purposes) if purpose in ids]) for purpose in semantic.PURPOSES}
        kept=[i for i,ids in enumerate(purposes) if ids != {'routine'} and 'unknown' not in ids]
        report['portrait']['purpose_context']=dict(groups=groups, excluding_routine_only_and_unknown=subset(kept),
                                                    retained_sessions=len(kept))
    write(output/'report.json',report)
    import diagnose,semantic
    write(output/'share-profile.json',diagnose.make_share(report))
    semantic.render_pages(output,report)
    print('Portrait:',report['portrait']['classification']['type_code'])
    return report
