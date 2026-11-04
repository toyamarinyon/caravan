"""Deterministic coverage and bounded contiguous windows; standard library only."""
from collections import defaultdict
import hashlib
import json
import execution

VERSION = 'source-month-project-v2'
WINDOW_VERSION = 'bounded-context-v6'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ordered_sessions(sessions, seed='caravan-v2'):
    """Give sources a turn, then months a turn, then projects a turn.

    Hash ordering removes chronological prefix bias while retaining reproducibility.
    This is coverage sampling, not a usage-proportional population estimate.
    """
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for session in sessions:
        groups[session['source']][session['date'][:7]][session['project']].append(session)
    queues = {}
    for source, months in groups.items():
        month_queues = {}
        for month, projects in months.items():
            keys = sorted(projects, key=lambda k: digest([seed, source, month, k]))
            for rows in projects.values():
                rows.sort(key=lambda s: digest([seed, s['key']]))
            queue = []
            while any(projects.values()):
                for key in keys:
                    if projects[key]:
                        queue.append(projects[key].pop(0))
            month_queues[month] = queue
        keys = sorted(months, key=lambda m: digest([seed, source, m]))
        queue = []
        while any(month_queues.values()):
            for key in keys:
                if month_queues[key]:
                    queue.append(month_queues[key].pop(0))
        queues[source] = queue
    ordered = []
    while any(queues.values()):
        for source in sorted(queues):
            if queues[source]:
                ordered.append(queues[source].pop(0))
    return ordered


def _allocate(lengths, budget):
    """Water-fill; preserve short messages and share the rest among long ones."""
    amounts = [0] * len(lengths)
    remaining = budget
    while remaining:
        active = [i for i, length in enumerate(lengths) if amounts[i] < length]
        if not active:
            break
        step = max(1, remaining // len(active))
        for i in active:
            used = min(step, lengths[i] - amounts[i], remaining)
            amounts[i] += used
            remaining -= used
    return amounts


def window(session, char_limit, rubric, seed='caravan-v2'):
    messages = session['messages']
    starts = [i for i, m in enumerate(messages) if m['role'] == 'user'
              and any(x['role'] == 'assistant' for x in messages[i+1:i+3])]
    if not starts:
        starts = [next(i for i, m in enumerate(messages) if m['role'] == 'user')]
    # Prefer eligible starts with a subsequent human reaction when available.
    reactions = [i for i in starts if any(m['role'] == 'user' for m in messages[i+2:i+5])]
    candidates = reactions or starts
    anchor = candidates[int(digest([seed, session['key'], 'window']), 16) % len(candidates)]
    # Retain the preceding response so "then fix it" is not detached from context.
    start = anchor-1 if anchor and messages[anchor-1]['role']=='assistant' else anchor
    windows = [list(range(start, min(start + 5, len(messages))))]
    # A second scene must be separated by at least one omitted message. It is
    # selected by position, never by content or a desired behavior.
    alternatives = []
    for candidate in candidates:
        other = candidate - 1 if candidate and messages[candidate-1]['role'] == 'assistant' else candidate
        indices = list(range(other, min(other + 5, len(messages))))
        if indices and (indices[-1] + 1 < windows[0][0] or windows[0][-1] + 1 < indices[0]):
            alternatives.append(indices)
    if alternatives:
        windows.append(alternatives[int(digest([seed, session['key'], 'second-scene']), 16) % len(alternatives)])
    windows.sort(key=lambda indices: indices[0])
    chosen = [messages[i] for indices in windows for i in indices]
    # Do not pull execution events from the unselected gap between scenes.
    facts = execution.excerpt(session.get('execution'), messages[windows[0][0]]['date'],
                              messages[windows[0][-1]]['date'], min(600, char_limit // 3))
    remaining = max(0, char_limit - execution.size(facts))
    lengths = [len(m['text']) for m in chosen]
    amounts = _allocate(lengths, remaining)
    scene_by_id = {messages[i]['id']: n + 1 for n, indices in enumerate(windows) for i in indices}
    excerpts = [dict(id=m['id'], role=m['role'], origin=m.get('origin','message'), text=m['text'][:amount],
                     truncated=amount < len(m['text']), scene=scene_by_id[m['id']]) for m, amount in zip(chosen, amounts)]
    quality = dict(messages=len(excerpts), truncated_messages=sum(m['truncated'] for m in excerpts),
                   complete_messages=sum(not m['truncated'] for m in excerpts),
                   has_human_followup=any(a['scene']==b['scene']==c['scene'] and a['role']=='user' and b['role']=='assistant' and c['role']=='user'
                       for i,a in enumerate(excerpts) for j,b in enumerate(excerpts[i+1:],i+1) for c in excerpts[j+1:]),
                   scenes=len(windows), position='multiple' if len(windows)>1 else 'start' if start==0 else 'end' if start+5>=len(messages) else 'middle')
    return dict(session=session['key'], source=session['source'], messages=excerpts, execution=facts,
                omitted_messages=len(messages)-len(excerpts), fingerprint=session['fingerprint'],
                quality=quality,
                cache_key=digest([rubric, WINDOW_VERSION, session['fingerprint'], excerpts, facts]))


def pack(sessions, budget, rubric, seed='caravan-v2'):
    """Reallocate unused input budget to the same selected windows, never exceed it.

    At most 4,000 characters per window prevents one long session taking the pool.
    More context does not create another independent observation or another review.
    """
    if not sessions:
        return []
    limits = [min(2000, budget // len(sessions))] * len(sessions)
    packets = [window(s, n, rubric, seed) for s, n in zip(sessions, limits)]
    def cost(p):
        return sum(len(m['text']) for m in p['messages']) + execution.size(p['execution'])
    remaining = budget - sum(map(cost, packets))
    while remaining > 0:
        active = [i for i, p in enumerate(packets) if p['quality']['truncated_messages'] and limits[i] < 4000]
        if not active:
            break
        allowance = max(1, remaining // len(active))
        spent = 0
        for i in active:
            old = cost(packets[i])
            limits[i] = min(4000, old + min(allowance, remaining))
            candidate = window(sessions[i], limits[i], rubric, seed)
            delta = cost(candidate) - old
            if 0 <= delta <= remaining:
                packets[i] = candidate
                remaining -= delta
                spent += delta
        if not spent:
            break
    assert sum(map(cost, packets)) <= budget
    return packets


def coverage(eligible, selected_sessions, packets, budget):
    """Aggregate diagnostics only; never include text, paths, session/project IDs."""
    from collections import Counter
    selected = {s['key'] for s in selected_sessions}
    months = sorted({s['date'][:7] for s in eligible})
    return dict(
        months=[dict(month=m, eligible=sum(s['date'].startswith(m) for s in eligible),
                     selected=sum(s['date'].startswith(m) and s['key'] in selected for s in eligible)) for m in months],
        eligible_projects=len({s['project'] for s in eligible}),
        selected_projects=len({s['project'] for s in selected_sessions}),
        messages=sum(len(p['messages']) for p in packets),
        truncated_messages=sum(m['truncated'] for p in packets for m in p['messages']),
        followup_windows=sum(p['quality']['has_human_followup'] for p in packets),
        positions=dict(Counter(p['quality']['position'] for p in packets)),
        budget_unused=budget-sum(sum(len(m['text']) for m in p['messages'])+execution.size(p['execution']) for p in packets),
        max_dimension_ratings=38*len(packets))
