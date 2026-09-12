# リモートからの直接印刷

ローカルの「プリント準備」は従来どおり、編集可能な3MFをBambu Studioで開きます。
Tailscale経由の「プリント開始」は別処理です。PCでスライス・検査した後、
確認画面でプレート・材料量・印刷時間・印刷先を表示します。
プレートとフィラメントの確認後に「印刷を開始」を押したときだけ送信します。
複数プレートを連続実行せず、1枚ごとに取り外しと確認を行います。

## 接続設定

### Bambu Connect（このPCで使用）

`config/printer.connect.example.json` を `config/printer.local.json` にコピーし、
`transport: "bambu_connect"` を指定します。このPCではログイン済みConnectの
`3DP-030-654`、A1 mini・0.4 mm・Textured PEI・外部スプールPLAを設定済みです。
LAN専用モードへの切り替えや認証情報の取り出しは不要で、Bambu Handyも引き続き使用します。

リモートの確認画面で「印刷を開始」を押すと、PCでスライスした今回の1プレートを
公式のURLスキームでConnectに取り込み、Import → Print → Sendまで進めます。
実際のプリセットを検証したうえで、CLI出力の未設定の機種IDと互換プリンター情報だけを
受け渡し用コピーに補完します。元の3MF・形状・G-codeは変更しません。

PCはログイン済み・ロック解除済みで、Connectが前面に出る状態が必要です。
操作中はマウス・キーボードを使わないでください。前面や画面内容が変われば停止します。
Connectが自動で前面に出なかった場合や再ログインが必要な場合はPCでの操作が必要です。
別セッションからの無人動作、最小化・ロック画面での動作には対応していません。

「送信を中止」はSendに入る前まで有効です。Send後の停止はBambu Handyまたは本体で行います。
同じ開始チケットは再使用せず、操作結果が不明な場合も自動再送しません。
Sendを押しただけで印刷開始とは判定せず、画面で今回のジョブとプリンターの開始状態が
一致した場合だけ開始済みと表示します。確認できない場合はHandy／本体での確認を案内します。

使用環境は `.runtime/connect-rpa-venv`、依存関係は `requirements-connect-rpa.lock` です。
サーバーの作業フォルダー `.remote-print/<ticket>/connect/` に画面認識とSend実行記録を残します。
これらのファイルとプリンター設定はHTTP配信しません。

### LAN通信（任意・従来の別方式）

対象はプロジェクトの既存プロファイルに合わせたA1 mini、0.4mmノズル、Bambu PLA Matteです。
`config/printer.example.json`を参考に、接続先PCに`config/printer.local.json`を作成します。
このファイルはGit管理外かつHTTP配信対象外です。LAN内IPとシリアル、
外部スプール／AMS Lite（0〜3）のスロットを設定します。
`access_code`を省略すると、指定シリアルに対応するBambu Studioの保存済みコードを読みます。
LAN専用・開発者モードを本体で有効にする必要があります。クラウド認証は使用しません。
接続情報が未設定の場合は確認画面にエラーを表示し、GUI起動へ代替しません。

## 共通検証とLAN方式の送信

- 元の部品・工程状態を変更せず、確認済み形状を別の作業領域に複製して印刷用データを作成します。
- 既存の姿勢衝突検査、元形状照合、Bambu CLIスライス、G-code/MD5/ベッド範囲/警告検査を実行します。
- 元のモデル・プリンター・フィラメント設定・パッケージが変更されていた場合は開始を拒否します。
- 保存された開始チケットは一度だけ使用します。通信切断・サーバー再起動時も開始命令を再送しません。
- 待機状態・SDカード・機器エラーを確認し、暗号化FTPで送信後、再取得してSHA-256を照合します。
- Bambuのインストール済みCAとプリンターのシリアルでTLS接続先を検証します。
- MQTTで開始要求を送信し、応答だけでなく対象ジョブのPREPARE/RUNNINGを確認します。
  開始結果が不明な場合はその旨を表示し、プリンター本体の確認を求めます。

実機の接続・開始テストにはプリンターのLAN設定が必要です。単体テストでは実機を動かしません。

通信実装の参照元：
[A1 miniのLAN通信実測](https://github.com/sksat/bambu-rs/blob/main/docs/protocol.md)、
[Paho MQTT API](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html)、
[Bambu Security White Paper](https://cdn1.bambulab.com/trust-center/file/bambulab-security-whitepaper-en.pdf)。
