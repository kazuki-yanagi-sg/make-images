"""投稿全体テンプレート向けの文言生成（LLM使用）"""
import json
import os
from copy import deepcopy

from openai import OpenAI


def _get_style_value(style: dict, *keys):
    """camelCase と snake_case の両方に対応してスタイル値を取得"""
    for key in keys:
        if key in style and style[key] is not None:
            return style[key]
    return None


def _calculate_max_chars(width: int, font_size: int) -> int:
    """width と font_size から適切な最大文字数を計算

    日本語は全角文字が多いため、font_size * 0.9 を1文字の幅とする。
    安全マージン20%を考慮して計算。
    """
    if not width or not font_size or font_size <= 0:
        return 50  # デフォルト

    char_width = font_size * 0.9
    max_chars = int(width / char_width * 0.8)
    return max(1, max_chars)  # 最低1文字


class CopyGenerationService:
    """構造JSONの各text要素にLLMで文言を生成して埋める"""

    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    def generate_slot_values(
        self,
        structure: dict,
        prompt: str,
        input_tags: list[str] | None = None,
    ) -> dict[str, str]:
        """LLMを使って全text要素のcontentを一括生成"""
        input_tags = input_tags or []

        # text要素を抽出
        text_elements = [
            el for el in structure.get("elements", [])
            if el.get("type") == "text"
        ]

        if not text_elements:
            return {}

        # モックキーの場合はルールベースにフォールバック
        if os.environ.get("OPENAI_API_KEY") == "mock_key":
            return self._generate_fallback(text_elements, prompt, input_tags)

        # LLMで一括生成
        return self._generate_with_llm(text_elements, prompt, input_tags)

    def _generate_with_llm(
        self,
        text_elements: list[dict],
        prompt: str,
        input_tags: list[str],
    ) -> dict[str, str]:
        """LLMで各text要素のcontentを一括生成"""

        # 要素情報を整理（width/height/font_sizeを含める）
        elements_info = []
        calculated_max_chars = {}

        for el in text_elements:
            style = el.get("style", {})
            width = el.get("width", 0)
            height = el.get("height", 0)
            font_size = _get_style_value(style, "fontSize", "font_size") or 24

            # max_charsを自動計算（slotに設定されていない場合）
            slot_max_chars = el.get("slot", {}).get("max_chars") if el.get("slot") else None
            if slot_max_chars:
                max_chars = slot_max_chars
            else:
                max_chars = _calculate_max_chars(width, font_size)

            calculated_max_chars[el.get("id")] = max_chars

            info = {
                "id": el.get("id"),
                "role": el.get("role", ""),
                "current_content": el.get("content", ""),
                "width": width,
                "height": height,
                "font_size": font_size,
                "max_chars": max_chars,
            }
            elements_info.append(info)

        system_prompt = """あなたはInstagram投稿画像のコピーライターです。
ユーザーが伝えたいメッセージを、各text要素に適切に配置してください。

【最重要ルール】
★ユーザーのプロンプト内容を必ず反映すること★
- ユーザーが「有限要素法」と言えば、出力に「有限要素法」を含める
- ユーザーが「航空会社」と言えば、出力に「航空会社」を含める
- current_contentはフォーマット参考のみ。内容はユーザーのプロンプトから生成する

【文字数ルール】
1. max_charsは絶対に超えない（超えると表示が崩れる）
2. 短くてもユーザーの意図が伝わる文言にする
3. 長い場合は要点を絞って要約する

【出力形式】
- JSON形式で返す（各要素のidをキー、生成した文言を値）"""

        user_prompt = f"""【ユーザーが伝えたいメッセージ】
{prompt}

【タグ】{', '.join(input_tags) if input_tags else 'なし'}

【要素情報】
以下の各要素にメッセージを配置してください。
★重要：ユーザーのメッセージ内容（上記）を必ず反映してください！
current_contentは長さ・フォーマットの参考のみです。

{json.dumps(elements_info, ensure_ascii=False, indent=2)}

JSON形式で返してください。例: {{"headline": "有限要素法で航空業界に貢献", "label_text": "会社説明"}}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            result = json.loads(response.choices[0].message.content)

            # max_chars制限を強制適用（LLMが守らなかった場合のフォールバック）
            for el_id, max_chars in calculated_max_chars.items():
                if el_id in result and len(result[el_id]) > max_chars:
                    result[el_id] = result[el_id][:max_chars]

            return result

        except Exception as e:
            print(f"LLM generation failed: {e}")
            return self._generate_fallback(text_elements, prompt, input_tags)

    def _generate_fallback(
        self,
        text_elements: list[dict],
        prompt: str,
        input_tags: list[str],
    ) -> dict[str, str]:
        """フォールバック: ルールベースで生成"""
        result = {}
        for el in text_elements:
            el_id = el.get("id", "")
            role = el.get("role", "").lower()
            style = el.get("style", {})
            width = el.get("width", 0)
            font_size = _get_style_value(style, "fontSize", "font_size") or 24

            if "cta" in el_id.lower() or "cta" in role:
                text = "詳しくはこちら"
            elif "headline" in el_id.lower() or "title" in el_id.lower():
                text = prompt.replace("。", "").strip()
            elif "label" in el_id.lower():
                text = input_tags[0] if input_tags else "INFO"
            else:
                text = prompt.replace("。", "").strip()

            # max_charsを計算して適用
            slot_max_chars = el.get("slot", {}).get("max_chars") if el.get("slot") else None
            if slot_max_chars:
                max_chars = slot_max_chars
            else:
                max_chars = _calculate_max_chars(width, font_size)

            result[el_id] = text[:max_chars]

        return result

    def fill_structure(self, structure: dict, slot_values: dict[str, str]) -> dict:
        """生成した文言を構造に埋め込む"""
        filled = deepcopy(structure)
        for element in filled.get("elements", []):
            el_id = element.get("id")
            if el_id and el_id in slot_values:
                element["content"] = slot_values[el_id]
        return filled
