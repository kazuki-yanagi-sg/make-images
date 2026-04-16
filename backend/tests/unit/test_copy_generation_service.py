"""Copy generation service のテスト"""
from app.services.copy_generation_service import CopyGenerationService


def sample_structure():
    return {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "headline",
                "type": "text",
                "role": "headline",
                "x": 120,
                "y": 120,
                "width": 840,
                "height": 180,
                "content": "",
                "slot": {"name": "headline", "required": True, "max_chars": 10},
            },
            {
                "id": "cta",
                "type": "text",
                "role": "cta",
                "x": 220,
                "y": 860,
                "width": 600,
                "height": 80,
                "content": "",
                "slot": {"name": "cta", "required": True, "max_chars": 12},
            },
        ],
    }


def test_generate_slot_values_respects_max_chars():
    service = CopyGenerationService()

    slot_values = service.generate_slot_values(
        structure=sample_structure(),
        prompt="これはかなり長い新卒採用スタートの告知文です",
        input_tags=["採用", "ポップ"],
    )

    assert len(slot_values["headline"]) <= 10


def test_fill_structure_sets_content_without_changing_element_count():
    service = CopyGenerationService()
    structure = sample_structure()

    filled = service.fill_structure(
        structure=structure,
        slot_values={"headline": "採用開始", "cta": "詳しくはこちら"},
    )

    assert len(filled["elements"]) == len(structure["elements"])
    assert filled["elements"][0]["content"] == "採用開始"
    assert filled["elements"][1]["content"] == "詳しくはこちら"


def test_fill_structure_keeps_original_geometry():
    service = CopyGenerationService()
    structure = sample_structure()

    filled = service.fill_structure(
        structure=structure,
        slot_values={"headline": "採用開始"},
    )

    assert filled["elements"][0]["id"] == "headline"
    assert filled["elements"][0]["x"] == 120
    assert filled["elements"][0]["y"] == 120
    assert filled["elements"][0]["width"] == 840
    assert filled["elements"][0]["height"] == 180
