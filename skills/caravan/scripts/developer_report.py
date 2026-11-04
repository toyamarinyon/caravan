"""Standalone developer reference generated from definitions and reviewed aggregates."""
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import diagnose as base
import rubric as definitions_source
import portrait
import journey
import brand


def h(value):
    return escape(str(value), quote=True)


def table(headers, rows, css=''):
    return '<div class="table-scroll"><table class="' + css + '"><thead><tr>' + ''.join(
        '<th scope="col">' + cell + '</th>' for cell in headers) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join('<td>' + cell + '</td>' for cell in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def render(report, rubric, extractor, modes):
    rules = base.CLASSIFICATION_RULES
    definitions = [{k: v for k, v in p.items() if k != 'pattern'} for p in definitions_source.PERSPECTIVES]
    observed = {p['id']: p for p in report['perspectives']}
    catalog = report.get('type_catalog', []) if report.get('portrait') else report['type_catalog']
    vector, repeated, ranked = base.score_styles(report['perspectives'], report['sessions'], catalog)
    adequate = (report['messages'] >= rules['min_messages'] and report['sessions'] >= rules['min_sessions']
                and len(repeated) >= rules['min_repeated_dimensions'])
    eligible = [t for t in ranked if adequate and t['supported'] >= rules['min_supported_dimensions']
                and t['score'] >= rules['min_similarity']]
    candidates = {t['code'] for t in eligible if eligible[0]['score'] - t['score'] < rules['candidate_gap']}
    titles = {p['id']: p['title'] for p in definitions}
    parts = {}
    summary=report.get('portrait')
    portrait_rules=summary['rules'] if summary else portrait.RULES
    parts['PORTRAIT']=('<p>38観点の件数を機械的に二分するのではなく、同じ抜粋を読んだAIが人の根拠発言と関連する観点を添えて4軸を要約します。'
        'これはMBTIの心理軸ではなく、今回の作業での選択を整理する仮の軸です。相互独立性・再現性・閾値は未検証です。</p>'
        +table(['軸','左側','右側','読み取り条件'],[[h(a['title']),h(a['left']['code']+' '+a['left']['label']),h(a['right']['code']+' '+a['right']['label']),h(a['hint'])] for a in (summary['axes'] if summary else portrait.AXES)])
        +f'<p>各会話で left / right / both / not_observed / uncertain / not_applicable を記録。観測した1会話を1票とし、両方は左右に0.5票ずつ配分します。未観測・不明・該当場面なしは分母から除外。'
        f'各軸{portrait_rules["min_sessions"]}会話未満は材料不足。片側への配分が{100*portrait_rules["dominance"]:g}%以上ならその側、それ以外は中間として両候補を残します。4軸がそろって初めて16通りからタイプ候補を出します。</p>'
        '<p>口調7種類は独立して観察し、共存可能。直接指示を攻撃性に、肯定を感謝に読み替えません。発見メモは抜粋ごとに最大2件で、0件も正常です。'
        '既存観点の具体例と、枠外の候補を区別します。根拠ID・匿名化した観察・本人への問いを必須とし、効果や世界的な新規性は認定しません。口調と発見メモはタイプ計算に入りません。</p>'
        '<p>原文引用・固有名詞・パス・秘密を自由記述に残さないこと。共有JSONには自由記述と口調を含めず、旧方式とは分類方式の版を分けます。</p>')
    if summary:
        parts['PORTRAIT']+='<h3>今回の会話を紹介する旅人</h3><p>representative-v1は、同じ上限付き抜粋の選択や任せ方を候補と読み比べる独立した編集上の判断です。4軸・分類・元の分析日時は変更しません。一人に絞れない場合は候補を並べます。旧結果の表示更新だけでは判断を追加しません。理由と発言参照は集計共有JSONに含めません。</p>'
        if report.get('representative'):
            parts['PORTRAIT']+=f'<p>旅人の検討日時：{h(report["representative"]["generated_at"])}</p>'
        aliases={t['code']:t for t in journey.catalog()}
        parts['PORTRAIT']+='<h3>旅の16タイプ：表示名の対応</h3><p>愛称とイラストは表示用です。判定コード・根拠・評価日時を変更しません。旧方式のタイプには適用しません。</p>'
        parts['PORTRAIT']+=table(['コード','現在の愛称','使い方の要約'],[[h(t['code']),h(aliases.get(t['code'],t)['name']),h(aliases.get(t['code'],{}).get('summary',t['tagline']))] for t in summary['classification']['type_catalog']])
        parts['PORTRAIT']+=f'<p>追加評価日時：{h(summary["generated_at"])} ／ {summary["sessions"]}会話 ／ 記号 {h(summary["classification"]["type_code"])}</p>'
        parts['PORTRAIT']+=table(['軸','左のみ','右のみ','両方','観測会話','左側への配分','判定'],[[h(a['title'])]+[str(a['counts'].get(k,0)) for k in ('left','right','both')]+[str(a['observed_sessions']),h(a['left_percent']),h(a['state'])] for a in summary['axes']])
        checks=portrait.material_checks(summary)
        parts['PORTRAIT']+='<p>1会話への依存の確認：観測した会話を1件ずつ除き、保存された閾値で4軸の状態を再計算。未観測・不明は除外対象にも入れません。両方の会話は左右0.5票ずつを同時に除きます。分類や診断日時は変えず、AIの誤読・標本の代表性・正解確率を測るものではありません。</p>'
        if checks:
            parts['PORTRAIT']+=table(['軸','判定が変わる除外の数','試した除外の数','除外後の状態'],[
                [h(a['title']),str(checks[a['id']]['changed']),str(checks[a['id']]['tested']),h(' / '.join(checks[a['id']]['states']))]
                for a in summary['axes'] if a['id'] in checks])
        parts['PORTRAIT']+=table(['口調','観測会話','評価可能','不明'],[[h(t['label']),str(t['sessions']),str(t['assessed_sessions']),str(t['uncertain_sessions'])] for t in summary['tones']])
        parts['PORTRAIT']+=f'<p>発見メモ：{len(summary["discoveries"])}種類。個別の内容と根拠は結果画面で確認できます。</p>'
    else:parts['PORTRAIT']+='<p>この保存済み結果では4軸・口調・発見メモは未評価です。旧分類を自動変換しません。</p>'
    parts['PORTRAIT']+='<h3>具体的な利用場面（practice-v1 / v2）</h3><p>同じ上限付き抜粋を別途読み、場面・本人の行動・AIの役割・その後を個別の発言参照で支えます。1会話最大1例、材料不足は掲載しません。v2では、つながった手順・トレードオフ・条件付きの選択を0〜3例選び、残りも展開できます。一般的な訂正だけで枠を埋めません。条件は本人の明言・周囲の状況・不明を区別し、別の案と手順にも本人の根拠を求めます。旧v1の保存結果は変換せず表示します。頻度順・優劣順ではありません。</p><p>本人の行動には本人の発言を必須とし、その後は未確認・AIの報告・本人の報告を区別します。効果の検証は行いません。問いと仮の依頼例を観察から分離し、分類・従来の分析日時は維持。全選択会話のレビューを検証し、抜粋と定義が一致した場合だけキャッシュを再利用します。形式検査は意味の正しさを保証しません。</p><p>自由記述は集計の共有JSONに含めません。利用者が例を選択し、文章を編集・確認して保存する独立したテキスト下書きだけを用意します。送信はせず、下書きの編集も診断に反映しません。</p>'
    parts['PORTRAIT']+='<p>現在の選定では、プロジェクト固有の用語を外しても、AIへの任せ方・条件・残すものや見送る案の組み合わせが伝わるかを確認します。作業の珍しさや専門用語だけでは選びません。一般的な助言にしかならない例も選出しません。他人との希少性や優劣を測る基準ではありません。保存済みの旧結果に、この選定確認を自動適用することはありません。</p>'
    practices=report.get('practices')
    parts['PORTRAIT']+=(f'<p>具体例の評価日時：{h(practices["generated_at"])} ／ 確認した会話 {practices["reviewed_sessions"]} ／ 掲載した場面 {len(practices["items"])}。個別の内容は結果画面にのみ表示。</p>' if practices else '<p>この保存済み結果では具体例は未評価です。</p>')
    parts['META'] = (f'<span>現在の評価基準 <code>{h(rubric)}</code></span><span>保存済み結果 <code>{h(report["method"])}</code></span><span>現在の抽出器 <code>{h(extractor)}</code></span>'
                     f'<span>詳細ページ更新 {h(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))}</span>')
    parts['SUMMARY'] = (f'<p>参照する診断：{h(report["generated_at"])} ／ {report["sessions"]}会話・'
                        f'{report["messages"]}人発言。集計は保存済みの結果を使用し、AIによる再評価は行っていません。</p>'
                        '<p>軸の説明・抽出設定・閾値は現在の実装から生成。タイプの重みは診断結果に保存された定義を使用します。'
                        '旧18観点の分類閾値は過去のレポートに保存されていないため、実装変更時の再現性に注意してください。4軸は保存済みの閾値を優先します。</p>')
    if report.get('purpose_summary') is not None:
        labels={'routine':'定型操作の依頼','research':'調査・説明','deliberation':'検討・相談','production':'制作・変更','mixed':'混在','unknown':'不明'}
        parts['SUMMARY'] += '<h3>利用目的と観点の併存</h3><p>同じ会話内の目的と観察の併存であり、目的が行動を生んだという意味ではありません。複数目的は重複し、会話の中の別の場面である可能性もあります。評価可能な場面のみを分母にします。件数が少ない比較は不安定です。</p>'
        for group in report['purpose_summary']:
            parts['SUMMARY'] += '<details><summary>'+h(labels[group['id']])+'：'+str(group['sessions'])+'会話</summary>' + table(['観点','観測 / 評価可能'], [[h(observed.get(item['id'],{}).get('title',item['id'])),str(item['observed'])+' / '+str(item['assessed'])] for item in group['perspectives']]) + '</details>'
    count_label='根拠のある会話' if report['method']=='semantic-38-v4' else '人の根拠発言'
    parts['COUNT_EXPLANATION']=('<b>c</b>＝観測の根拠がある会話数（1会話最大1）、' if report['method']=='semantic-38-v4' else '<b>c</b>＝観測の根拠となる人の発言数、')
    cards = []
    metric_rows = []
    for i, p in enumerate(definitions, 1):
        m = observed.get(p['id'], {})
        unassessed = not m or m.get('not_assessed',False)
        assessed = m.get('assessed_sessions', 0)
        count, sessions = m.get('count', 0), m.get('sessions', 0)
        rate = '未評価' if unassessed else f'{100*sessions/assessed:.1f}%' if assessed else '評価可能な場面なし'
        observation = '今回：未評価。0件・未観測として扱いません。' if unassessed else f'今回：{sessions} / {assessed}評価可能な会話 · {rate}'
        detail_counts = '' if unassessed else f'<p class="small">{count_label} {count}件 ／ 不明 {m.get("uncertain_sessions",0)}会話 ／ 該当場面なし {m.get("not_applicable_sessions",0)}会話</p>'
        forms = ''
        if p.get('forms'):
            actual = {f['id']: f['sessions'] for f in m.get('observed_forms',[])}
            forms = '<p class="small">分類には未使用。以下は順序のない選択肢で、優劣・推奨順ではありません。</p><ul>' + ''.join(
                '<li>'+h(f['label'])+('：未評価' if unassessed else f'：{actual.get(f["id"],0)}会話')+'</li>' for f in p['forms']) + '</ul>'
            forms += '<p class="small">読み取り条件：'+h(p['assessment_hint'])+'</p>'
        examples = ''.join(f'<dt>{label}</dt><dd>{h(p["examples"][key])}</dd>'
                           for key, label in [('general', '共通'), ('planner', 'ゲームプランナー'), ('designer', 'デザイナー')])
        cards.append(f'<article class="axis" id="axis-{h(p["id"])}" data-axis>'
                     f'<div class="eyebrow">{i:02d} · {h(p["group"])}</div><h3>{h(p["title"])}</h3>'
                     f'<code>{h(p["id"])}</code><p>{h(p["description"])}</p>'
                     f'<p class="metric">{observation}</p>{detail_counts}{forms}'
                     f'<details><summary>解釈の問いと依頼例</summary><p>{h(p["question"])}</p>'
                     '<p class="small">以下は作成した例です。一致だけで観測と判定するものではありません。</p>'
                     f'<dl>{examples}</dl></details></article>')
        metric_rows.append([f'<a href="#axis-{h(p["id"])}">{h(p["title"])}</a>', '—' if unassessed else str(count), '—' if unassessed else str(sessions),
                            '—' if unassessed else str(assessed), '—' if unassessed else str(m.get('uncertain_sessions', 0)),
                            '—' if unassessed else str(m.get('not_applicable_sessions',0)), rate,
                            '分類には未使用' if p.get('kind') in ('process','tooling') else f'{vector.get(p["id"],0):.4f}', '該当' if p['id'] in repeated else '—'])
    parts['AXES'] = ''.join(cards)
    parts['METRICS'] = table(['観点', 'c：'+count_label, 'o：観測会話', 'a：評価可能', 'u：不明', '該当場面なし', '観測割合', 'v：分類用の値', '繰り返し観測'], metric_rows)
    parts['MODES'] = table(['モード', '最大会話数', '本文＋実行情報の文字数上限'],
                          [[h(name), str(n), f'{chars:,}'] for name, (n, chars) in modes.items()])
    coverage=report.get('sampling',{}).get('source_coverage')
    parts['COVERAGE']=('<p>この保存済み結果にはエージェント別の抽出内訳がありません。再抽出後に記録されます。</p>' if coverage is None else
        table(['エージェント','期間内の読取会話','作業場所で除外','条件に合う会話','分析に選択','扱い'],
              [[h(row['source'])]+[str(row[key]) for key in ('available_sessions','excluded_project_sessions','eligible_sessions','selected_sessions')]+[h(row['reason'])] for row in coverage]))
    sample=report.get('sampling',{}).get('coverage')
    parts['COVERAGE']+='<div id="sample-coverage"><h3>今回の抽出内訳と文脈の省略</h3>'
    sampling=report.get('sampling',{})
    diagnostics=report.get('diagnostics',{})
    parts['COVERAGE']+=table(['読取・処理の記録','値'],[
        [label,h(sampling.get(key,'記録なし'))] for label,key in [('本文と実行情報の文字数','read_chars'),('文字数上限','char_budget'),('新規読取文字数','new_read_chars'),('評価を再利用した会話数','cache_hits')]]
        +[[label,h(diagnostics.get(key,0))] for label,key in [('走査ファイル数','files_scanned'),('読取不可ファイル数','unreadable_files'),('不正な行数','malformed_lines')]])
    if sample is None:
        parts['COVERAGE']+='<p>この保存済み結果には月別・作業場所別の抽出内訳がありません。表示の更新だけでは過去の抽出範囲を作り直しません。</p>'
    else:
        parts['COVERAGE']+=table(['対象期間内の最初の発言の月','抽出した会話','条件に合う会話'],
            [[h(row['month']),str(row['selected']),str(row['eligible'])] for row in sample['months']])
        parts['COVERAGE']+=(f'<p>条件に合う作業場所 {sample["eligible_projects"]}箇所のうち {sample["selected_projects"]}箇所を含みます。'
            f'{sample["messages"]}発言中 {sample["truncated_messages"]}発言が文字数上限で途中切れ。'
            f'人→AI→人の往復があるのは {sample["followup_windows"]}会話です。</p>')
    parts['COVERAGE']+='<p>普段の利用比率や全履歴の代表性は保証しません。途中切れがなくても前後の文脈や添付資料は省略されています。1会話を外す確認の内訳は「4軸・口調・発見メモ」を参照してください。AIの読み違いや抽出の偏りを検証するものではありません。</p></div>'
    labels = [
        ('evidence_smoothing', '少数根拠を補正する定数'), ('repeated_messages', '繰り返し観測：'+count_label+'数の下限'),
        ('repeated_sessions', '繰り返し観測：観測会話数の下限'), ('min_messages', '材料充足：抽出内の人発言数の下限'),
        ('min_sessions', '材料充足：分析会話数の下限'), ('min_repeated_dimensions', '材料充足：繰り返し観測した軸数の下限'),
        ('min_supported_dimensions', 'タイプ候補：重みを持つ軸のうち繰り返し観測した軸数の下限'),
        ('min_similarity', 'タイプ候補：類似度の下限（以上）'), ('candidate_gap', '同列候補：候補内の首位との類似度差（未満）'),
        ('score_decimals', '判定前に類似度を丸める小数桁数')]
    parts['RULES'] = table(['判定条件', '設定値', 'コード上のキー'],
                          [[h(label), h(rules[key]), '<code>' + h(key) + '</code>'] for key, label in labels])
    parts['FORMULA'] = h(f'v_i = (o_i / a_i) × c_i / (c_i + {rules["evidence_smoothing"]})\n'
                        'score(t) = Σ(v_i × w_t,i) / (√Σ(v_i²) × √Σ(w_t,i²))')
    parts['WEIGHTS'] = table(['タイプ'] + [f'<a href="#axis-{h(p["id"])}" title="{h(p["title"])}">{i:02d}<br>{h(p["id"])}</a>'
                                                        for i, p in enumerate(base.PERSPECTIVES, 1)],
                            [[f'<strong>{h(t["code"])} {h(t["name"])}</strong>'] + [
                                f'<span class="weight w{int(t["weights"].get(p["id"],0))}">{t["weights"].get(p["id"],0) or "—"}</span>'
                                for p in base.PERSPECTIVES] for t in catalog], 'weights')
    rank_rows = []
    for t in ranked:
        if not adequate:
            decision = '材料不足'
        elif t['supported'] < rules['min_supported_dimensions']:
            decision = '支持する軸が不足'
        elif t['score'] < rules['min_similarity']:
            decision = '類似度が閾値未満'
        else:
            decision = '同列候補' if t['code'] in candidates else '候補の首位から差あり'
        rank_rows.append([h(t['code']+' '+t['name']), f'{t["score"]:.4f}', str(t['supported']), h(decision),
                          h('、'.join(titles.get(key, key) for key in t['reasons']) or '—')])
    parts['RANKING'] = table(['タイプ', '類似度', '支持する軸数', '現在の条件による判定', '繰り返し観測と重みが重なる軸'], rank_rows)
    audit=report.get('execution_audit')
    parts['EXECUTION']='<p>実行記録はまだ収集していません。機能を使っていないという意味ではありません。</p>'
    if audit:
        parts['EXECUTION']=(f'<p>{h(audit["scope"])} ／ {h(audit["generated_at"])} ／ {audit["days"]}日・{audit["sessions"]}会話ファイルの集計。</p>'
            + table(['記録種別','要求','応答あり','エラー応答','設定等の記録'],[[h(f['label'])]+[str(f.get(k,0)) for k in ('requested','returned','error','recorded')] for f in audit['features']])
            + '<p>モデル記録：'+h('、'.join(audit['models']) or '確認できず')+'</p>'
            + '<p>推論設定の記録：'+h('、'.join(audit['efforts']) or '確認できず')+'</p>'
            + '<p>各ファイル最大'+str(audit['limit_per_file'])+'イベント。上限による省略 '+str(audit['omitted_events'])+'件。0件は一致記録なしで、未使用の証明ではありません。</p>')
    template = brand.embed_logo((Path(__file__).parent.parent / 'assets/developer-report.html').read_text(encoding='utf-8'))
    # One replacement pass: content must not be interpreted as a template token.
    import re
    return re.sub(r'__([A-Z]+)__', lambda m: parts[m.group(1)], template)
