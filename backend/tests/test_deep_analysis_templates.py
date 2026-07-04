"""templates.py: 6 模板 + 路由表 + 字段定义的约束校验。"""
import pytest

from app.services.deep_analysis.templates import (
    BUCKET_TEMPLATES, ROUTING_TABLE, BUCKET_FIELD_DEFS,
    BUCKET_DISPLAY_NAMES, COMPANY_TYPES, COMPANY_TYPE_LABELS,
)


def test_six_buckets_exist():
    expected = {"industry_chain", "equipment", "material", "financial", "risk", "catalyst"}
    assert set(BUCKET_TEMPLATES.keys()) == expected
    assert set(BUCKET_FIELD_DEFS.keys()) == expected
    assert set(BUCKET_DISPLAY_NAMES.keys()) == expected


@pytest.mark.parametrize("bid", list(BUCKET_TEMPLATES.keys()))
def test_template_has_markdown_placeholder(bid):
    assert "{markdown}" in BUCKET_TEMPLATES[bid], f"{bid} 模板缺 {{markdown}} 占位符"


@pytest.mark.parametrize("bid", list(BUCKET_TEMPLATES.keys()))
def test_template_has_json_keyword(bid):
    """DeepSeek JSON 模式要求 prompt 含 'json' 关键字。"""
    assert "json" in BUCKET_TEMPLATES[bid].lower(), f"{bid} 模板缺 'json' 关键字"


@pytest.mark.parametrize("bid", list(BUCKET_TEMPLATES.keys()))
def test_template_lists_all_declared_fields(bid):
    """模板必须提及 BUCKET_FIELD_DEFS[bid] 中所有字段名。"""
    tpl = BUCKET_TEMPLATES[bid]
    for field in BUCKET_FIELD_DEFS[bid]:
        assert field in tpl, f"{bid} 模板未提及字段 {field}"


def test_routing_table_has_5_company_types():
    expected = {"equipment", "material", "packaging", "ip", "general"}
    assert set(ROUTING_TABLE.keys()) == expected


def test_routing_values_subset_of_buckets():
    for cid, buckets in ROUTING_TABLE.items():
        for b in buckets:
            assert b in BUCKET_TEMPLATES, f"{cid} 路由到未知 bucket {b}"


def test_company_types_match_routing():
    assert set(COMPANY_TYPES) == set(ROUTING_TABLE.keys())
    assert set(COMPANY_TYPE_LABELS.keys()) == set(ROUTING_TABLE.keys())
    assert COMPANY_TYPE_LABELS["general"] == "综合"


def test_general_route_excludes_equipment_and_material():
    """综合模式不跑 equipment/material 专属桶。"""
    assert "equipment" not in ROUTING_TABLE["general"]
    assert "material" not in ROUTING_TABLE["general"]


def test_equipment_route_includes_equipment_bucket():
    assert "equipment" in ROUTING_TABLE["equipment"]
    assert "material" not in ROUTING_TABLE["equipment"]


def test_material_route_includes_material_bucket():
    assert "material" in ROUTING_TABLE["material"]
    assert "equipment" not in ROUTING_TABLE["material"]
