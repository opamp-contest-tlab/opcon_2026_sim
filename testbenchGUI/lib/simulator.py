# import ipywidgets as widgets
# from IPython.display import display, clear_output, HTML
from pathlib import Path
from decimal import Decimal
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import time, subprocess, re, math, os
import tabulate as _tabulate

# 日本語などの全角文字を端末上の表示幅で計算する
_tabulate.WIDE_CHARS_MODE = True
tabulate = _tabulate.tabulate
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
                pd_val = f"({w_val}+{tmp})*2"
                ps_val = f"({w_val}+{tmp})*2"

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
    plt.savefig("out/ac2_gain_phase.pdf", transparent=True)
    plt.savefig("out/ac2_gain_phase.svg", transparent=True)
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
    plt.savefig("out/ac4_cmrr.pdf", transparent=True)
    plt.savefig("out/ac4_cmrr.svg", transparent=True)
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
    plt.savefig("out/ac5_psrr.pdf", transparent=True)
    plt.savefig("out/ac5_psrr.svg", transparent=True)
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
    plt.savefig("out/dc2_input_range.pdf", transparent=True)
    plt.savefig("out/dc2_input_range.svg", transparent=True)
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
    plt.savefig("out/dc3_output_range.pdf", transparent=True)
    plt.savefig("out/dc3_output_range.svg", transparent=True)
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
    plt.savefig("out/dc3_input_range.pdf", transparent=True)
    plt.savefig("out/dc3_input_range.svg", transparent=True)
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
    plt.savefig("out/sr_waveform.pdf", transparent=True)
    plt.savefig("out/sr_waveform.svg", transparent=True)
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
    plt.savefig("out/sr_waveform.pdf", transparent=True)
    plt.savefig("out/sr_waveform.svg", transparent=True)
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
    plt.savefig("out/sr_waveform2.pdf", transparent=True)
    plt.savefig("out/sr_waveform2.svg", transparent=True)
    plt.title('Slew Rate (Detailed View)')
    # plt.show()
    plt.close()


def plot_dep1_3():
    """
    部門1-3の結果プロットを一括実行する関数
    """
    with open("result1.lis", "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

    # ac2: 利得・位相余裕
    ac2_block = parse_table_from_lis(lines, label="ac2", header_token="freq")
    if ac2_block:
        plot_ac2_gain_phase(ac2_block)
    else:
        print("ac2 のデータが見つかりませんでした。")

    # ac4: CMRR
    ac4_block = parse_table_from_lis(lines, label="ac4", header_token="freq")
    if ac4_block:
        plot_ac4_cmrr(ac4_block)
    else:
        print("ac4 (CMRR) のデータが見つかりませんでした。")

    # ac5: PSRR（電源ライン上下）
    ac5_block = parse_table_from_lis(lines, label="ac5", header_token="freq")
    if ac5_block:
        plot_ac5_psrr(ac5_block)
    else:
        print("ac5 (PSRR) のデータが見つかりませんでした。")

    # dc2: DCスイープ
    dc2_block = parse_table_from_lis(lines, label="dc2", header_token="volt")
    if dc2_block:
        plot_dc_sweep1(dc2_block)
    else:
        print("dc2 のデータが見つかりませんでした。")

    # dc3: DCスイープその2
    dc3_block = parse_table_from_lis(lines, label="dc3", header_token="volt")
    if dc3_block:
        plot_dc_sweep2(dc3_block)
    else:
        print("dc3 のデータが見つかりませんでした。")

    # sr: スルーレート (別ファイル)
    with open('result2.lis', "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

    sr_block = parse_table_from_lis(lines, label="sr", header_token="time")
    if sr_block:
        plot_sr(sr_block)
    else:
        print("sr のデータが見つかりませんでした。")

def plot_dep4():
    """
    部門4の結果プロットを一括実行する関数
    """
    with open("result1.lis", "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

    # ac1: 利得・位相余裕
    ac1_block = parse_table_from_lis(lines, label="ac1", header_token="freq")
    if ac1_block:
        plot_ac2_gain_phase(ac1_block)
    else:
        print("ac1 のデータが見つかりませんでした。")

    # ac2: 帯域幅
    ac2_block = parse_table_from_lis(lines, label="ac2", header_token="freq")
    if ac2_block:
        plot_ac2_gain_phase(ac2_block)
    else:
        print("ac2 のデータが見つかりませんでした。")

    # dc2: 入力電圧範囲
    dc2_block = parse_table_from_lis(lines, label="dc2", header_token="volt")
    if dc2_block:
        plot_dc_sweep3(dc2_block)
    else:
        print("dc2 のデータが見つかりませんでした。")

    # tran1: スルーレート
    tran1_block = parse_table_from_lis(lines, label="tran1", header_token="time")
    if tran1_block:
        plot_sr2(tran1_block)
    else:
        print("tran1 のデータが見つかりませんでした。")


def print_performance_table(results, sim_type, psvoltage=None, error_flag=False):
    """シミュレーション結果の性能表を標準出力へ表示する。"""
    if error_flag:
        print("この回路は演算増幅器として動作していません。")
        print("(シミュレーション中にエラーが発生しました。)")
        return

    print("最後に提出した回路の解析結果")
    if not results.get("const", False):
        print("[警告] 制約条件を満たしていません。")

    rows = []

    def row(label, value, condition="-"):
        rows.append([label, value, condition])

    # row("スコア", f"{results[f'fom{sim_type}']:.3e}")
    for department in ("dep1", "dep2", "dep3", "dep4"):
        fom = results.get(f"fom{department}")
        row(
            f"FOM ({department})",
            f"{fom:.3e}" if fom is not None else "-",
            "今回の解析で算出",
        )
    if sim_type in ["dep1", "dep2", "dep3"]:
        row("電源電圧(V)", f"{psvoltage:.3f}")
        row("消費電流(A)", f"{results['ib']:.8f}", "各解析で基準値の±50%以内")
        row("消費電力(W)", f"{results['pdis']:.7f}", "<= 0.1 W")
        row("出力抵抗(Ohm)", f"{results['ro']:.3e}")
        row("直流利得(dB)", f"{results['dcgain_db']:.2f}", ">= 40 dB")
        row("位相余裕(deg)", f"{results['pm']:.2f}", ">= 45 deg")
        row("利得帯域幅積(Hz)", f"{results['gbw']:.3e}", ">= 1.000e+06 Hz")
        row("入力換算雑音(V)", f"{results['irn']:.6f}")
        row("スルーレート(V/s)", f"{results['sr']:.3e}", ">= 1.000e+05 V/s")
        row("全高調波歪(%)", f"{results['thd']:.4f}", "<= 1.0 %")
        row("同相除去比(dB)", f"{results['cmrr_db']:.2f}", ">= 40 dB")
        row("電源電圧変動除去比(dB)", f"{results['psrr_db']:.2f}", ">= 40 dB")
        row("同相入力範囲(%)", f"{results['cmir']:.2f}", ">= 5.0 %")
        row("出力電圧範囲(%)", f"{results['ovr']:.2f}", ">= 5.0 %")
    elif sim_type == "dep4":
        row("電源電圧(V)", "5.000")
        row("消費電流(A)", f"{results['ib']:.8f}")
        row("消費電力(W)", f"{results['pdis']:.7f}")
        row("直流利得(dB)", f"{results['dcgain_db']:.2f}", ">= 40 dB")
        row("位相余裕(deg)", f"{results['pm']:.2f}", ">= 45 deg")
        row("スルーレート(V/s)", f"{results['sr']:.3e}", ">= 1.000e+06 V/s")
        row("全高調波歪(%)", f"{results['thd']:.4f}", "<= 0.1 %")
        row("帯域幅(Hz)", f"{results['bw']:.3e}", ">= 2.000e+04 Hz")
        row("入力電圧振幅(V)", f"{results['ivr']:.2f}", ">= 0.1 V")
        row("オフセット電圧", f"{results['offset']:.2f}", "絶対値 <= 0.1 V")

    row("占有面積(um^2)", "本プログラムでは未算出")
    print(tabulate(
        rows,
        headers=["項目", "値", "最低満たすべき条件"],
        tablefmt="simple",
        colalign=("left", "right", "left"),
        disable_numparse=True,
    ))


def _clear_output_directory(output_dir="out"):
    """結果出力用ディレクトリを初期化する。"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    for path in output_path.iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()


def _write_processed_netlist(department, source_file="opamp.sp", output_file="tmp.sp"):
    """opamp.spを処理し、HSPICEが読み込むtmp.spへ保存する。"""
    source_path = Path(source_file)
    output_path = Path(output_file)
    netlist_text = source_path.read_text(encoding="utf-8")
    processed_netlist = process_netlist(netlist_text, department)
    output_path.write_text(processed_netlist + "\n", encoding="utf-8")


def _run_hspice(input_file, output_file):
    """HSPICEを実行する。"""
    return subprocess.run(
        ["hspice", "-i", input_file, "-o", output_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


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


def _prepare_slew_rate_simulation(sr_vp):
    """部門1〜3の1回目の結果からSR用のVPを決めて2回目を実行する。"""
    _run_hspice("sim1.sp", "result1.lis")

    df = _read_measurement_csv("result1.ms4.csv")
    cmr1 = _measurement_value(df["cmr1"], 0, 0.1)
    cmr2 = _measurement_value(df["cmr2"], 0, 0.1)
    vp = min(cmr1, cmr2) if sr_vp == "min" else 0.1

    Path("for_sr.lib").write_text(
        f"* Vp value for SR\n\n.lib vpval\n.param vp={vp}\n.endl vpval\n\n",
        encoding="utf-8",
    )
    _run_hspice("sim2.sp", "result2.lis")


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


def _plot_simulation_results(sim_type):
    """シミュレーション結果から波形プロットを生成する。"""
    try:
        if sim_type in {"dep1", "dep2", "dep3"}:
            plot_dep1_3()
        elif sim_type == "dep4":
            plot_dep4()
    except Exception as error:
        print("波形プロット中にエラーが発生しました:", error)


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


def simulate_and_print(sim_type="dep1", sr_vp="min"):
    """HSPICEシミュレーションを実行し、結果を標準出力へ表示する。"""
    _clear_output_directory()
    _write_processed_netlist(sim_type)
    print("シミュレーション中...")

    results = {}
    psvoltage = None
    error_flag = False

    try:
        if sim_type in {"dep1", "dep2", "dep3"}:
            _prepare_slew_rate_simulation(sr_vp)
            results, psvoltage = _extract_dep1_3_results()
        elif sim_type == "dep4":
            _run_hspice("sim3.sp", "result1.lis")
            results = _extract_dep4_results()
        else:
            raise ValueError(f"未知のシミュレーション部門です: {sim_type}")
    except Exception as error:
        print("結果の抽出中にエラーが発生しました:", error)
        error_flag = True

    print("シミュレーション完了")
    print_performance_table(
        results,
        sim_type,
        psvoltage=psvoltage,
        error_flag=error_flag,
    )
    if not error_flag:
        _plot_simulation_results(sim_type)
    _cleanup_simulation_files()
