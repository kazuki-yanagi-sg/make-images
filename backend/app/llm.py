import os
import json
import base64
import re
import io
from typing import Any

from dotenv import load_dotenv
from PIL import Image, ImageOps

from app.prompts import load_system_prompt, load_user_prompt

load_dotenv()


def _validate_and_fix_structure(result: dict[str, Any]) -> dict[str, Any]:
    """Validate and fix LLM output to match expected schema.

    LLMはパーセンテージ座標（0-100）で出力するため、ピクセル座標に変換する。
    """

    # Ensure canvas exists with defaults
    if "canvas" not in result:
        result["canvas"] = {"width": 1080, "height": 1080, "background": "#FFFFFF"}

    canvas_width = result["canvas"].get("width", 1080)
    canvas_height = result["canvas"].get("height", 1080)
    coordinate_type = result.get("coordinate_type", "percent")

    # Fix elements
    elements = result.get("elements", [])
    for i, element in enumerate(elements):
        # Ensure id exists
        if "id" not in element:
            element["id"] = f"element_{i}"

        # 座標を正規化
        for coord in ["x", "y", "width", "height"]:
            if coord in element:
                val = element[coord]
                if isinstance(val, (int, float)):
                    if coordinate_type == "percent":
                        if 0 <= val <= 100:
                            if coord in ["x", "width"]:
                                element[coord] = int(val / 100 * canvas_width)
                            else:
                                element[coord] = int(val / 100 * canvas_height)
                        else:
                            element[coord] = int(val)
                    else:
                        element[coord] = int(val)

        # Ensure z_index exists
        if "z_index" not in element:
            element["z_index"] = i

    result["coordinate_type"] = "pixel"
    return result


def _validate_and_fix_auto_tags(tags: list[str]) -> list[str]:
    """Ensure all tags have # prefix and filter out noise."""
    if not tags:
        return []

    fixed_tags = []
    noise_words = {"and", "the", "a", "an", "of", "in", "on", "at", "to", "for", "with"}

    for tag in tags:
        if not isinstance(tag, str):
            continue
        tag = tag.strip()

        # Skip noise words
        if tag.lower() in noise_words:
            continue

        # Skip very short tags (likely noise)
        if len(tag) < 2:
            continue

        # Add # prefix if missing
        if not tag.startswith("#"):
            tag = f"#{tag}"

        if tag not in fixed_tags:
            fixed_tags.append(tag)

    return fixed_tags[:10]  # Limit to 10 tags

# Lazy-initialized client
_openai_client = None


def _get_openai_client():
    """Get OpenAI client (lazy initialization)."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "dummy_key"))
    return _openai_client


def _encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _encode_reference_image(image_bytes: bytes, max_side: int = 1600, quality: int = 85) -> str:
    """参照画像をLLM投入向けに縮小・圧縮してbase64化する。"""
    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)

    if image.mode not in ("RGB", "L"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if "A" in image.getbands():
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image)
        image = background
    elif image.mode == "L":
        image = image.convert("RGB")

    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(output.getvalue()).decode("utf-8")


def _prune_structure_for_reference_prompt(structure: dict[str, Any]) -> dict[str, Any]:
    """LLM補正用に巨大フィールドを除去した軽量構造を返す。"""

    def prune_value(key: str, value: Any) -> Any:
        if key in {"src", "svg_text"}:
            return None

        if isinstance(value, dict):
            pruned = {}
            for child_key, child_value in value.items():
                pruned_child = prune_value(child_key, child_value)
                if pruned_child is not None:
                    pruned[child_key] = pruned_child
            return pruned

        if isinstance(value, list):
            return [item for item in (prune_value("", item) for item in value) if item is not None]

        if isinstance(value, str) and len(value) > 500:
            return value[:500]

        return value

    return prune_value("", structure)


def _prune_structure_for_text_intent_prompt(structure: dict[str, Any]) -> dict[str, Any]:
    """Text intent 推定用に geometry を保った軽量構造へ絞る。"""
    pruned_elements: list[dict[str, Any]] = []
    for element in structure.get("elements", []):
        element_type = element.get("type")
        if element_type == "text":
            pruned_elements.append(
                {
                    "id": element.get("id"),
                    "type": "text",
                    "content": element.get("content", ""),
                    "x": element.get("x"),
                    "y": element.get("y"),
                    "width": element.get("width"),
                    "height": element.get("height"),
                    "rotation": element.get("rotation"),
                    "is_vertical": element.get("is_vertical", False),
                    "style": {
                        "fontSize": (element.get("style") or {}).get("fontSize"),
                        "fontWeight": (element.get("style") or {}).get("fontWeight"),
                        "fontFamily": (element.get("style") or {}).get("fontFamily"),
                        "color": (element.get("style") or {}).get("color"),
                        "textAlign": (element.get("style") or {}).get("textAlign"),
                    },
                }
            )
        elif element_type == "shape":
            pruned_elements.append(
                {
                    "id": element.get("id"),
                    "type": "shape",
                    "shape_type": element.get("shape_type"),
                    "x": element.get("x"),
                    "y": element.get("y"),
                    "width": element.get("width"),
                    "height": element.get("height"),
                    "style": {
                        "backgroundColor": (element.get("style") or {}).get("backgroundColor"),
                        "borderColor": (element.get("style") or {}).get("borderColor"),
                        "borderWidth": (element.get("style") or {}).get("borderWidth"),
                    },
                }
            )
        elif element_type == "image":
            pruned_elements.append(
                {
                    "id": element.get("id"),
                    "type": "image",
                    "x": element.get("x"),
                    "y": element.get("y"),
                    "width": element.get("width"),
                    "height": element.get("height"),
                }
            )

    return {
        "canvas": structure.get("canvas", {}),
        "coordinate_type": structure.get("coordinate_type", "pixel"),
        "elements": pruned_elements,
    }


def _validate_and_fix_text_intents(
    result: dict[str, Any],
    extracted_structure: dict[str, Any],
) -> dict[str, Any]:
    """LLM返却の text intent だけを正規化する。"""
    text_ids = {
        str(element.get("id"))
        for element in extracted_structure.get("elements", [])
        if element.get("type") == "text" and element.get("id")
    }
    allowed_text_flow = {"horizontal", "vertical", "rotated_ccw_90", "stacked_ascii"}
    allowed_text_align = {"left", "center", "right"}
    allowed_background_hint = {"none", "solid_rect", "border_rect"}
    allowed_emphasis_role = {"headline", "label", "note", "quote", "name", "department", "index"}

    normalized_elements: list[dict[str, Any]] = []
    for element in result.get("elements", []):
        element_id = str(element.get("id") or "")
        if element_id not in text_ids:
            continue

        layout_intent = element.get("layout_intent") or {}
        if not isinstance(layout_intent, dict):
            layout_intent = {}

        normalized_intent: dict[str, Any] = {}
        text_flow = layout_intent.get("text_flow")
        if text_flow in allowed_text_flow:
            normalized_intent["text_flow"] = text_flow
        text_align = layout_intent.get("text_align")
        if text_align in allowed_text_align:
            normalized_intent["text_align"] = text_align
        background_hint = layout_intent.get("background_hint")
        if background_hint in allowed_background_hint:
            normalized_intent["background_hint"] = background_hint
        emphasis_role = layout_intent.get("emphasis_role")
        if emphasis_role in allowed_emphasis_role:
            normalized_intent["emphasis_role"] = emphasis_role

        for key in ("background_color", "border_color"):
            value = layout_intent.get(key)
            if isinstance(value, str) and value:
                normalized_intent[key] = value
        border_width = layout_intent.get("border_width")
        if isinstance(border_width, (int, float)) and border_width > 0:
            normalized_intent["border_width"] = float(border_width)

        normalized_elements.append(
            {
                "id": element_id,
                "type": "text",
                "layout_intent": normalized_intent,
            }
        )

    return {"elements": normalized_elements}


def extract_template_structure(image_bytes: bytes) -> tuple[dict, str, list[str]]:
    """
    Given an image, uses OpenAI Vision to extract semantic structure,
    an atmosphere description, and auto-generated tags.

    Returns:
        tuple: (structure_dict, atmosphere_str, auto_tags_list)
    """
    if os.environ.get("OPENAI_API_KEY") == "mock_key":
        return {"elements": []}, "Default atmosphere", []

    base64_image = _encode_image(image_bytes)

    system_prompt = load_system_prompt("extract_structure")
    user_prompt = load_user_prompt("extract_structure")

    response = _get_openai_client().chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ]
    )

    result = json.loads(response.choices[0].message.content)
    atmosphere = result.pop("atmosphere", "Default atmosphere")
    auto_tags = result.pop("auto_tags", [])

    # Validate and fix the output
    result = _validate_and_fix_structure(result)
    auto_tags = _validate_and_fix_auto_tags(auto_tags)

    return result, atmosphere, auto_tags


def correct_pptx_structure_with_reference(
    reference_image_bytes: bytes,
    extracted_structure: dict[str, Any],
) -> tuple[dict, str, list[str]]:
    """PPTX由来の構造を正解画像で補正する。"""
    if os.environ.get("OPENAI_API_KEY") == "mock_key":
        normalized = _validate_and_fix_structure(dict(extracted_structure))
        return normalized, "Default atmosphere", []

    base64_image = _encode_reference_image(reference_image_bytes)
    prompt_structure = _prune_structure_for_reference_prompt(extracted_structure)
    system_prompt = load_system_prompt("correct_pptx_structure")
    user_prompt = load_user_prompt("correct_pptx_structure").format(
        extracted_structure=json.dumps(prompt_structure, ensure_ascii=False)
    )

    response = _get_openai_client().chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ],
            },
        ],
    )

    result = json.loads(response.choices[0].message.content)
    atmosphere = result.pop("atmosphere", "Default atmosphere")
    auto_tags = result.pop("auto_tags", [])

    result = _validate_and_fix_structure(result)
    auto_tags = _validate_and_fix_auto_tags(auto_tags)

    return result, atmosphere, auto_tags


def infer_pptx_text_presentation(
    extracted_structure: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str]]:
    """PPTX text 要素の見せ方だけを LLM で解釈する。"""
    if os.environ.get("OPENAI_API_KEY") == "mock_key":
        normalized = {"elements": []}
        for element in extracted_structure.get("elements", []):
            if element.get("type") != "text":
                continue
            style = element.get("style") or {}
            color = str(style.get("color") or element.get("color") or "#000000")
            content = str(element.get("content") or "")
            background_hint = "none"
            if color.lower() != "#ffffff" and len(content) <= 12 and int(element.get("width", 0) or 0) > int(element.get("height", 0) or 0):
                background_hint = "solid_rect"
            if color.lower() == "#ffffff" and ("年度" in content or "入社" in content):
                background_hint = "border_rect"
            text_flow = "horizontal"
            if element.get("rotation") in {-90, -90.0}:
                text_flow = "rotated_ccw_90"
            elif element.get("is_vertical"):
                text_flow = "vertical"
            normalized["elements"].append(
                {
                    "id": element.get("id"),
                    "type": "text",
                    "layout_intent": {
                        "text_flow": text_flow,
                        "text_align": str(style.get("textAlign") or "left"),
                        "background_hint": background_hint,
                    },
                }
            )
        return normalized, "Default atmosphere", []

    prompt_structure = _prune_structure_for_text_intent_prompt(extracted_structure)
    system_prompt = load_system_prompt("infer_pptx_text_presentation")
    user_prompt = load_user_prompt("infer_pptx_text_presentation").format(
        extracted_structure=json.dumps(prompt_structure, ensure_ascii=False)
    )

    response = _get_openai_client().chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    result = json.loads(response.choices[0].message.content)
    atmosphere = result.pop("atmosphere", "Default atmosphere")
    auto_tags = result.pop("auto_tags", [])

    result = _validate_and_fix_text_intents(result, extracted_structure)
    auto_tags = _validate_and_fix_auto_tags(auto_tags)
    return result, atmosphere, auto_tags


def get_embedding(text: str) -> list[float]:
    """Get embedding vector using OpenAI."""
    if os.environ.get("OPENAI_API_KEY") == "mock_key":
        return [0.0] * 1536

    response = _get_openai_client().embeddings.create(
        input=text, model="text-embedding-3-small"
    )
    return response.data[0].embedding


def generate_new_design(prompt: str, base_structure: dict) -> dict:
    """Generate text/colors based on a template structure using OpenAI."""
    if os.environ.get("OPENAI_API_KEY") == "mock_key":
        return base_structure

    system_prompt = load_system_prompt("generate_design")
    user_prompt = load_user_prompt("generate_design").format(
        base_structure=json.dumps(base_structure),
        instruction=prompt
    )

    response = _get_openai_client().chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    new_structure = json.loads(response.choices[0].message.content)

    # Validation / Correction Loop
    validate_system_prompt = load_system_prompt("validate_layout")
    validate_user_template = load_user_prompt("validate_layout")

    for _ in range(2):
        validate_user_prompt = validate_user_template.format(
            generated_structure=json.dumps(new_structure)
        )

        check_response = _get_openai_client().chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": validate_system_prompt},
                {"role": "user", "content": validate_user_prompt}
            ]
        )

        new_structure = json.loads(check_response.choices[0].message.content)

    return new_structure
