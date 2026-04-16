"""画像比較サービスのテスト

TDDルールに従い、テストを先に作成。
"""

import pytest
import numpy as np
from PIL import Image
import io


class TestImageComparator:
    """画像比較サービスのテスト"""

    def test_compare_identical_images_returns_zero_diff(self):
        """同一画像の比較では差分が0であること"""
        from app.services.image_comparator import ImageComparator

        # 同一の赤い画像を作成
        img = Image.new("RGB", (100, 100), color="red")

        comparator = ImageComparator()
        result = comparator.compare(img, img)

        assert result.diff_percentage == 0.0
        assert result.diff_pixel_count == 0

    def test_compare_different_images_returns_nonzero_diff(self):
        """異なる画像の比較では差分が0より大きいこと"""
        from app.services.image_comparator import ImageComparator

        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="blue")

        comparator = ImageComparator()
        result = comparator.compare(img1, img2)

        assert result.diff_percentage > 0
        assert result.diff_pixel_count > 0

    def test_compare_generates_diff_image(self):
        """差分ハイライト画像が生成されること"""
        from app.services.image_comparator import ImageComparator

        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="blue")

        comparator = ImageComparator()
        result = comparator.compare(img1, img2)

        assert result.diff_image is not None
        assert isinstance(result.diff_image, Image.Image)
        assert result.diff_image.size == (100, 100)

    def test_compare_resizes_images_if_different_size(self):
        """サイズが異なる画像はリサイズして比較すること"""
        from app.services.image_comparator import ImageComparator

        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (200, 200), color="red")

        comparator = ImageComparator()
        result = comparator.compare(img1, img2)

        # 同じ色なので差分は小さいはず
        assert result.diff_percentage < 10.0

    def test_compare_partial_diff(self):
        """部分的に異なる画像の差分を正しく検出すること"""
        from app.services.image_comparator import ImageComparator

        # 白い画像
        img1 = Image.new("RGB", (100, 100), color="white")
        # 半分が白、半分が黒の画像
        img2 = Image.new("RGB", (100, 100), color="white")
        for x in range(50):
            for y in range(100):
                img2.putpixel((x, y), (0, 0, 0))

        comparator = ImageComparator()
        result = comparator.compare(img1, img2)

        # 約50%の差分
        assert 40.0 < result.diff_percentage < 60.0

    def test_compare_with_threshold(self):
        """閾値を指定して小さな差分を無視できること"""
        from app.services.image_comparator import ImageComparator

        # わずかに異なる色
        img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = Image.new("RGB", (100, 100), color=(250, 0, 0))  # 少しだけ暗い赤

        comparator = ImageComparator()

        # 閾値なし
        result_strict = comparator.compare(img1, img2, threshold=0)

        # 閾値あり（10以下の差分は無視）
        result_lenient = comparator.compare(img1, img2, threshold=10)

        assert result_strict.diff_percentage > result_lenient.diff_percentage

    def test_load_image_from_path(self):
        """ファイルパスから画像を読み込めること"""
        from app.services.image_comparator import ImageComparator
        import tempfile
        import os

        # 一時ファイルに画像を保存
        img = Image.new("RGB", (100, 100), color="green")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f, format="PNG")
            temp_path = f.name

        try:
            comparator = ImageComparator()
            loaded_img = comparator.load_image(temp_path)

            assert loaded_img is not None
            assert loaded_img.size == (100, 100)
        finally:
            os.unlink(temp_path)

    def test_load_image_from_bytes(self):
        """バイト列から画像を読み込めること"""
        from app.services.image_comparator import ImageComparator

        img = Image.new("RGB", (100, 100), color="blue")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()

        comparator = ImageComparator()
        loaded_img = comparator.load_image(img_bytes)

        assert loaded_img is not None
        assert loaded_img.size == (100, 100)

    def test_save_diff_image(self):
        """差分画像を保存できること"""
        from app.services.image_comparator import ImageComparator
        import tempfile
        import os

        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="blue")

        comparator = ImageComparator()
        result = comparator.compare(img1, img2)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name

        try:
            comparator.save_diff_image(result.diff_image, temp_path)

            # ファイルが存在すること
            assert os.path.exists(temp_path)

            # 読み込み可能であること
            saved_img = Image.open(temp_path)
            assert saved_img.size == (100, 100)
        finally:
            os.unlink(temp_path)


class TestComparisonResult:
    """比較結果データクラスのテスト"""

    def test_result_has_required_fields(self):
        """結果に必要なフィールドがあること"""
        from app.services.image_comparator import ComparisonResult

        diff_img = Image.new("RGB", (100, 100), color="red")
        result = ComparisonResult(
            diff_percentage=50.0,
            diff_pixel_count=5000,
            diff_image=diff_img,
            original_size=(100, 100),
            compared_size=(100, 100),
        )

        assert result.diff_percentage == 50.0
        assert result.diff_pixel_count == 5000
        assert result.diff_image is not None
        assert result.original_size == (100, 100)
        assert result.compared_size == (100, 100)

    def test_result_summary(self):
        """結果のサマリー文字列を取得できること"""
        from app.services.image_comparator import ComparisonResult

        diff_img = Image.new("RGB", (100, 100), color="red")
        result = ComparisonResult(
            diff_percentage=25.5,
            diff_pixel_count=2550,
            diff_image=diff_img,
            original_size=(100, 100),
            compared_size=(100, 100),
        )

        summary = result.summary()

        assert "25.5" in summary or "25.50" in summary
        assert "2550" in summary
