import pytest

from .compatibility_cases import build_compatibility_cases
from .compatibility_check import check_case


@pytest.fixture(scope="module")
def compatibility_cases(tmp_path_factory):
    return {case.id: case for case in build_compatibility_cases(tmp_path_factory.mktemp("compatibility") / "inputs")}


IDS = ["W01", "X01", "X02", "P01", "P02", "W03", "W04", "X03", "X04", "P03", "P04",
       *[f"W{i:02d}" for i in range(5, 16)], "WR01", "WR02", *[f"X{i:02d}" for i in range(5, 11)],
       "XR01", "XR02", "P05", "P06", "PR01", "WN01", "XN01", "PN01", "W00", "X00", "P00",
       "WU01", "XU01", "PU01", "WM01", "WM02", "WR03", "XR03", "XR04", "WN02", "WM03", "W16", "X11"]


@pytest.mark.parametrize("case_id", IDS)
def test_extraction_and_export_compatibility(case_id, compatibility_cases, tmp_path):
    assert set(IDS) == set(compatibility_cases), "新增用例必须纳入自动运行"
    check_case(compatibility_cases[case_id], tmp_path / "out")
