# HHKB Pointer Boost

指定したキーを押している間だけ、ポインターの速度を上げる常駐アプリです。HHKB Studio のポインティングスティックで、普段は細かく動かし、長い距離を動かすときだけ速くする使い方を想定しています。

Windows 版と Mac 版があり、どちらもこのリポジトリから入れられます。

| | Windows | Mac |
|---|---|---|
| 置き場所 | `windows/` | `mac/` |
| 作り | Python + tkinter（追加パッケージ不要） | Swift のメニューバーアプリ（macOS 13 以降） |
| 変える値 | Windows のポインター速度（1〜20） | マウスのトラッキング速度（0〜5、システム設定の最大は 3） |
| 常駐先 | タスクバーの通知領域（H+ アイコン） | メニューバー（H+ アイコン） |
| 自動起動 | HKCU の Run に登録 | `~/Library/LaunchAgents` に登録 |

```sh
git clone https://github.com/yi7242/hhkb-pointer-boost.git
```

## Windows

1. Python 3.10 以降を入れる（python.org 版か `uv python install`）。
2. `windows\hhkb_pointer_boost.cmd` をダブルクリックすると設定画面が開く。
3. 設定画面で「Windowsログイン時に自動起動する」をオンにして「適用」を押すと、次回のログインから自動で常駐する。

常駐中は通知領域の H+ アイコンをダブルクリックすると設定画面が開き、右クリックで有効／無効の切り替えと終了ができます。設定ウィンドウを閉じても常駐は続きます。設定は `%LOCALAPPDATA%\HHKBPointerBoost\settings.json` に保存されます。

## Mac

1. ターミナルで `xcode-select --install` を実行し、Command Line Tools を入れる（Xcode 本体は不要）。
2. `mac/build.sh --install` を実行する。`~/Applications/HHKB Pointer Boost.app` ができて起動する。
3. メニューバーの H+ アイコンから「設定を開く…」を選び、キーと速度を決める。速度はスライダーを動かした時点で反映される。
4. 「ログイン時に自動起動する」をオンにすると、次回のログインから自動で常駐する。

`mac/build.sh` だけを実行すると、`mac/build/HHKB Pointer Boost.app` を作るところで止まります。GitHub Actions でも同じビルドを行っており、Actions の実行結果から zip をダウンロードすることもできます。

Mac 版はシステム設定の「トラッキング速度」と同じ値を、接続中のマウスだけに設定します。トラックパッドの速度は変えません。終了すると通常時の速度に戻します。

### Mac の許可

- F13〜F15 をトリガーにする場合は「プライバシーとセキュリティ → 入力監視」でこのアプリを許可し、アプリを再起動する。Option・Shift・Control・Command とマウスボタンは許可なしで読める想定。押しても「加速中」にならない場合は、同じく入力監視を許可する。
- `build.sh` で作り直すと署名が変わるため、入力監視の許可を付け直す必要がある。

## 設定できる項目

- 機能のオン／オフ
- 押している間だけ速度を切り替えるキー
- 通常時の速度とキー押下中の速度
- キーを確認する間隔（16〜100 ms）
- ログイン時の自動起動

## キーの選び方

Windows の Ctrl＋ホイールはズーム、Shift＋ホイールは横スクロールになり、Alt を単独で押すとメニューが開くことがあります。Mac の Option＋クリックや Command＋クリックも、アプリごとに別の動作が割り当てられています。HHKB のキーマップで空いている物理キーを F13 に割り当て、トリガーを「F13（専用キー向け）」にすると、ほかの操作とぶつかりません。

## アイコン

`icon/make_hhkb_icon.py` を実行すると、Windows 用の `windows/hhkb_pointer_boost.ico` と Mac 用の `mac/AppIcon.png` を作り直します。Mac のメニューバーのアイコンは `mac/main.swift` の `makeIcon` が同じ図形を描いているので、デザインを変えるときは両方を直してください。
