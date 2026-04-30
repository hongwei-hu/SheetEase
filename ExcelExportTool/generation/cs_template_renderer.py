from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..exceptions import ExportError


@dataclass(frozen=True)
class CSharpPropertyModel:
    """IR: one property declaration for an info class."""

    json_name: str
    type_name: str
    property_name: str
    summary: str


@dataclass(frozen=True)
class CSharpClassModel:
    """IR: generic C# class descriptor used by renderer templates."""

    class_name: str
    interface_name: str
    summary: Optional[str]
    body_blocks: List[str]


@dataclass(frozen=True)
class CSharpEnumMemberModel:
    """IR: one enum member with optional xml summary."""

    name: str
    value: str
    summary: Optional[str]


@dataclass(frozen=True)
class CSharpEnumModel:
    """IR: enum descriptor used by enum file renderer."""

    namespace_name: str
    enum_name: str
    auto_summary: str
    members: List[CSharpEnumMemberModel]


@dataclass(frozen=True)
class CSharpScriptModel:
    """IR: top-level C# script file descriptor."""

    using_block: str
    namespace_name: str
    class_blocks: List[str]


class TemplateRenderError(ExportError):
    def __init__(self, template_name: str, reason: str):
        super().__init__(f"模板渲染失败: {template_name} -> {reason}")


_CLASS_TEMPLATE = """public class {{ model.class_name }}{% if model.interface_name %} : {{ model.interface_name }}{% endif %}
{
{% if model.body_blocks %}
{% for block in model.body_blocks %}	{{ block | replace('\\n', '\\n\\t') }}
{% if not loop.last %}
{% endif %}
{% endfor %}
{% else %}	
{% endif %}
}"""

_INFO_CLASS_TEMPLATE = """{% if model.summary %}{{ model.summary }}
{% endif %}public class {{ model.class_name }} : {{ model.interface_name }}
{
{% for prop in properties %}	{{ prop.summary }}
	[JsonProperty(\"{{ prop.json_name }}\")]
    public {{ prop.type_name }} {{ prop.property_name }} { get; private set; }{% if not loop.last %}

{% endif %}{% endfor %}
}"""

_DATA_CLASS_TEMPLATE = """{% if model.summary %}{{ model.summary }}
{% endif %}public class {{ model.class_name }} : {{ model.interface_name }}
{
{% if model.body_blocks %}{% for block in model.body_blocks %}	{{ block | replace('\\n', '\\n\\t') }}{% if not loop.last %}

{% endif %}{% endfor %}{% else %}	
{% endif -%}
}"""

_ENUM_TEMPLATE = """namespace {{ model.namespace_name }}
{
	{{ model.auto_summary }}
	public enum {{ model.enum_name }}
	{
{% for member in model.members %}{% if member.summary %}		{{ member.summary }}
{% endif %}		{{ member.name }} = {{ member.value }},

{% endfor %}	}
}"""

_SCRIPT_FILE_TEMPLATE = """{{ model.using_block }}namespace {{ model.namespace_name }}
{
    {{ model.class_blocks | join('\\n\\n') | replace('\\n', '\\n\\t') }}
}"""


class CSharpTemplateRenderer:
    """Jinja2-based renderer for C# generation.

    The renderer is template-first (phase 1), while taking typed IR models
    to prepare a smooth migration to a richer IR pipeline (phase 2).
    """

    def __init__(self) -> None:
        try:
            from jinja2 import Environment, StrictUndefined
        except Exception as exc:
            raise ImportError(
                "缺少依赖 jinja2，请先安装: pip install jinja2"
            ) from exc

        self._env = Environment(
            autoescape=False,
            trim_blocks=False,
            lstrip_blocks=False,
            keep_trailing_newline=False,
            undefined=StrictUndefined,
        )

    def _render(self, template_name: str, template_text: str, **kwargs) -> str:
        try:
            template = self._env.from_string(template_text)
            return template.render(**kwargs)
        except Exception as exc:
            raise TemplateRenderError(template_name, str(exc)) from exc

    def render_enum(self, model: CSharpEnumModel) -> str:
        return self._render("enum", _ENUM_TEMPLATE, model=model)

    def render_info_class(self, model: CSharpClassModel, properties: List[CSharpPropertyModel]) -> str:
        return self._render("info_class", _INFO_CLASS_TEMPLATE, model=model, properties=properties)

    def render_data_class(self, model: CSharpClassModel) -> str:
        return self._render("data_class", _DATA_CLASS_TEMPLATE, model=model)

    def render_class(self, model: CSharpClassModel) -> str:
        return self._render("class", _CLASS_TEMPLATE, model=model)

    def render_script(self, model: CSharpScriptModel) -> str:
        return self._render("script_file", _SCRIPT_FILE_TEMPLATE, model=model)
