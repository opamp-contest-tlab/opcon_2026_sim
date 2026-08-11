# オペアンプ設計コンテスト評価システム

`testbenchGUI` にあるネットリストを HSPICE でシミュレーションし、各部門の性能と FOM（Figure of Merit）を表示するプログラムです。

## 実行条件

### 必須ソフトウェア

- Python 3.11 以上
- HSPICE（`hspice` コマンドを実行できること）

### Python パッケージ

次のパッケージをインストールしてください。

```bash
python3 -m pip install matplotlib numpy pandas tabulate
```

### 必要なファイル

次のファイル・ディレクトリが必要です。

- `testbenchGUI/opamp.sp`：評価対象のオペアンプネットリスト
- `testbenchGUI/sim1.sp`〜`sim3.sp`：HSPICE の解析用ネットリスト
- `testbenchGUI/lib/`：解析用ライブラリと MOSFET モデル
- `testbenchGUI/testbench.py`
- `testbenchGUI/lib/simulator.py`

`opamp.sp` には、評価対象となる `.subckt opamp ... .ends opamp` の定義を記述してください。

### MOSFET モデル

`testbenchGUI/testbench.py` の次の設定でモデルファイルの場所を指定します。

```python
DEP1_MODEL_PATH = BASE_DIR / "lib" / "new018.mdl"
DEP4_MODEL_PATH = "/home/cad/PDK/PDK_520/common/data/sim/lib/spice_model/PTS06_spice_400.txt"
```

使用する環境に合わせて `DEP4_MODEL_PATH` を変更してください。指定したファイルが存在しない場合、実行できません。

また、HSPICE が使用するモデルに合わせて `testbenchGUI/lib/settings.lib` の設定も確認してください。

## 実行方法

プロジェクトのルートディレクトリから `testbenchGUI` へ移動し、部門を引数に指定して実行します。

```bash
cd testbenchGUI
python3 testbench.py dep1
```

指定できる部門は `dep1`、`dep2`、`dep3`、`dep4` です。

```bash
python3 testbench.py dep1
python3 testbench.py dep2
python3 testbench.py dep3
python3 testbench.py dep4
```

部門を省略した場合は `dep1` が使用されます。

```bash
python3 testbench.py
```

## 実行時の処理

1. `opamp.sp` を読み込みます。
2. `process_netlist()` により、部門に応じた MOSFET の `ad`、`as`、`pd`、`ps` パラメータを付加・更新します。
3. 処理後のネットリストを一時ファイル `tmp.sp` として作成します。
4. 部門1〜3では `sim1.sp` と `sim2.sp`、部門4では `sim3.sp` を HSPICE で実行します。
5. 解析結果、制約条件、実行部門のスコアを表示します。
6. 算出可能な `FOM (dep1)`〜`FOM (dep4)` を表示します。今回の解析で算出できない FOM は `-` になります。

`tmp.sp` や HSPICE の結果ファイルはシミュレーション終了時に削除されます。解析用の波形プロットは `out/` に保存されます。

## 実行結果の例

正常に実行されると、性能表に次のような項目が表示されます。

```text
FOM (dep1)
FOM (dep2)
FOM (dep3)
FOM (dep4)
```

HSPICE が見つからない場合は、`hspice` コマンドが PATH に登録されているか確認してください。
