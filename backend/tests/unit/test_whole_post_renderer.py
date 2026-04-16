"""Whole post renderer のテスト"""
from app.services.whole_post_renderer import WholePostRenderer


def test_renderer_outputs_html_and_css():
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080, "background_color": "#ffffff"},
        "elements": [
            {
                "id": "headline",
                "type": "text",
                "role": "headline",
                "x": 100,
                "y": 120,
                "width": 800,
                "height": 180,
                "content": "新卒採用スタート",
                "style": {
                    "font_size": 64,
                    "font_weight": 700,
                    "color": "#111111",
                    "align": "center",
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "新卒採用スタート" in result.html
    assert ".ig-post" in result.css
    assert "width: 1080px" in result.css
    assert "font-size: 64px" in result.css


def test_renderer_keeps_element_identity_in_markup():
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "cta",
                "type": "text",
                "role": "cta",
                "x": 120,
                "y": 840,
                "width": 400,
                "height": 80,
                "content": "詳しくはこちら",
                "style": {"font_size": 32, "color": "#222222"},
            }
        ],
    }

    result = renderer.render(structure)

    assert 'data-element-id="cta"' in result.html
    assert ".element-cta" in result.css


def test_renderer_supports_camel_case_style_keys():
    """LLMがcamelCaseで出力するケースに対応"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "headline",
                "type": "text",
                "x": 50,
                "y": 100,
                "width": 540,
                "height": 86,
                "content": "INTERVIEW",
                "style": {
                    "color": "#FFFFFF",
                    "fontSize": 72,
                    "fontWeight": "bold",
                    "fontFamily": "sans-serif",
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "font-size: 72px" in result.css
    assert "font-weight: bold" in result.css
    assert "font-family: sans-serif" in result.css


def test_renderer_outputs_z_index():
    """z_indexがCSS出力される"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "bg",
                "type": "image",
                "x": 0,
                "y": 0,
                "width": 1080,
                "height": 1080,
                "z_index": 0,
            },
            {
                "id": "text",
                "type": "text",
                "x": 50,
                "y": 50,
                "width": 200,
                "height": 50,
                "z_index": 2,
                "content": "Test",
            },
        ],
    }

    result = renderer.render(structure)

    assert "z-index: 0" in result.css
    assert "z-index: 2" in result.css


def test_renderer_handles_shape_with_border():
    """shape要素のborderがCSS出力される"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "border_frame",
                "type": "shape",
                "shape_type": "border",
                "x": 0,
                "y": 0,
                "width": 1080,
                "height": 1080,
                "style": {
                    "borderColor": "#3D3D7A",
                    "borderWidth": 20,
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "border:" in result.css
    assert "#3D3D7A" in result.css
    assert "20px" in result.css


def test_renderer_handles_shape_with_background():
    """shape要素のbackgroundColorがCSS出力される"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "label_bar",
                "type": "shape",
                "shape_type": "rect",
                "x": 54,
                "y": 86,
                "width": 270,
                "height": 54,
                "style": {
                    "backgroundColor": "#FFFF00",
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "background-color: #FFFF00" in result.css


def test_renderer_converts_percent_coordinates_to_pixels():
    """coordinate_type: percentの場合、座標をピクセルに変換する"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 810, "height": 1012},
        "coordinate_type": "percent",  # パーセンテージ座標を使用
        "elements": [
            {
                "id": "text_element",
                "type": "text",
                "x": 50.0,     # 50% = 405px
                "y": 25.0,     # 25% = 253px
                "width": 20.0, # 20% = 162px
                "height": 10.0, # 10% = 101.2px
                "content": "テスト",
            }
        ],
    }

    result = renderer.render(structure)

    # パーセンテージがピクセルに変換されることを確認
    assert "left: 405" in result.css or "left: 405.0" in result.css
    assert "top: 253" in result.css
    assert "width: 162" in result.css
    assert "height: 101" in result.css


def test_renderer_keeps_pixel_coordinates_when_no_coordinate_type():
    """coordinate_typeが指定されていない場合、従来通りピクセルとして扱う"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        # coordinate_type未指定 = ピクセル
        "elements": [
            {
                "id": "text_element",
                "type": "text",
                "x": 100,
                "y": 200,
                "width": 300,
                "height": 50,
                "content": "テスト",
            }
        ],
    }

    result = renderer.render(structure)

    # 値がそのままピクセルとして出力されることを確認
    assert "left: 100px" in result.css
    assert "top: 200px" in result.css
    assert "width: 300px" in result.css
    assert "height: 50px" in result.css


def test_renderer_outputs_font_info_from_element():
    """PDF抽出のフォント情報（element直下）がCSS出力される"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 810, "height": 1012},
        "coordinate_type": "percent",
        "elements": [
            {
                "id": "text_1",
                "type": "text",
                "x": 4.2,
                "y": 5.53,
                "width": 25.19,
                "height": 2.57,
                "content": "EastendCompany",
                "font_size": 21.0,  # element直下のフォントサイズ
                "font_name": "Nexa-Black",  # element直下のフォント名
                "color": "#ffffff",  # element直下の色
            }
        ],
    }

    result = renderer.render(structure)

    assert "font-size: 21" in result.css or "font-size: 21.0" in result.css
    assert "font-family:" in result.css
    assert "Nexa-Black" in result.css or "nexa-black" in result.css.lower()
    assert "color: #ffffff" in result.css


def test_renderer_outputs_vertical_writing_mode():
    """縦書き要素にwriting-mode: vertical-rlがCSS出力される"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 810, "height": 1012},
        "coordinate_type": "percent",
        "elements": [
            {
                "id": "vertical_text",
                "type": "text",
                "x": 88.0,
                "y": 4.5,
                "width": 7.3,
                "height": 35.6,
                "content": "営業部で一番になった",
                "is_vertical": True,  # 縦書きフラグ
            }
        ],
    }

    result = renderer.render(structure)

    assert "writing-mode: vertical-rl" in result.css


def test_renderer_prefers_style_over_element_font_info():
    """styleとelement両方にフォント情報がある場合、styleを優先"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "text_1",
                "type": "text",
                "x": 100,
                "y": 100,
                "width": 200,
                "height": 50,
                "content": "Test",
                "font_size": 20.0,  # element直下
                "style": {
                    "fontSize": 32,  # styleの方を優先
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "font-size: 32px" in result.css
    assert "font-size: 20" not in result.css


def test_renderer_handles_gradient_background():
    """shape要素のグラデーションがlinear-gradientでCSS出力される"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 810, "height": 1012},
        "coordinate_type": "percent",
        "elements": [
            {
                "id": "gradient_bg",
                "type": "shape",
                "shape_type": "rect",
                "x": 0,
                "y": 0,
                "width": 33.9,
                "height": 99.3,
                "style": {
                    "gradient": {
                        "start": "#266bb3",
                        "end": "#2e9fd6",
                        "direction": "vertical",
                    }
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "linear-gradient" in result.css
    assert "to bottom" in result.css
    assert "#266bb3" in result.css
    assert "#2e9fd6" in result.css


def test_renderer_handles_horizontal_gradient():
    """水平グラデーションがto rightでCSS出力される"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "h_gradient",
                "type": "shape",
                "shape_type": "rect",
                "x": 0,
                "y": 0,
                "width": 500,
                "height": 100,
                "style": {
                    "gradient": {
                        "start": "#ff0000",
                        "end": "#0000ff",
                        "direction": "horizontal",
                    }
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "linear-gradient" in result.css
    assert "to right" in result.css
    assert "#ff0000" in result.css
    assert "#0000ff" in result.css


def test_renderer_uses_image_src_instead_of_placeholder():
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1350},
        "elements": [
            {
                "id": "hero",
                "type": "image",
                "x": 360,
                "y": 0,
                "width": 720,
                "height": 1350,
                "src": "data:image/png;base64,AAA",
            }
        ],
    }

    result = renderer.render(structure)

    assert '<img class="element-hero-image"' in result.html
    assert 'src="data:image/png;base64,AAA"' in result.html
    assert "background: linear-gradient(135deg" not in result.css


def test_renderer_outputs_crop_styles_for_image():
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1350},
        "elements": [
            {
                "id": "hero",
                "type": "image",
                "x": 360,
                "y": 0,
                "width": 720,
                "height": 1350,
                "src": "data:image/png;base64,AAA",
                "crop": {"left": 0.1, "right": 0.2, "top": 0.05, "bottom": 0.15},
            }
        ],
    }

    result = renderer.render(structure)

    assert ".element-hero-image {" in result.css
    assert "left: -90.0px" in result.css
    assert "top: -84.375px" in result.css
    assert "width: 1028.5714285714287px" in result.css
    assert "height: 1687.5px" in result.css


def test_renderer_handles_gradient_stops_and_fill_image_for_shape():
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1350},
        "elements": [
            {
                "id": "shape_a",
                "type": "shape",
                "shape_type": "freeform",
                "x": 0,
                "y": 0,
                "width": 360,
                "height": 1350,
                "path_points": [
                    {"x": 100, "y": 0},
                    {"x": 0, "y": 0},
                    {"x": 0, "y": 100},
                ],
                "style": {
                    "gradient": {
                        "stops": [
                            {"color": "#82d1e0", "offset": 0.0},
                            {"color": "#2bace2", "offset": 0.432},
                            {"color": "#384b9d", "offset": 1.0},
                        ],
                        "direction": "diagonal",
                    },
                    "fillImage": {"src": "data:image/svg+xml;base64,BBB"},
                },
            }
        ],
    }

    result = renderer.render(structure)

    assert "linear-gradient(135deg" in result.css
    assert "#82d1e0 0.0%" in result.css
    assert "#2bace2 43.2%" in result.css
    assert "data:image/svg+xml;base64,BBB" in result.css
    assert "clip-path: polygon(100% 0%, 0% 0%, 0% 100%)" in result.css


def test_renderer_outputs_transform_for_rotation_and_flip():
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1350},
        "elements": [
            {
                "id": "shape_a",
                "type": "shape",
                "shape_type": "rect",
                "x": 10,
                "y": 20,
                "width": 100,
                "height": 120,
                "rotation": 90,
                "flip_h": True,
                "flip_v": True,
            }
        ],
    }

    result = renderer.render(structure)

    assert "transform: rotate(90deg) scale(-1, -1);" in result.css


def test_renderer_outputs_overflow_hidden_for_horizontal_text():
    """横書きテキストはオーバーフローを隠し、省略記号を表示"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "long_text",
                "type": "text",
                "x": 100,
                "y": 100,
                "width": 200,
                "height": 50,
                "content": "非常に長いテキストがここに入ります",
                "is_vertical": False,
            }
        ],
    }

    result = renderer.render(structure)

    assert "overflow: hidden" in result.css
    assert "white-space: nowrap" in result.css
    assert "text-overflow: ellipsis" in result.css


def test_renderer_outputs_overflow_hidden_for_vertical_text():
    """縦書きテキストもオーバーフローを隠す"""
    renderer = WholePostRenderer()
    structure = {
        "canvas": {"width": 1080, "height": 1080},
        "elements": [
            {
                "id": "vertical_long",
                "type": "text",
                "x": 100,
                "y": 100,
                "width": 50,
                "height": 300,
                "content": "縦書きの長いテキストです",
                "is_vertical": True,
            }
        ],
    }

    result = renderer.render(structure)

    # 要素自身に overflow: hidden が設定されること
    # (.ig-postではなく.element-vertical_longに)
    assert ".element-vertical_long {" in result.css
    element_css = result.css.split(".element-vertical_long {")[1].split("}")[0]
    assert "overflow: hidden" in element_css
    assert "writing-mode: vertical-rl" in result.css
