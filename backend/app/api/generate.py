"""Generate API - デザイン生成エンドポイント"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.models.component import Component
from app.services.template_composer import TemplateComposer

router = APIRouter()


# デモ用サンプルコンポーネント
DEMO_COMPONENTS = {
    "header": Component(
        name="採用ヘッダー_ポップ",
        role="header",
        description="新卒採用 ポップ 明るい",
        template_html='<header style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; text-align: center; border-radius: 12px 12px 0 0;"><h1 style="margin: 0; font-size: 1.8rem;">{{title}}</h1></header>',
        template_css="",
        slots={"title": {"type": "text", "max_chars": 30}}
    ),
    "body": Component(
        name="採用ボディ",
        role="body",
        description="採用情報 本文",
        template_html='<main style="padding: 2rem; background: white;"><p style="font-size: 1.1rem; line-height: 1.8; color: #333;">{{content}}</p></main>',
        template_css="",
        slots={"content": {"type": "text", "max_chars": 200}}
    ),
    "cta": Component(
        name="採用CTA",
        role="cta",
        description="応募ボタン",
        template_html='<div style="padding: 1.5rem; background: #f8f9fa; text-align: center; border-radius: 0 0 12px 12px;"><button style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 1rem 3rem; font-size: 1.1rem; border-radius: 30px; cursor: pointer; font-weight: bold;">{{cta_text}}</button></div>',
        template_css="",
        slots={"cta_text": {"type": "text", "max_chars": 20}}
    ),
}


class GenerateRequest(BaseModel):
    """生成リクエスト"""
    model_config = ConfigDict(extra="forbid")

    tags: list[str] = Field(..., min_length=1, description="検索タグ")
    prompt: str = Field(..., min_length=1, description="ユーザープロンプト")


class ComponentResponse(BaseModel):
    """コンポーネントレスポンス"""
    name: str
    role: str
    description: str


class GenerateResponse(BaseModel):
    """生成レスポンス"""
    output_html: str
    output_css: str
    selected_components: list[ComponentResponse]
    all_slots: dict[str, dict]


@router.post("/generate", response_model=GenerateResponse)
async def generate_design(request: GenerateRequest):
    """デザインを生成（デモモード）

    現在はDBなしのデモモードで動作。
    サンプルコンポーネントを使用してHTML/CSSを生成します。
    """
    try:
        composer = TemplateComposer()

        normalized_prompt = request.prompt.strip()

        default_slot_values = {
            "header": {"title": normalized_prompt[:30] or "新卒採用スタート！"},
            "body": {"content": normalized_prompt or "私たちと一緒に、新しい未来を創りませんか？若手社員が活躍できる環境で、あなたの可能性を広げてください。"},
            "cta": {"cta_text": "エントリーする"},
        }

        # テンプレート合成
        result = composer.compose_with_slots(
            components=DEMO_COMPONENTS,
            slot_values=default_slot_values,
            wrap_in_container=True
        )

        # レスポンス作成
        selected_components = [
            ComponentResponse(
                name=comp.name,
                role=comp.role,
                description=comp.description
            )
            for comp in DEMO_COMPONENTS.values()
        ]

        return GenerateResponse(
            output_html=result.html,
            output_css=result.css,
            selected_components=selected_components,
            all_slots=result.all_slots
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
