# import ipywidgets as widgets
# from IPython.display import display, clear_output, HTML
from pathlib import Path
from decimal import Decimal
import ast
import os
import sys
import traceback
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import time, subprocess, re, math
import tabulate as _tabulate

# 最終結果の Markdown はプロジェクトルートへ保存する。
# 波形画像の out/ は従来どおり実行ディレクトリに保存する。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXECUTION_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = EXECUTION_DIR / "out"
RESULT_MARKDOWN_PATH = PROJECT_ROOT / "simulatinon_results.md"

# 日本語などの全角文字を端末上の表示幅で計算する
_tabulate.WIDE_CHARS_MODE = True
tabulate = _tabulate.tabulate


def _debug_enabled(debug=None):
    """デバッグモードが有効かを返す。環境変数でも切り替えられる。"""
    if debug is not None:
        return debug
    return os.environ.get("SIMULATOR_DEBUG", "").lower() in {
        "1", "true", "yes", "on"
    }


def _debug_exception(context, error, debug=False):
    """デバッグ時に例外の発生関数・行番号・トレースバックを表示する。"""
    if not debug:
        return

    traceback_frames = traceback.extract_tb(error.__traceback__)
    if traceback_frames:
        frame = traceback_frames[-1]
        location = f"{frame.name} ({frame.filename}:{frame.lineno})"
    else:
        location = "発生箇所を特定できません"
    print(f"[DEBUG] {context}: {location}", file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def _debug_subprocess_result(result, debug=False):
    """デバッグ時にHSPICEの終了コードと出力を表示する。"""
    if not debug:
        return
    stdout = result.stdout.decode(errors="replace") if isinstance(result.stdout, bytes) else result.stdout
    stderr = result.stderr.decode(errors="replace") if isinstance(result.stderr, bytes) else result.stderr
    print(f"[DEBUG] HSPICE returncode: {result.returncode}", file=sys.stderr)
    if stdout:
        print(f"[DEBUG] HSPICE stdout:\n{stdout}", file=sys.stderr)
    if stderr:
        print(f"[DEBUG] HSPICE stderr:\n{stderr}", file=sys.stderr)


def _print_hspice_error(result, output_file):
    """HSPICE異常終了時に、標準出力・標準エラー・.lisを表示する。"""
    if result.returncode == 0:
        return

    print(f"HSPICE error (exit code: {result.returncode})")
    messages = []
    for label, stream in (("stdout", result.stdout), ("stderr", result.stderr)):
        if isinstance(stream, bytes):
            stream = stream.decode(errors="replace")
        if stream:
            messages.append(f"[HSPICE {label}]\n{stream.rstrip()}")

    output_path = Path(output_file)
    if output_path.exists():
        lis_text = output_path.read_text(encoding="utf-8", errors="ignore")
        if lis_text:
            messages.append(f"[HSPICE出力: {output_path}]\n{lis_text.rstrip()}")

    if messages:
        print("\n\n".join(messages))
    else:
        print("HSPICE did not return an error message.")
# matplotlibの設定
plt.rcParams["font.family"] = 'Nimbus Roman'
plt.rcParams['xtick.direction'] = 'in'  # 内向き
plt.rcParams['ytick.direction'] = 'in'  # 内向き


def process_netlist(netlist_text, department):
    """
    ネットリスト内のMOSFET行を処理し、ad, as, pd, ps パラメータを追加または更新する
    """
    # 部門ごとの定数設定
    if department in ['dep1', 'dep2', 'dep3']:
        tmp = '0.6u'
    elif department == 'dep4':
        tmp = '1.0u'
    else:
        raise ValueError("Invalid department")
    processed_lines = []
    for line in netlist_text.splitlines():
        stripped = line.strip()
        
        # MOSFET行判定（行頭が M の場合）
        if stripped.startswith("M"):
            # w=<something> を取り出す
            w_match = re.search(r"w\s*=\s*([\d\.]+[munp]?)", line, re.IGNORECASE)
            if w_match:
                w_val = w_match.group(1)  # 例: "5u"

                # 値生成
                ad_val = f"{w_val}*{tmp}"
                as_val = f"{w_val}*{tmp}"
                pd_val = f"{w_val}+{tmp}*2"
                ps_val = f"{w_val}+{tmp}*2"

                # 既存の ad/as/pd/ps を削除してから追加する
                line = re.sub(r"\bad\s*=\s*[^ ]+", "", line)
                line = re.sub(r"\bas\s*=\s*[^ ]+", "", line)
                line = re.sub(r"\bpd\s*=\s*[^ ]+", "", line)
                line = re.sub(r"\bps\s*=\s*[^ ]+", "", line)

                # 余分なスペースを削除
                line = re.sub(r"\s+", " ", line).strip()

                # 最後に新しい ad/as/pd/ps を追加
                line += f" ad='{ad_val}' as='{as_val}' pd='{pd_val}' ps='{ps_val}'"
        if 'psvoltage' in stripped and department in ['dep4']:
            # 部門4はpsvoltageを5.0に設定
            line = re.sub(r"psvoltage\s*=\s*[\d\.]+", f"psvoltage={5.0}", line, flags=re.IGNORECASE)

        processed_lines.append(line)

    return "\n".join(processed_lines)


_SPICE_SCALE = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}


def _spice_value(value, parameters):
    """SPICE の数値、単位、パラメータ、加減乗除式を安全に評価する。"""
    expression = value.strip().strip("'\"").lower()
    expression = re.sub(
        r"((?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(meg|[tgkmunpf])",
        lambda match: str(float(match.group(1)) * _SPICE_SCALE[match.group(2)]),
        expression,
    )

    tree = ast.parse(expression, mode="eval")

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in parameters:
            return parameters[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = evaluate(node.operand)
            return operand if isinstance(node.op, ast.UAdd) else -operand
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right
        raise ValueError(f"Unsupported SPICE expression: {value}")

    return evaluate(tree)


def _read_netlist_parameters(netlist_text):
    """.PARAM の単一行・継続行を読み込み、数値パラメータを返す。"""
    parameters = {}
    in_param_block = False
    for raw_line in netlist_text.splitlines():
        line = raw_line.split("$", 1)[0].strip()
        if not line:
            continue
        if line.lower().startswith(".param"):
            in_param_block = True
            param_text = line[6:].strip()
        elif in_param_block and line.startswith("+"):
            param_text = line[1:].strip()
        else:
            in_param_block = False
            continue

        assignments = re.findall(
            r"([A-Za-z_]\w*)\s*=\s*('[^']+'|\"[^\"]+\"|[^\s]+)",
            param_text,
            flags=re.IGNORECASE,
        )
        for name, value in assignments:
            parameters[name.lower()] = _spice_value(value, parameters)
    return parameters


def _extract_mos_geometry(netlist_text):
    """opamp サブサーキット内の MOS 寸法を SI 単位で抽出する。"""
    parameters = _read_netlist_parameters(netlist_text)
    geometry = []
    in_opamp = False
    for raw_line in netlist_text.splitlines():
        line = raw_line.split("$", 1)[0].strip()
        lower = line.lower()
        if re.match(r"\.subckt\s+opamp(?:\s|$)", lower):
            in_opamp = True
            continue
        if in_opamp and re.match(r"\.ends(?:\s+opamp)?(?:\s|$)", lower):
            break
        if not in_opamp or not re.match(r"m\S*\s", line, re.IGNORECASE):
            continue

        values = {}
        for name in ("l", "w", "m", "ad", "as", "pd", "ps"):
            match = re.search(
                rf"\b{name}\s*=\s*('[^']+'|\"[^\"]+\"|[^\s]+)",
                line,
                re.IGNORECASE,
            )
            if match:
                values[name] = _spice_value(match.group(1), parameters)
        if "l" in values and "w" in values:
            values["name"] = line.split()[0]
            geometry.append(values)
    return geometry


def _extract_dep4_passive_values(netlist_text):
    """部門4の opamp サブサーキット内にある抵抗・容量値を抽出する。"""
    parameters = _read_netlist_parameters(netlist_text)
    values = {"resistance": [], "capacitance": []}
    in_opamp = False
    for raw_line in netlist_text.splitlines():
        line = raw_line.split("$", 1)[0].strip()
        lower = line.lower()
        if re.match(r"\.subckt\s+opamp(?:\s|$)", lower):
            in_opamp = True
            continue
        if in_opamp and re.match(r"\.ends(?:\s+opamp)?(?:\s|$)", lower):
            break
        if not in_opamp or not line or line.startswith("*"):
            continue

        tokens = line.split()
        if len(tokens) < 4 or tokens[0][0].upper() not in {"R", "C"}:
            continue
        try:
            component_value = _spice_value(tokens[3], parameters)
        except (SyntaxError, ValueError, ZeroDivisionError):
            continue
        key = "resistance" if tokens[0][0].upper() == "R" else "capacitance"
        values[key].append(component_value)
    return values


_RESISTOR_PARALLEL_COUNTS = (1, 2, 5, 10, 50)
_DEP4_RESISTOR_PARALLEL_COUNTS = (1, 2, 5, 10, 50, 100, 200, 1000)


def _resistor_unit_stages(unit_resistance, parallel_counts=_RESISTOR_PARALLEL_COUNTS):
    """単位抵抗値から、直列・並列構成の各段階を生成する。"""
    return tuple(
        (unit_resistance / parallel_count, parallel_count)
        for parallel_count in parallel_counts
    )


def _unit_resistor_count(
    resistance,
    unit_resistance=50.0,
    parallel_counts=_RESISTOR_PARALLEL_COUNTS,
    stage_index=0,
):
    """抵抗値を、指定した単位抵抗の個数へ再帰的に換算する。

    各段階で抵抗値を基準抵抗と余りに分解し、商に対応する単位抵抗数を
    加算する。並列数は ``parallel_counts`` で指定する。
    """
    if resistance <= 0:
        return 0
    stages = _resistor_unit_stages(unit_resistance, parallel_counts)
    if stage_index == len(stages):
        # 最小段階より小さい値は、目標抵抗値以下になるよう並列数を切り上げる。
        return math.ceil(unit_resistance / resistance)

    stage_resistance, stage_count = stages[stage_index]
    quotient, remainder = divmod(resistance, stage_resistance)
    if math.isclose(remainder, 0.0, rel_tol=1e-9, abs_tol=1e-9):
        remainder = 0.0
    return int(quotient) * stage_count + _unit_resistor_count(
        remainder, unit_resistance, parallel_counts, stage_index + 1
    )


def calculate_mos_area(netlist_text, department="dep1"):
    """指定部門の回路面積を um^2 で返す。

    AD/AS がない部門1〜3の MOS は、拡散幅 0.6um として補完する。
    PD/PS は ``W + 2 * 0.6um`` となるが、面積計算には AD/AS のみを使う。
    部門1〜3は抵抗を50Ω単位抵抗（0.4um×0.4um）、容量を
    1fF/um^2 に換算して加算する。
    部門4は MOS・抵抗・容量を部門4固有の換算式で計算する。
    """
    area_m2 = 0.0
    for values in _extract_mos_geometry(netlist_text):
        multiplier = values.get("m", 1.0)
        if department == "dep4":
            # 部門4: MOS = W * (L * 2um)
            # W/L は SI 単位で抽出済みなので、2um幅の面積として加算する。
            area_m2 += values["w"] * values["l"] * 2 * multiplier
            continue
        diffusion_area = values.get("ad", 0.0) + values.get("as", 0.0)
        if department in {"dep1", "dep2", "dep3"}:
            diffusion_area += sum(
                values["w"] * 0.6e-6
                for key in ("ad", "as")
                if key not in values
            )
        area_m2 += values["w"] * values["l"] * multiplier
        area_m2 += diffusion_area * multiplier
    if department == "dep4":
        passive_values = _extract_dep4_passive_values(netlist_text)
        area_um2 = area_m2 / 1e-12
        area_um2 += sum(passive_values["capacitance"]) / 3e-15
        area_um2 += sum(
            _unit_resistor_count(
                resistance,
                unit_resistance=1e3,
                parallel_counts=_DEP4_RESISTOR_PARALLEL_COUNTS,
            )
            * 4
            for resistance in passive_values["resistance"]
        )
        return area_um2
    area_um2 = area_m2 / 1e-12
    if department in {"dep1", "dep2", "dep3"}:
        passive_values = _extract_dep4_passive_values(netlist_text)
        area_um2 += sum(
            _unit_resistor_count(resistance) * 0.4 * 0.4
            for resistance in passive_values["resistance"]
        )
        area_um2 += sum(passive_values["capacitance"]) / 1e-15
    return area_um2


def validate_mos_geometry(netlist_text, tolerance=1e-9):
    """PD/PS と AD/AS が矩形拡散形状として整合するか検証する。

    既存のネットリストが使う形状 ``A = W*x, P = W+2*x`` を検証する。
    寸法が欠落している MOS は検証不能として False を返す。
    """
    for values in _extract_mos_geometry(netlist_text):
        required = ("ad", "as", "pd", "ps")
        if not all(key in values for key in required):
            return False
        expected_ad = values["w"] * (values["pd"] - values["w"]) / 2
        expected_as = values["w"] * (values["ps"] - values["w"]) / 2
        scale = max(values["ad"], values["as"], 1e-30)
        if abs(expected_ad - values["ad"]) > tolerance * scale:
            return False
        if abs(expected_as - values["as"]) > tolerance * scale:
            return False
    return True


def calculate_mos_area_from_file(source_file="./opamp.sp", department="dep1"):
    """opamp.sp を読み込み、MOS 面積 (um^2) を計算する。"""
    return calculate_mos_area(
        Path(source_file).read_text(encoding="utf-8"), department=department
    )

# =========================================
# 共通：.lis からテーブルを抜き出す関数
# =========================================
def parse_table_from_lis(lines, label, header_token):
    """
    HSPICE .lis の中から、
    - 特定のラベル（ac2, ac4, ac5, dc2, dc3 など）
    - その直後に出てくる 'freq' または 'volt' を先頭に持つ表
    を抜き出す。
    """
    # ラベルの位置を探す
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == label:
            start_idx = idx
            break
    if start_idx is None:
        return None

    # ヘッダ行（freq / volt で始まる行）を探す
    header_idx = None
    for j in range(start_idx + 1, len(lines)):
        parts = lines[j].split()
        if parts and parts[0].lower() == header_token.lower():
            header_idx = j
            break
    if header_idx is None:
        return None

    header_line = lines[header_idx]

    # ヘッダ継続行（out, param など）をスキップして、最初の数値行を探す
    k = header_idx + 1
    header_cont = []
    while k < len(lines):
        line = lines[k]
        if not line.strip():
            k += 1
            continue
        first_non = line.lstrip()[0]
        if first_non in "+-.0123456789":
            break  # ここからデータ
        header_cont.append(line)
        k += 1

    # データ行を読み取り
    data = []
    for idx in range(k, len(lines)):
        line = lines[idx]
        if not line.strip():
            break
        first_non = line.lstrip()[0]
        if first_non not in "+-.0123456789":
            break
        parts = line.split()
        try:
            vals = [float(p) for p in parts]
        except ValueError:
            break
        data.append(vals)

    if not data:
        return None

    return {
        "label": label,
        "header": header_line,
        "header_cont": header_cont,
        "data": data,  # list of [x, y1, y2, ...]
    }


# =========================================
# 各解析ごとのプロット関数群
# =========================================
def plot_ac2_gain_phase(block):
    """
    ac2: 周波数 – 利得(dB) – 位相(deg)
    """
    arr = block["data"]
    freq = [row[0] for row in arr]
    gain = [row[1] for row in arr]
    phase = [row[2] for row in arr]

    fig, ax1 = plt.subplots()
    ax1.set_xscale("log")
    l1 = ax1.plot(freq, gain, color='#005AFF', label="Gain", zorder=5)
    ax1.set_xlabel("Frequency [Hz]")
    ax1.set_ylabel("Gain [dB]")
    ax1.grid(True, which="both", linestyle=':')

    ax2 = ax1.twinx()
    l2 = ax2.plot(freq, phase, color='#03AF7A', linestyle='--', label="Phase", zorder=10)
    ax2.set_ylabel("Phase [deg]")

    plt.xlim(min(freq), max(freq))
    lines = l1 + l2
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels)
    ax1.set_zorder(11)
    ax2.set_zorder(10)
    ax1.patch.set_visible(False)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ac2_gain_phase.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "ac2_gain_phase.svg", transparent=True)
    plt.title("Gain & Phase")
    # plt.show()
    plt.close()


def plot_ac4_cmrr(block):
    """
    ac4: CMRR (vdb(od)-vdb(oc)) [dB]
    """
    arr = block["data"]
    freq = [row[0] for row in arr]
    od = [row[1] for row in arr]
    oc = [row[2] for row in arr]
    cmrr = [row[3] for row in arr]

    plt.figure()
    plt.xscale("log")
    plt.plot(freq, od, label="od", color='#005AFF', linestyle='--')
    plt.plot(freq, oc, label="oc", color='#03AF7A', linestyle='--')
    plt.plot(freq, cmrr, label="CMRR", color='#FF4B00')
    plt.xlabel("Frequency [Hz]")
    plt.ylabel("CMR [dB]")
    plt.grid(True, which="both", linestyle=':')
    plt.xlim(min(freq), max(freq))
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ac4_cmrr.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "ac4_cmrr.svg", transparent=True)
    plt.title("CMRR")
    # plt.show()
    plt.close()


def plot_ac5_psrr(block):
    """
    ac5: PSRR (電源ライン上下)
    param vdb(od,odd), param vdb(od,oss)
    """
    arr = block["data"]
    freq = [row[0] for row in arr]
    psrr_top = [row[1] for row in arr]    # 例: VDD側
    psrr_bottom = [row[2] for row in arr] # 例: VSS側

    plt.figure()
    plt.xscale("log")
    # freq=0.1のときに値が小さい方を実線, 大きい方を破線にする
    if psrr_top[0] < psrr_bottom[0]:
        plt.plot(freq, psrr_top, label="PSRR (Vdd)", color='#005AFF', linestyle='-')
        plt.plot(freq, psrr_bottom, label="PSRR (Vss)", color='#03AF7A', linestyle='--')
    else:
        plt.plot(freq, psrr_top, label="PSRR (Vdd)", color='#005AFF', linestyle='--')
        plt.plot(freq, psrr_bottom, label="PSRR (Vss)", color='#03AF7A', linestyle='-')
    plt.xlabel("Frequency [Hz]")
    plt.ylabel("PSR [dB]")
    plt.grid(True, which="both", linestyle=':')
    plt.xlim(min(freq), max(freq))
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "ac5_psrr.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "ac5_psrr.svg", transparent=True)
    plt.title("PSRR")
    # plt.show()
    plt.close()


def plot_dc_sweep1(block):
    """
    dc2 : DCスイープ1
    同相入力範囲
    """
    arr = block["data"]
    vin = [row[0] for row in arr]
    out1 = [row[1] for row in arr]
    out2 = [row[2] for row in arr]

    plt.figure()
    plt.plot(vin, out1, label="out(Positive)", color='#005AFF')
    plt.plot(vin, out2, label="out(Negative)", color='#03AF7A')
    plt.plot(vin, [-i*0.5 for i in vin], label="out(ideal)", color="#FF4B00", linestyle=':')
    plt.plot(vin, [i*0.5 for i in vin], color="#FF4B00", linestyle=':')
    plt.xlabel("Input [V]")
    plt.ylabel("Output [V]")
    plt.xlim(min(vin), max(vin))
    plt.grid(True, which="both", linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "dc2_input_range.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "dc2_input_range.svg", transparent=True)
    plt.title('Input Voltage Range')
    # plt.show()
    plt.close()

def plot_dc_sweep2(block):
    """
    dc3 : DCスイープ2
    出力電圧範囲
    """
    arr = block["data"]
    vin = [row[0] for row in arr]
    out1 = [row[1] for row in arr]
    out2 = [row[2] for row in arr]

    plt.figure()
    plt.plot(vin, out1, label="out(Positive)", color='#005AFF')
    plt.plot(vin, out2, label="out(Negative)", color='#03AF7A')
    plt.plot(vin, [-i for i in vin], label="out(ideal)", color="#FF4B00", linestyle=':')
    plt.plot(vin, [i for i in vin], color="#FF4B00", linestyle=':')
    plt.xlabel("Input [V]")
    plt.ylabel("Output [V]")
    plt.xlim(min(vin), max(vin))
    plt.grid(True, which="both", linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "dc3_output_range.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "dc3_output_range.svg", transparent=True)
    plt.title('Output Voltage Range')
    # plt.show()
    plt.close()

def plot_dc_sweep3(block):
    """
    dc3 : DCスイープ3
    (部門4用)
    """
    arr = block["data"]
    vin = [row[0] for row in arr]
    out = [row[1] for row in arr]
    out2 = [row[2] for row in arr]

    plt.figure()
    plt.plot(vin, out, label="out(Positive)", color='#005AFF')
    plt.plot(vin, out2, label="out(Negative)", color='#03AF7A')
    plt.plot(vin, [-i*4 for i in vin], label="out(ideal)", color="#FF4B00", linestyle=':')
    plt.plot(vin, [i*4 for i in vin], color="#FF4B00", linestyle=':')
    plt.xlabel("Input [V]")
    plt.ylabel("Output [V]")
    plt.xlim(min(vin), max(vin))
    plt.grid(True, which="both", linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "dc3_input_range.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "dc3_input_range.svg", transparent=True)
    plt.title('Output Voltage Range')
    # plt.show()
    plt.close()

def plot_sr(block):
    """
    スルーレート(部門1-3)
    """
    arr = block["data"]
    # 0.8e6秒までのデータを取得
    time = [row[0]*1e6 for row in arr if row[0] <= 0.8e-6]
    out1 = [row[1] for row in arr if row[0] <= 0.8e-6]
    out2 = [row[2] for row in arr if row[0] <= 0.8e-6]
    plt.figure()
    plt.plot(time, out1, label="out(Rise)", color='#005AFF')
    plt.plot(time, out2, label="out(Fall)", color='#03AF7A')
    plt.xlabel("Time [us]")
    plt.ylabel("Output [V]")
    plt.xlim(0, 0.8)
    plt.grid(True, which="both", linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "sr_waveform.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "sr_waveform.svg", transparent=True)
    plt.title('Slew Rate')
    # plt.show()
    plt.close()

def plot_sr2(block):
    """
    スルーレート(部門4)
    """
    arr = block["data"]
    time = [row[0]*1e6 for row in arr if row[0]]
    out1 = [row[1] for row in arr if row[0]]
    out2 = [row[2] for row in arr if row[0]]
    plt.figure()
    plt.plot(time, out1, label="out(Rise)", color='#005AFF')
    plt.plot(time, out2, label="out(Fall)", color='#03AF7A')
    plt.xlabel("Time [us]")
    plt.ylabel("Output [V]")
    plt.grid(True, which="both", linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "sr_waveform.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "sr_waveform.svg", transparent=True)
    plt.title('Slew Rate')
    # plt.show()
    plt.close()

    plt.figure()
    plt.plot(time, out1, label="out(Rise)", color='#005AFF')
    plt.plot(time, out2, label="out(Fall)", color='#03AF7A')
    plt.xlabel("Time [us]")
    plt.ylabel("Output [V]")
    plt.xlim(0, 20)
    plt.grid(True, which="both", linestyle=':')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "sr_waveform2.pdf", transparent=True)
    plt.savefig(OUTPUT_DIR / "sr_waveform2.svg", transparent=True)
    plt.title('Slew Rate (Detailed View)')
    # plt.show()
    plt.close()


def plot_dep1_3():
    """
    部門1-3の結果プロットを一括実行する関数
    """
    # with open("result1.lis", "r", encoding="utf-8", errors="ignore") as f:
    #     lines = f.read().splitlines()

    # # ac2: 利得・位相余裕
    # ac2_block = parse_table_from_lis(lines, label="ac2", header_token="freq")
    # if ac2_block:
    #     plot_ac2_gain_phase(ac2_block)
    # else:
    #     print("ac2 のデータが見つかりませんでした。")

    # # ac4: CMRR
    # ac4_block = parse_table_from_lis(lines, label="ac4", header_token="freq")
    # if ac4_block:
    #     plot_ac4_cmrr(ac4_block)
    # else:
    #     print("ac4 (CMRR) のデータが見つかりませんでした。")

    # # ac5: PSRR（電源ライン上下）
    # ac5_block = parse_table_from_lis(lines, label="ac5", header_token="freq")
    # if ac5_block:
    #     plot_ac5_psrr(ac5_block)
    # else:
    #     print("ac5 (PSRR) のデータが見つかりませんでした。")

    # # dc2: DCスイープ
    # dc2_block = parse_table_from_lis(lines, label="dc2", header_token="volt")
    # if dc2_block:
    #     plot_dc_sweep1(dc2_block)
    # else:
    #     print("dc2 のデータが見つかりませんでした。")

    # # dc3: DCスイープその2
    # dc3_block = parse_table_from_lis(lines, label="dc3", header_token="volt")
    # if dc3_block:
    #     plot_dc_sweep2(dc3_block)
    # else:
    #     print("dc3 のデータが見つかりませんでした。")

    # sr: スルーレート (別ファイル)
    with open('result2.lis', "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

    sr_block = parse_table_from_lis(lines, label="sr", header_token="time")
    if sr_block:
        plot_sr(sr_block)
    else:
        print("SR data was not found.")

def plot_dep4():
    """
    部門4の結果プロットを一括実行する関数
    """
    # with open("result1.lis", "r", encoding="utf-8", errors="ignore") as f:
    #     lines = f.read().splitlines()

    # # ac1: 利得・位相余裕
    # ac1_block = parse_table_from_lis(lines, label="ac1", header_token="freq")
    # if ac1_block:
    #     plot_ac2_gain_phase(ac1_block)
    # else:
    #     print("ac1 のデータが見つかりませんでした。")

    # # ac2: 帯域幅
    # ac2_block = parse_table_from_lis(lines, label="ac2", header_token="freq")
    # if ac2_block:
    #     plot_ac2_gain_phase(ac2_block)
    # else:
    #     print("ac2 のデータが見つかりませんでした。")

    # # dc2: 入力電圧範囲
    # dc2_block = parse_table_from_lis(lines, label="dc2", header_token="volt")
    # if dc2_block:
    #     plot_dc_sweep3(dc2_block)
    # else:
    #     print("dc2 のデータが見つかりませんでした。")

    # tran1: スルーレート
    tran1_block = parse_table_from_lis(lines, label="tran1", header_token="time")
    if tran1_block:
        plot_sr2(tran1_block)
    else:
        print("TRAN1 data was not found.")


def print_performance_table(
    results,
    sim_type,
    psvoltage=None,
    error_flag=False,
    mos_area=None,
    markdown_path=None,
):
    """シミュレーション結果を英語の端末表とMarkdownで出力する。"""
    if error_flag:
        print("This circuit does not operate as an operational amplifier.")
        print("(An error occurred during the simulation.)")
        return

    print("Analysis results for the latest submitted circuit")
    if not results.get("const", False):
        print("[Warning] The circuit does not satisfy all constraints.")

    rows = []

    def si_value(value, unit, decimals=3):
        """数値をSI接頭語付きの工学記法で表示する。"""
        prefixes = (
            (1e9, "G"),
            (1e6, "M"),
            (1e3, "k"),
            (1.0, ""),
            (1e-3, "m"),
            (1e-6, "u"),
            (1e-9, "n"),
            (1e-12, "p"),
        )
        if value == 0:
            return f"{value:.{decimals}f} {unit}"
        magnitude = abs(value)
        scale, prefix = next(
            (scale, prefix)
            for scale, prefix in prefixes
            if magnitude >= scale
        )
        return f"{value / scale:.{decimals}f} {prefix}{unit}"

    def row(label, value, condition="-"):
        rows.append([label, value, condition])

    for department in ("dep1", "dep2", "dep3", "dep4"):
        fom = results.get(f"fom{department}")
        row(
            f"FOM ({department})",
            f"{fom:.3e}" if fom is not None else "-",
            "Calculated in this analysis",
        )
    if sim_type in ["dep1", "dep2", "dep3"]:
        row("Supply voltage (V)", si_value(psvoltage, "V"))
        row("Supply current (A)", si_value(results["ib"], "A"), "Within ±50% of the reference value")
        row("Power consumption (W)", si_value(results["pdis"], "W"), "<= 100 mW")
        row("Output resistance (Ω)", si_value(results["ro"], "Ω"))
        row("DC gain (dB)", f"{results['dcgain_db']:.2f}", ">= 40 dB")
        row("Phase margin (deg)", f"{results['pm']:.2f}", ">= 45 deg")
        row("Gain-bandwidth product (Hz)", si_value(results["gbw"], "Hz"), ">= 1 MHz")
        row("Input-referred noise (V)", si_value(results["irn"], "V"))
        row("Slew rate (V/s)", si_value(results["sr"], "V/s"), ">= 100 kV/s")
        row("Total harmonic distortion (%)", f"{results['thd']:.4f}", "<= 1.0 %")
        row("Common-mode rejection ratio (dB)", f"{results['cmrr_db']:.2f}", ">= 40 dB")
        row("Power-supply rejection ratio (dB)", f"{results['psrr_db']:.2f}", ">= 40 dB")
        row("Common-mode input range (%)", f"{results['cmir']:.2f}", ">= 5.0 %")
        row("Output voltage range (%)", f"{results['ovr']:.2f}", ">= 5.0 %")
    elif sim_type == "dep4":
        row("Supply voltage (V)", si_value(5.0, "V"))
        row("Supply current (A)", si_value(results["ib"], "A"))
        row("Power consumption (W)", si_value(results["pdis"], "W"))
        row("DC gain (dB)", f"{results['dcgain_db']:.2f}", ">= 40 dB")
        row("Phase margin (deg)", f"{results['pm']:.2f}", ">= 45 deg")
        row("Slew rate (V/s)", si_value(results["sr"], "V/s"), ">= 1 MV/s")
        row("Total harmonic distortion (%)", f"{results['thd']:.4f}", "<= 0.1 %")
        row("Bandwidth (Hz)", si_value(results["bw"], "Hz"), ">= 20 kHz")
        row("Input voltage amplitude (V)", si_value(results["ivr"], "V"), ">= 100 mV")
        row("Offset voltage (V)", si_value(results["offset"], "V"), "Absolute value <= 100 mV")

    row(
        "Occupied area (μm²)",
        f"{mos_area:.3f}" if mos_area is not None else "Unavailable",
    )
    headers = ["Metric", "Value", "Requirement"]
    table_kwargs = dict(
        headers=headers,
        colalign=("left", "right", "left"),
        disable_numparse=True,
    )
    print(tabulate(rows, tablefmt="simple_grid", **table_kwargs))
    if markdown_path is not None:
        markdown_numeric_values = {
            "FOM (dep1)": results.get("fomdep1"),
            "FOM (dep2)": results.get("fomdep2"),
            "FOM (dep3)": results.get("fomdep3"),
            "FOM (dep4)": results.get("fomdep4"),
            "Supply voltage (V)": psvoltage if sim_type != "dep4" else 5.0,
            "Supply current (A)": results.get("ib"),
            "Power consumption (W)": results.get("pdis"),
            "Output resistance (Ω)": results.get("ro"),
            "DC gain (dB)": results.get("dcgain_db"),
            "Phase margin (deg)": results.get("pm"),
            "Gain-bandwidth product (Hz)": results.get("gbw"),
            "Input-referred noise (V)": results.get("irn"),
            "Slew rate (V/s)": results.get("sr"),
            "Total harmonic distortion (%)": results.get("thd"),
            "Common-mode rejection ratio (dB)": results.get("cmrr_db"),
            "Power-supply rejection ratio (dB)": results.get("psrr_db"),
            "Common-mode input range (%)": results.get("cmir"),
            "Output voltage range (%)": results.get("ovr"),
            "Bandwidth (Hz)": results.get("bw"),
            "Input voltage amplitude (V)": results.get("ivr"),
            "Offset voltage (V)": results.get("offset"),
            "Occupied area (μm²)": mos_area,
        }
        label_map = {
            "Metric": "項目",
            "FOM": "FOM",
            "Supply voltage (V)": "電源電圧(V)",
            "Supply current (A)": "消費電流(A)",
            "Power consumption (W)": "消費電力(W)",
            "Output resistance (Ω)": "出力抵抗(Ω)",
            "DC gain (dB)": "直流利得(dB)",
            "Phase margin (deg)": "位相余裕(deg)",
            "Gain-bandwidth product (Hz)": "利得帯域幅積(Hz)",
            "Input-referred noise (V)": "入力換算雑音(V)",
            "Slew rate (V/s)": "スルーレート(V/s)",
            "Total harmonic distortion (%)": "全高調波歪(%)",
            "Common-mode rejection ratio (dB)": "同相除去比(dB)",
            "Power-supply rejection ratio (dB)": "電源電圧変動除去比(dB)",
            "Common-mode input range (%)": "同相入力範囲(%)",
            "Output voltage range (%)": "出力電圧範囲(%)",
            "Bandwidth (Hz)": "帯域幅(Hz)",
            "Input voltage amplitude (V)": "入力電圧振幅(V)",
            "Offset voltage (V)": "オフセット電圧(V)",
            "Occupied area (μm²)": "占有面積(μm²)",
        }
        condition_map = {
            "Calculated in this analysis": "今回の解析で算出",
            "Within ±50% of the reference value": "各解析で基準値の±50%以内",
            "Absolute value <= 0.1 V": "絶対値 <= 0.1 V",
        }
        markdown_rows = [
            [
                label_map.get(label, label),
                (
                    f"{markdown_numeric_values[label]:.3e}"
                    if markdown_numeric_values.get(label) is not None
                    else value
                ),
                condition_map.get(condition, condition),
            ]
            for label, value, condition in rows
        ]
        markdown_kwargs = dict(
            headers=["項目", "値", "最低満たすべき条件"],
            colalign=("left", "right", "left"),
            disable_numparse=True,
        )
        markdown = (
            "# シミュレーション結果\n\n"
            + tabulate(markdown_rows, tablefmt="github", **markdown_kwargs)
            + "\n\n## SR波形プレビュー\n\n"
        )
        sr_image = OUTPUT_DIR / "sr_waveform.svg"
        if sr_image.exists():
            markdown += "![SR波形](out/sr_waveform.svg)\n"
        else:
            markdown += "SR波形画像は生成されませんでした。\n"
        Path(markdown_path).write_text(
            markdown,
            encoding="utf-8",
        )


def _clear_output_directory(output_dir=OUTPUT_DIR):
    """結果出力用ディレクトリを初期化する。"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    for path in output_path.iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()


def _write_processed_netlist(
    department, source_file="./opamp.sp", output_file="tmp.sp"
):
    """opamp.spを処理し、HSPICEが読み込むtmp.spへ保存する。"""
    source_path = Path(source_file)
    output_path = Path(output_file)
    netlist_text = source_path.read_text(encoding="utf-8")
    processed_netlist = process_netlist(netlist_text, department)
    output_path.write_text(processed_netlist + "\n", encoding="utf-8")


def _run_hspice(input_file, output_file, debug=False):
    """HSPICEを実行し、異常終了時はエラー内容を表示する。"""
    result = subprocess.run(
        ["hspice", "-i", input_file, "-o", output_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _print_hspice_error(result, output_file)
    _debug_subprocess_result(result, debug)
    return result


def _read_measurement_csv(filename, **kwargs):
    """HSPICEが出力した測定CSVを読み込む。"""
    return pd.read_csv(filename, skiprows=3, skipinitialspace=True, **kwargs)


def _measurement_value(series, index, default):
    """測定値が failed の場合は既定値を返す。"""
    value = series[index]
    return default if value == "failed" else value


def _extract_thd(lis_content, default):
    """.lis からTHDを抽出する。"""
    pattern = (
        r"(?i)total\s+harmonic\s+distortion\s*=\s*"
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
        r"\s*percent"
    )
    values = re.findall(pattern, lis_content)
    return float(values[-1]) if values else default


def _prepare_slew_rate_simulation(sr_vp, debug=False):
    """部門1〜3の1回目の結果からSR用のVPを決めて2回目を実行する。"""
    _run_hspice("sim1.sp", "result1.lis", debug=debug)

    df = _read_measurement_csv("result1.ms4.csv")
    cmr1 = _measurement_value(df["cmr1"], 0, 0.1)
    cmr2 = _measurement_value(df["cmr2"], 0, 0.1)
    vp = min(cmr1, cmr2) if sr_vp == "min" else 0.1

    Path("for_sr.lib").write_text(
        f"* Vp value for SR\n\n.lib vpval\n.param vp={vp}\n.endl vpval\n\n",
        encoding="utf-8",
    )
    _run_hspice("sim2.sp", "result2.lis", debug=debug)


def _extract_dep1_3_results():
    """部門1〜3のシミュレーション結果を抽出する。"""
    lis_content = Path("result1.lis").read_text(encoding="utf-8")
    results = {}

    # 消費電流・消費電力
    dfs = [
        _read_measurement_csv(
            filename,
            usecols=[3, 4],
        )
        for filename in ("result1.ms0.csv", "result1.ms1.csv", "result1.ms2.csv")
    ]
    reference_ib = dfs[1]["ib"][1]
    results["ib"] = reference_ib
    results["pdis"] = dfs[1]["pdis"][1]

    ib_diff = 0.0
    ib_const = True
    for df in dfs:
        for index in range(3):
            current_ib = df["ib"][index]
            ib_diff = max(ib_diff, abs(current_ib - reference_ib) / reference_ib)
            ib_const = ib_const and reference_ib * 0.5 <= current_ib <= reference_ib * 1.5
    results["ib_const"] = ib_const
    results["ib_diff"] = ib_diff
    results["pdis_const"] = results["pdis"] <= 0.1

    # 出力抵抗
    ro_df = _read_measurement_csv("result1.ma1.csv")
    rosim = _measurement_value(ro_df["ro"], 0, 1e6)
    r1, r2 = ro_df["r1"][0], ro_df["r2"][0]
    beta, rl = ro_df["beta"][0], ro_df["rl"][0]

    # 直流利得・位相余裕・利得帯域幅積
    gain_df = _read_measurement_csv("result1.ma2.csv")
    dcgain = _measurement_value(gain_df["dcgain"], 0, 1e-5)
    dcgain_db = _measurement_value(gain_df["dcgain_db"], 0, 0.0)
    ro = max(
        (1 + beta * dcgain)
        / ((1 / rosim) - (1 / (r1 + r2)) - (beta * dcgain / rl)),
        0.1,
    )
    results["ro"] = ro
    results["dcgain"] = ((rl + ro) * dcgain) / rl
    results["dcgain_db"] = 20 * math.log10((rl + ro) / rl) + dcgain_db
    results["dcgain_const"] = results["dcgain_db"] >= 40
    results["pm"] = _measurement_value(gain_df["pm"], 0, 0.0)
    results["pm_const"] = results["pm"] >= 45
    results["gbw"] = _measurement_value(gain_df["gbw"], 0, 0.0)
    results["gbw_const"] = results["gbw"] >= 1e6

    # 入力換算雑音・スルーレート・THD
    noise_df = _read_measurement_csv("result1.ma3.csv")
    results["irn"] = _measurement_value(noise_df["irn"], 0, 1e6)
    sr_df = _read_measurement_csv("result2.mt0.csv")
    results["sr"] = _measurement_value(sr_df["sr"], 0, 0.0)
    results["sr_const"] = results["sr"] >= 1e5
    results["thd"] = _extract_thd(lis_content, 10.0)
    results["thd_const"] = results["thd"] <= 1.0

    # CMRR・PSRR
    cmrr_df = _read_measurement_csv("result1.ma6.csv")
    results["cmrr"] = _measurement_value(cmrr_df["cmrr"], 0, 0.0)
    results["cmrr_db"] = _measurement_value(cmrr_df["cmrr_db"], 0, 0.0)
    results["cmrr_const"] = results["cmrr_db"] >= 40.0

    psrr_df = _read_measurement_csv("result1.ma7.csv")
    results["psrr"] = _measurement_value(psrr_df["psrr"], 0, 0.0)
    results["psrr_db"] = _measurement_value(psrr_df["psrr_db"], 0, 0.0)
    results["psrr_const"] = results["psrr_db"] >= 40.0

    # 同相入力範囲
    cmir_df = _read_measurement_csv("result1.ms4.csv")
    psvoltage = cmir_df["psvoltage"][0]
    cmr1 = _measurement_value(cmir_df["cmr1"], 0, psvoltage)
    cmr2 = _measurement_value(cmir_df["cmr2"], 0, psvoltage)
    results["cmir"] = 0.5 * (cmr1 + cmr2) / psvoltage * 100
    results["cmir_const"] = results["cmir"] >= 5.0

    # 出力電圧範囲
    ovr_df = _read_measurement_csv("result1.ms8.csv")
    psvoltage = ovr_df["psvoltage"][0]
    ovr1 = _measurement_value(ovr_df["ovr1"], 0, psvoltage)
    ovr2 = _measurement_value(ovr_df["ovr2"], 0, psvoltage)
    if ovr_df["ovr1"][0] != "failed" and ovr_df["ovr2"][0] != "failed":
        results["ovr"] = ovr_df["ovr"][0]
    else:
        results["ovr"] = (ovr1 + ovr2) / (2 * psvoltage) * 100
    results["ovr_const"] = results["ovr"] >= 5.0

    # 制約確認とFOM
    results["const"] = all(
        results[key] for key in results if key.endswith("_const")
    )
    results["fomdep1"] = (
        results["sr"] * results["cmir"] * min(results["dcgain"], 1e9)
    ) / results["ib"]
    results["fomdep2"] = (
        results["gbw"] * results["pm"]
    ) / (results["pdis"] ** 2 * results["ro"] * results["irn"])
    results["fomdep3"] = (results["psrr"] * results["cmrr"]) / psvoltage
    return results, psvoltage


def _extract_dep4_results():
    """部門4のシミュレーション結果を抽出する。"""
    lis_content = Path("result1.lis").read_text(encoding="utf-8")
    results = {}

    power_df = _read_measurement_csv("result1.ms2.csv")
    results["ib"] = power_df["ib"][0]
    results["pdis"] = power_df["pdis"][0]
    results["offset"] = power_df["offset"][0]
    results["offset_const"] = abs(results["offset"]) <= 0.1

    gain_df = _read_measurement_csv("result1.ma0.csv")
    results["dcgain_db"] = _measurement_value(gain_df["dcgain_db"], 1, 0.0)
    results["dcgain_const"] = results["dcgain_db"] >= 40

    pm = 0.0
    for value in gain_df["pm"]:
        if value == "failed":
            pm = 0.0
            break
        pm = max(pm, value)
    results["pm"] = pm
    results["pm_const"] = results["pm"] >= 45

    bandwidth_df = _read_measurement_csv("result1.ma1.csv")
    results["bw"] = _measurement_value(bandwidth_df["bandwidth"], 0, 0.0)
    results["bw_const"] = results["bw"] >= 2e4

    input_range_df = _read_measurement_csv("result1.ms3.csv")
    results["ivr"] = _measurement_value(input_range_df["inrng"], 0, 0.0)
    results["ivr_const"] = results["ivr"] >= 0.1

    slew_rate_df = _read_measurement_csv("result1.mt4.csv")
    results["sr"] = _measurement_value(slew_rate_df["sr"], 0, 0.0)
    results["sr_const"] = results["sr"] >= 1e6

    results["thd"] = _extract_thd(lis_content, 10.0)
    results["thd_const"] = results["thd"] <= 0.1
    results["const"] = all(
        results[key] for key in results if key.endswith("_const")
    )
    results["fomdep4"] = 1.0 / results["pdis"]
    return results


def _plot_simulation_results(sim_type, debug=False):
    """シミュレーション結果から波形プロットを生成する。"""
    try:
        if sim_type in {"dep1", "dep2", "dep3"}:
            plot_dep1_3()
        elif sim_type == "dep4":
            plot_dep4()
    except Exception as error:
        print("An error occurred while plotting waveforms:", error)
        _debug_exception("波形プロット", error, debug)


def _cleanup_simulation_files():
    """シミュレーションで生成した一時ファイルを削除する。"""
    filenames = [
        "tmp.sp",
        "for_sr.lib",
        "result1.lis",
        "result2.lis",
        "result1.ma0.csv",
        "result1.ma1.csv",
        "result1.ma2.csv",
        "result1.ma3.csv",
        "result1.ma6.csv",
        "result1.ma7.csv",
        "result1.ms0.csv",
        "result1.ms1.csv",
        "result1.ms2.csv",
        "result1.ms3.csv",
        "result1.ms4.csv",
        "result1.ms8.csv",
        "result2.mt0.csv",
        "result1.mt4.csv",
    ]

    for filename in filenames:
        path = Path(filename)
        if path.exists():
            path.unlink()


def simulate_and_print(sim_type="dep1", sr_vp="min", debug=None):
    """HSPICEシミュレーションを実行し、結果を標準出力へ表示する。

    ``debug=True`` または ``SIMULATOR_DEBUG=1`` を指定すると、例外の
    発生関数・行番号・トレースバックとHSPICEの出力を表示する。
    """
    debug = _debug_enabled(debug)
    try:
        _clear_output_directory()
        mos_area = calculate_mos_area_from_file("./opamp.sp", department=sim_type)
        _write_processed_netlist(sim_type)
    except Exception as error:
        print("An error occurred while preparing the simulation:", error)
        _debug_exception("シミュレーション準備", error, debug)
        return

    print("Running simulation...")

    results = {}
    psvoltage = None
    error_flag = False

    try:
        if sim_type in {"dep1", "dep2", "dep3"}:
            _prepare_slew_rate_simulation(sr_vp, debug=debug)
            results, psvoltage = _extract_dep1_3_results()
        elif sim_type == "dep4":
            _run_hspice("sim3.sp", "result1.lis", debug=debug)
            results = _extract_dep4_results()
        else:
            raise ValueError(f"Unknown simulation department: {sim_type}")
    except Exception as error:
        print("An error occurred while extracting results:", error)
        _debug_exception("シミュレーション結果の抽出", error, debug)
        error_flag = True

    print("Simulation complete")
    if not error_flag:
        _plot_simulation_results(sim_type, debug=debug)
        # 波形生成後にMarkdownを作成し、SR波形をプレビューへ含める。
        print_performance_table(
            results,
            sim_type,
            psvoltage=psvoltage,
            mos_area=mos_area,
            error_flag=False,
            markdown_path=RESULT_MARKDOWN_PATH,
        )
    else:
        print_performance_table(
            results,
            sim_type,
            psvoltage=psvoltage,
            mos_area=mos_area,
            error_flag=True,
        )
    _cleanup_simulation_files()
