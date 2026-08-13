# オペアンプ設計コンテスト評価システム

`testbenchGUI` にあるネットリストを HSPICE でシミュレーションし、指定した部門の性能、制約条件、FOM（Figure of Merit）を表示するプログラムです。

## 実行条件

### 必須ソフトウェア

- Python 3.11 以上
- HSPICE（`hspice` コマンドを PATH から実行できること）

### Python パッケージ

```bash
python3 -m pip install matplotlib numpy pandas tabulate
```

テストを実行する場合は、追加で `pytest` が必要です。

```bash
python3 -m pip install pytest
```

## 準備

評価対象の回路を `testbenchGUI/opamp.sp` に、次の形式で記述してください。

```spice
.subckt opamp ...
...
.ends opamp
```

部門1〜3では `testbenchGUI/lib/new018.mdl` を MOSFET モデルとして使用します。部門4を実行する場合は、別途入手したモデルファイルを任意の場所に配置し、`testbenchGUI/testbench.py` の `DEP4_MODEL_PATH` を環境に合わせて変更してください。

```python
DEP1_MODEL_PATH = BASE_DIR / "lib" / "<モデルファイル>"
DEP4_MODEL_PATH = "/path/to/<モデルファイル>"
```

モデルファイルのパスは環境ごとに異なるため、実際の配置先に置き換えてください。指定したファイルが存在しない場合、その部門は実行できません。HSPICE のモデル定義と `testbenchGUI/lib/settings.lib` の参照方法が一致していることも確認してください。

## 実行方法

プロジェクトのルートディレクトリから、次のように実行します。`testbench.py` が内部で `testbenchGUI` を作業ディレクトリに設定するため、移動は不要です。

```bash
python3 testbenchGUI/testbench.py dep1
```

指定できる部門は `dep1`、`dep2`、`dep3`、`dep4` です。部門を省略した場合は `dep1` が使用されます。

```bash
python3 testbenchGUI/testbench.py dep2
python3 testbenchGUI/testbench.py dep3
python3 testbenchGUI/testbench.py dep4
python3 testbenchGUI/testbench.py
```

## 実行時の処理

1. `opamp.sp` を読み込み、部門に応じて MOSFET の `ad`、`as`、`pd`、`ps` パラメータを付加・更新します。
2. 処理後のネットリストを一時ファイル `tmp.sp` として作成します。
3. 部門1〜3では `sim1.sp` と `sim2.sp`、部門4では `sim3.sp` を HSPICE で実行します。
4. 解析結果を端末に表示し、算出可能な `FOM (dep1)`〜`FOM (dep4)` を出力します。今回の解析で算出できない FOM は `-` になります。
5. 回路面積を計算し、波形プロットと性能表を保存します。

実行のたびに `testbenchGUI/out/` は初期化されます。生成される主なファイルは次のとおりです。

- `testbenchGUI/out/`：解析用の PDF/SVG 波形プロット
- `simulatinon_results.md`：性能表と SR 波形プレビュー（プロジェクトルート）

`tmp.sp`、`for_sr.lib`、HSPICE の `.lis`・測定 CSV などの一時ファイルは、シミュレーション終了時に削除されます。HSPICE が見つからない場合は、`hspice` コマンドが PATH に登録されているか、また HSPICE の実行ライセンスが利用可能か確認してください。