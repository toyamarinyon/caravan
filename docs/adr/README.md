# 設計判断の記録（ADR）

このプロジェクトの「何を、なぜ選び、何を引き受けたか」を残します。機能一覧や作業日報ではなく、後から設計を変えるときの判断材料です。運用開始：2026-11-03。

## 一覧

| ADR | 状態 | 決定 |
|---|---|---|
| [0001](0001-record-decisions.md) | Accepted | ADRをリポジトリで運用する |
| [0002](0002-observations-and-type-summary.md) | Accepted | 優劣を測らず、多観点の観察と4軸の要約を分ける |
| [0003](0003-bounded-semantic-review.md) | Accepted | 実行中のAIが上限付き抜粋を読み、評価をキャッシュする |
| [0004](0004-consent-and-private-data.md) | Accepted | 読取の承諾・処理先の説明・共有項目の制限を維持する |
| [0005](0005-multi-agent-source-coverage.md) | Accepted | 複数エージェントの履歴を抽出枠に含める |
| [0006](0006-tool-events-and-human-intent.md) | Accepted | ツールの実行記録と本人の意図を分ける |
| [0007](0007-stable-standalone-reports.md) | Accepted | 固定HTML・独立した詳細画面・診断と表示の分離 |
| [0008](0008-travel-names-and-art.md) | Accepted | 旅の愛称と共通の画像制作ルールを表示層で管理する |
| [0009](0009-impeccable-design-workflow.md) | Accepted | Impeccableで既存画面を整え、検査と実画面の確認を分ける |
| [0010](0010-presentation-summary.md) | Accepted | 固定レポート内に16:9の発表用サマリーを持つ |
| [0011](0011-public-distribution.md) | Accepted | 明示したファイルだけをMITライセンス・新しい履歴で公開する |
| [0012](0012-installed-skill-workspace.md) | Accepted | Codex・Claude Codeの個人用スキル導入と診断の作業場所を分ける |
| [0013](0013-user-selected-analysis-mode.md) | Accepted | 分析量の違いを説明し、本人の選択と承諾の後に抽出する |
| [0014](0014-caravan-brand.md) | Accepted | Caravanの表示名と軽量ロゴを採用し、既存の識別名・診断を維持する |
| [0015](0015-development-browser-checks.md) | Accepted | 開発専用Playwrightで架空ページを描画し、配布には含めない |
| [0016](0016-caravan-repository-name.md) | Accepted | 公開リポジトリ・診断スキル・配布名をCaravanへ統一する |
| [0017](0017-no-user-packages.md) | Accepted | 利用者には追加パッケージを導入せず、標準ライブラリと既存環境で動かす |
| [0018](0018-budgeted-context-and-materials.md) | Accepted | 予算内で時期・作業場所と文脈を広げ、材料の限界・1会話への依存を表示する |
| [0019](0019-private-result-backup.md) | Accepted | 本人用の保存・復元を共有用プロフィールと分ける |
| [0020](0020-bounded-analysis-validation.md) | Accepted | 合成例の意味確認と、総予算を固定した抽出比較を分ける |
| [0021](0021-grounded-use-cases.md) | Accepted | 具体的な利用場面を入口にし、16タイプと集計共有の境界を維持する |
| [0022](0022-specific-choices-without-quota.md) | Accepted | 条件・別案・つながった手順を根拠付きで整理し、冒頭の件数を埋めない |
| [0023](0023-overview-before-practices.md) | Accepted | 冒頭は旅人と4軸で全体像を示し、具体的な工夫を直後に続ける |
| [0024](0024-result-reading-structure.md) | Accepted | 結果の具体例を役割別に整理し、追加の観察と内部参照表示を分ける |
| [0025](0025-japanese-prose-review.md) | Accepted | 表示と生成手順の日本語を推敲し、保存済みの分析は維持する |
| [0026](0026-restored-result-html.md) | Accepted | 詳細JSONから復元した結果を単独HTMLとして保存できるようにする |

| [0027](0027-current-result-backup.md) | Accepted | 詳細JSONから旧分類を除き、現在の旅人名で保存する |
| [0028](0028-portable-distinctive-practices.md) | Superseded by 0033 | プロジェクトを知らなくても伝わる、特徴的なAIへの任せ方と選択の組み合わせを選ぶ |
| [0029](0029-private-presentations-outside-repository.md) | Accepted | 個人の発表資料は開発履歴を含むリポジトリ外で管理する |
| [0030](0030-explicit-publication-remote.md) | Accepted | originと公開用ブランチ・worktreeを同じGit管理下に置く |
| [0031](0031-separate-art-originals-from-skill.md) | Accepted | 元PNGを開発用素材へ移し、診断スキルには配信用画像だけを含める |
| [0032](0032-kimi-desktop-history.md) | Accepted | Kimiデスクトップ版のWire 1.5から本人の入力と完了したAI回答を読み取る |
| [0033](0033-separate-collaboration-from-scene.md) | Accepted | AIとの進め方を、根拠となる作業場面と分けて生成する |
| [0034](0034-purpose-and-separated-scenes.md) | Accepted | 目的と選択機会を区別し、長い会話の離れた場面を同じ予算で読む |
| [0035](0035-representative-traveler.md) | Accepted | 中間・併用を保ち、同じ抜粋から紹介する旅人を別途選ぶ |

0002〜0008は、この会話と実装を照合した**事後記録**です。記録日は実際の決定日を意味しません。記載した比較対象は判断を説明するため今回整理したもので、過去にすべてを実験したという意味ではありません。

## いつ書くか

次のような、今後の変更に制約や理由を残す決定が対象です。

- 診断対象・評価基準・分類・不明値・互換性の扱い
- 履歴を読む範囲、処理先、承諾、共有や保存の境界
- 抽出・キャッシュ・モデル接続・依存関係
- 出力形式、データと表示の責務、継続的に使う制作方式

誤字修正・余白調整・同じ仕様内のバグ修正・通常の画像差し替えには原則不要です。提案を試しただけで採用済みとは記録しません。

## 更新の流れ

1. 関連作業の前にこの一覧と該当ADRを読む。
2. [テンプレート](template.md)をコピーし、次の未使用番号で `NNNN-short-title.md` を作る。番号を再利用しない。
3. 背景・決定・理由・比較対象・影響・再検討条件・実装への参照を短く書く。実装済みか、これから実装するかを明示する。
4. 未決定なら Proposed、依頼や合意によって採用が確認できれば Accepted にする。既に認められた通常作業に新たな承認待ちは設けない。
5. 一覧・関連ドキュメント・必要な実装を同じ変更に含め、ローカルGitに記録する。

状態は Proposed（検討中）／Accepted（採用）／Rejected（不採用）／Superseded（後続ADRで置換）／Deprecated（後継なしで廃止）。

採用済みの判断を変える場合は、新ADRから旧ADRを参照し、旧ADRに状態と置換先を追記します。元の背景・理由を新方針に書き換えません。誤字・リンク修正と、日付付きの実装状況追記は可能です。

## 記録の境界

個人の会話・抜粋・診断タイプ・正確な集計・認証情報・ユーザー固有の絶対パスは書きません。根拠にはリポジトリ内の相対リンク、テスト、コミットを使います。私的な `output/` の実データへリンクしません。

ADRは理由、READMEは利用方法、SKILL.mdは実行手順、定義ファイルは具体的な指標・閾値の正本です。細部をADRへ丸ごと複製しません。矛盾を見つけたら、現在の依頼と実装を確認して該当文書を整えます。

## まだ採用済みとして扱わないもの

- Bedrockへの接続実装・モデルや日本リージョンの固定・料金の保証。現在は利用中のエージェントが読む方式。
- 追加エージェントの全面対応や、ログ形式の永続的な互換保証。
- 4軸や閾値の統計的妥当性、口調と回答精度の因果関係、発見メモの技法としての有効性。
- 履歴や診断結果の公開・自動送信。0011の公開配布はツールのソースのみを対象とする。
