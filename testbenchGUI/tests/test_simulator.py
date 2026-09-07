from pathlib import Path

import pytest
import lib.simulator as simulator

from lib.simulator import (
    EXECUTION_DIR,
    OUTPUT_DIR,
    PROJECT_ROOT,
    RESULT_MARKDOWN_PATH,
    _debug_exception,
    _extract_tf_output_resistance,
    _unit_resistor_count,
    calculate_mos_area,
    calculate_mos_area_from_file,
    print_performance_table,
    process_netlist,
    validate_mos_geometry,
)


def test_output_paths_keep_out_in_execution_directory():
    """波形画像は実行ディレクトリ、Markdownはその親階層へ保存する。"""
    execution_directory = Path(__file__).parents[1]

    assert EXECUTION_DIR == execution_directory
    assert PROJECT_ROOT == execution_directory.parent
    assert OUTPUT_DIR == execution_directory / "out"
    assert RESULT_MARKDOWN_PATH == execution_directory.parent / "simulatinon_results.md"


def test_extract_tf_output_resistance_from_listing():
    lis_content = """
 ****     small-signal transfer characteristics

      v(out)/vin                               =  1.489e+00
      input resistance at             vin      =  1.000e+20
      output resistance at v(out)              =  5.093e+03

          ***** job concluded
    """

    assert _extract_tf_output_resistance(lis_content, 1e6) == pytest.approx(5093.0)


def test_extract_tf_output_resistance_uses_default_when_absent():
    assert _extract_tf_output_resistance("no TF result", 1e6) == 1e6


OPAMP_NETLIST = Path(__file__).parents[1] / "opamp.sp"
SAMPLE_NETLISTS = {
    "dep1": Path(__file__).with_name("dep1.sp"),
}


def test_calculate_mos_area_for_opamp_netlist():
    """opamp.sp のMOS・抵抗面積を合計する。"""
    area = calculate_mos_area(OPAMP_NETLIST.read_text(encoding="utf-8"))

    # MOS: 796.02、R1 (100MEGΩ): 100e6 / 50 * 0.4um * 0.4um = 320000
    assert area == pytest.approx(320796.02)


def test_calculate_mos_area_from_file_reads_source_file():
    assert calculate_mos_area_from_file(OPAMP_NETLIST) == pytest.approx(320796.02)


def test_validate_mos_geometry_for_opamp_netlist():
    source = OPAMP_NETLIST.read_text(encoding="utf-8")
    assert validate_mos_geometry(process_netlist(source, "dep1"))


def test_dep1_sample_netlist_has_valid_mos_geometry_and_expected_area():
    """配置された部門1サンプルのMOS・抵抗面積を検証する。"""
    netlist = SAMPLE_NETLISTS["dep1"].read_text(encoding="utf-8")

    assert validate_mos_geometry(netlist)
    assert calculate_mos_area(netlist, department="dep1") == pytest.approx(320796.02)


def test_dep1_sample_netlist_is_processed_without_leaving_old_geometry():
    """部門1サンプルのMOSに標準の拡散寸法を設定する。"""
    source = SAMPLE_NETLISTS["dep1"].read_text(encoding="utf-8")
    processed = process_netlist(source, "dep1")

    mos_lines = [
        line for line in processed.splitlines()
        if line.lstrip().startswith("M")
    ]
    assert len(mos_lines) == 14
    assert all("ad='" in line and "as='" in line for line in mos_lines)
    assert all("pd='" in line and "ps='" in line for line in mos_lines)
    assert validate_mos_geometry(processed)


def test_calculate_mos_area_supports_units_parameters_and_ignores_external_mos():
    netlist = """
    Moutside d g s b model w=100u l=100u m=10
    .param mult=3
    .subckt opamp in out vdd vss
    M1 out in vss vss cmosn w=2u l=0.3u m=mult ad='2u*0.6u' as='2u*0.6u' pd='2u+1.2u' ps='2u+1.2u'
    M2 out in vdd vdd cmosp w='1u' l='0.2u' ad='1u*0.6u' as='1u*0.6u' pd='1u+1.2u' ps='1u+1.2u'
    .ends opamp
    """

    # M1: (2*0.3 + 2*1.2)*3 = 9.0, M2: 0.2 + 1.2 = 1.4 um^2
    assert calculate_mos_area(netlist) == pytest.approx(10.4)
    assert validate_mos_geometry(netlist)


def test_calculate_mos_area_supports_parameter_on_continuation_line():
    """.PARAM の継続行で定義した値を MOS の m に使える。"""
    netlist = """
    .PARAM
    + val1=23
    .subckt opamp in out vdd vss
    M1 N001 N001 Vdd Vdd cmosp l=0.2u w=4.1u m=val1
    .ends opamp
    """

    # AD/AS を 4.1u*0.6u として補完し、m=23 倍する。
    assert calculate_mos_area(netlist, department="dep1") == pytest.approx(132.02)


def test_process_netlist_calculates_diffusion_geometry_for_parameterized_mos():
    """m が .PARAM の値でも AD/AS/PD/PS を生成し、数値評価できる。"""
    source = """.PARAM
+ val1=23
M1 N001 N001 Vdd Vdd cmosp l=0.2u w=4.1u m=val1
"""

    # AD/AS がない場合も、部門1〜3の既定値で拡散面積を補完する。
    raw_netlist = f""".PARAM
+ val1=23
.subckt opamp in out vdd vss
{source.splitlines()[-1]}
.ends opamp
"""
    assert calculate_mos_area(raw_netlist, department="dep1") == pytest.approx(132.02)

    processed = process_netlist(source, "dep1")
    assert "ad='4.1u*0.6u'" in processed
    assert "as='4.1u*0.6u'" in processed
    assert "pd='4.1u+0.6u*2'" in processed
    assert "ps='4.1u+0.6u*2'" in processed

    netlist = f""".PARAM
+ val1=23
.subckt opamp in out vdd vss
{processed.splitlines()[-1]}
.ends opamp
"""

    # (ゲート面積 0.82 + 拡散面積 2.46 + 2.46) * m=23 = 132.02 um^2
    assert calculate_mos_area(netlist) == pytest.approx(132.02)


def test_calculate_area_for_dep4_uses_mos_capacitor_and_resistor_formulas():
    """部門4は MOS・容量・抵抗を指定の um^2 換算式で合計する。"""
    netlist = """
    .subckt opamp in out vdd vss
    M1 out in vss vss model w=12u l=1.2u m=2
    C1 out 0 6f
    R1 in out 6k
    .ends opamp
    Cexternal out 0 1p
    Rexternal in out 100k
    """

    # MOS: 12 * (1.2 * 2) * 2 = 57.6
    # C: 6f / 3f = 2, R: 6k / 1k * 4 = 24
    assert calculate_mos_area(netlist, department="dep4") == pytest.approx(83.6)


def test_unit_resistor_count_recursively_uses_modulo_for_dep1_to_dep3_rule():
    """余りを小さい基準抵抗へ再帰的に分解して単位抵抗数を求める。"""
    assert _unit_resistor_count(100) == 2
    assert _unit_resistor_count(50) == 1
    assert _unit_resistor_count(25) == 2
    assert _unit_resistor_count(10) == 5
    assert _unit_resistor_count(5) == 10
    assert _unit_resistor_count(1) == 50
    assert _unit_resistor_count(75) == 3
    assert _unit_resistor_count(35) == 7
    assert _unit_resistor_count(60) == 6


def test_dep1_to_dep3_add_resistor_and_capacitor_unit_area():
    """部門1〜3では抵抗・容量を単位面積へ換算して加算する。"""
    netlist = """
    .subckt opamp in out vdd vss
    R1 in out 25
    R2 in out 100
    C1 in out 6f
    .ends opamp
    """

    # 抵抗: (2 + 2) * 0.4um * 0.4um = 0.64um^2、容量: 6fF = 6um^2
    for department in ("dep1", "dep2", "dep3"):
        assert calculate_mos_area(netlist, department=department) == pytest.approx(6.64)


def test_dep4_uses_recursive_resistor_count_with_existing_sheet_resistance():
    """部門4は1kΩ・4um^2の単位抵抗で再帰的に抵抗数を求める。"""
    netlist = """
    .subckt opamp in out vdd vss
    R1 in out 6k
    R2 in out 2.1k
    R3 in out 15
    .ends opamp
    """

    # R1: 1kΩを6個直列 = 6個、R2: 1kΩを2個 + 100Ω = 2 + 10 = 12個
    # R3: 10Ω + 5Ω = 100 + 200 = 300個
    assert calculate_mos_area(netlist, department="dep4") == pytest.approx(1272.0)


def test_print_performance_table_uses_english_simple_grid_and_markdown(
    tmp_path, capsys, monkeypatch
):
    """性能表を英語の端末表とMarkdownファイルで出力する。"""
    results = {
        "const": True,
        "ib": 1e-3,
        "pdis": 1e-2,
        "dcgain_db": 60.0,
        "pm": 60.0,
        "sr": 2e6,
        "thd": 0.01,
        "bw": 1e5,
        "ivr": 0.2,
        "offset": 0.01,
    }

    markdown_path = tmp_path / "simulation_results.md"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "sr_waveform.svg").write_text("<svg />", encoding="utf-8")
    monkeypatch.setattr(simulator, "OUTPUT_DIR", output_dir)
    print_performance_table(
        results, "dep4", mos_area=10.0, markdown_path=markdown_path
    )

    output = capsys.readouterr().out
    assert "| Metric" not in output
    assert "Occupied area (mm²)" in output
    assert "+" in output
    assert "├" in output
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "| 項目" in markdown
    assert "| ---" in markdown
    assert "占有面積(mm²)" in markdown
    assert "1.000e-03" in markdown
    assert "![SR波形](testbenchGUI/out/sr_waveform.svg)" in markdown


def test_print_performance_table_applies_one_square_millimeter_area_limit(
    tmp_path, capsys
):
    """占有面積1 mm²以下を制約として判定し、表に表示する。"""
    results = {"const": True}

    print_performance_table(results, "dep4", mos_area=1_000_000.0)
    output = capsys.readouterr().out

    assert "Occupied area (mm²)" in output
    assert "<= 1 mm²" in output
    assert "[Warning]" not in output
    assert results["area_const"] is True

    print_performance_table(results, "dep4", mos_area=1_000_000.1)
    output = capsys.readouterr().out

    assert "[Warning]" in output
    assert results["area_const"] is False


def test_validate_mos_geometry_rejects_inconsistent_perimeter():
    netlist = """
    .subckt opamp in out vdd vss
    M1 out in vss vss cmosn w=2u l=0.3u ad=1.2u as=1.2u pd=1u ps=5.2u
    .ends opamp
    """

    assert not validate_mos_geometry(netlist)


def test_debug_exception_reports_failing_function_and_traceback(capsys):
    """デバッグ出力に例外を発生させた関数名とトレースバックを含める。"""
    def failing_function():
        raise RuntimeError("intentional failure")

    try:
        failing_function()
    except RuntimeError as error:
        _debug_exception("テスト", error, debug=True)

    captured = capsys.readouterr()
    assert "failing_function" in captured.err
    assert "RuntimeError: intentional failure" in captured.err
