#!/usr/bin/env python3
"""画像比較CLIツール

元画像（PNG）と生成HTML/画像を比較し、差分をハイライト表示する。

使用例:
    # 2つの画像を比較
    python compare_images.py original.png generated.png

    # 元画像とHTMLを比較（HTMLをスクリーンショット化）
    python compare_images.py original.png template.html --html

    # 差分画像を保存
    python compare_images.py original.png generated.png -o diff.png

    # 閾値を指定（小さな差分を無視）
    python compare_images.py original.png generated.png --threshold 10
"""

import argparse
import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image
from app.services.image_comparator import ImageComparator


async def capture_html_screenshot(html_path: str, width: int, height: int) -> bytes:
    """HTMLファイルをスクリーンショット化する"""
    from app.services.screenshot_service import capture_screenshot

    html_content = Path(html_path).read_text(encoding="utf-8")

    # HTMLとCSSを分離（簡易的な処理）
    css = ""
    html = html_content

    # <style>タグがあれば抽出
    if "<style>" in html_content and "</style>" in html_content:
        start = html_content.index("<style>") + 7
        end = html_content.index("</style>")
        css = html_content[start:end]
        html = html_content[:start-7] + html_content[end+8:]

    return await capture_screenshot(html, css, width, height)


def main():
    parser = argparse.ArgumentParser(
        description="元画像と生成結果を比較して差分を表示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "original",
        help="元画像のパス（PNG/JPG）",
    )

    parser.add_argument(
        "target",
        help="比較対象のパス（画像またはHTML）",
    )

    parser.add_argument(
        "--html",
        action="store_true",
        help="比較対象がHTMLファイルの場合に指定",
    )

    parser.add_argument(
        "-o", "--output",
        help="差分画像の出力先パス（指定しない場合は diff_output.png）",
        default="diff_output.png",
    )

    parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="差分と見なす閾値（0-255、デフォルト: 0）",
    )

    parser.add_argument(
        "--width",
        type=int,
        default=1080,
        help="HTML比較時のビューポート幅（デフォルト: 1080）",
    )

    parser.add_argument(
        "--height",
        type=int,
        default=1080,
        help="HTML比較時のビューポート高さ（デフォルト: 1080）",
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="サマリー出力を抑制",
    )

    args = parser.parse_args()

    # 元画像を読み込み
    if not Path(args.original).exists():
        print(f"エラー: 元画像が見つかりません: {args.original}", file=sys.stderr)
        sys.exit(1)

    comparator = ImageComparator()
    original_img = comparator.load_image(args.original)

    # 比較対象を読み込み
    if args.html:
        if not Path(args.target).exists():
            print(f"エラー: HTMLファイルが見つかりません: {args.target}", file=sys.stderr)
            sys.exit(1)

        # HTMLをスクリーンショット化
        print(f"HTMLをスクリーンショット化中: {args.target}")
        try:
            screenshot_bytes = asyncio.run(
                capture_html_screenshot(args.target, args.width, args.height)
            )
            target_img = comparator.load_image(screenshot_bytes)
        except Exception as e:
            print(f"エラー: スクリーンショットの取得に失敗しました: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if not Path(args.target).exists():
            print(f"エラー: 比較画像が見つかりません: {args.target}", file=sys.stderr)
            sys.exit(1)
        target_img = comparator.load_image(args.target)

    # 比較実行
    print(f"画像を比較中...")
    result = comparator.compare(original_img, target_img, threshold=args.threshold)

    # 結果を出力
    if not args.quiet:
        print("\n" + "=" * 50)
        print("比較結果")
        print("=" * 50)
        print(result.summary())
        print("=" * 50)

        # 差分率に応じたメッセージ
        if result.diff_percentage == 0:
            print("\n完全一致です！")
        elif result.diff_percentage < 5:
            print("\nほぼ一致しています（差分率 5%未満）")
        elif result.diff_percentage < 20:
            print("\n若干の差分があります（差分率 20%未満）")
        else:
            print("\n大きな差分があります")

    # 差分画像を保存
    comparator.save_diff_image(result.diff_image, args.output)
    print(f"\n差分画像を保存しました: {args.output}")

    # 終了コードを返す（差分率に応じて）
    if result.diff_percentage == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
