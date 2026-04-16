"""画像比較サービス

元画像と生成結果の差分を計算し、ハイライト表示する。
"""

from dataclasses import dataclass
from typing import Union
import io
import numpy as np
from PIL import Image


@dataclass
class ComparisonResult:
    """比較結果"""
    diff_percentage: float
    diff_pixel_count: int
    diff_image: Image.Image
    original_size: tuple[int, int]
    compared_size: tuple[int, int]

    def summary(self) -> str:
        """結果のサマリー文字列を返す"""
        return (
            f"差分率: {self.diff_percentage:.2f}%\n"
            f"差分ピクセル数: {self.diff_pixel_count}\n"
            f"元画像サイズ: {self.original_size[0]}x{self.original_size[1]}\n"
            f"比較画像サイズ: {self.compared_size[0]}x{self.compared_size[1]}"
        )


class ImageComparator:
    """画像比較サービス"""

    def load_image(self, source: Union[str, bytes]) -> Image.Image:
        """画像を読み込む

        Args:
            source: ファイルパスまたはバイト列

        Returns:
            PIL Image オブジェクト
        """
        if isinstance(source, bytes):
            return Image.open(io.BytesIO(source)).convert("RGB")
        else:
            return Image.open(source).convert("RGB")

    def compare(
        self,
        img1: Image.Image,
        img2: Image.Image,
        threshold: int = 0,
    ) -> ComparisonResult:
        """2つの画像を比較する

        Args:
            img1: 元画像
            img2: 比較画像
            threshold: 差分と見なす閾値（0-255）

        Returns:
            ComparisonResult オブジェクト
        """
        original_size = img1.size
        compared_size = img2.size

        # サイズが異なる場合は大きい方に合わせてリサイズ
        target_size = (
            max(img1.size[0], img2.size[0]),
            max(img1.size[1], img2.size[1]),
        )

        if img1.size != target_size:
            img1 = img1.resize(target_size, Image.Resampling.LANCZOS)
        if img2.size != target_size:
            img2 = img2.resize(target_size, Image.Resampling.LANCZOS)

        # numpy配列に変換
        arr1 = np.array(img1, dtype=np.float32)
        arr2 = np.array(img2, dtype=np.float32)

        # 差分を計算
        diff = np.abs(arr1 - arr2)

        # 各ピクセルの最大差分（RGB各チャンネルの最大）
        max_diff_per_pixel = np.max(diff, axis=2)

        # 閾値を適用
        diff_mask = max_diff_per_pixel > threshold

        # 差分ピクセル数と差分率を計算
        total_pixels = target_size[0] * target_size[1]
        diff_pixel_count = int(np.sum(diff_mask))
        diff_percentage = (diff_pixel_count / total_pixels) * 100

        # 差分ハイライト画像を生成
        diff_image = self._create_diff_image(img1, img2, diff_mask)

        return ComparisonResult(
            diff_percentage=diff_percentage,
            diff_pixel_count=diff_pixel_count,
            diff_image=diff_image,
            original_size=original_size,
            compared_size=compared_size,
        )

    def _create_diff_image(
        self,
        img1: Image.Image,
        img2: Image.Image,
        diff_mask: np.ndarray,
    ) -> Image.Image:
        """差分ハイライト画像を生成する

        差分がある箇所を赤くハイライト、
        差分がない箇所は元画像をグレースケール化して表示。

        Args:
            img1: 元画像（リサイズ済み）
            img2: 比較画像（リサイズ済み）
            diff_mask: 差分マスク（True = 差分あり）

        Returns:
            差分ハイライト画像
        """
        # 元画像をグレースケール化してベースにする
        gray = img1.convert("L").convert("RGB")
        gray_arr = np.array(gray)

        # 差分箇所を赤くハイライト
        highlight_color = np.array([255, 0, 0], dtype=np.uint8)

        # 結果画像を作成
        result_arr = gray_arr.copy()

        # 差分箇所を赤で上書き
        result_arr[diff_mask] = highlight_color

        return Image.fromarray(result_arr)

    def save_diff_image(self, image: Image.Image, path: str) -> None:
        """差分画像を保存する

        Args:
            image: 保存する画像
            path: 保存先パス
        """
        image.save(path, format="PNG")
