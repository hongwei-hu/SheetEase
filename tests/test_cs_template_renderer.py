import pytest

from ExcelExportTool.generation.cs_generation import (
    _build_enum_source,
    generate_data_class,
    generate_info_class,
    wrap_class_str,
)
from ExcelExportTool.generation.cs_template_renderer import (
    CSharpTemplateRenderer,
    TemplateRenderError,
)


def test_build_enum_source_renders_summary_and_members():
    content = _build_enum_source(
        enum_type_name="Quality",
        enum_names=["Low", "High"],
        enum_values=[1, 2],
        remarks=["low quality", "high quality"],
        name_space="ConfigDataName",
    )
    assert "public enum Quality" in content
    assert "Low = 1" in content
    assert "High = 2" in content
    assert "/// <summary> low quality </summary>" in content


def test_generate_data_class_composite_multiplier_exists_when_needed():
    content = generate_data_class(
        sheet_name="Reward",
        need_generate_keys=False,
        composite_keys=True,
        composite_multiplier=9973,
    )
    assert "public class RewardConfig : ConfigDataWithCompositeId<RewardInfo>" in content
    assert "protected override int CompositeMultiplier => 9973;" in content


def test_wrap_class_str_keeps_interface_and_body():
    content = wrap_class_str(
        class_name="A",
        class_content_str="public int id { get; private set; }",
        interface_name="IItem",
    )
    assert "public class A : IItem" in content
    assert "public int id { get; private set; }" in content


def test_generate_info_class_still_auto_adds_id_with_template_renderer():
    content = generate_info_class(
        "Item",
        {"name": "string"},
        {"name": "name"},
    )
    assert "[JsonProperty(\"name\")]" in content
    assert "[JsonProperty(\"id\")]" in content
    assert "public int id { get; private set; }" in content
    assert "public string name { get; private set; }\n\n\t/// <summary> Auto-added to satisfy IConfigRawInfo </summary>" in content


def test_template_renderer_raises_template_error_on_invalid_template():
    renderer = CSharpTemplateRenderer()
    with pytest.raises(TemplateRenderError):
        renderer._render("bad", "{% if x %}", x=True)
