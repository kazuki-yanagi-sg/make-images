"""Template Composer Service - コンポーネントをHTML/CSSに合成"""
import re
from dataclasses import dataclass, field
from app.models.component import Component


# 役割の表示順序
ROLE_ORDER = ["header", "body", "cta", "footer", "decoration"]


@dataclass
class FilledSlot:
    """スロットが埋められたコンポーネント"""
    html: str
    slot_values: dict[str, str] = field(default_factory=dict)


@dataclass
class ComposedTemplate:
    """合成されたテンプレート"""
    html: str
    css: str
    all_slots: dict[str, dict] = field(default_factory=dict)


class TemplateComposer:
    """コンポーネントをHTML/CSSに合成するサービス"""

    def compose(
        self,
        components: dict[str, Component],
        wrap_in_container: bool = False
    ) -> ComposedTemplate:
        """役割ごとのコンポーネントを合成

        Args:
            components: roleをキーとしたコンポーネントの辞書
            wrap_in_container: コンテナでラップするかどうか

        Returns:
            合成されたHTML/CSS
        """
        if not components:
            return ComposedTemplate(html="", css="", all_slots={})

        # 役割の順序でソート
        sorted_roles = sorted(
            components.keys(),
            key=lambda r: ROLE_ORDER.index(r) if r in ROLE_ORDER else len(ROLE_ORDER)
        )

        # HTMLを結合
        html_parts = []
        for role in sorted_roles:
            comp = components[role]
            if comp.template_html:
                html_parts.append(comp.template_html)

        combined_html = "\n".join(html_parts)

        if wrap_in_container:
            combined_html = f'<div class="design-container">\n{combined_html}\n</div>'

        # CSSを結合
        css_parts = []
        for role in sorted_roles:
            comp = components[role]
            if comp.template_css:
                css_parts.append(comp.template_css)

        combined_css = "\n".join(css_parts)

        # 全スロット情報を収集
        all_slots = {}
        for comp in components.values():
            if comp.slots:
                all_slots.update(comp.slots)

        return ComposedTemplate(
            html=combined_html,
            css=combined_css,
            all_slots=all_slots
        )

    def fill_slots(
        self,
        component: Component,
        values: dict[str, str]
    ) -> FilledSlot:
        """コンポーネントのスロットに値を埋め込む

        Args:
            component: コンポーネント
            values: スロット名と値の辞書

        Returns:
            スロットが埋められたコンポーネント
        """
        html = component.template_html or ""
        filled_values = {}

        for slot_name, value in values.items():
            # スロット定義を確認
            slot_def = component.slots.get(slot_name, {}) if component.slots else {}
            max_chars = slot_def.get("max_chars")

            # 文字数制限を適用
            if max_chars and len(value) > max_chars:
                value = value[:max_chars]

            filled_values[slot_name] = value

            # プレースホルダーを置換
            placeholder = "{{" + slot_name + "}}"
            html = html.replace(placeholder, value)

        return FilledSlot(html=html, slot_values=filled_values)

    def compose_with_slots(
        self,
        components: dict[str, Component],
        slot_values: dict[str, dict[str, str]],
        wrap_in_container: bool = False
    ) -> ComposedTemplate:
        """スロットを埋めた状態でコンポーネントを合成

        Args:
            components: roleをキーとしたコンポーネントの辞書
            slot_values: roleをキーとしたスロット値の辞書
            wrap_in_container: コンテナでラップするかどうか

        Returns:
            合成されたHTML/CSS
        """
        if not components:
            return ComposedTemplate(html="", css="", all_slots={})

        # 役割の順序でソート
        sorted_roles = sorted(
            components.keys(),
            key=lambda r: ROLE_ORDER.index(r) if r in ROLE_ORDER else len(ROLE_ORDER)
        )

        # HTMLを結合（スロットを埋めながら）
        html_parts = []
        all_filled_values = {}

        for role in sorted_roles:
            comp = components[role]
            if comp.template_html:
                # このroleのスロット値を取得
                role_slot_values = slot_values.get(role, {})
                filled = self.fill_slots(comp, role_slot_values)
                html_parts.append(filled.html)
                all_filled_values.update(filled.slot_values)

        combined_html = "\n".join(html_parts)

        if wrap_in_container:
            combined_html = f'<div class="design-container">\n{combined_html}\n</div>'

        # CSSを結合
        css_parts = []
        for role in sorted_roles:
            comp = components[role]
            if comp.template_css:
                css_parts.append(comp.template_css)

        combined_css = "\n".join(css_parts)

        # 全スロット情報を収集
        all_slots = {}
        for comp in components.values():
            if comp.slots:
                all_slots.update(comp.slots)

        return ComposedTemplate(
            html=combined_html,
            css=combined_css,
            all_slots=all_slots
        )
