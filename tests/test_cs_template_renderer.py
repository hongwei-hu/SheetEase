import pytest

from ExcelExportTool.generation.cs_generation import (
    _build_enum_source,
    build_script_model,
    generate_data_class,
    generate_info_class,
    wrap_class_str,
)
from ExcelExportTool.generation.cs_template_renderer import (
    CSharpTemplateRenderer,
    CSharpScriptModel,
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


def test_generate_data_class_empty_body_has_single_blank_line_between_braces():
    content = generate_data_class(
        sheet_name="Reward",
        need_generate_keys=False,
        composite_keys=False,
        composite_multiplier=46340,
    )
    normalized = content.replace("\r\n", "\n").replace("    ", "\t")
    assert "public class RewardConfig : ConfigDataBase<RewardInfo>" in normalized
    assert "{\n\t\n}" in normalized
    assert "{\n\t\n\n}" not in normalized


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


def test_build_script_model_includes_enum_namespace_using_when_needed():
    model = build_script_model(
        sheet_name="Item",
        properties_dict={"kind": "enum(ItemType)", "name": "string"},
        property_remarks={"kind": "kind", "name": "name"},
        need_generate_keys=False,
        composite_keys=False,
        composite_multiplier=46340,
    )
    assert "using Data.TableScript;" in model.using_block
    assert model.namespace_name == "Data.TableScript"
    assert len(model.class_blocks) == 2


def test_render_script_joins_class_blocks_with_single_blank_line():
    renderer = CSharpTemplateRenderer()
    model = CSharpScriptModel(
        using_block="using A;\n\n",
        namespace_name="Demo.Space",
        class_blocks=["public class A {}", "public class B {}"],
    )
    content = renderer.render_script(model)
    assert "namespace Demo.Space" in content
    normalized = content.replace("\r\n", "\n").replace("\t", "")
    assert "public class A {}\n\npublic class B {}" in normalized
