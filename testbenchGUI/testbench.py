import argparse
import os
from pathlib import Path

# このファイルが存在するフォルダをカレントディレクトリに設定
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

# ユーザー設定：使用するモデルファイルのパス
# 別のモデルを使用する場合は、この値を変更する。
# オペアンプ設計コンテストのホームページから入手できるので任意の場所に配置し、ここでPATHを定義する
DEP1_MODEL_PATH = BASE_DIR / "lib" / "new018.mdl"
# 試作の部に参加したであれば、フェニテック社のモデルファイルを入手しているはずなので、それまでPATHを定義する
DEP4_MODEL_PATH = "/home/cad/PDK/PDK_520/common/data/sim/lib/spice_model/PTS06_spice_400.txt"


def resolve_model_path(model_path, name):
    """モデルパスを絶対パスへ変換し、存在を確認する。"""
    path = Path(model_path).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    path = path.resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"{name} のモデルファイルが見つかりません: {path}"
        )
    return path


def configure_model_path(department):
    """指定された部門で使用するモデルファイルだけを検証して設定する。"""
    if department in {"dep1", "dep2", "dep3"}:
        model_path = resolve_model_path(DEP1_MODEL_PATH, "DEP1_MODEL_PATH")
        os.environ["DEP1_MODEL_PATH"] = str(model_path)
    elif department == "dep4":
        model_path = resolve_model_path(DEP4_MODEL_PATH, "DEP4_MODEL_PATH")
        os.environ["DEP4_MODEL_PATH"] = str(model_path)
    else:
        raise ValueError(f"未知のシミュレーション部門です: {department}")

def main():
    parser = argparse.ArgumentParser(
        description="オペアンプのシミュレーションを実行します。"
    )
    parser.add_argument(
        "department",
        nargs="?",
        choices=("dep1", "dep2", "dep3", "dep4"),
        default="dep1",
        help="シミュレーション部門 (既定値: dep1)",
    )
    args = parser.parse_args()

    configure_model_path(args.department)

    from lib.simulator import simulate_and_print
    simulate_and_print(args.department)


if __name__ == "__main__":
    main()
