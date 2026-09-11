from collections import Counter
import argparse
import re


def parse_args():
  parser = argparse.ArgumentParser(description="Preprocess Netlist")
  parser.add_argument("-i", "--input", type=str, required=True, help="Input netlist file")
  parser.add_argument("--sec", type=int, required=True, help="Section of contest")
  return parser.parse_args()


def num_eng(value):
  # 工学表記を数値に変換
  units = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3,
    "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12,
    "f": 1e-15, "mil": 25.4e-6,
  }

  match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)([a-z]*)", str(value).lower())
  if not match:
    raise ValueError(f"Invalid number: {value}")

  num, unit = match.groups()
  if unit and unit not in units:
    raise ValueError(f"Invalid unit: {unit}")

  return float(num) * units.get(unit, 1)


def count_res(res, sheet_res):
  # 抵抗を構成するシート数を計算
  steps = [1, 2, 5, 10, 25, 50]
  count = 0

  while res >= 1:
    for step in steps:
      unit_res = sheet_res / step
      if res >= unit_res:
        n = int(res / unit_res)
        count += n * step
        res -= unit_res * n
        break
    else:
      raise ValueError(f"Resistance cannot be represented: {res}")

  return count


def proc_mos(line, nmos_model, pmos_model, diff):
  # MOSFETの端子とパラメータを取得
  model_re = rf"({re.escape(nmos_model)}|{re.escape(pmos_model)})"
  match = re.fullmatch(rf"(m\S+)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(\S+))?\s+{model_re}\s+(.*)", line)

  if not match:
    raise ValueError(f"Invalid MOSFET line: {line}")

  name, drain, gate, source, bulk, model, params = match.groups()

  # 3端子MOSFETのBulkを補完
  if bulk is None:
    bulk = "vss" if model == nmos_model else source

  # パラメータを取得
  params = re.findall(r"(\w+)=([^\s]+)", params)

  if sum(k == "w" for k, v in params) != 1:
    raise ValueError(f"Invalid W parameter: {line}")
  if sum(k == "l" for k, v in params) != 1:
    raise ValueError(f"Invalid L parameter: {line}")
  if sum(k == "m" for k, v in params) > 1:
    raise ValueError(f"Invalid M parameter: {line}")

  params = dict(params)
  w = num_eng(params["w"]) * 1e6
  l = num_eng(params["l"]) * 1e6
  m = num_eng(params.get("m", "1"))

  # 拡散領域を計算
  ad = as_ = w * diff
  pd = ps = 2 * (w + diff)

  return {
    "name": name, "drain": drain, "gate": gate, "source": source,
    "bulk": bulk, "model": model, "w": w, "l": l, "m": m,
    "ad": ad, "as": as_, "pd": pd, "ps": ps,
  }


def proc_rc(line, device):
  # 素子名、端子、パラメータを取得
  match = re.fullmatch(rf"({device}\S+)\s+(\S+)\s+(\S+)\s+(.*)", line)
  if not match:
    raise ValueError(f"Invalid {device.upper()} line: {line}")

  name, node1, node2, params = match.groups()
  tokens = params.split()

  # RまたはCの値を取得
  values = [t for t in tokens if re.match(r"^[\d.+-]", t) or t.startswith(f"{device}=")]
  if len(values) != 1:
    raise ValueError(f"Invalid {device.upper()} value: {line}")

  value = num_eng(re.sub(r"^[rc]=", "", values[0]))

  # Mを取得
  m_params = [t for t in tokens if t.startswith("m=")]
  if len(m_params) > 1:
    raise ValueError(f"Multiple M parameters: {line}")

  m = num_eng(m_params[0][2:]) if m_params else 1
  if m < 1 or not float(m).is_integer():
    raise ValueError(f"Invalid M: {m} in {line}")

  return {
    "name": name, "node1": node1, "node2": node2,
    "value": value, "m": int(m),
  }


def check_ideal_gnd(nodes, line):
  # 理想GNDの使用を禁止
  for node in nodes:
    if node.replace("!", "") in ("0", "gnd", "ground"):
      raise ValueError(f"Ideal ground is not allowed: {line}")


def check_netlist(netlist, sec):
  """
  ネットリストを検証する関数

  Input:
      netlist: ネットリストの内容
      sec: コンテストの部門(部門1-3と部門4で)
  """
  # 部門ごとのパラメータを設定
  if sec in [1, 2, 3]:
    # MOSのモデル名
    nmos_model = "cmosn"
    pmos_model = "cmosp"
    # MOSFET拡散層長さ(um)
    diff = 0.6
    # MOSFETのW([min, max, step], 単位はum)
    w_range = [0.27, None, 0.01]
    # MOSFETのL([min, max, step], 単位はum)
    l_range = [0.18, lambda w: min(10 * w, 50), 0.01]

    # シート抵抗(Ω/sq)
    sheet_res = 50
    # シート1辺の長さ(um)
    sheet_length = 0.4
    # 抵抗値の範囲([min, max, step])
    res_range = [1, 1e8, 1]

    # 単位面積容量(F/um^2)
    unit_cap = 1e-15
    # 容量の範囲([min, max, step], 単位はF)
    cap_range = [1e-13, None, None]

    # psvoltageの範囲([min, max], 単位はV)
    psvoltage_range = [0.0, 3.0]

  elif sec == 4:
    # MOSのモデル名
    nmos_model = "bsim3v3n"
    pmos_model = "bsim3v3p"
    # MOSFET拡散層長さ(um)
    diff = 1.0
    # MOSFETのW([min, max, step], 単位はum)
    w_range = [1.2, None, 0.1]
    # MOSFETのL([min, max, step], 単位はum)
    l_range = [0.6, lambda w: min(10 * w, 140), 0.1]

    # シート抵抗(Ω/sq)
    sheet_res = 3e3
    # シート1辺の長さ(um)
    sheet_length = 2
    # 抵抗値の範囲([min, max, step])
    res_range = [60, 5e7, 1]

    # 単位面積容量(F/um^2)
    unit_cap = 3e-15
    # 容量の範囲([min, max, step], 単位はF)
    cap_range = [1e-13, None, None]

    # psvoltageの範囲([min, max], 単位はV)
    psvoltage_range = [0.0, 5.0]

  else:
    raise ValueError(f"Invalid section: {sec}")

  # 全角空白、括弧、カンマを整形
  netlist = netlist.replace("　", " ")
  netlist = re.sub(r"[(){}\[\]]", "", netlist)
  netlist = netlist.replace(",", " ")

  # コメントを削除
  netlist = re.sub(r"\$.*", "", netlist)
  netlist = re.sub(r"(?m)^[^\S\n]*\*.*\n?", "", netlist)

  # 継続行を結合
  netlist = re.sub(r"\n[^\S\n]*\+[^\S\n]*", " ", netlist)

  # 空白と=前後を整形
  netlist = re.sub(r"(?m)^[^\S\n]+|[^\S\n]+$", "", netlist)
  netlist = re.sub(r"[^\S\n]+", " ", netlist)
  netlist = re.sub(r"[^\S\n]*=[^\S\n]*", "=", netlist)

  # 空白行を削除して小文字化
  netlist = re.sub(r"\n+", "\n", netlist).strip().lower()

  if not netlist:
    raise ValueError("Empty netlist.")

  # 1行目がタイトル行なら削除
  if not netlist.startswith("."):
    netlist = re.sub(r"^[^\n]*\n?", "", netlist, count=1)

  if not netlist:
    raise ValueError("Empty netlist.")

  subckt = False
  subckt_found = False
  psvoltage = None
  nodes = Counter()

  mos_area = 0.0
  res_area = 0.0
  cap_area = 0.0
  new_netlist = []

  for line in netlist.splitlines():
    # クォートを禁止
    if "'" in line or '"' in line:
      raise ValueError(f"Quote is not allowed: {line}")

    # .subcktをチェック
    if line.startswith(".subckt"):
      if subckt_found:
        raise ValueError("Multiple .subckt lines found.")
      if not re.fullmatch(r"\.subckt opamp inm inp out vdd vss", line):
        raise ValueError(f"Invalid .subckt line: {line}")

      subckt = True
      subckt_found = True
      new_netlist.append(line)
      continue

    # .endsをチェック
    if line.startswith(".ends"):
      if not subckt:
        raise ValueError(f"Invalid .ends line: {line}")

      subckt = False
      new_netlist.append(line)
      continue

    # .paramをチェック
    if line.startswith(".param"):
      if subckt:
        raise ValueError(f".param inside .subckt: {line}")

      match = re.fullmatch(r"\.param psvoltage=(\S+?)v?", line)
      if not match:
        raise ValueError(f"Invalid .param line: {line}")
      if psvoltage is not None:
        raise ValueError("Multiple psvoltage definitions found.")

      psvoltage = num_eng(match.group(1))

      if psvoltage < psvoltage_range[0] or psvoltage > psvoltage_range[1]:
        raise ValueError(f"psvoltage out of range: {line}")

      new_netlist.append(line)
      continue

    # その他のコマンドを禁止
    if line.startswith("."):
      raise ValueError(f"Invalid command line: {line}")

    # サブサーキット外の記述を禁止
    if not subckt:
      raise ValueError(f"Invalid line outside .subckt: {line}")

    # MOSFET行のチェックと書き換え
    if line.startswith("m"):
      mos = proc_mos(line, nmos_model, pmos_model, diff)
      w, l, m = mos["w"], mos["l"], mos["m"]

      check_ideal_gnd([mos["drain"], mos["gate"], mos["source"], mos["bulk"]], line)

      # NMOSのBulkをチェック
      if mos["model"] == nmos_model and mos["bulk"] != "vss":
        raise ValueError(f"NMOS bulk must be vss: {line}")

      # Wをチェック
      if w < w_range[0]:
        raise ValueError(f"W is too small: {w} in {line}")
      if w_range[1] is not None and w > w_range[1]:
        raise ValueError(f"W is too large: {w} in {line}")
      if w_range[2] is not None and abs(w / w_range[2] - round(w / w_range[2])) > 1e-6:
        raise ValueError(f"Invalid W step: {w} in {line}")

      # Lをチェック
      l_max = l_range[1](w) if callable(l_range[1]) else l_range[1]

      if l < l_range[0]:
        raise ValueError(f"L is too small: {l} in {line}")
      if l_max is not None and l > l_max:
        raise ValueError(f"L is too large: {l} in {line}")
      if l_range[2] is not None and abs(l / l_range[2] - round(l / l_range[2])) > 1e-6:
        raise ValueError(f"Invalid L step: {l} in {line}")

      # Mをチェック
      if m < 1 or not float(m).is_integer():
        raise ValueError(f"Invalid M: {m} in {line}")

      # 面積を計算
      mos_area += w * (l + 2 * diff) * m

      # ノードを記録
      nodes.update([mos["drain"], mos["gate"], mos["source"], mos["bulk"]])

      # MOSFETを再構成
      line = (
        f'{mos["name"]} {mos["drain"]} {mos["gate"]} {mos["source"]} {mos["bulk"]} {mos["model"]} '
        f'l={l * 1e-6:.6e} w={w * 1e-6:.6e} m={m:g} '
        f'as={mos["as"] * 1e-12:.6e} ps={mos["ps"] * 1e-6:.6e} '
        f'ad={mos["ad"] * 1e-12:.6e} pd={mos["pd"] * 1e-6:.6e}'
      )

    # 抵抗行のチェックと書き換え
    elif line.startswith("r"):
      res = proc_rc(line, "r")
      r, m = res["value"], res["m"]

      check_ideal_gnd([res["node1"], res["node2"]], line)

      # 抵抗値をチェック
      if r < res_range[0]:
        raise ValueError(f"R is too small: {r} in {line}")
      if res_range[1] is not None and r > res_range[1]:
        raise ValueError(f"R is too large: {r} in {line}")
      if res_range[2] is not None and abs(r / res_range[2] - round(r / res_range[2])) > 1e-6:
        raise ValueError(f"Invalid R step: {r} in {line}")

      # 面積を計算
      res_area += count_res(r, sheet_res) * sheet_length ** 2 * m

      # ノードを記録
      nodes.update([res["node1"], res["node2"]])

      # 抵抗を再構成
      line = f'{res["name"]} {res["node1"]} {res["node2"]} r={r:g} m={m:g}'

    # 容量行のチェックと書き換え
    elif line.startswith("c"):
      cap = proc_rc(line, "c")
      c, m = cap["value"], cap["m"]

      check_ideal_gnd([cap["node1"], cap["node2"]], line)

      # 容量値をチェック
      if c < cap_range[0]:
        raise ValueError(f"C is too small: {c} in {line}")
      if cap_range[1] is not None and c > cap_range[1]:
        raise ValueError(f"C is too large: {c} in {line}")
      if cap_range[2] is not None and abs(c / cap_range[2] - round(c / cap_range[2])) > 1e-6:
        raise ValueError(f"Invalid C step: {c} in {line}")

      # 面積を計算
      cap_area += c / unit_cap * m

      # ノードを記録
      nodes.update([cap["node1"], cap["node2"]])

      # 容量を再構成
      line = f'{cap["name"]} {cap["node1"]} {cap["node2"]} c={c:g} m={m:g}'

    # M/R/C以外の素子を禁止
    else:
      raise ValueError(f"Invalid element: {line}")

    new_netlist.append(line)

  # .subcktをチェック
  if not subckt_found:
    raise ValueError(".subckt not found.")
  if subckt:
    raise ValueError(".subckt is not closed.")

  # psvoltageをチェック
  if psvoltage is None:
    raise ValueError("psvoltage not found.")

  # フローティングノードをチェック
  floating_nodes = [node for node, count in nodes.items() if count == 1 and node not in ("inm", "inp")]
  if floating_nodes:
    raise ValueError(f"Floating nodes found: {', '.join(floating_nodes)}")
  
  # 内部にグランド(gnd, 0, ground)があるかチェック
  if any(node in ("0", "gnd", "ground") for node in nodes):
    raise ValueError("Internal ground node found.")

  # 面積を計算
  area = mos_area + res_area + cap_area

  # ネットリストを再構成
  new_netlist = "\n".join(new_netlist)

  return new_netlist, psvoltage, area, mos_area, res_area, cap_area


def main():
  args = parse_args()

  # 入力ファイルを読み込む
  with open(args.input, "r") as f:
    netlist = f.read()

  # ネットリストをチェック
  new_netlist, psvoltage, area, mos_area, res_area, cap_area = check_netlist(netlist, args.sec)

  # 結果を出力
  print("Processed netlist:")
  print(new_netlist.replace("\n", r"\n"))
  print(f"psvoltage: {psvoltage}")
  print(f"Total area[um^2]: {area}")
  print(f"MOS area[um^2]: {mos_area}")
  print(f"Resistor area[um^2]: {res_area}")
  print(f"Capacitor area[um^2]: {cap_area}")


if __name__ == "__main__":
  main()
