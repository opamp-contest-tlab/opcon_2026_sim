import argparse
import csv
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys

# このファイルが存在するフォルダをカレントディレクトリに設定
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

# ユーザー設定：使用するモデルファイルのパス
# 別のモデルを使用する場合は、この値を変更する。
# オペアンプ設計コンテストのホームページから入手できるので任意の場所に配置し、ここでPATHを定義する
DEP1_MODEL_PATH = BASE_DIR / "lib" / "new018.mdl"
# 試作の部に参加したであれば、フェニテック社のモデルファイルを入手しているはずなので、それまでPATHを定義する
DEP4_MODEL_PATH = "/home/cad/PDK/PDK_520/common/data/sim/lib/spice_model/PTS06_spice_400.txt"

# HSPICE 実行仕様:
# - 部門1の sim1.sp と sim2.sp を順番に実行する。
# - DEP1_MODEL_PATH を絶対パスとして HSPICE の環境変数へ設定する。
# - HSPICE 実行前に opamp.sp を tmp.sp へコピーする。
# - 結果は lis/ 配下の .lis と測定CSVに保存し、削除しない。
# - opamp.sp のネットリストは前処理・書き換えを行わない。


def resolve_model_path(model_path, name):
    """モデルファイルを確認し、HSPICE が参照できる絶対パスを返す。"""
    path = Path(model_path).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{name} のモデルファイルが見つかりません: {path}")
    return path


def run_hspice(input_file, output_file):
    """入力ネットリストを HSPICE で実行し、生成された .lis を返す。"""
    executable = shutil.which("hspice")
    if executable is None:
        raise RuntimeError("hspice コマンドが PATH 上に見つかりません。")

    command = [executable, "-i", input_file.name, "-o", str(output_file)]
    print("$", " ".join(command))
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode == 0:
        return output_file

    print(f"HSPICE error (exit code: {result.returncode})", file=sys.stderr)
    if result.stdout:
        print(f"[stdout]\n{result.stdout.rstrip()}", file=sys.stderr)
    if result.stderr:
        print(f"[stderr]\n{result.stderr.rstrip()}", file=sys.stderr)
    if output_file.is_file():
        print(
            f"[listing: {output_file}]\n"
            f"{output_file.read_text(encoding='utf-8', errors='replace').rstrip()}",
            file=sys.stderr,
        )
    raise RuntimeError(f"HSPICE の実行に失敗しました: {input_file.name}")


def copy_opamp_to_tmp():
    # NOTE: 拡散長の処理を加えていないので本番環境ではここで加える処理を追加するべし
    """opamp.sp を加工せず、テストベンチが参照する tmp.sp へコピーする。"""
    source_file = BASE_DIR / "opamp.sp"
    target_file = BASE_DIR / "tmp.sp"
    if not source_file.is_file():
        raise FileNotFoundError(f"オペアンプのネットリストが見つかりません: {source_file}")
    shutil.copyfile(source_file, target_file)
    print(f"Copied: {source_file.name} -> {target_file.name}")
    return target_file


def clear_lis_directory(output_dir):
    """lis配下のシミュレーション生成物をすべて削除する。"""
    output_dir = Path(output_dir).resolve()
    expected_dir = (BASE_DIR / "lis").resolve()
    if output_dir != expected_dir:
        raise RuntimeError(f"削除対象のlisフォルダが不正です: {output_dir}")

    for path in output_dir.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    print(f"Cleared: {output_dir}")


def write_for_sr_lib(vp):
    """sim2.sp が参照する ``for_sr.lib`` にパルス振幅を設定する。"""
    path = BASE_DIR / "for_sr.lib"
    path.write_text(
        "* Vp value for SR\n\n.lib vpval\n.param vp={:.16g}\n.endl vpval\n".format(vp),
        encoding="utf-8",
    )
    print(f"Created: {path.name} (vp={vp:.6g})")
    return path


def extract_tf_output_resistance(listing_path):
    """HSPICE の .TF listing から最後に出力された出力抵抗を取得する。

    ``.TF`` の結果は測定 CSV には出力されないため、small-signal transfer
    characteristics 節だけを対象にする。複数の .ALTER / .TF がある場合は、
    HSPICE の最終実行結果に当たる最後の値を返す。
    """
    path = Path(listing_path)
    if not path.is_file():
        return None

    content = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(
        r"(?is)small-signal\s+transfer\s+characteristics(.*?)(?=\*{5,}|\Z)",
        content,
    )
    number = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?)"
    values = [
        value
        for block in blocks
        for value in re.findall(
            rf"(?i)output\s+resistance\s+at\s+.*?=\s*{number}", block
        )
    ]
    if not values:
        return None

    return float(values[-1].replace("D", "E").replace("d", "e"))


def extract_total_harmonic_distortion(listing_path):
    """HSPICE listing から最後に出力された THD [%] を取得する。"""
    path = Path(listing_path)
    if not path.is_file():
        return None

    content = path.read_text(encoding="utf-8", errors="replace")
    number = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?)"
    values = re.findall(
        rf"(?i)total\s+harmonic\s+distortion\s*=\s*{number}\s*percent",
        content,
    )
    if not values:
        return None

    return float(values[-1].replace("D", "E").replace("d", "e"))


def run_dep1_simulations(output_dir):
    """sim1のampをvpへ設定してからsim2を実行する。"""
    sim1_file = BASE_DIR / "sim1.sp"
    sim2_file = BASE_DIR / "sim2.sp"
    for input_file in (sim1_file, sim2_file):
        if not input_file.is_file():
            raise FileNotFoundError(f"テストベンチが見つかりません: {input_file}")

    # sim1.sp を実行し、srdc の測定値 amp を取得する。
    try:
        listing_file = run_hspice(sim1_file, output_dir / "result1.lis")
    except RuntimeError:
        results = {"abort": True}
        print(results)
        return results
    results = extract_from_csv()
    print(results)
    amp = results.get("amp")
    if not isinstance(amp, (int, float)) or amp <= 0:
        amp = 0.1
        print("sim1.sp の amp が取得できないため、vp=100m を使用します。")

    # sim1のampをvpvalとしてfor_sr.libへ設定後、sim2.spを実行する。
    write_for_sr_lib(amp)
    try:
        listing_file = run_hspice(sim2_file, output_dir / "result2.lis")
    except RuntimeError:
        results = {"abort": True}
        print(results)
        return results
    return print_measurements(listing_file)


def run_random_dep1_simulation(output_dir):
    """デバッグ用JSONから無作為に選んだネットリストで部門1を実行する。"""
    case_dir = BASE_DIR.parent / "debugs" / "tmp_opa-contest_dep1"
    case_files = list(case_dir.glob("*.json"))
    if not case_files:
        raise FileNotFoundError(f"デバッグ用JSONが見つかりません: {case_dir}")

    case_file = random.choice(case_files)
    try:
        with case_file.open(encoding="utf-8") as file:
            case = json.load(file)
    except (OSError, ValueError) as error:
        raise RuntimeError(f"JSONを読み込めません: {case_file}") from error

    netlist = case.get("netlist")
    if not isinstance(netlist, str) or not netlist.strip():
        raise RuntimeError(f"netlist がない、または空のJSONです: {case_file}")

    tmp_file = BASE_DIR / "tmp.sp"
    tmp_file.write_text(netlist, encoding="utf-8")
    print(f"Selected random case: {case_file.name}")
    return run_dep1_simulations(output_dir)


def extract_from_csv():
    """``lis/result1.*.csv`` から部門1の測定結果を抽出して返す。

    HSPICE の測定 CSV は先頭3行がメタデータで、4行目がヘッダーである。
    測定失敗時の ``failed`` も、結果確認のため文字列のまま返す。
    """
    csv_dir = BASE_DIR / "lis"

    def read_first_row(filename):
        """測定 CSV の最初のデータ行を {列名: float} で返す。"""
        path = csv_dir / filename
        if not path.is_file():
            return {}

        with path.open(encoding="utf-8", newline="") as file:
            for _ in range(3):
                next(file, None)
            reader = csv.DictReader(file, skipinitialspace=True)
            row = next(reader, None)

        if row is None:
            return {}

        values = {}
        for name, value in row.items():
            if value is None:
                continue
            if value.strip().lower() == "failed":
                values[name.strip()] = "failed"
                continue
            try:
                # HSPICE が指数部に D を用いる場合にも対応する。
                values[name.strip()] = float(value.replace("D", "E").replace("d", "e"))
            except ValueError:
                continue
        return values

    results = {}

    # 消費電流・消費電力: 25 ℃、電源電圧 half V の行(result1.ms1.csvの2行目)を使用する。
    power_path = csv_dir / "result1.ms1.csv"
    if power_path.is_file():
        with power_path.open(encoding="utf-8", newline="") as file:
            for _ in range(3):
                next(file, None)
            power_rows = list(csv.DictReader(file, skipinitialspace=True))
        if len(power_rows) > 1:
            for name in ("ib", "pdis"):
                value = power_rows[1].get(name, "")
                if value.strip().lower() != "failed":
                    try:
                        results[name] = float(value.replace("D", "E").replace("d", "e"))
                    except ValueError:
                        pass
    # 消費電流の9パターン(result1.ms0.csv, result1.ms1.csv, result1.ms2.csv)
    # における、基準条件の ib に対する最大変動率 (ibr) を求める。
    # ibr が 50% 未満であることを const の条件とする。
    reference_ib = results.get("ib")
    ib_values = []
    ib_measurement_failed = False
    for filename in ("result1.ms0.csv", "result1.ms1.csv", "result1.ms2.csv"):
        path = csv_dir / filename
        if not path.is_file():
            ib_measurement_failed = True
            continue

        with path.open(encoding="utf-8", newline="") as file:
            for _ in range(3):
                next(file, None)
            rows = csv.DictReader(file, skipinitialspace=True)
            for row in rows:
                value = row.get("ib")
                if value is None or value.strip().lower() == "failed":
                    ib_measurement_failed = True
                    continue
                try:
                    ib_values.append(float(value.replace("D", "E").replace("d", "e")))
                except ValueError:
                    ib_measurement_failed = True

    if reference_ib is not None and reference_ib != 0 and ib_values:
        ibr = max(
            abs(value - reference_ib) / abs(reference_ib) for value in ib_values
        )
        results["ibr"] = ibr * 100  # num -> % 変換
        # 既存の出力キーを利用している呼び出し元との互換性を維持する。
        results["ib_diff"] = ibr
        results["ib_const"] = not ib_measurement_failed and ibr < 0.5
    else:
        results["ibr"] = None
        results["ib_const"] = False

    # 出力抵抗: .TF の結果は CSV 化されないため result1.lis から取得する。
    rosim = extract_tf_output_resistance(csv_dir / "result1.lis")
    if rosim is not None:
        results["rosim"] = max(rosim, 0.1)

    # THD: .FFT の結果は CSV 化されないため result1.lis から取得する。
    thd = extract_total_harmonic_distortion(csv_dir / "result1.lis")
    if thd is not None:
        results["thd"] = thd

    # 利得・位相余裕・雑音・CMRR・PSRR。
    for filename, names in (
        # ("result1.ma2.csv", ("dcgain", "dcgain_db", "ugf", "gbw", "pm")),
        # ("result1.ma3.csv", ("input_noise", "irn")),
        # ("result1.ma6.csv", ("cmrr", "cmrr_db")),
        # ("result1.ma7.csv", ("psrr", "psrr_db")),
        # ("result1.ms9.csv", ("vpmax", "vnmax", "amp")),
        ("result1.ma2.csv", ("dcgain", "dcgain_db", "ugf", "gbw", "pm")),
        ("result1.ma3.csv", ("input_noise", "irn")),
        ("result1.ma6.csv", ("cmrr",)),
        ("result1.ma7.csv", ("psrr",)),
        ("result1.ms9.csv", ("ib_tt", "pdis_tt",)),
        ("result1.ms10.csv", ("vpmax", "vnmax", "amp",)),
    ):
        values = read_first_row(filename)
        for name in names:
            if name in values:
                results[name] = values[name]

    # 同相入力範囲・出力電圧範囲はテストベンチで計算済みの百分率を使用する。
    values = read_first_row("result1.ms4.csv")
    if "psvoltage" in values:
        results["psvoltage"] = values["psvoltage"]

    for filename, names in (
        # ("result1.ms3.csv", ("ib_tt", "pdis_tt")),
        # ("result1.ms0.csv", ("ib", "pdis", "cmr")),
        # ("result1.ms8.csv", ("ovr1", "ovr2", "ovr")),
    ):
        values = read_first_row(filename)
        for name in names:
            if name in values:
                results["cmir" if name == "cmr" else name] = values[name]

    # sim2.sp のスルーレート測定結果。
    values = read_first_row("result2.mt0.csv")
    for name in (
        "vo1min", "vo1max", "vo1f", "vi1f",
        "srr1", "srr2", "srr3", "srr",
        "vo2max", "vo2min", "vo2f", "vi2f",
        "srf1", "srf2", "srf3", "srf", "sr",
    ):
        if name in values:
            results[name] = values[name]
    # 個別の処理の計算
    error_limit = 0.05

    # CMIR: result1.printsw4 の数値列は、それぞれ
    # [V(in1), V(out1, os), V(out2, os), out1 の誤差, out2 の誤差]。
    # .MEAS の交差点探索が failed になる場合があるので、各出力の誤差が
    # しきい値以下である行から対応する V(in) の最大値を求める。
    cmir_path = csv_dir / "result1.printsw4"
    cmr1_candidates = []
    cmr2_candidates = []
    if cmir_path.is_file():
        with cmir_path.open(encoding="utf-8", errors="replace") as file:
            for line in file:
                fields = line.split()
                if len(fields) != 5:
                    continue
                try:
                    values = [
                        float(field.replace("D", "E").replace("d", "e"))
                        for field in fields
                    ]
                except ValueError:
                    continue

                if values[3] < error_limit:
                    cmr1_candidates.append(values[0])
                if values[4] < error_limit:
                    cmr2_candidates.append(values[0])

    results["cmr1"] = max(cmr1_candidates) if cmr1_candidates else 0.0
    results["cmr2"] = max(cmr2_candidates) if cmr2_candidates else 0.0

    # OVR: result1.printsw8 の数値列は [V(in), V(out1, os), V(out2, os),
    # out1 の誤差, out2 の誤差]。各出力の誤差が 0.05 以下である行から、
    # 対応する V(in) の最大値を求める。
    ovr_path = csv_dir / "result1.printsw8"
    ovr1_candidates = []
    ovr2_candidates = []
    if ovr_path.is_file():
        with ovr_path.open(encoding="utf-8", errors="replace") as file:
            for line in file:
                fields = line.split()
                if len(fields) not in (3, 5):
                    continue
                try:
                    values = [
                        float(field.replace("D", "E").replace("d", "e"))
                        for field in fields
                    ]
                except ValueError:
                    continue

                vin, vout1, vout2 = values[:3]
                if vin == 0:
                    continue
                # 誤差列がない古い出力形式では、出力電圧から算出する。
                ovr1_error = values[3] if len(values) == 5 else 1 - abs(vout1 / vin)
                ovr2_error = values[4] if len(values) == 5 else 1 - abs(vout2 / vin)
                if ovr1_error <= error_limit:
                    ovr1_candidates.append(vin)
                if ovr2_error <= error_limit:
                    ovr2_candidates.append(vin)

    results["ovr1"] = max(ovr1_candidates) if ovr1_candidates else 0.0
    results["ovr2"] = max(ovr2_candidates) if ovr2_candidates else 0.0

    psvoltage = results.get("psvoltage")
    if isinstance(psvoltage, (int, float)) and psvoltage != 0:
        results["cmir"] = round( (0.5 * (results["cmr1"] + results["cmr2"]) / psvoltage * 100) ,5)
        results["ovr"] = round_sig( ((abs(results["ovr1"]) + abs(results["ovr2"])) / psvoltage * 100) ,5)

    return results

import math
def round_sig(value, digits=4):
    # 有効数字で丸める関数
    if value == 0:
        return 0.0
    return round(value, digits - 1 - int(math.floor(math.log10(abs(value)))))


def print_measurements(listing_file):
    """HSPICE が生成した測定CSVの抽出結果をそのまま表示する。"""
    results = extract_from_csv()
    print(results)
    return results


def main():
    """部門1の sim1.sp と sim2.sp をそのまま HSPICE で実行する。"""
    parser = argparse.ArgumentParser(
        description="部門1のオペアンプHSPICEシミュレーションを実行します。"
    )
    parser.add_argument(
        "--mode",
        choices=("normal", "random"),
        default="normal",
        help="normal: opamp.spを使用、random: デバッグ用JSONを無作為に使用",
    )
    args = parser.parse_args()

    os.environ["DEP1_MODEL_PATH"] = str(
        resolve_model_path(DEP1_MODEL_PATH, "DEP1_MODEL_PATH")
    )
    output_dir = BASE_DIR / "lis"
    output_dir.mkdir(exist_ok=True)

    # sim1.sp と sim2.sp は tmp.sp を .include する。
    if args.mode == "random":
        results = run_random_dep1_simulation(output_dir)
    else:
        copy_opamp_to_tmp()
        results = run_dep1_simulations(output_dir)
    clear_lis_directory(output_dir)
    return results


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
