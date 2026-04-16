"""FastAPI entrypoint"""
import base64
import io
import json
import tempfile
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from PIL import Image, ImageChops, ImageStat
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import Base, Generation, Template, engine, get_db
from app.llm import (
    extract_template_structure,
    get_embedding,
    infer_pptx_text_presentation,
)
from app.services.copy_generation_service import CopyGenerationService
from app.services.html_exporter import HtmlExporter
from app.services.template_analyzer import TemplateAnalyzer
from app.services.template_search_service import TemplateSearchService
from app.services.visual_correction_pipeline import run_visual_correction_pipeline
from app.services.whole_post_renderer import WholePostRenderer
from app.vector_store import add_template_vector, get_collection


Base.metadata.create_all(bind=engine)
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",  # Vite default
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_origin_regex=r"http://localhost:\d+",  # 開発環境用: 全localhostポート許可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class LegacyTemplateRecord:
    id: str
    json_data: str
    structure_json: dict[str, Any]
    manual_tags_json: list[str]
    auto_tags_json: list[str]
    search_text: str
    name: str | None = None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1)
    tags: list[str] = Field(..., min_length=1)


class ElementStyleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: str | None = None
    backgroundColor: str | None = None
    borderColor: str | None = None
    rotation: float | None = None
    is_vertical: bool | None = None


class TemplateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structure_json: dict = Field(..., description="Updated structure JSON")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/templates")
async def upload_template(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    manual_tags: str | None = Form(None),
    db: Session = Depends(get_db),
):
    Base.metadata.create_all(bind=db.get_bind())

    is_pdf = file.filename.endswith(".pdf")
    is_image = file.filename.endswith((".jpg", ".jpeg", ".png"))
    is_pptx = file.filename.endswith(".pptx")

    if not is_pdf and not is_image and not is_pptx:
        raise HTTPException(status_code=400, detail="Invalid file type")

    parsed_manual_tags = _parse_tags_form(manual_tags)
    if not parsed_manual_tags:
        raise HTTPException(status_code=400, detail="manual_tags is required")

    content = await file.read()

    if is_pdf:
        # PDFの場合: TemplateAnalyzerを使用
        structure_json, atmosphere, auto_tags = _extract_from_pdf(content, file.filename)
    elif is_pptx:
        structure_json, atmosphere, auto_tags = _extract_from_pptx(
            content,
            file.filename,
        )
    else:
        # 画像の場合: 従来のLLM解析を使用
        structure_json, atmosphere, auto_tags = extract_template_structure(content)

    # 視覚補正パイプライン: PPTXの場合のみ実行
    if is_pptx:
        # 一旦レンダリングして視覚補正を実行
        initial_rendered = WholePostRenderer().render(_ensure_structure_has_content(structure_json))
        structure_json = await run_visual_correction_pipeline(
            structure_json=structure_json,
            html=initial_rendered.html,
            css=initial_rendered.css,
        )

    search_text = _build_search_text(parsed_manual_tags, auto_tags, atmosphere, structure_json)
    embedding = get_embedding(search_text or atmosphere or (name or file.filename))

    # 最終レンダリング（補正済みstructure_jsonを使用）
    rendered = WholePostRenderer().render(_ensure_structure_has_content(structure_json))

    template_id = str(uuid.uuid4())
    vector_id = str(uuid.uuid4())
    template_payload = {
        "id": template_id,
        "name": name or file.filename,
        "json_data": json.dumps(structure_json),
        "vector_id": vector_id,
        "source_image_path": file.filename,
        "structure_json": structure_json,
        "manual_tags_json": parsed_manual_tags,
        "auto_tags_json": auto_tags,
        "search_text": search_text,
        "embedding_json": embedding,
        "preview_html": rendered.html,
        "preview_css": rendered.css,
        "atmosphere": atmosphere,
    }
    _persist_template(db, template_payload)

    add_template_vector(
        template_id,
        embedding,
        metadata=_build_vector_metadata(
            atmosphere=atmosphere,
            manual_tags=parsed_manual_tags,
            auto_tags=auto_tags,
        ),
    )

    return {
        "message": "success",
        "template_id": template_id,
        "manual_tags": parsed_manual_tags,
        "auto_tags": auto_tags,
        "structure_json": structure_json,
        "preview_html": rendered.html,
        "preview_css": rendered.css,
    }


@app.get("/api/templates")
async def list_templates(db: Session = Depends(get_db)):
    templates = (
        db.query(Template)
        .order_by(Template.created_at.desc(), Template.id.desc())
        .all()
    )

    return [
        {
            "id": template.id,
            "name": template.name,
            "manual_tags": template.manual_tags_json or [],
            "auto_tags": template.auto_tags_json or [],
            "created_at": template.created_at.isoformat() if template.created_at else None,
        }
        for template in templates
    ]


@app.post("/api/generate")
async def generate_design(req: GenerateRequest, db: Session = Depends(get_db)):
    Base.metadata.create_all(bind=db.get_bind())

    templates = _load_whole_post_templates(db)
    if not templates:
        raise HTTPException(status_code=404, detail="No suitable template found")

    return _generate_from_whole_post_template(req, db, templates)


@app.get("/api/templates/{template_id}")
async def get_template_detail(template_id: str, db: Session = Depends(get_db)):
    template = _get_template_or_404(db, template_id)
    structure = template.structure_json or json.loads(template.json_data)
    return {
        "id": template.id,
        "name": template.name,
        "manual_tags": template.manual_tags_json or [],
        "auto_tags": template.auto_tags_json or [],
        "structure_json": structure,
        "preview_html": template.preview_html or "",
        "preview_css": template.preview_css or "",
        "atmosphere": template.atmosphere,
    }


@app.patch("/api/templates/{template_id}")
async def update_template(
    template_id: str,
    req: TemplateUpdateRequest,
    db: Session = Depends(get_db),
):
    """テンプレートのstructure_jsonを更新する"""
    template = _get_template_or_404(db, template_id)

    # structure_jsonを更新
    structure = req.structure_json

    # プレビューHTMLを再生成
    rendered = WholePostRenderer().render(_ensure_structure_has_content(structure))

    template.structure_json = structure
    template.json_data = json.dumps(structure)
    template.preview_html = rendered.html
    template.preview_css = rendered.css
    db.add(template)
    db.commit()
    db.refresh(template)

    return {
        "message": "success",
        "template_id": template.id,
        "structure_json": structure,
        "preview_html": rendered.html,
        "preview_css": rendered.css,
    }


@app.patch("/api/templates/{template_id}/elements/{element_id}/style")
async def update_template_element_style(
    template_id: str,
    element_id: str,
    req: ElementStyleUpdateRequest,
    db: Session = Depends(get_db),
):
    template = _get_template_or_404(db, template_id)
    structure = json.loads(json.dumps(template.structure_json or json.loads(template.json_data)))

    target_element = None
    for element in structure.get("elements", []):
        if str(element.get("id")) == element_id:
            target_element = element
            break
    if target_element is None:
        raise HTTPException(status_code=404, detail="Element not found")

    # rotation と is_vertical は要素レベルのプロパティ
    element_level_props = {"rotation", "is_vertical"}
    style = target_element.setdefault("style", {})
    for key, value in req.model_dump(exclude_none=True).items():
        if key in element_level_props:
            target_element[key] = value
        else:
            style[key] = value

    rendered = WholePostRenderer().render(_ensure_structure_has_content(structure))
    template.structure_json = structure
    template.json_data = json.dumps(structure)
    template.preview_html = rendered.html
    template.preview_css = rendered.css
    db.add(template)
    db.commit()
    db.refresh(template)

    return {
        "template_id": template.id,
        "element": target_element,
        "preview_html": rendered.html,
        "preview_css": rendered.css,
        "structure_json": structure,
    }


@app.get("/templates/{template_id}/editor", response_class=HTMLResponse)
async def template_editor(template_id: str, db: Session = Depends(get_db)):
    template = _get_template_or_404(db, template_id)
    structure = template.structure_json or json.loads(template.json_data)
    return HTMLResponse(_build_template_editor_html(template, structure))


def _generate_from_whole_post_template(
    req: GenerateRequest,
    db: Session,
    templates: list[Any],
):
    search_service = TemplateSearchService()
    search_results = search_service.search(
        templates=templates,
        input_tags=req.tags or [],
        prompt=req.prompt,
    )

    if not search_results:
        raise HTTPException(status_code=404, detail="No suitable template found")

    selected = search_results[0]
    structure = selected.template.structure_json or json.loads(selected.template.json_data)

    copy_service = CopyGenerationService()
    generated_slots = copy_service.generate_slot_values(
        structure=structure,
        prompt=req.prompt,
        input_tags=req.tags or [],
    )
    filled_structure = copy_service.fill_structure(structure, generated_slots)
    rendered = WholePostRenderer().render(filled_structure)

    generation_id = str(uuid.uuid4())
    generation = Generation(
        id=generation_id,
        input_tags=req.tags or [],
        input_prompt=req.prompt,
        selected_template_id=selected.template.id,
        candidate_template_ids=[result.template.id for result in search_results],
        matched_tag_reasons={
            result.template.id: result.matched_tags for result in search_results
        },
        filled_structure_json=filled_structure,
        output_html=rendered.html,
        output_css=rendered.css,
    )
    db.add(generation)
    db.commit()

    exporter = HtmlExporter(output_dir="./sample")
    exported_path = exporter.export(
        html=rendered.html,
        css=rendered.css,
        generation_id=generation_id,
    )

    return {
        "generation_id": generation_id,
        "template_id": selected.template.id,
        "matched_tags": selected.matched_tags,
        "filled_structure": filled_structure,
        "output_html": rendered.html,
        "output_css": rendered.css,
        "exported_file": exported_path,
    }
def _parse_tags_form(raw_tags: str | None) -> list[str]:
    if raw_tags is None:
        return []

    raw_tags = raw_tags.strip()
    if not raw_tags:
        return []

    try:
        value = json.loads(raw_tags)
        if isinstance(value, list):
            return [tag.strip() for tag in value if isinstance(tag, str) and tag.strip()]
    except json.JSONDecodeError:
        pass

    return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]


def _generate_auto_tags(atmosphere: str, structure: dict[str, Any]) -> list[str]:
    tags = []
    for token in atmosphere.split():
        cleaned = token.strip()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
        if len(tags) >= 3:
            break

    if not tags and structure.get("elements"):
        tags.append("layout")

    return tags


def _build_search_text(
    manual_tags: list[str],
    auto_tags: list[str],
    atmosphere: str,
    structure: dict[str, Any],
) -> str:
    roles = [
        element.get("role", "")
        for element in structure.get("elements", [])
        if element.get("role")
    ]
    tokens = manual_tags + auto_tags + roles
    if atmosphere:
        tokens.append(atmosphere)
    return " ".join(token for token in tokens if token)


def _build_vector_metadata(
    atmosphere: str,
    manual_tags: list[str],
    auto_tags: list[str],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if atmosphere:
        metadata["atmosphere"] = atmosphere
    if manual_tags:
        metadata["manual_tags"] = manual_tags
    if auto_tags:
        metadata["auto_tags"] = auto_tags
    return metadata


def _ensure_structure_has_content(structure: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(structure))
    for element in normalized.get("elements", []):
        if element.get("type") == "text" and "content" not in element:
            element["content"] = ""
    return normalized


def _template_columns(db: Session) -> set[str]:
    try:
        return {column["name"] for column in inspect(db.get_bind()).get_columns("templates")}
    except Exception:
        return set()


def _supports_whole_post_schema(db: Session) -> bool:
    columns = _template_columns(db)
    required = {"name", "manual_tags_json", "auto_tags_json", "structure_json"}
    return required.issubset(columns)


def _persist_template(db: Session, template_payload: dict[str, Any]) -> None:
    if _supports_whole_post_schema(db):
        db_item = Template(**template_payload)
        db.add(db_item)
        db.commit()
        return

    db.execute(
        text(
            "INSERT INTO templates (id, json_data, vector_id) "
            "VALUES (:id, :json_data, :vector_id)"
        ),
        {
            "id": template_payload["id"],
            "json_data": template_payload["json_data"],
            "vector_id": template_payload["vector_id"],
        },
    )
    db.commit()


def _get_template_or_404(db: Session, template_id: str) -> Template:
    template = db.query(Template).filter(Template.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


def _build_template_editor_html(template: Template, structure: dict[str, Any]) -> str:
    rendered_html = template.preview_html or ""
    rendered_css = template.preview_css or ""
    state = {
        "id": template.id,
        "name": template.name,
        "manual_tags": template.manual_tags_json or [],
        "auto_tags": template.auto_tags_json or [],
        "structure_json": structure,
        "preview_html": rendered_html,
        "preview_css": rendered_css,
    }
    state_json = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    canvas = structure.get("canvas", {})
    canvas_width = int(canvas.get("width", 1080))
    canvas_height = int(canvas.get("height", 1350))
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Template Editor</title>
  <style>
    :root {{
      --bg: #f3f1ea;
      --panel: #fffdf7;
      --ink: #1f2937;
      --muted: #667085;
      --line: #d7d0c3;
      --accent: #0f6cbd;
      --accent-soft: rgba(15, 108, 189, 0.18);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top left, #fff9ef 0%, #ece6d8 55%, #e6eef6 100%);
      color: var(--ink);
      font-family: 'Helvetica Neue', Arial, sans-serif;
    }}
    .template-editor {{
      display: grid;
      grid-template-columns: minmax(360px, 1fr) 360px;
      min-height: 100vh;
      gap: 20px;
      padding: 20px;
    }}
    .preview-panel, .elements-panel {{
      background: rgba(255,255,255,0.88);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: 0 20px 50px rgba(35, 50, 69, 0.08);
      overflow: hidden;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(238,242,247,0.85));
    }}
    .panel-title {{
      font-size: 20px;
      font-weight: 700;
    }}
    .tag-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }}
    .tag-chip {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: #eef4ff;
      color: #12406b;
      border: 1px solid #c9daf3;
    }}
    .preview-wrap {{
      padding: 20px;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      overflow: auto;
      min-height: calc(100vh - 110px);
    }}
    .preview-viewport {{
      width: min(100%, 760px);
    }}
    .preview-stage-shell {{
      position: relative;
      width: {canvas_width}px;
      height: {canvas_height}px;
      transform-origin: top left;
    }}
    .preview-stage {{
      position: absolute;
      inset: 0;
      overflow: hidden;
      background: white;
    }}
    .overlay-layer {{
      position: absolute;
      inset: 0;
      pointer-events: none;
    }}
    .overlay-box {{
      position: absolute;
      border: 1px solid transparent;
      background: transparent;
      transition: border-color 120ms ease, box-shadow 120ms ease, background-color 120ms ease;
      pointer-events: auto;
      cursor: pointer;
    }}
    .overlay-box.is-hovered {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-soft);
      background: rgba(15, 108, 189, 0.06);
    }}
    .overlay-box.is-selected {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(15, 108, 189, 0.24);
      background: rgba(15, 108, 189, 0.1);
    }}
    .elements-scroll {{
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: calc(100vh - 42px);
    }}
    .inspector {{
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 12px;
    }}
    .inspector-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 10px;
    }}
    .control-label {{
      font-size: 12px;
      color: var(--muted);
      font-weight: 700;
      display: grid;
      gap: 6px;
    }}
    input[type="color"] {{
      width: 100%;
      height: 42px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: white;
      padding: 4px;
    }}
    .action-row {{
      display: flex;
      gap: 10px;
    }}
    button {{
      border: none;
      border-radius: 12px;
      background: var(--accent);
      color: white;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{
      background: #eef4ff;
      color: #12406b;
    }}
    .element-list {{
      overflow: auto;
      padding: 14px;
      display: grid;
      gap: 10px;
    }}
    .element-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: #fffdfa;
      cursor: pointer;
      transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
    }}
    .element-card.is-hovered, .element-card.is-selected {{
      border-color: var(--accent);
      box-shadow: 0 8px 22px rgba(15, 108, 189, 0.12);
      transform: translateY(-1px);
    }}
    .element-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 8px;
    }}
    .meta-pill {{
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid #d5dbe7;
      background: #f8fafc;
      color: #334155;
    }}
    .element-content {{
      font-size: 13px;
      line-height: 1.45;
      color: #111827;
      word-break: break-word;
    }}
    .empty-state {{
      font-size: 13px;
      color: var(--muted);
      padding: 8px 0;
    }}
    @media (max-width: 1080px) {{
      .template-editor {{
        grid-template-columns: 1fr;
      }}
      .preview-wrap {{
        min-height: auto;
      }}
      .elements-scroll {{
        min-height: auto;
      }}
    }}
  </style>
</head>
<body>
  <div class="template-editor">
    <section class="preview-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">Preview</div>
          <div class="tag-row">
            <span class="tag-chip">{template.name or template.id}</span>
            <span class="tag-chip">ID: {template.id}</span>
          </div>
        </div>
      </div>
      <div class="preview-wrap">
        <div class="preview-viewport" id="preview-viewport">
          <div class="preview-stage-shell" id="preview-stage-shell">
            <div class="preview-stage" id="preview-frame"></div>
            <div class="overlay-layer" id="overlay-layer"></div>
          </div>
        </div>
      </div>
    </section>
    <aside class="elements-panel">
      <div class="elements-scroll">
        <div class="inspector">
          <div>
            <div class="panel-title" style="font-size:18px;">Elements</div>
            <div class="tag-row" id="editor-tag-row"></div>
          </div>
          <div id="selection-summary" class="empty-state">要素を選択してください。</div>
          <div class="inspector-grid">
            <label class="control-label">Text
              <input id="color-picker" class="color-picker" type="color" value="#000000">
            </label>
            <label class="control-label">Fill
              <input id="background-picker" type="color" value="#ffffff">
            </label>
            <label class="control-label">Border
              <input id="border-picker" type="color" value="#000000">
            </label>
          </div>
          <div class="action-row">
            <button id="apply-style-button" type="button">色を反映</button>
            <button id="reload-button" class="secondary" type="button">再読込</button>
          </div>
        </div>
        <div class="element-list" id="elements-panel"></div>
      </div>
    </aside>
  </div>
  <script>
    window.__TEMPLATE_EDITOR_STATE__ = {state_json};
  </script>
  <script>
    (() => {{
      const state = window.__TEMPLATE_EDITOR_STATE__;
      let hoveredId = null;
      let selectedId = null;
      const previewStage = document.getElementById('preview-frame');
      const overlayLayer = document.getElementById('overlay-layer');
      const stageShell = document.getElementById('preview-stage-shell');
      const viewport = document.getElementById('preview-viewport');
      const list = document.getElementById('elements-panel');
      const summary = document.getElementById('selection-summary');
      const tagRow = document.getElementById('editor-tag-row');
      const colorPicker = document.getElementById('color-picker');
      const backgroundPicker = document.getElementById('background-picker');
      const borderPicker = document.getElementById('border-picker');
      const applyButton = document.getElementById('apply-style-button');
      const reloadButton = document.getElementById('reload-button');

      function escapeHtml(value) {{
        return String(value ?? '').replace(/[&<>\"']/g, (char) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[char]));
      }}

      function getElements() {{
        return state.structure_json.elements || [];
      }}

      function updateScale() {{
        const canvas = state.structure_json.canvas || {{ width: 1080, height: 1350 }};
        const viewportWidth = Math.min(viewport.clientWidth || canvas.width, canvas.width);
        const scale = viewportWidth / canvas.width;
        stageShell.style.transform = `scale(${{scale}})`;
        viewport.style.height = `${{canvas.height * scale}}px`;
      }}

      function renderPreview() {{
        previewStage.innerHTML = `<style>${{state.preview_css || ''}}</style>${{state.preview_html || ''}}`;
      }}

      function buildMetaPills(element) {{
        const pills = [];
        pills.push(`<span class="meta-pill">${{escapeHtml(element.type)}}</span>`);
        pills.push(`<span class="meta-pill">${{escapeHtml(element.id)}}</span>`);
        if (element.shape_type) pills.push(`<span class="meta-pill">${{escapeHtml(element.shape_type)}}</span>`);
        if (element.layout_intent?.text_flow) pills.push(`<span class="meta-pill">${{escapeHtml(element.layout_intent.text_flow)}}</span>`);
        return pills.join('');
      }}

      function renderElements() {{
        list.innerHTML = getElements().map((element) => `
          <div class="element-card ${{element.id === hoveredId ? 'is-hovered' : ''}} ${{element.id === selectedId ? 'is-selected' : ''}}" data-element-id="${{escapeHtml(element.id)}}">
            <div class="element-meta">${{buildMetaPills(element)}}</div>
            <div class="element-content">${{escapeHtml(element.content || '') || '<span class="empty-state">contentなし</span>'}}</div>
          </div>
        `).join('');
      }}

      function renderOverlays() {{
        const canvas = state.structure_json.canvas || {{ width: 1080, height: 1350 }};
        const coordType = state.structure_json.coordinate_type || 'pixel';

        // percentの場合はpixelに変換
        function toPixel(val, canvasSize) {{
          if (coordType === 'percent') {{
            return (val / 100) * canvasSize;
          }}
          return val;
        }}

        overlayLayer.innerHTML = getElements().map((element) => {{
          const x = toPixel(element.x || 0, canvas.width);
          const y = toPixel(element.y || 0, canvas.height);
          const w = toPixel(element.width || 0, canvas.width);
          const h = toPixel(element.height || 0, canvas.height);
          return `
            <button
              type="button"
              class="overlay-box ${{element.id === hoveredId ? 'is-hovered' : ''}} ${{element.id === selectedId ? 'is-selected' : ''}}"
              data-element-id="${{escapeHtml(element.id)}}"
              style="left:${{x}}px;top:${{y}}px;width:${{Math.max(w, 2)}}px;height:${{Math.max(h, 2)}}px;"
              aria-label="${{escapeHtml(element.id)}}"
            ></button>
          `;
        }}).join('');
      }}

      function syncInspector() {{
        const element = getElements().find((item) => item.id === selectedId);
        tagRow.innerHTML = [...(state.manual_tags || []), ...(state.auto_tags || [])]
          .map((tag) => `<span class="tag-chip">${{escapeHtml(tag)}}</span>`).join('');
        if (!element) {{
          summary.textContent = '要素を選択してください。';
          return;
        }}
        const style = element.style || {{}};
        summary.innerHTML = `
          <strong>${{escapeHtml(element.id)}}</strong><br>
          type: ${{escapeHtml(element.type)}} / x:${{element.x}} y:${{element.y}} w:${{element.width}} h:${{element.height}}
        `;
        colorPicker.value = toColorInput(style.color, '#000000');
        backgroundPicker.value = toColorInput(style.backgroundColor, '#ffffff');
        borderPicker.value = toColorInput(style.borderColor, '#000000');
      }}

      function toColorInput(value, fallback) {{
        if (!value || typeof value !== 'string') return fallback;
        const trimmed = value.trim();
        if (/^#([0-9a-fA-F]{{6}})$/.test(trimmed)) return trimmed;
        return fallback;
      }}

      function bindInteractions() {{
        [...document.querySelectorAll('[data-element-id]')].forEach((node) => {{
          node.addEventListener('mouseenter', () => {{
            hoveredId = node.dataset.elementId;
            renderOverlays();
            renderElements();
          }});
          node.addEventListener('mouseleave', () => {{
            hoveredId = null;
            renderOverlays();
            renderElements();
          }});
          node.addEventListener('click', () => {{
            selectedId = node.dataset.elementId;
            renderOverlays();
            renderElements();
            syncInspector();
            bindInteractions();
          }});
        }});
      }}

      async function reloadTemplate() {{
        const response = await fetch(`/api/templates/${{state.id}}`);
        const payload = await response.json();
        Object.assign(state, payload);
        renderAll();
      }}

      async function applyStyle() {{
        if (!selectedId) return;
        const body = {{
          color: colorPicker.value,
          backgroundColor: backgroundPicker.value,
          borderColor: borderPicker.value,
        }};
        const response = await fetch(`/api/templates/${{state.id}}/elements/${{encodeURIComponent(selectedId)}}/style`, {{
          method: 'PATCH',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(body),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          alert(payload.detail || '更新に失敗しました。');
          return;
        }}
        state.structure_json = payload.structure_json;
        state.preview_html = payload.preview_html;
        state.preview_css = payload.preview_css;
        renderAll();
      }}

      function renderAll() {{
        renderPreview();
        renderElements();
        renderOverlays();
        syncInspector();
        updateScale();
        bindInteractions();
      }}

      window.addEventListener('resize', updateScale);
      reloadButton.addEventListener('click', reloadTemplate);
      applyButton.addEventListener('click', applyStyle);
      renderAll();
    }})();
  </script>
</body>
</html>"""


def _load_whole_post_templates(db: Session) -> list[Template]:
    if not _supports_whole_post_schema(db):
        rows = db.execute(
            text("SELECT id, json_data, vector_id FROM templates")
        ).mappings().all()
        metadata_by_id = _load_vector_metadata_map([row["id"] for row in rows])

        templates: list[LegacyTemplateRecord] = []
        for row in rows:
            structure_json = json.loads(row["json_data"])
            metadata = metadata_by_id.get(row["id"], {})
            manual_tags = _normalize_metadata_tags(metadata.get("manual_tags"))
            auto_tags = _normalize_metadata_tags(metadata.get("auto_tags"))
            atmosphere = metadata.get("atmosphere", "")
            search_text = _build_search_text(
                manual_tags,
                auto_tags,
                atmosphere,
                structure_json,
            )
            templates.append(
                LegacyTemplateRecord(
                    id=row["id"],
                    json_data=row["json_data"],
                    structure_json=structure_json,
                    manual_tags_json=manual_tags,
                    auto_tags_json=auto_tags,
                    search_text=search_text,
                    name=row["id"],
                )
            )
        return templates
    return db.query(Template).all()


def _load_vector_metadata_map(template_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not template_ids:
        return {}

    try:
        result = get_collection().get(ids=template_ids, include=["metadatas"])
    except Exception:
        return {}

    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    return {
        template_id: (metadata or {})
        for template_id, metadata in zip(ids, metadatas)
    }


def _normalize_metadata_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _extract_from_pdf(
    content: bytes, filename: str
) -> tuple[dict[str, Any], str, list[str]]:
    """PDFからテンプレート構造を抽出する

    Args:
        content: PDFファイルのバイナリデータ
        filename: ファイル名

    Returns:
        tuple: (structure_json, atmosphere, auto_tags)
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        analyzer = TemplateAnalyzer()
        result = analyzer.analyze(tmp_path)

        # PDF抽出結果を既存フォーマットに変換
        structure_json = _convert_pdf_result_to_structure(result)
        atmosphere = result.atmosphere
        auto_tags = result.auto_tags

        return structure_json, atmosphere, auto_tags
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_from_pptx(
    content: bytes,
    filename: str,
) -> tuple[dict[str, Any], str, list[str]]:
    """PPTXを抽出し、geometry は deterministic、text の見せ方だけ LLM で補う。"""
    from app.services.pptx_structure_extractor import PPTXStructureExtractor

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        extractor = PPTXStructureExtractor()
        result = extractor.extract(tmp_path)
        structure_json = _convert_pptx_result_to_structure(result.to_dict())
        text_intents, atmosphere, auto_tags = infer_pptx_text_presentation(structure_json)
        final_structure = _apply_text_layout_intents(structure_json, text_intents)
        final_structure = _normalize_reference_header_alignment(final_structure)
        return final_structure, atmosphere, auto_tags
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_from_pptx_with_reference(
    content: bytes,
    filename: str,
    reference_image_content: bytes,
) -> tuple[dict[str, Any], str, list[str]]:
    """互換用ラッパ。現在は参照画像を使わず PPTX 単体抽出を行う。"""
    return _extract_from_pptx(content, filename)


def _convert_pdf_result_to_structure(result) -> dict[str, Any]:
    """PDF解析結果を既存の構造フォーマットに変換

    PDF抽出要素のみを使用し、LLM要素は役割情報として付与する。
    LLM要素で座標が不明なものは追加しない（重複防止）。
    """
    elements = []

    # テキスト要素を変換
    for i, text_elem in enumerate(result.text_elements):
        elem = {
            "id": f"text_{i}",
            "type": "text",
            "x": text_elem.get("x", 0),
            "y": text_elem.get("y", 0),
            "width": text_elem.get("width", 10),
            "height": text_elem.get("height", 5),
            "content": text_elem.get("content", ""),
            "z_index": i,
        }

        # フォント情報を追加（pdfplumber抽出）
        if text_elem.get("font_size"):
            elem["font_size"] = text_elem["font_size"]
        if text_elem.get("font_name"):
            elem["font_name"] = text_elem["font_name"]
        if text_elem.get("color"):
            elem["color"] = text_elem["color"]
        if text_elem.get("is_vertical"):
            elem["is_vertical"] = text_elem["is_vertical"]

        elements.append(elem)

    # LLM解析の役割情報をPDF要素にマージ
    for llm_elem in result.llm_elements:
        llm_content = llm_elem.get("content", "").strip()
        llm_role = llm_elem.get("role")
        if not llm_content or not llm_role:
            continue

        # PDF要素とマッチング（部分一致も考慮）
        best_match = None
        best_score = 0

        for elem in elements:
            pdf_content = elem.get("content", "").strip()
            if not pdf_content:
                continue

            # 完全一致
            if pdf_content == llm_content:
                best_match = elem
                break

            # 部分一致（LLMコンテンツがPDFコンテンツを含む、またはその逆）
            if llm_content in pdf_content or pdf_content in llm_content:
                score = min(len(llm_content), len(pdf_content))
                if score > best_score:
                    best_score = score
                    best_match = elem

        # マッチした場合、役割を付与
        if best_match and "role" not in best_match:
            best_match["role"] = llm_role
            # IDを更新（LLMが提供したIDを使用）
            elem_id = llm_elem.get("id")
            if elem_id:
                best_match["id"] = elem_id

    return {
        "canvas": {
            "width": int(result.canvas.get("width", 1080)),
            "height": int(result.canvas.get("height", 1080)),
            "background": "#FFFFFF",
        },
        "coordinate_type": "percent",  # PDF抽出座標はパーセンテージ
        "elements": elements,
    }


def _convert_pptx_result_to_structure(result: dict[str, Any]) -> dict[str, Any]:
    """PPTX抽出結果を既存の構造フォーマットに変換する。"""
    canvas = result.get("canvas", {})
    width = int(canvas.get("width", 1080))
    height = int(canvas.get("height", 1350))

    elements: list[dict[str, Any]] = []
    z_index = 0

    def to_pixel_x(value: float) -> int:
        return int(round((value / 100) * width))

    def to_pixel_y(value: float) -> int:
        return int(round((value / 100) * height))

    for i, shape in enumerate(result.get("shape_elements", [])):
        style: dict[str, Any] = {}
        if shape.get("fill_color"):
            style["backgroundColor"] = shape["fill_color"]
        if shape.get("stroke_color") and shape.get("stroke_width"):
            style["borderColor"] = shape["stroke_color"]
            style["borderWidth"] = shape["stroke_width"]
        gradient = shape.get("gradient")
        if gradient:
            style["gradient"] = gradient
        if shape.get("fill_image"):
            style["fillImage"] = shape["fill_image"]

        elements.append({
            "id": f"shape_{i}",
            "type": "shape",
            "shape_type": "border" if style.get("borderColor") and not style.get("backgroundColor") and not style.get("fillImage") else shape.get("shape_type", "rect"),
            "x": to_pixel_x(shape.get("x", 0)),
            "y": to_pixel_y(shape.get("y", 0)),
            "width": to_pixel_x(shape.get("width", 0)),
            "height": to_pixel_y(shape.get("height", 0)),
            "z_index": z_index,
            "style": style,
            "path_points": shape.get("path_points"),
            "rotation": shape.get("rotation"),
            "flip_h": shape.get("flip_h", False),
            "flip_v": shape.get("flip_v", False),
        })
        z_index += 1

    for i, image in enumerate(result.get("image_elements", [])):
        elements.append({
            "id": f"image_{i}",
            "type": "image",
            "x": to_pixel_x(image.get("x", 0)),
            "y": to_pixel_y(image.get("y", 0)),
            "width": to_pixel_x(image.get("width", 0)),
            "height": to_pixel_y(image.get("height", 0)),
            "z_index": z_index,
            "content": image.get("format", "image").upper(),
            "src": image.get("src"),
            "crop": image.get("crop"),
            "image_format": image.get("format"),
        })
        z_index += 1

    for i, text in enumerate(result.get("text_elements", [])):
        style = {
            "fontSize": text.get("font_size"),
            "fontWeight": text.get("font_weight"),
            "fontFamily": text.get("font_name"),
            "color": text.get("color"),
            "textAlign": text.get("text_align"),
        }
        style = {key: value for key, value in style.items() if value is not None}

        elements.append({
            "id": f"text_{i}",
            "type": "text",
            "x": to_pixel_x(text.get("x", 0)),
            "y": to_pixel_y(text.get("y", 0)),
            "width": to_pixel_x(text.get("width", 0)),
            "height": to_pixel_y(text.get("height", 0)),
            "content": text.get("content", ""),
            "z_index": z_index,
            "style": style,
            "font_size": text.get("font_size"),
            "font_name": text.get("font_name"),
            "color": text.get("color"),
            "is_vertical": text.get("is_vertical", False),
            "rotation": text.get("rotation"),
        })
        z_index += 1

    return {
        "canvas": {
            "width": width,
            "height": height,
            "background": "#FFFFFF",
        },
        "coordinate_type": "pixel",
        "elements": elements,
    }


def _merge_corrected_structure(
    base_structure: dict[str, Any],
    corrected_structure: dict[str, Any],
) -> dict[str, Any]:
    """LLM補正結果を安全にベース構造へマージする。"""
    merged = json.loads(json.dumps(base_structure))

    merged_canvas = merged.setdefault("canvas", {})
    for key, value in corrected_structure.get("canvas", {}).items():
        if value is not None:
            if key in {"width", "height"}:
                if _should_accept_canvas_override(merged_canvas.get(key), value):
                    merged_canvas[key] = value
                continue
            merged_canvas[key] = value

    merged["coordinate_type"] = corrected_structure.get("coordinate_type", merged.get("coordinate_type", "pixel"))

    base_elements = {element.get("id"): element for element in merged.get("elements", []) if element.get("id")}
    corrected_elements = corrected_structure.get("elements", [])
    corrected_ids = set()

    for corrected in corrected_elements:
        element_id = corrected.get("id")
        if not element_id:
            continue
        corrected_ids.add(element_id)
        if element_id in base_elements:
            sanitized = _sanitize_corrected_element(
                base_elements[element_id],
                corrected,
                merged_canvas,
            )
            base_elements[element_id] = _deep_merge_dict(base_elements[element_id], sanitized)
        else:
            base_elements[element_id] = corrected

    ordered_elements: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for element in merged.get("elements", []):
        element_id = element.get("id")
        if not element_id:
            ordered_elements.append(element)
            continue
        ordered_elements.append(base_elements[element_id])
        seen_ids.add(element_id)

    for corrected in corrected_elements:
        element_id = corrected.get("id")
        if element_id and element_id not in seen_ids:
            ordered_elements.append(base_elements[element_id])
            seen_ids.add(element_id)

    merged["elements"] = ordered_elements
    return merged


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """辞書を再帰的にマージする。"""
    merged = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


def _should_accept_canvas_override(base_value: Any, corrected_value: Any) -> bool:
    """キャンバスサイズの上書きを許容するか判定する。"""
    if not isinstance(base_value, (int, float)) or not isinstance(corrected_value, (int, float)):
        return False
    return abs(base_value - corrected_value) <= 4


def _sanitize_corrected_element(
    base_element: dict[str, Any],
    corrected_element: dict[str, Any],
    canvas: dict[str, Any],
) -> dict[str, Any]:
    """破壊的な補正を除外して要素差分を返す。"""
    sanitized: dict[str, Any] = {
        "id": corrected_element.get("id", base_element.get("id")),
        "type": corrected_element.get("type", base_element.get("type")),
    }

    if corrected_element.get("type") != base_element.get("type"):
        return sanitized

    for key, value in corrected_element.items():
        if key in {"id", "type"}:
            continue

        if key in {"x", "y", "width", "height"}:
            if _should_accept_geometry_override(
                base_element=base_element,
                key=key,
                corrected_value=value,
                canvas=canvas,
            ):
                sanitized[key] = value
            continue

        if key == "shape_type":
            if _should_accept_shape_type_override(base_element.get("shape_type"), value):
                sanitized[key] = value
            continue

        if key == "style" and isinstance(value, dict):
            filtered_style = _sanitize_corrected_style(base_element, value)
            if filtered_style:
                sanitized["style"] = filtered_style
            continue

        if key == "content":
            if not base_element.get("content") and value:
                sanitized[key] = value
            continue

        if key == "rotation":
            base_rotation = base_element.get("rotation")
            if base_element.get("type") == "text" and base_rotation in {-90, -90.0, 90, 90.0}:
                if value not in {base_rotation, None}:
                    continue
            sanitized[key] = value
            continue

        sanitized[key] = value

    return sanitized


def _should_accept_geometry_override(
    base_element: dict[str, Any],
    key: str,
    corrected_value: Any,
    canvas: dict[str, Any],
) -> bool:
    """座標・サイズ変更を許容するか判定する。"""
    if not isinstance(corrected_value, (int, float)):
        return False

    base_value = base_element.get(key)
    if not isinstance(base_value, (int, float)):
        return True

    if key in {"width", "height"} and corrected_value <= 0:
        return False

    if key in {"x", "width"}:
        canvas_size = canvas.get("width", 1080)
    else:
        canvas_size = canvas.get("height", 1350)

    base_size = abs(base_value) if abs(base_value) > 0 else canvas_size

    if key in {"x", "y"}:
        allowed_delta = max(24, int(canvas_size * 0.02))
    else:
        if base_element.get("type") == "text":
            allowed_delta = max(18, int(base_size * 0.02))
        else:
            allowed_delta = max(32, int(base_size * 0.15), int(canvas_size * 0.03))

    return abs(base_value - corrected_value) <= allowed_delta


def _should_accept_shape_type_override(base_shape_type: Any, corrected_shape_type: Any) -> bool:
    """shape_type変更を許容するか判定する。"""
    if corrected_shape_type is None:
        return False
    if base_shape_type is None:
        return True
    if base_shape_type == corrected_shape_type:
        return True
    if base_shape_type in {"freeform", "border"}:
        return False
    return corrected_shape_type == base_shape_type


def _sanitize_corrected_style(base_element: dict[str, Any], corrected_style: dict[str, Any]) -> dict[str, Any]:
    """要素種別ごとに安全なstyle差分だけを残す。"""
    element_type = base_element.get("type")

    if element_type == "text":
        allowed_keys = {
            "fontSize",
            "fontWeight",
            "fontFamily",
            "color",
            "textAlign",
            "lineHeight",
            "font_size",
            "font_weight",
            "font_family",
            "text_align",
            "line_height",
        }
        if base_element.get("is_vertical") or base_element.get("rotation") is not None:
            allowed_keys.discard("textAlign")
            allowed_keys.discard("text_align")
        return {
            key: value
            for key, value in corrected_style.items()
            if key in allowed_keys and value is not None
        }

    return {}


def _merge_text_grounding(
    base_structure: dict[str, Any],
    grounded_structure: dict[str, Any],
) -> dict[str, Any]:
    """text 要素専用の OCR 補正結果を安全に適用する。"""
    merged = json.loads(json.dumps(base_structure))
    grounded_by_id = {
        element.get("id"): element
        for element in grounded_structure.get("elements", [])
        if element.get("id") and element.get("type") == "text"
    }

    if not grounded_by_id:
        return merged

    canvas = merged.get("canvas", {})
    canvas_width = int(canvas.get("width", 1080))
    canvas_height = int(canvas.get("height", 1350))

    for element in merged.get("elements", []):
        if element.get("type") != "text":
            continue

        grounded = grounded_by_id.get(element.get("id"))
        if not grounded:
            continue

        if _normalize_text_content(element.get("content")) != _normalize_text_content(grounded.get("content", element.get("content"))):
            continue

        x = grounded.get("x")
        y = grounded.get("y")
        width = grounded.get("width")
        height = grounded.get("height")
        if not all(isinstance(value, int) for value in [x, y, width, height]):
            continue
        if width <= 0 or height <= 0:
            continue
        if x < 0 or y < 0 or x >= canvas_width or y >= canvas_height:
            continue

        element["x"] = x
        element["y"] = y
        element["width"] = min(width, canvas_width - x)
        element["height"] = min(height, canvas_height - y)

        if grounded.get("rotation") is not None:
            element["rotation"] = grounded["rotation"]
        if "is_vertical" in grounded:
            element["is_vertical"] = grounded["is_vertical"]

    return merged


def _apply_text_layout_intents(
    base_structure: dict[str, Any],
    text_intent_patch: dict[str, Any],
) -> dict[str, Any]:
    """LLM が返した text の見せ方だけを既存 geometry に重ねる。"""
    merged = json.loads(json.dumps(base_structure))
    intents_by_id = {
        str(element.get("id")): _sanitize_text_layout_intent(element.get("layout_intent") or {})
        for element in text_intent_patch.get("elements", [])
        if element.get("type") == "text" and element.get("id")
    }
    if not intents_by_id:
        return merged

    existing_ids = {str(element.get("id")) for element in merged.get("elements", []) if element.get("id")}
    new_elements: list[dict[str, Any]] = []

    for element in merged.get("elements", []):
        if element.get("type") != "text":
            new_elements.append(element)
            continue

        layout_intent = intents_by_id.get(str(element.get("id")))
        if not layout_intent:
            new_elements.append(element)
            continue

        element["layout_intent"] = layout_intent
        style = element.setdefault("style", {})

        text_flow = layout_intent.get("text_flow")
        if text_flow in {"rotated_ccw_90", "stacked_ascii"}:
            element["rotation"] = -90.0
            element["is_vertical"] = False
            style.setdefault("textAlign", "center")
        elif text_flow == "vertical":
            element["rotation"] = None
            element["is_vertical"] = True
        elif text_flow == "horizontal":
            if element.get("rotation") in {-90, -90.0, 90, 90.0}:
                element["rotation"] = None
            element["is_vertical"] = False

        if layout_intent.get("text_align") in {"left", "center", "right"}:
            style["textAlign"] = layout_intent["text_align"]

        _apply_text_background_hint(new_elements, element, existing_ids, layout_intent)
        new_elements.append(element)

    for index, element in enumerate(new_elements):
        element["z_index"] = index
    merged["elements"] = new_elements
    return merged


def _sanitize_text_layout_intent(layout_intent: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    if not isinstance(layout_intent, dict):
        return sanitized
    if layout_intent.get("text_flow") in {"horizontal", "vertical", "rotated_ccw_90", "stacked_ascii"}:
        sanitized["text_flow"] = layout_intent["text_flow"]
    if layout_intent.get("text_align") in {"left", "center", "right"}:
        sanitized["text_align"] = layout_intent["text_align"]
    if layout_intent.get("background_hint") in {"none", "solid_rect", "border_rect"}:
        sanitized["background_hint"] = layout_intent["background_hint"]
    if layout_intent.get("emphasis_role") in {"headline", "label", "note", "quote", "name", "department", "index"}:
        sanitized["emphasis_role"] = layout_intent["emphasis_role"]
    for key in ("background_color", "border_color"):
        value = layout_intent.get(key)
        if isinstance(value, str) and value:
            sanitized[key] = value
    border_width = layout_intent.get("border_width")
    if isinstance(border_width, (int, float)) and border_width > 0:
        sanitized["border_width"] = float(border_width)
    return sanitized


def _apply_text_background_hint(
    existing_elements: list[dict[str, Any]],
    text_element: dict[str, Any],
    existing_ids: set[str],
    layout_intent: dict[str, Any],
) -> None:
    hint = layout_intent.get("background_hint")
    if hint not in {"solid_rect", "border_rect"}:
        return

    overlapping_shape = _find_overlapping_shape_for_text(existing_elements, text_element)
    if overlapping_shape:
        style = overlapping_shape.setdefault("style", {})
        if hint == "solid_rect":
            style["backgroundColor"] = layout_intent.get("background_color") or _default_text_background_color(text_element)
        else:
            overlapping_shape["shape_type"] = "border"
            style["backgroundColor"] = layout_intent.get("background_color") or _default_border_background_color(text_element)
            style["borderColor"] = layout_intent.get("border_color") or _default_border_color(text_element)
            style["borderWidth"] = float(layout_intent.get("border_width") or style.get("borderWidth") or 1.0)
        return

    shape_id = f"shape_bg_{text_element.get('id')}"
    if shape_id in existing_ids:
        return

    style: dict[str, Any]
    shape_type: str
    if hint == "solid_rect":
        shape_type = "rect"
        style = {"backgroundColor": layout_intent.get("background_color") or _default_text_background_color(text_element)}
    else:
        shape_type = "border"
        style = {
            "backgroundColor": layout_intent.get("background_color") or _default_border_background_color(text_element),
            "borderColor": layout_intent.get("border_color") or _default_border_color(text_element),
            "borderWidth": float(layout_intent.get("border_width") or 1.0),
        }

    existing_elements.append(
        {
            "id": shape_id,
            "type": "shape",
            "shape_type": shape_type,
            "x": int(text_element.get("x", 0)),
            "y": int(text_element.get("y", 0)),
            "width": int(text_element.get("width", 0)),
            "height": int(text_element.get("height", 0)),
            "style": style,
        }
    )
    existing_ids.add(shape_id)


def _default_text_background_color(text_element: dict[str, Any]) -> str:
    return "#FFFFFF" if _is_dark_text_element(text_element) else "rgba(32, 32, 32, 0.38)"


def _default_border_background_color(text_element: dict[str, Any]) -> str:
    return "rgba(32, 32, 32, 0.38)" if _is_bright_text_element(text_element) else "#FFFFFF"


def _default_border_color(text_element: dict[str, Any]) -> str:
    return "#FFFFFF" if _is_bright_text_element(text_element) else "#373737"


def _augment_text_background_shapes(
    structure: dict[str, Any],
    reference_image_content: bytes,
) -> dict[str, Any]:
    """参照PNGから、text背後の背景矩形を補完する。"""
    augmented = json.loads(json.dumps(structure))
    try:
        reference = Image.open(io.BytesIO(reference_image_content)).convert("RGB")
    except Exception:
        return augmented

    elements = augmented.get("elements", [])
    if not elements:
        return augmented

    existing_ids = {str(element.get("id")) for element in elements if element.get("id")}
    new_elements: list[dict[str, Any]] = []

    for element in elements:
        if element.get("type") != "text":
            new_elements.append(element)
            continue

        linked_shape = _find_overlapping_shape_for_text(new_elements, element)
        if linked_shape and linked_shape.get("shape_type") == "border":
            style = linked_shape.setdefault("style", {})
            if not style.get("backgroundColor") and _is_bright_text_element(element):
                style["backgroundColor"] = "rgba(32, 32, 32, 0.38)"

        if _is_dark_text_element(element) and not linked_shape:
            rect = _detect_light_background_rect(reference, element)
            if rect is not None:
                bg_id = f"shape_bg_{element.get('id')}"
                if bg_id not in existing_ids:
                    new_elements.append(
                        {
                            "id": bg_id,
                            "type": "shape",
                            "shape_type": "rect",
                            "x": rect["x"],
                            "y": rect["y"],
                            "width": rect["width"],
                            "height": rect["height"],
                            "style": {"backgroundColor": "#FFFFFF"},
                        }
                    )
                    existing_ids.add(bg_id)
                _fit_text_element_to_background_rect(element, rect)

        new_elements.append(element)

    for index, element in enumerate(new_elements):
        element["z_index"] = index

    augmented["elements"] = new_elements
    return augmented


def _find_overlapping_shape_for_text(
    elements: list[dict[str, Any]],
    text_element: dict[str, Any],
) -> dict[str, Any] | None:
    text_x = int(text_element.get("x", 0))
    text_y = int(text_element.get("y", 0))
    text_w = int(text_element.get("width", 0))
    text_h = int(text_element.get("height", 0))

    for element in reversed(elements):
        if element.get("type") != "shape":
            continue
        style = element.get("style") or {}
        shape_type = str(element.get("shape_type") or "")
        if shape_type == "freeform" or style.get("fillImage"):
            continue
        x = int(element.get("x", 0))
        y = int(element.get("y", 0))
        width = int(element.get("width", 0))
        height = int(element.get("height", 0))
        if width <= 0 or height <= 0:
            continue
        if width * height > max(1, text_w * text_h) * 8 and shape_type != "border":
            continue
        if (
            x <= text_x + 4
            and y <= text_y + 4
            and x + width >= text_x + text_w - 4
            and y + height >= text_y + text_h - 4
        ):
            return element
    return None


def _is_bright_text_element(element: dict[str, Any]) -> bool:
    color = str((element.get("style") or {}).get("color") or element.get("color") or "#000000")
    return _hex_luma(color) >= 180


def _is_dark_text_element(element: dict[str, Any]) -> bool:
    if element.get("rotation") is not None or element.get("is_vertical"):
        return False
    color = str((element.get("style") or {}).get("color") or element.get("color") or "#000000")
    return _hex_luma(color) <= 140


def _hex_luma(color: str) -> int:
    hex_color = str(color).lstrip("#")
    if len(hex_color) != 6:
        return 0
    try:
        red = int(hex_color[0:2], 16)
        green = int(hex_color[2:4], 16)
        blue = int(hex_color[4:6], 16)
    except ValueError:
        return 0
    return int((red * 299 + green * 587 + blue * 114) / 1000)


def _detect_light_background_rect(
    reference_image: Image.Image,
    text_element: dict[str, Any],
) -> dict[str, int] | None:
    text_x = int(text_element.get("x", 0))
    text_y = int(text_element.get("y", 0))
    text_w = int(text_element.get("width", 0))
    text_h = int(text_element.get("height", 0))
    if text_w <= 0 or text_h <= 0:
        return None

    crop_margin_x = max(18, int(text_w * 0.45))
    crop_margin_y = max(12, int(text_h * 0.9))
    left = max(0, text_x - crop_margin_x)
    top = max(0, text_y - crop_margin_y)
    right = min(reference_image.width, text_x + text_w + crop_margin_x)
    bottom = min(reference_image.height, text_y + text_h + crop_margin_y)
    if right - left <= 0 or bottom - top <= 0:
        return None

    gray_image = reference_image.crop((left, top, right, bottom)).convert("L")

    local_target = (
        text_x - left,
        text_y - top,
        text_x - left + text_w - 1,
        text_y - top + text_h - 1,
    )

    for threshold in (230, 225, 220, 215, 210, 205):
        rect = _find_light_component_rect(gray_image, local_target, threshold)
        if rect is None:
            continue
        rect_x, rect_y, rect_w, rect_h = rect
        return {
            "x": left + rect_x,
            "y": top + rect_y,
            "width": rect_w,
            "height": rect_h,
        }

    return None


def _find_light_component_rect(
    gray_image: Image.Image,
    local_target: tuple[int, int, int, int],
    threshold: int,
) -> tuple[int, int, int, int] | None:
    width, height = gray_image.size
    if width <= 0 or height <= 0:
        return None

    px = gray_image.load()
    visited = [[False] * width for _ in range(height)]
    target_left, target_top, target_right, target_bottom = local_target
    target_width = max(1, target_right - target_left + 1)
    target_height = max(1, target_bottom - target_top + 1)
    target_area = target_width * target_height
    target_cx = (target_left + target_right) / 2.0
    target_cy = (target_top + target_bottom) / 2.0

    best_rect: tuple[int, int, int, int] | None = None
    best_score = -1.0

    for y in range(height):
        for x in range(width):
            if visited[y][x] or px[x, y] < threshold:
                continue

            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            area = 0

            while queue:
                cx, cy = queue.popleft()
                area += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)

                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    if visited[ny][nx] or px[nx, ny] < threshold:
                        continue
                    visited[ny][nx] = True
                    queue.append((nx, ny))

            rect_width = max_x - min_x + 1
            rect_height = max_y - min_y + 1
            if rect_width < int(target_width * 0.65) or rect_height < int(target_height * 0.5):
                continue
            if rect_width > int(target_width * 2.4) or rect_height > int(target_height * 2.4):
                continue

            overlap_width = max(0, min(max_x, target_right) - max(min_x, target_left) + 1)
            overlap_height = max(0, min(max_y, target_bottom) - max(min_y, target_top) + 1)
            overlap_area = overlap_width * overlap_height
            surrounds = (
                min_x <= target_left
                and min_y <= target_top
                and max_x >= target_right
                and max_y >= target_bottom
            )
            cover_ratio = overlap_area / target_area
            if not surrounds and cover_ratio < 0.18:
                continue

            center_distance = abs(((min_x + max_x) / 2.0) - target_cx) + abs(((min_y + max_y) / 2.0) - target_cy)
            score = cover_ratio * 1000.0
            if surrounds:
                score += 500.0
            score += min(area, rect_width * rect_height) * 0.01
            score -= center_distance * 1.5

            if score > best_score:
                best_score = score
                best_rect = (min_x, min_y, rect_width, rect_height)

    return best_rect


def _fit_text_element_to_background_rect(
    element: dict[str, Any],
    rect: dict[str, int],
) -> None:
    font_size = float(
        (element.get("style") or {}).get("fontSize")
        or element.get("font_size")
        or 16
    )
    padding_x = max(10, int(round(font_size * 0.35)))
    padding_y = max(4, int(round(font_size * 0.18)))
    box_width = max(12, rect["width"] - (padding_x * 2))
    box_height = max(int(round(font_size * 1.15)), rect["height"] - (padding_y * 2))

    element["x"] = rect["x"] + padding_x
    element["width"] = box_width
    element["height"] = min(rect["height"], box_height)
    element["y"] = rect["y"] + max(0, (rect["height"] - element["height"]) // 2)


def _normalize_reference_header_alignment(
    structure: dict[str, Any],
) -> dict[str, Any]:
    normalized = json.loads(json.dumps(structure))
    canvas = normalized.get("canvas", {})
    canvas_width = int(canvas.get("width", 1080))
    canvas_height = int(canvas.get("height", 1350))

    for element in normalized.get("elements", []):
        if element.get("type") != "text":
            continue
        if element.get("rotation") is not None or element.get("is_vertical"):
            continue
        if not _is_bright_text_element(element):
            continue

        x = int(element.get("x", 0))
        y = int(element.get("y", 0))
        width = int(element.get("width", 0))
        height = int(element.get("height", 0))
        if x > int(canvas_width * 0.08):
            continue
        if y > int(canvas_height * 0.14):
            continue
        if width < 160 or width > int(canvas_width * 0.38):
            continue
        if height > 64:
            continue
        if "\n" in str(element.get("content") or ""):
            continue

        style = element.setdefault("style", {})
        style["textAlign"] = "center"

    return normalized


def _normalize_text_content(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(value.split())


def _filter_images_by_reference(
    structure: dict[str, Any],
    reference_image_content: bytes,
    threshold: float = 50.0,
) -> dict[str, Any]:
    """参照PNGと一致しない画像要素を除外する。"""
    filtered = json.loads(json.dumps(structure))
    elements = filtered.get("elements", [])
    if not elements:
        return filtered

    try:
        reference = Image.open(io.BytesIO(reference_image_content)).convert("RGB")
    except Exception:
        return filtered

    kept_elements: list[dict[str, Any]] = []
    for element in elements:
        if element.get("type") != "image" or not element.get("src"):
            kept_elements.append(element)
            continue

        diff_score = _calculate_image_difference(element, reference)
        if diff_score is None or diff_score <= threshold:
            kept_elements.append(element)

    filtered["elements"] = kept_elements
    return filtered


def _calculate_image_difference(element: dict[str, Any], reference_image: Image.Image) -> float | None:
    """画像要素と参照PNG領域の平均差分を返す。"""
    src = element.get("src")
    if not isinstance(src, str) or "," not in src:
        return None

    try:
        _, encoded = src.split(",", 1)
        image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
    except Exception:
        return None

    crop = element.get("crop") or {}
    left = max(0.0, min(1.0, float(crop.get("left", 0.0))))
    right = max(0.0, min(1.0, float(crop.get("right", 0.0))))
    top = max(0.0, min(1.0, float(crop.get("top", 0.0))))
    bottom = max(0.0, min(1.0, float(crop.get("bottom", 0.0))))

    width, height = image.size
    crop_box = (
        int(width * left),
        int(height * top),
        max(int(width * left) + 1, int(width * (1 - right))),
        max(int(height * top) + 1, int(height * (1 - bottom))),
    )
    image = image.crop(crop_box)

    rendered_width = max(1, int(element.get("width", 0)))
    rendered_height = max(1, int(element.get("height", 0)))
    image = image.resize((rendered_width, rendered_height), Image.Resampling.LANCZOS)

    x = max(0, int(element.get("x", 0)))
    y = max(0, int(element.get("y", 0)))
    reference_region = reference_image.crop((x, y, x + rendered_width, y + rendered_height))
    if reference_region.size != (rendered_width, rendered_height):
        reference_region = reference_region.resize((rendered_width, rendered_height), Image.Resampling.LANCZOS)

    diff = ImageChops.difference(image, reference_region)
    mean = ImageStat.Stat(diff).mean
    return sum(mean) / len(mean)
