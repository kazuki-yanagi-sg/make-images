"use client";

import { CSSProperties, ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState, useTransition } from "react";

import {
  applyStylePatchToStructure,
  buildTemplateOptionLabel,
  buildCanvasBackground,
  buildCroppedImageStyle,
  buildFrameStylePx,
  buildGradientCss,
  generateHtmlFromStructure,
  getStyleValue,
  normalizeColorInput,
  sortElementsByZIndex,
  TemplateDetail,
  TemplateElement,
  TemplateStructure,
  TemplateSummary,
  toElementTableRow,
} from "./template-editor-model";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const DEFAULT_TEXT_COLOR = "#111111";
const DEFAULT_BORDER_COLOR = "#d6d3d1";
const MAX_HISTORY_SIZE = 50;

type TemplatePreviewWorkbenchProps = {
  initialTemplateSummaries?: TemplateSummary[];
  initialTemplate?: TemplateDetail | null;
};

export function TemplatePreviewWorkbench({
  initialTemplateSummaries = [],
  initialTemplate = null,
}: TemplatePreviewWorkbenchProps) {
  const [templateSummaries, setTemplateSummaries] = useState<TemplateSummary[]>(initialTemplateSummaries);
  const [selectedTemplateId, setSelectedTemplateId] = useState(initialTemplate?.id ?? initialTemplateSummaries[0]?.id ?? "");
  const [template, setTemplate] = useState<TemplateDetail | null>(initialTemplate);
  const [selectedElementId, setSelectedElementId] = useState<string | null>(null);
  const [hoveredElementId, setHoveredElementId] = useState<string | null>(null);
  const [textColor, setTextColor] = useState(DEFAULT_TEXT_COLOR);
  const [backgroundColor, setBackgroundColor] = useState<string | null>(null);
  const [bgEnabled, setBgEnabled] = useState(false); // 背景色を有効にするか
  const [borderColor, setBorderColor] = useState<string | null>(null);
  const [rotation, setRotation] = useState<number>(0);
  const [isVertical, setIsVertical] = useState<boolean>(false);
  const [positionX, setPositionX] = useState<number>(0);
  const [positionY, setPositionY] = useState<number>(0);
  const [elementWidth, setElementWidth] = useState<number>(100);
  const [elementHeight, setElementHeight] = useState<number>(100);
  const [content, setContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(initialTemplateSummaries.length === 0);
  const [isPending, startTransition] = useTransition();

  // テンプレート登録用の状態
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  // DB保存用の状態
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // Undo履歴（元のstructure_jsonを保存）
  const [history, setHistory] = useState<TemplateStructure[]>([]);
  const [originalStructure, setOriginalStructure] = useState<TemplateStructure | null>(null);
  const isDraggingRef = useRef(false);
  const isLoadingSelectionRef = useRef(false); // 選択変更時の初期ロード中フラグ

  const canvas = template?.structure_json.canvas ?? { width: 1080, height: 1350 };
  const elements = template?.structure_json.elements ?? [];
  const selectedElement =
    elements.find((element) => element.id === selectedElementId) ?? elements[0] ?? null;

  useEffect(() => {
    if (initialTemplateSummaries.length) {
      setIsBootstrapping(false);
      return;
    }

    startTransition(async () => {
      try {
        setIsBootstrapping(true);
        const summaries = await fetchTemplateSummaries();
        setTemplateSummaries(summaries);
        if (!summaries.length) {
          setIsBootstrapping(false);
          return;
        }

        const initialTemplateId = summaries[0].id;
        setSelectedTemplateId(initialTemplateId);
        const payload = await fetchTemplate(initialTemplateId);
        setTemplate(payload);
        setOriginalStructure(payload.structure_json);
        setHistory([]);
        setIsBootstrapping(false);
      } catch (loadError) {
        setIsBootstrapping(false);
        setError(loadError instanceof Error ? loadError.message : "テンプレート一覧の取得に失敗しました。");
      }
    });
  }, []);

  useEffect(() => {
    if (!elements.length) {
      setSelectedElementId(null);
      return;
    }

    if (!selectedElementId || !elements.some((element) => element.id === selectedElementId)) {
      setSelectedElementId(elements[0].id);
    }
  }, [elements, selectedElementId]);

  // 選択要素が変わったときに、その要素のスタイルを読み込む
  useEffect(() => {
    // 選択変更時の初期ロード開始
    isLoadingSelectionRef.current = true;

    if (!selectedElement) {
      setTextColor(DEFAULT_TEXT_COLOR);
      setBackgroundColor(null);
      setBgEnabled(false);
      setBorderColor(null);
      setRotation(0);
      setIsVertical(false);
      setPositionX(0);
      setPositionY(0);
      setElementWidth(100);
      setElementHeight(100);
      setContent("");
      // 次のマイクロタスクでフラグをリセット
      queueMicrotask(() => { isLoadingSelectionRef.current = false; });
      return;
    }

    // 元の要素のスタイルを取得（originalStructureから）
    const origElement = originalStructure?.elements.find(e => e.id === selectedElement.id);
    const origStyle = origElement?.style ?? {};

    setTextColor(normalizeColorInput(asString(selectedElement.style?.color), DEFAULT_TEXT_COLOR));

    // 背景色：元々持っているか、ユーザーが有効化した場合
    const origBgColor = asString(origStyle.backgroundColor);
    const currentBgColor = asString(selectedElement.style?.backgroundColor);
    if (origBgColor || currentBgColor) {
      setBgEnabled(true);
      setBackgroundColor(normalizeColorInput(currentBgColor, origBgColor || "#ffffff"));
    } else {
      setBgEnabled(false);
      setBackgroundColor(null);
    }

    // 枠線色
    const origBorderColor = asString(origStyle.borderColor);
    setBorderColor(origBorderColor ? normalizeColorInput(asString(selectedElement.style?.borderColor), origBorderColor) : null);

    setRotation(selectedElement.rotation ?? 0);
    setIsVertical(selectedElement.is_vertical ?? false);
    setPositionX(selectedElement.x ?? 0);
    setPositionY(selectedElement.y ?? 0);
    setElementWidth(selectedElement.width ?? 100);
    setElementHeight(selectedElement.height ?? 100);
    setContent(selectedElement.content ?? "");

    // 次のマイクロタスクでフラグをリセット（すべてのstate更新後）
    queueMicrotask(() => { isLoadingSelectionRef.current = false; });
  }, [selectedElementId, originalStructure]);

  // スタイル変更時にリアルタイムでプレビューに反映（DBには保存しない）
  const isFirstRender = useRef(true);
  useEffect(() => {
    // 初回レンダリング時は履歴に追加しない
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    if (!template || !selectedElementId) {
      return;
    }

    // 選択変更時の初期ロード中はスキップ
    if (isLoadingSelectionRef.current) {
      return;
    }

    // ドラッグ中は履歴追加とテンプレート更新をスキップ（ドラッグ側で処理）
    if (isDraggingRef.current) {
      return;
    }

    // 履歴に現在の状態を保存（変更前）
    setHistory(prev => {
      const newHistory = [...prev, template.structure_json];
      if (newHistory.length > MAX_HISTORY_SIZE) {
        return newHistory.slice(-MAX_HISTORY_SIZE);
      }
      return newHistory;
    });

    const stylePatch: { color?: string; backgroundColor?: string; borderColor?: string } = {
      color: textColor,
    };
    if (bgEnabled && backgroundColor !== null) {
      stylePatch.backgroundColor = backgroundColor;
    }
    if (borderColor !== null) {
      stylePatch.borderColor = borderColor;
    }

    const updated = {
      ...template,
      structure_json: applyStylePatchToStructure(
        template.structure_json,
        selectedElementId,
        stylePatch,
        { rotation, is_vertical: isVertical, x: positionX, y: positionY, width: elementWidth, height: elementHeight, content },
      ),
    };

    setTemplate(updated);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textColor, backgroundColor, bgEnabled, borderColor, rotation, isVertical, positionX, positionY, elementWidth, elementHeight, content, selectedElementId]);

  // Ctrl+Z でUndo
  const handleUndo = useCallback(() => {
    if (history.length === 0 || !template) {
      return;
    }

    const previousStructure = history[history.length - 1];
    setHistory(prev => prev.slice(0, -1));
    setTemplate({
      ...template,
      structure_json: previousStructure,
    });

    // 選択中の要素のスタイルも更新
    if (selectedElementId) {
      const prevElement = previousStructure.elements.find(e => e.id === selectedElementId);
      if (prevElement) {
        setTextColor(normalizeColorInput(asString(prevElement.style?.color), DEFAULT_TEXT_COLOR));
        if (bgEnabled && backgroundColor !== null) {
          setBackgroundColor(normalizeColorInput(asString(prevElement.style?.backgroundColor), backgroundColor));
        }
        if (borderColor !== null) {
          setBorderColor(normalizeColorInput(asString(prevElement.style?.borderColor), borderColor));
        }
        setRotation(prevElement.rotation ?? 0);
        setIsVertical(prevElement.is_vertical ?? false);
        setPositionX(prevElement.x ?? 0);
        setPositionY(prevElement.y ?? 0);
        setElementWidth(prevElement.width ?? 100);
        setElementHeight(prevElement.height ?? 100);
        setContent(prevElement.content ?? "");
      }
    }
  }, [history, template, selectedElementId, bgEnabled, backgroundColor, borderColor]);

  // キーボードイベントリスナー
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'z') {
        event.preventDefault();
        handleUndo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleUndo]);

  async function fetchTemplateSummaries() {
    const response = await fetch(`${API_BASE_URL}/api/templates`);
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(payload?.detail ?? "テンプレート一覧の取得に失敗しました。");
    }

    return (await response.json()) as TemplateSummary[];
  }

  async function fetchTemplate(templateId: string) {
    const response = await fetch(`${API_BASE_URL}/api/templates/${templateId}`);
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(payload?.detail ?? "テンプレートの取得に失敗しました。");
    }

    return (await response.json()) as TemplateDetail;
  }

  async function handleLoadTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedTemplateId = selectedTemplateId.trim();
    if (!normalizedTemplateId) {
      setError("テンプレートを選択してください。");
      return;
    }

    startTransition(async () => {
      setError(null);
      try {
        const payload = await fetchTemplate(normalizedTemplateId);
        setTemplate(payload);
        setOriginalStructure(payload.structure_json);
        setHistory([]);
      } catch (loadError) {
        setTemplate(null);
        setOriginalStructure(null);
        setError(loadError instanceof Error ? loadError.message : "テンプレートの取得に失敗しました。");
      }
    });
  }

  // テンプレートをアップロード・登録
  async function handleUploadTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!uploadFile) {
      setUploadError("ファイルを選択してください。");
      return;
    }

    if (!uploadTags.trim()) {
      setUploadError("タグを入力してください（カンマ区切り）。");
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      if (uploadName.trim()) {
        formData.append("name", uploadName.trim());
      }
      formData.append("manual_tags", uploadTags.trim());

      const response = await fetch(`${API_BASE_URL}/api/templates`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "テンプレートの登録に失敗しました。");
      }

      const result = await response.json();
      setUploadSuccess(`テンプレートを登録しました (ID: ${result.template_id})`);

      // フォームをリセット
      setUploadFile(null);
      setUploadName("");
      setUploadTags("");

      // 一覧を更新
      const summaries = await fetchTemplateSummaries();
      setTemplateSummaries(summaries);

      // 新しく登録したテンプレートを選択
      if (result.template_id) {
        setSelectedTemplateId(result.template_id);
        const payload = await fetchTemplate(result.template_id);
        setTemplate(payload);
        setOriginalStructure(payload.structure_json);
        setHistory([]);
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "テンプレートの登録に失敗しました。");
    } finally {
      setIsUploading(false);
    }
  }

  // HTMLとしてダウンロード（structure_jsonから直接生成）
  function handleDownloadHtml() {
    if (!template) {
      setError("テンプレートを先に読み込んでください。");
      return;
    }

    // フロントエンドの編集を反映したstructure_jsonからHTMLを生成
    const htmlContent = generateHtmlFromStructure(
      template.structure_json,
      template.name ?? template.id
    );

    const blob = new Blob([htmlContent], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${template.name ?? template.id}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // DBにstructure_jsonを保存
  async function handleSaveToDb() {
    if (!template) {
      setError("テンプレートを先に読み込んでください。");
      return;
    }

    setIsSaving(true);
    setError(null);
    setSaveSuccess(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/templates/${template.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          structure_json: template.structure_json,
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? "保存に失敗しました。");
      }

      const result = await response.json();
      setSaveSuccess("保存しました");

      // 保存後、originalStructureを更新（これで「変更あり」判定が解除される）
      setOriginalStructure(template.structure_json);
      setHistory([]);

      // 3秒後にメッセージをクリア
      setTimeout(() => setSaveSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました。");
    } finally {
      setIsSaving(false);
    }
  }

  function handleSelectElement(element: TemplateElement) {
    setSelectedElementId(element.id);
  }

  function handleDeleteElement() {
    if (!template || !selectedElementId) return;

    const elementToDelete = elements.find(e => e.id === selectedElementId);
    if (!elementToDelete) return;

    const confirmMessage = `要素「${elementToDelete.type}#${elementToDelete.id}」を削除しますか？\n\n内容: ${(elementToDelete.content ?? "").slice(0, 50) || "(なし)"}`;
    if (!confirm(confirmMessage)) return;

    // 履歴に保存
    setHistory(prev => {
      const newHistory = [...prev, template.structure_json];
      return newHistory.length > MAX_HISTORY_SIZE ? newHistory.slice(-MAX_HISTORY_SIZE) : newHistory;
    });

    // 要素を削除
    const newElements = elements.filter(e => e.id !== selectedElementId);
    setTemplate({
      ...template,
      structure_json: {
        ...template.structure_json,
        elements: newElements,
      },
    });

    // 次の要素を選択
    if (newElements.length > 0) {
      setSelectedElementId(newElements[0].id);
    } else {
      setSelectedElementId(null);
    }
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-[linear-gradient(180deg,#ebe6dc_0%,#f5f1e9_45%,#fbfaf7_100%)] text-stone-900">
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8 overflow-hidden px-5 py-8 sm:px-8 xl:px-12">
        <section className="rounded-[2rem] border border-stone-300/70 bg-white/80 p-6 shadow-[0_24px_80px_rgba(60,46,28,0.12)] backdrop-blur md:p-8">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-stone-500">
                Template Editor Frontend
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-stone-900 md:text-5xl">
                保存済み構造JSONを見ながら、要素単位で確認して色を直す画面
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-stone-600 md:text-base">
                DB の保存済みテンプレートをプルダウンから選んで読み込みます。プレビュー上の要素は
                hover で青枠表示、クリックで選択できます。右下のテーブルではタグ名相当の `type#id`
                と style をまとめて確認できます。
              </p>
            </div>
            <div className="rounded-3xl border border-stone-200 bg-stone-950 px-5 py-4 text-stone-50">
              <p className="text-xs uppercase tracking-[0.24em] text-stone-400">API</p>
              <p className="mt-1 text-sm font-medium break-all">{API_BASE_URL}/api/templates/:id</p>
              <p className="mt-1 text-xs text-stone-400">PATCH /elements/:element_id/style で色保存</p>
            </div>
          </div>
        </section>

        <section className="grid gap-8 xl:grid-cols-[380px_minmax(0,1fr)]">
          <aside className="space-y-8">
            <form
              onSubmit={handleLoadTemplate}
              className="rounded-[2rem] border border-stone-300/70 bg-[#171311] p-6 text-stone-50 shadow-[0_30px_80px_rgba(23,17,11,0.28)]"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.26em] text-stone-400">
                Loader
              </p>
              <h2 className="mt-2 text-2xl font-semibold">テンプレートを開く</h2>
              <p className="mt-2 text-sm leading-6 text-stone-300">
                バックエンド DB に記録済みのテンプレートを一覧から選択してください。
              </p>

              <label className="mt-6 block">
                <span className="mb-2 block text-sm font-medium text-stone-200">保存済みテンプレート</span>
                <select
                  value={selectedTemplateId}
                  onChange={(event) => setSelectedTemplateId(event.target.value)}
                  className="w-full rounded-2xl border border-stone-700 bg-stone-900 px-4 py-3 text-sm text-stone-50 outline-none transition focus:border-sky-400"
                >
                  <option value="">テンプレートを選択してください</option>
                  {templateSummaries.map((summary) => (
                    <option key={summary.id} value={summary.id}>
                      {buildTemplateOptionLabel(summary)}
                    </option>
                  ))}
                </select>
              </label>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <button
                  type="submit"
                  disabled={isPending || !selectedTemplateId}
                  className="w-full rounded-full bg-sky-300 px-5 py-3 text-sm font-semibold text-stone-950 transition hover:bg-sky-200 disabled:cursor-not-allowed disabled:bg-stone-600 disabled:text-stone-300"
                >
                  {isPending ? "読み込み中..." : "選択テンプレートを開く"}
                </button>
                <button
                  type="button"
                  disabled={isPending}
                  onClick={() => {
                    startTransition(async () => {
                      try {
                        setError(null);
                        setIsBootstrapping(true);
                        const summaries = await fetchTemplateSummaries();
                        setTemplateSummaries(summaries);
                        setIsBootstrapping(false);
                      } catch (loadError) {
                        setIsBootstrapping(false);
                        setError(
                          loadError instanceof Error
                            ? loadError.message
                            : "テンプレート一覧の取得に失敗しました。",
                        );
                      }
                    });
                  }}
                  className="w-full rounded-full border border-stone-600 px-5 py-3 text-sm font-semibold text-stone-100 transition hover:border-stone-400 hover:bg-white/5 disabled:cursor-not-allowed disabled:border-stone-700 disabled:text-stone-500"
                >
                  一覧を更新
                </button>
              </div>

              <p className="mt-4 text-xs leading-6 text-stone-400">
                {isBootstrapping
                  ? "テンプレート一覧を読み込み中です。"
                  : templateSummaries.length
                  ? `${templateSummaries.length} 件のテンプレートを取得しました。`
                  : "まだ保存済みテンプレートがありません。"}
              </p>

              {error ? (
                <div className="mt-4 rounded-2xl border border-rose-400/40 bg-rose-950/30 px-4 py-3 text-sm text-rose-100">
                  {error}
                </div>
              ) : null}
            </form>

            {/* テンプレート登録フォーム */}
            <form
              onSubmit={handleUploadTemplate}
              className="rounded-[2rem] border border-stone-300/70 bg-[#171311] p-6 text-stone-50 shadow-[0_30px_80px_rgba(23,17,11,0.28)]"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.26em] text-stone-400">
                Register
              </p>
              <h2 className="mt-2 text-2xl font-semibold">テンプレートを登録</h2>
              <p className="mt-2 text-sm leading-6 text-stone-300">
                PowerPoint、PDF、または画像ファイルをアップロードして、構造JSONを抽出しDBに保存します。
              </p>

              <label className="mt-6 block">
                <span className="mb-2 block text-sm font-medium text-stone-200">ファイル</span>
                <input
                  type="file"
                  accept=".pptx,.pdf,.jpg,.jpeg,.png"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                  className="w-full rounded-2xl border border-stone-700 bg-stone-900 px-4 py-3 text-sm text-stone-50 outline-none transition file:mr-4 file:rounded-lg file:border-0 file:bg-sky-600 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-sky-500 focus:border-sky-400"
                />
                {uploadFile && (
                  <p className="mt-2 text-xs text-stone-400">
                    選択中: {uploadFile.name}
                  </p>
                )}
              </label>

              <label className="mt-4 block">
                <span className="mb-2 block text-sm font-medium text-stone-200">名前（任意）</span>
                <input
                  type="text"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                  placeholder="テンプレート名を入力..."
                  className="w-full rounded-2xl border border-stone-700 bg-stone-900 px-4 py-3 text-sm text-stone-50 outline-none transition placeholder:text-stone-500 focus:border-sky-400"
                />
              </label>

              <label className="mt-4 block">
                <span className="mb-2 block text-sm font-medium text-stone-200">タグ（カンマ区切り）</span>
                <input
                  type="text"
                  value={uploadTags}
                  onChange={(e) => setUploadTags(e.target.value)}
                  placeholder="例: interview, business, minimal"
                  className="w-full rounded-2xl border border-stone-700 bg-stone-900 px-4 py-3 text-sm text-stone-50 outline-none transition placeholder:text-stone-500 focus:border-sky-400"
                />
              </label>

              <button
                type="submit"
                disabled={isUploading || !uploadFile || !uploadTags.trim()}
                className="mt-5 w-full rounded-full bg-emerald-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-stone-600 disabled:text-stone-300"
              >
                {isUploading ? "登録中..." : "テンプレートを登録"}
              </button>

              {uploadError && (
                <div className="mt-4 rounded-2xl border border-rose-400/40 bg-rose-950/30 px-4 py-3 text-sm text-rose-100">
                  {uploadError}
                </div>
              )}

              {uploadSuccess && (
                <div className="mt-4 rounded-2xl border border-emerald-400/40 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-100">
                  {uploadSuccess}
                </div>
              )}
            </form>

            <section className="rounded-[2rem] border border-stone-300/70 bg-white/85 p-6 shadow-[0_18px_50px_rgba(60,46,28,0.1)]">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-stone-500">Selection</p>
              <h2 className="mt-2 text-2xl font-semibold text-stone-900">選択中の要素</h2>
              {selectedElement ? (
                <div className="mt-5 space-y-5">
                  <div className="rounded-3xl bg-stone-100 p-4">
                    <p className="text-xs uppercase tracking-[0.22em] text-stone-500">Tag</p>
                    <p className="mt-2 text-lg font-semibold text-stone-900">
                      {selectedElement.type}#{selectedElement.id}
                    </p>
                  </div>

                  {/* テキスト編集 */}
                  {(selectedElement.type === "text" || selectedElement.content) && (
                    <div className="rounded-[1.4rem] border border-stone-200 bg-stone-50 p-4">
                      <span className="block text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">テキスト内容</span>
                      <textarea
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        rows={3}
                        className="mt-3 w-full rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm text-stone-800 outline-none transition focus:border-sky-400 resize-y"
                        placeholder="テキストを入力..."
                      />
                    </div>
                  )}

                  {/* 色編集 */}
                  <div className="space-y-3">
                    <ColorField label="文字色" value={textColor} onChange={setTextColor} />

                    {/* 背景色トグル＋カラーピッカー */}
                    <div className="rounded-[1.4rem] border border-stone-200 bg-stone-50 p-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">背景色</span>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={bgEnabled}
                          onClick={() => {
                            if (!bgEnabled) {
                              setBgEnabled(true);
                              setBackgroundColor("#ffffff");
                            } else {
                              setBgEnabled(false);
                              setBackgroundColor(null);
                            }
                          }}
                          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
                            bgEnabled ? "bg-teal-600" : "bg-stone-300"
                          }`}
                        >
                          <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                            bgEnabled ? "translate-x-6" : "translate-x-1"
                          }`} />
                        </button>
                      </div>
                      {bgEnabled && backgroundColor !== null && (
                        <div className="mt-3 space-y-2">
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => setBackgroundColor("transparent")}
                              className={`h-10 w-10 rounded-lg border-2 transition ${
                                backgroundColor === "transparent"
                                  ? "border-teal-500 ring-2 ring-teal-200"
                                  : "border-stone-300 hover:border-stone-400"
                              }`}
                              title="透明"
                              style={{
                                background: "repeating-conic-gradient(#ccc 0% 25%, #fff 0% 50%) 50% / 12px 12px",
                              }}
                            />
                            <input
                              type="color"
                              value={backgroundColor === "transparent" ? "#ffffff" : backgroundColor}
                              onChange={(e) => setBackgroundColor(e.target.value)}
                              className="h-10 w-10 cursor-pointer rounded-lg border border-stone-300"
                            />
                            <input
                              type="text"
                              value={backgroundColor}
                              onChange={(e) => {
                                const val = e.target.value.trim().toLowerCase();
                                if (val === "transparent") {
                                  setBackgroundColor("transparent");
                                } else {
                                  setBackgroundColor(normalizeColorInput(e.target.value, backgroundColor === "transparent" ? "#ffffff" : backgroundColor));
                                }
                              }}
                              className="h-10 flex-1 rounded-xl border border-stone-300 bg-white px-3 text-sm font-mono"
                            />
                          </div>
                          {backgroundColor === "transparent" && (
                            <p className="text-xs text-stone-500">透明が選択されています</p>
                          )}
                        </div>
                      )}
                    </div>

                    {borderColor !== null && (
                      <ColorField label="枠線色" value={borderColor} onChange={setBorderColor} />
                    )}
                  </div>

                  {/* 位置調整（スクロール対応） */}
                  <div className="rounded-[1.4rem] border border-stone-200 bg-stone-50 p-4">
                    <span className="block text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">位置 (スクロールで調整)</span>
                    <div className="mt-3 grid grid-cols-2 gap-3">
                      <label className="flex items-center gap-2">
                        <span className="text-sm text-stone-600 w-6">X:</span>
                        <ScrollableNumberInput
                          value={Math.round(positionX)}
                          onChange={setPositionX}
                          step={5}
                        />
                      </label>
                      <label className="flex items-center gap-2">
                        <span className="text-sm text-stone-600 w-6">Y:</span>
                        <ScrollableNumberInput
                          value={Math.round(positionY)}
                          onChange={setPositionY}
                          step={5}
                        />
                      </label>
                    </div>
                  </div>

                  {/* サイズ調整（スクロール対応） */}
                  <div className="rounded-[1.4rem] border border-stone-200 bg-stone-50 p-4">
                    <span className="block text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">サイズ (スクロールで調整)</span>
                    <div className="mt-3 grid grid-cols-2 gap-3">
                      <label className="flex items-center gap-2">
                        <span className="text-sm text-stone-600 w-6">W:</span>
                        <ScrollableNumberInput
                          value={Math.round(elementWidth)}
                          onChange={setElementWidth}
                          step={5}
                        />
                      </label>
                      <label className="flex items-center gap-2">
                        <span className="text-sm text-stone-600 w-6">H:</span>
                        <ScrollableNumberInput
                          value={Math.round(elementHeight)}
                          onChange={setElementHeight}
                          step={5}
                        />
                      </label>
                    </div>
                  </div>

                  {/* テキスト専用オプション */}
                  {selectedElement.type === "text" && (
                    <div className="grid grid-cols-2 gap-3">
                      <label className="rounded-[1.4rem] border border-stone-200 bg-stone-50 p-3">
                        <span className="block text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">回転</span>
                        <div className="mt-2 flex items-center gap-2">
                          <ScrollableNumberInput
                            value={rotation}
                            onChange={setRotation}
                            step={5}
                          />
                          <span className="text-xs text-stone-500">°</span>
                        </div>
                      </label>

                      <div className="flex items-center justify-between rounded-[1.4rem] border border-stone-200 bg-stone-50 p-3">
                        <span className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">縦書き</span>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={isVertical}
                          onClick={() => setIsVertical(!isVertical)}
                          className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
                            isVertical ? "bg-teal-600" : "bg-stone-300"
                          }`}
                        >
                          <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                            isVertical ? "translate-x-6" : "translate-x-1"
                          }`} />
                        </button>
                      </div>
                    </div>
                  )}

                  {/* アクションボタン */}
                  <div className="grid gap-3 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={handleUndo}
                      disabled={history.length === 0}
                      className="w-full rounded-full border border-stone-300 bg-white px-4 py-2.5 text-sm font-semibold text-stone-900 transition hover:bg-stone-50 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-400"
                    >
                      元に戻す {history.length > 0 && `(${history.length})`}
                    </button>
                    <button
                      type="button"
                      onClick={handleDeleteElement}
                      className="w-full rounded-full border border-red-300 bg-red-50 px-4 py-2.5 text-sm font-semibold text-red-700 transition hover:bg-red-100"
                    >
                      要素を削除
                    </button>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={handleSaveToDb}
                      disabled={isSaving}
                      className="w-full rounded-full bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-stone-400"
                    >
                      {isSaving ? "保存中..." : "DBに保存"}
                    </button>
                    <button
                      type="button"
                      onClick={handleDownloadHtml}
                      className="w-full rounded-full bg-stone-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-stone-800"
                    >
                      HTML保存
                    </button>
                  </div>

                  {saveSuccess && (
                    <div className="rounded-2xl border border-emerald-400/40 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                      {saveSuccess}
                    </div>
                  )}

                  {/* スタイル一覧（読みやすく改善） */}
                  <details className="rounded-[1.4rem] border border-stone-200 bg-stone-50">
                    <summary className="cursor-pointer px-4 py-3 text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 hover:bg-stone-100">
                      スタイル詳細 ({Object.keys(toElementTableRow(selectedElement).styleMap).length}項目)
                    </summary>
                    <div className="border-t border-stone-200 p-3 space-y-1.5">
                      {Object.entries(toElementTableRow(selectedElement).styleMap).map(([key, value]) => (
                        <div key={key} className="flex items-start gap-2 text-xs">
                          <span className="font-mono font-medium text-stone-700 shrink-0">{key}:</span>
                          <span className="font-mono text-stone-500 break-all">{value}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                </div>
              ) : (
                <p className="mt-5 text-sm leading-6 text-stone-500">
                  先にテンプレートを読み込んでください。
                </p>
              )}
            </section>
          </aside>

          <div className="grid gap-8">
            <section className="rounded-[2rem] border border-stone-300/70 bg-white/85 p-5 shadow-[0_18px_50px_rgba(60,46,28,0.1)]">
              <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-stone-500">
                    Preview
                  </p>
                  <h2 className="mt-1 text-lg font-semibold text-stone-900">構造JSONプレビュー</h2>
                </div>
                {template ? (
                  <div className="flex flex-wrap gap-2">
                    {template.manual_tags.map((tag) => (
                      <span
                        key={`manual-${tag}`}
                        className="rounded-full bg-stone-900 px-3 py-1 text-xs font-medium text-white"
                      >
                        {tag}
                      </span>
                    ))}
                    {template.auto_tags.map((tag) => (
                      <span
                        key={`auto-${tag}`}
                        className="rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-950"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="overflow-hidden rounded-[1.5rem] border border-stone-200 bg-[radial-gradient(circle_at_top,#f4efe6,white_62%)] p-4">
                {template ? (
                  <StructurePreviewStage
                    canvas={canvas}
                    elements={elements}
                    selectedElementId={selectedElement?.id ?? null}
                    hoveredElementId={hoveredElementId}
                    onHoverElement={setHoveredElementId}
                    onSelectElement={handleSelectElement}
                    onMoveElement={(elementId, x, y) => {
                      // ドラッグ開始時のみ履歴に追加
                      if (!isDraggingRef.current && template) {
                        isDraggingRef.current = true;
                        setHistory(prev => {
                          const newHistory = [...prev, template.structure_json];
                          return newHistory.length > MAX_HISTORY_SIZE ? newHistory.slice(-MAX_HISTORY_SIZE) : newHistory;
                        });
                      }
                      // 位置を直接テンプレートに反映（履歴追加なしで）
                      setTemplate(prev => {
                        if (!prev) return prev;
                        return {
                          ...prev,
                          structure_json: {
                            ...prev.structure_json,
                            elements: prev.structure_json.elements.map(el =>
                              el.id === elementId ? { ...el, x, y } : el
                            ),
                          },
                        };
                      });
                      if (selectedElementId === elementId) {
                        setPositionX(x);
                        setPositionY(y);
                      }
                    }}
                    onResizeElement={(elementId, x, y, width, height) => {
                      // リサイズ開始時のみ履歴に追加
                      if (!isDraggingRef.current && template) {
                        isDraggingRef.current = true;
                        setHistory(prev => {
                          const newHistory = [...prev, template.structure_json];
                          return newHistory.length > MAX_HISTORY_SIZE ? newHistory.slice(-MAX_HISTORY_SIZE) : newHistory;
                        });
                      }
                      // サイズと位置を直接テンプレートに反映
                      setTemplate(prev => {
                        if (!prev) return prev;
                        return {
                          ...prev,
                          structure_json: {
                            ...prev.structure_json,
                            elements: prev.structure_json.elements.map(el =>
                              el.id === elementId ? { ...el, x, y, width, height } : el
                            ),
                          },
                        };
                      });
                      if (selectedElementId === elementId) {
                        setPositionX(x);
                        setPositionY(y);
                        setElementWidth(width);
                        setElementHeight(height);
                      }
                    }}
                    onDragEnd={() => {
                      isDraggingRef.current = false;
                    }}
                  />
                ) : (
                  <div className="grid min-h-[680px] place-items-center rounded-[1.2rem] border border-dashed border-stone-300 px-6 text-center text-sm text-stone-500">
                    {isBootstrapping
                      ? "保存済みテンプレートを読み込み中です。"
                      : "保存済みテンプレートを選択すると、ここにプレビューと要素境界が表示されます。"}
                  </div>
                )}
              </div>
            </section>

            <section className="rounded-[2rem] border border-stone-300/70 bg-[#171311] p-5 text-stone-100 shadow-[0_18px_50px_rgba(60,46,28,0.16)]">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-stone-400">
                    Elements
                  </p>
                  <h2 className="mt-1 text-lg font-semibold text-white">構成要素テーブル</h2>
                </div>
                {template ? (
                  <p className="text-sm text-stone-400">
                    hover で青枠、click で選択。テーブル行を押しても同じ要素を選択します。
                  </p>
                ) : null}
              </div>

              <div className="mt-5 overflow-x-auto rounded-[1.4rem] border border-white/10 bg-black/20">
                <table className="w-full table-fixed border-collapse text-left text-sm">
                  <thead className="bg-white/6 text-stone-300">
                    <tr>
                      <th className="w-[120px] px-4 py-3 font-medium">Tag</th>
                      <th className="w-[60px] px-4 py-3 font-medium text-center">Z</th>
                      <th className="w-[200px] px-4 py-3 font-medium">Content</th>
                      <th className="px-4 py-3 font-medium">Style</th>
                    </tr>
                  </thead>
                  <tbody>
                    {elements.length ? (
                      elements.map((element) => {
                        const row = toElementTableRow(element);
                        const isHovered = hoveredElementId === element.id;
                        const isSelected = selectedElement?.id === element.id;
                        return (
                          <tr
                            key={element.id}
                            onMouseEnter={() => setHoveredElementId(element.id)}
                            onMouseLeave={() => setHoveredElementId((current) => (current === element.id ? null : current))}
                            onClick={() => handleSelectElement(element)}
                            className="cursor-pointer border-t border-white/10 transition"
                            style={{
                              backgroundColor: isHovered
                                ? "rgba(37,99,235,0.18)"
                                : isSelected
                                  ? "rgba(15,118,110,0.22)"
                                  : "transparent",
                            }}
                          >
                            <td className="px-4 py-3 align-top font-medium text-white truncate">{row.tagLabel}</td>
                            <td className="px-4 py-3 align-top text-center font-mono text-stone-300">{row.zIndex}</td>
                            <td className="px-4 py-3 align-top text-stone-300">
                              <div className="line-clamp-3 whitespace-pre-wrap break-all">{row.content || "-"}</div>
                            </td>
                            <td className="px-4 py-3 align-top text-stone-400 overflow-hidden">
                              <div className="line-clamp-4 break-all">{row.styleText || "style はありません。"}</div>
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-stone-400">
                          読み込まれた要素がありません。
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}

type ColorFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
};

function ColorField({ label, value, onChange }: ColorFieldProps) {
  return (
    <label className="rounded-[1.4rem] border border-stone-200 bg-stone-50 p-4">
      <span className="block text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">{label}</span>
      <div className="mt-3 flex items-center gap-3">
        <input
          type="color"
          value={value}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
          className="h-11 w-16 cursor-pointer rounded-lg border border-stone-300 bg-transparent p-1"
        />
        <input
          type="text"
          value={value}
          onChange={(event) => onChange(normalizeColorInput(event.target.value, value))}
          className="h-11 w-full rounded-xl border border-stone-300 bg-white px-3 text-sm text-stone-800 outline-none transition focus:border-sky-400"
        />
      </div>
    </label>
  );
}

type ScrollableNumberInputProps = {
  value: number;
  onChange: (value: number) => void;
  step?: number;
};

function ScrollableNumberInput({ value, onChange, step = 5 }: ScrollableNumberInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -step : step;
      onChange(value + delta);
    };

    // non-passive listener to allow preventDefault
    input.addEventListener("wheel", handleWheel, { passive: false });
    return () => input.removeEventListener("wheel", handleWheel);
  }, [value, onChange, step]);

  return (
    <input
      ref={inputRef}
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value) || 0)}
      step={step}
      className="h-9 w-full rounded-lg border border-stone-300 bg-white px-2 text-sm font-mono text-center"
    />
  );
}

function asString(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

type ResizeHandle = 'nw' | 'n' | 'ne' | 'w' | 'e' | 'sw' | 's' | 'se';

type StructurePreviewStageProps = {
  canvas: { width: number; height: number; background?: string; backgroundColor?: string; background_color?: string };
  elements: TemplateElement[];
  selectedElementId: string | null;
  hoveredElementId: string | null;
  onHoverElement: (elementId: string | null) => void;
  onSelectElement: (element: TemplateElement) => void;
  onMoveElement: (elementId: string, x: number, y: number) => void;
  onResizeElement: (elementId: string, x: number, y: number, width: number, height: number) => void;
  onDragEnd?: () => void;
};

// スナップガイドの閾値（ピクセル）
const SNAP_THRESHOLD = 5;

type GuideLines = {
  vertical: number[];   // x座標の配列（縦線）
  horizontal: number[]; // y座標の配列（横線）
};

function calculateSnapGuides(
  movingElement: { x: number; y: number; width: number; height: number },
  otherElements: TemplateElement[],
  canvasWidth: number,
  canvasHeight: number,
): GuideLines {
  const guides: GuideLines = { vertical: [], horizontal: [] };

  // 移動中の要素の中心
  const movingCenterX = movingElement.x + movingElement.width / 2;
  const movingCenterY = movingElement.y + movingElement.height / 2;

  // キャンバス中心との比較
  const canvasCenterX = canvasWidth / 2;
  const canvasCenterY = canvasHeight / 2;

  if (Math.abs(movingCenterX - canvasCenterX) < SNAP_THRESHOLD) {
    guides.vertical.push(canvasCenterX);
  }
  if (Math.abs(movingCenterY - canvasCenterY) < SNAP_THRESHOLD) {
    guides.horizontal.push(canvasCenterY);
  }

  // 他の要素との比較
  for (const element of otherElements) {
    const elementCenterX = element.x + element.width / 2;
    const elementCenterY = element.y + element.height / 2;

    // 水平中心が揃っている場合 → 縦線
    if (Math.abs(movingCenterX - elementCenterX) < SNAP_THRESHOLD) {
      guides.vertical.push(elementCenterX);
    }

    // 垂直中心が揃っている場合 → 横線
    if (Math.abs(movingCenterY - elementCenterY) < SNAP_THRESHOLD) {
      guides.horizontal.push(elementCenterY);
    }

    // 端揃え（左端-左端、右端-右端、上端-上端、下端-下端）
    if (Math.abs(movingElement.x - element.x) < SNAP_THRESHOLD) {
      guides.vertical.push(element.x);
    }
    if (Math.abs(movingElement.x + movingElement.width - (element.x + element.width)) < SNAP_THRESHOLD) {
      guides.vertical.push(element.x + element.width);
    }
    if (Math.abs(movingElement.y - element.y) < SNAP_THRESHOLD) {
      guides.horizontal.push(element.y);
    }
    if (Math.abs(movingElement.y + movingElement.height - (element.y + element.height)) < SNAP_THRESHOLD) {
      guides.horizontal.push(element.y + element.height);
    }
  }

  // 重複を除去
  guides.vertical = [...new Set(guides.vertical)];
  guides.horizontal = [...new Set(guides.horizontal)];

  return guides;
}

function StructurePreviewStage({
  canvas,
  elements,
  selectedElementId,
  hoveredElementId,
  onHoverElement,
  onSelectElement,
  onMoveElement,
  onResizeElement,
  onDragEnd,
}: StructurePreviewStageProps) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);
  const [dragging, setDragging] = useState<{
    elementId: string;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);
  const [resizing, setResizing] = useState<{
    elementId: string;
    handle: ResizeHandle;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    origWidth: number;
    origHeight: number;
  } | null>(null);
  const [guideLines, setGuideLines] = useState<GuideLines>({ vertical: [], horizontal: [] });

  useEffect(() => {
    const node = stageRef.current;
    if (!node) {
      return;
    }

    const updateScale = () => {
      const width = node.clientWidth;
      if (!width || !canvas.width) {
        return;
      }
      setScale(width / canvas.width);
    };

    updateScale();
    const observer = new ResizeObserver(updateScale);
    observer.observe(node);

    return () => observer.disconnect();
  }, [canvas.width]);

  // ドラッグ中のmousemove/mouseupをwindowで監視
  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaX = (e.clientX - dragging.startX) / scale;
      const deltaY = (e.clientY - dragging.startY) / scale;
      const newX = dragging.origX + deltaX;
      const newY = dragging.origY + deltaY;

      // 移動中の要素を取得してスナップガイドを計算
      const movingElement = elements.find(el => el.id === dragging.elementId);
      if (movingElement) {
        const guides = calculateSnapGuides(
          { x: newX, y: newY, width: movingElement.width, height: movingElement.height },
          elements.filter(el => el.id !== dragging.elementId),
          canvas.width,
          canvas.height,
        );
        setGuideLines(guides);
      }

      onMoveElement(dragging.elementId, newX, newY);
    };

    const handleMouseUp = () => {
      setDragging(null);
      setGuideLines({ vertical: [], horizontal: [] }); // ガイドラインをクリア
      onDragEnd?.();
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [dragging, scale, onMoveElement, onDragEnd, elements, canvas.width, canvas.height]);

  // リサイズ中のmousemove/mouseupをwindowで監視
  useEffect(() => {
    if (!resizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaX = (e.clientX - resizing.startX) / scale;
      const deltaY = (e.clientY - resizing.startY) / scale;

      let newX = resizing.origX;
      let newY = resizing.origY;
      let newWidth = resizing.origWidth;
      let newHeight = resizing.origHeight;

      // リサイズハンドルに応じて位置とサイズを計算
      switch (resizing.handle) {
        case 'nw':
          newX = resizing.origX + deltaX;
          newY = resizing.origY + deltaY;
          newWidth = resizing.origWidth - deltaX;
          newHeight = resizing.origHeight - deltaY;
          break;
        case 'n':
          newY = resizing.origY + deltaY;
          newHeight = resizing.origHeight - deltaY;
          break;
        case 'ne':
          newY = resizing.origY + deltaY;
          newWidth = resizing.origWidth + deltaX;
          newHeight = resizing.origHeight - deltaY;
          break;
        case 'w':
          newX = resizing.origX + deltaX;
          newWidth = resizing.origWidth - deltaX;
          break;
        case 'e':
          newWidth = resizing.origWidth + deltaX;
          break;
        case 'sw':
          newX = resizing.origX + deltaX;
          newWidth = resizing.origWidth - deltaX;
          newHeight = resizing.origHeight + deltaY;
          break;
        case 's':
          newHeight = resizing.origHeight + deltaY;
          break;
        case 'se':
          newWidth = resizing.origWidth + deltaX;
          newHeight = resizing.origHeight + deltaY;
          break;
      }

      // 最小サイズを保証
      if (newWidth < 10) {
        if (resizing.handle.includes('w')) {
          newX = resizing.origX + resizing.origWidth - 10;
        }
        newWidth = 10;
      }
      if (newHeight < 10) {
        if (resizing.handle.includes('n')) {
          newY = resizing.origY + resizing.origHeight - 10;
        }
        newHeight = 10;
      }

      onResizeElement(resizing.elementId, newX, newY, newWidth, newHeight);
    };

    const handleMouseUp = () => {
      setResizing(null);
      onDragEnd?.();
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [resizing, scale, onResizeElement, onDragEnd]);

  const sortedElements = sortElementsByZIndex(elements);

  const handleDragStart = (e: React.MouseEvent, element: TemplateElement) => {
    e.preventDefault();
    onSelectElement(element);
    setDragging({
      elementId: element.id,
      startX: e.clientX,
      startY: e.clientY,
      origX: element.x,
      origY: element.y,
    });
  };

  const handleResizeStart = (e: React.MouseEvent, element: TemplateElement, handle: ResizeHandle) => {
    e.preventDefault();
    e.stopPropagation();
    setResizing({
      elementId: element.id,
      handle,
      startX: e.clientX,
      startY: e.clientY,
      origX: element.x,
      origY: element.y,
      origWidth: element.width,
      origHeight: element.height,
    });
  };

  const resizeHandlePositions: { handle: ResizeHandle; style: React.CSSProperties; cursor: string }[] = [
    { handle: 'nw', style: { top: -4, left: -4 }, cursor: 'nwse-resize' },
    { handle: 'n', style: { top: -4, left: '50%', transform: 'translateX(-50%)' }, cursor: 'ns-resize' },
    { handle: 'ne', style: { top: -4, right: -4 }, cursor: 'nesw-resize' },
    { handle: 'w', style: { top: '50%', left: -4, transform: 'translateY(-50%)' }, cursor: 'ew-resize' },
    { handle: 'e', style: { top: '50%', right: -4, transform: 'translateY(-50%)' }, cursor: 'ew-resize' },
    { handle: 'sw', style: { bottom: -4, left: -4 }, cursor: 'nesw-resize' },
    { handle: 's', style: { bottom: -4, left: '50%', transform: 'translateX(-50%)' }, cursor: 'ns-resize' },
    { handle: 'se', style: { bottom: -4, right: -4 }, cursor: 'nwse-resize' },
  ];

  return (
    <div
      ref={stageRef}
      className="relative mx-auto w-full max-w-[860px] overflow-hidden rounded-[1.2rem] border border-stone-300 shadow-[0_24px_60px_rgba(52,40,24,0.14)]"
      style={{
        aspectRatio: `${canvas.width}/${canvas.height}`,
        background: buildCanvasBackground(canvas),
        cursor: dragging ? "grabbing" : "default",
      }}
    >
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{
          width: canvas.width,
          height: canvas.height,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
        }}
      >
        {sortedElements.map((element) => (
          <RenderedElement key={element.id} element={element} />
        ))}

        {sortedElements.map((element) => {
          const frameStyle = buildFrameStylePx(element);
          const isHovered = hoveredElementId === element.id;
          const isSelected = selectedElementId === element.id;
          const isDragging = dragging?.elementId === element.id;
          const isResizing = resizing?.elementId === element.id;
          const isActive = isDragging || isResizing;

          // rotation がある場合：寸法を入れ替えて初期状態を作り、CSS回転で元の見た目に戻す
          const rotation = typeof element.rotation === "number" ? element.rotation : 0;
          const overlayStyle: Record<string, unknown> = { ...frameStyle };
          if (rotation !== 0) {
            const originalWidth = frameStyle.width as number;
            const originalHeight = frameStyle.height as number;
            const originalLeft = frameStyle.left as number;
            const originalTop = frameStyle.top as number;

            const centerX = originalLeft + originalWidth / 2;
            const centerY = originalTop + originalHeight / 2;

            const newWidth = originalHeight;
            const newHeight = originalWidth;

            overlayStyle.width = newWidth;
            overlayStyle.height = newHeight;
            overlayStyle.left = centerX - newWidth / 2;
            overlayStyle.top = centerY - newHeight / 2;

            overlayStyle.transform = `rotate(${rotation}deg)`;
            overlayStyle.transformOrigin = "center center";
          }

          return (
            <div
              key={`${element.id}-overlay`}
              role="button"
              tabIndex={0}
              aria-label={`${element.type} ${element.id}`}
              onMouseEnter={() => !dragging && !resizing && onHoverElement(element.id)}
              onMouseLeave={() => !dragging && !resizing && onHoverElement(null)}
              onMouseDown={(e) => handleDragStart(e, element)}
              className="absolute rounded-sm"
              style={{
                ...overlayStyle,
                cursor: isDragging ? "grabbing" : isResizing ? "default" : "grab",
                border: isActive
                  ? "2px dashed #f59e0b"
                  : isHovered
                    ? "2px solid #2563eb"
                    : isSelected
                      ? "2px solid #0f766e"
                      : "1px solid rgba(37,99,235,0.08)",
                backgroundColor: isActive
                  ? "rgba(245,158,11,0.15)"
                  : isHovered
                    ? "rgba(37,99,235,0.12)"
                    : isSelected
                      ? "rgba(15,118,110,0.10)"
                      : "transparent",
              }}
            >
              <span className="sr-only">{element.id}</span>
              {/* リサイズハンドル（選択中の要素のみ表示） */}
              {isSelected && !isDragging && resizeHandlePositions.map(({ handle, style, cursor }) => (
                <div
                  key={handle}
                  onMouseDown={(e) => handleResizeStart(e, element, handle)}
                  style={{
                    position: 'absolute',
                    width: 8,
                    height: 8,
                    backgroundColor: resizing?.handle === handle ? '#f59e0b' : '#0f766e',
                    border: '1px solid white',
                    borderRadius: 2,
                    cursor,
                    zIndex: 10,
                    ...style,
                  }}
                />
              ))}
            </div>
          );
        })}

        {/* スナップガイドライン（縦線） */}
        {guideLines.vertical.map((x, i) => (
          <div
            key={`guide-v-${i}`}
            style={{
              position: 'absolute',
              left: x,
              top: 0,
              width: 1,
              height: canvas.height,
              backgroundColor: '#f43f5e',
              pointerEvents: 'none',
              zIndex: 9999,
            }}
          />
        ))}

        {/* スナップガイドライン（横線） */}
        {guideLines.horizontal.map((y, i) => (
          <div
            key={`guide-h-${i}`}
            style={{
              position: 'absolute',
              left: 0,
              top: y,
              width: canvas.width,
              height: 1,
              backgroundColor: '#f43f5e',
              pointerEvents: 'none',
              zIndex: 9999,
            }}
          />
        ))}
      </div>
    </div>
  );
}

function RenderedElement({ element }: { element: TemplateElement }) {
  if (element.type === "image") {
    return <RenderedImageElement element={element} />;
  }

  if (element.type === "shape") {
    return <RenderedShapeElement element={element} />;
  }

  return <RenderedTextElement element={element} />;
}

function RenderedTextElement({ element }: { element: TemplateElement }) {
  const frameStyle = buildFrameStylePx(element);
  const style = element.style ?? {};
  const fontSize =
    getStyleValue(style, "fontSize", "font_size") ?? getStyleValue(element, "font_size");
  const fontWeight = getStyleValue(style, "fontWeight", "font_weight");
  const fontFamily = getStyleValue(style, "fontFamily", "font_family");
  const color = getStyleValue(style, "color") ?? "#111111";
  const textAlign = getStyleValue(style, "textAlign", "text_align", "align") ?? "left";
  const lineHeight = getStyleValue(style, "lineHeight", "line_height");
  const backgroundColor = getStyleValue(style, "backgroundColor", "background_color");
  const borderColor = getStyleValue(style, "borderColor", "border_color");
  const borderWidth = getStyleValue(style, "borderWidth", "border_width") ?? 1;

  const baseStyle: CSSProperties = {
    ...frameStyle,
    color: typeof color === "string" ? color : DEFAULT_TEXT_COLOR,
    fontSize: typeof fontSize === "number" ? `${fontSize}px` : undefined,
    fontWeight: typeof fontWeight === "string" || typeof fontWeight === "number" ? fontWeight : undefined,
    fontFamily: typeof fontFamily === "string" ? fontFamily : undefined,
    textAlign: typeof textAlign === "string" ? (textAlign as CSSProperties["textAlign"]) : undefined,
    lineHeight: typeof lineHeight === "number" || typeof lineHeight === "string" ? String(lineHeight) : undefined,
    whiteSpace: "pre-wrap",
    overflow: "hidden",
    backgroundColor: typeof backgroundColor === "string" ? backgroundColor : undefined,
    border: typeof borderColor === "string" ? `${borderWidth}px solid ${borderColor}` : undefined,
    boxSizing: "border-box",
    pointerEvents: "none",
  };

  const rotation = typeof element.rotation === "number" ? element.rotation : 0;
  const isVertical = element.is_vertical === true;
  const w = frameStyle.width as number;
  const h = frameStyle.height as number;

  // rotation がある場合、要素全体を回転（寸法を入れ替えてから回転）
  if (rotation !== 0) {
    const left = frameStyle.left as number;
    const top = frameStyle.top as number;

    const centerX = left + w / 2;
    const centerY = top + h / 2;

    // 寸法を入れ替え
    baseStyle.width = h;
    baseStyle.height = w;
    baseStyle.left = centerX - h / 2;
    baseStyle.top = centerY - w / 2;

    baseStyle.transform = `rotate(${rotation}deg)`;
    baseStyle.transformOrigin = "center center";

    // 回転後、テキストは水平（長軸に沿う）
    baseStyle.writingMode = "horizontal-tb";
  } else {
    // rotation = 0 の場合、is_vertical フラグに基づいて縦書き/横書きを決定
    if (isVertical) {
      baseStyle.writingMode = "vertical-rl";
    } else {
      baseStyle.writingMode = "horizontal-tb";
    }
  }

  return <div style={baseStyle}>{element.content ?? ""}</div>;
}

function RenderedImageElement({ element }: { element: TemplateElement }) {
  const frameStyle = buildFrameStylePx(element);
  const src = typeof element.src === "string"
    ? element.src
    : typeof element.content === "string" && element.content.startsWith("data:image")
      ? element.content
      : undefined;

  // rotation がある場合：寸法を入れ替えて初期状態を作り、CSS回転で元の見た目に戻す
  const rotation = typeof element.rotation === "number" ? element.rotation : 0;
  const imageFrameStyle: CSSProperties = { ...frameStyle };
  if (rotation !== 0) {
    const originalWidth = frameStyle.width as number;
    const originalHeight = frameStyle.height as number;
    const originalLeft = frameStyle.left as number;
    const originalTop = frameStyle.top as number;

    const centerX = originalLeft + originalWidth / 2;
    const centerY = originalTop + originalHeight / 2;

    const newWidth = originalHeight;
    const newHeight = originalWidth;

    imageFrameStyle.width = newWidth;
    imageFrameStyle.height = newHeight;
    imageFrameStyle.left = centerX - newWidth / 2;
    imageFrameStyle.top = centerY - newHeight / 2;

    imageFrameStyle.transform = `rotate(${rotation}deg)`;
    imageFrameStyle.transformOrigin = "center center";
  }

  if (!src) {
    return (
      <div
        style={{
          ...imageFrameStyle,
          overflow: "hidden",
          display: "grid",
          placeItems: "center",
          background: "linear-gradient(135deg, #dbeafe, #c7d2fe)",
          color: "rgba(15, 23, 42, 0.55)",
          fontSize: "14px",
          pointerEvents: "none",
        }}
      >
        image
      </div>
    );
  }

  return (
    <div style={{ ...imageFrameStyle, overflow: "hidden", background: "#ffffff" }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        draggable={false}
        style={{
          ...buildCroppedImageStyle(element.crop),
          objectFit: "cover",
          userSelect: "none",
          pointerEvents: "none",
        }}
      />
    </div>
  );
}

function RenderedShapeElement({ element }: { element: TemplateElement }) {
  const frameStyle = buildFrameStylePx(element);
  const style = element.style ?? {};
  const backgroundColor =
    getStyleValue(style, "backgroundColor", "background_color") ??
    getStyleValue(element, "fill_color");
  const borderColor =
    getStyleValue(style, "borderColor", "border_color") ??
    getStyleValue(element, "stroke_color");
  const borderWidth =
    getStyleValue(style, "borderWidth", "border_width") ??
    getStyleValue(element, "stroke_width") ??
    1;
  const gradientCss = buildGradientCss(getStyleValue(style, "gradient"));
  const pathPoints = Array.isArray(getStyleValue(element, "path_points"))
    ? (getStyleValue(element, "path_points") as Array<Record<string, unknown>>)
    : [];
  const fillImage = getStyleValue(element, "fill_image");
  const fillImageSrc =
    fillImage && typeof fillImage === "object" && typeof (fillImage as Record<string, unknown>).src === "string"
      ? ((fillImage as Record<string, unknown>).src as string)
      : undefined;

  const shapeStyle: CSSProperties = {
    ...frameStyle,
    boxSizing: "border-box",
    overflow: "hidden",
    background: typeof gradientCss === "string" ? gradientCss : undefined,
    backgroundColor: typeof backgroundColor === "string" ? backgroundColor : undefined,
    border: typeof borderColor === "string" ? `${borderWidth}px solid ${borderColor}` : undefined,
    backgroundImage: fillImageSrc ? `url(${fillImageSrc})` : undefined,
    backgroundSize: "cover",
    backgroundPosition: "center",
    pointerEvents: "none",
  };

  if (pathPoints.length) {
    shapeStyle.clipPath = `polygon(${pathPoints
      .map((point) => `${Number(point.x ?? 0).toFixed(2)}% ${Number(point.y ?? 0).toFixed(2)}%`)
      .join(", ")})`;
  }

  // rotation がある場合：寸法を入れ替えて初期状態を作り、CSS回転で元の見た目に戻す
  const rotation = typeof element.rotation === "number" ? element.rotation : 0;
  if (rotation !== 0) {
    const originalWidth = shapeStyle.width as number;
    const originalHeight = shapeStyle.height as number;
    const originalLeft = shapeStyle.left as number;
    const originalTop = shapeStyle.top as number;

    const centerX = originalLeft + originalWidth / 2;
    const centerY = originalTop + originalHeight / 2;

    const newWidth = originalHeight;
    const newHeight = originalWidth;

    shapeStyle.width = newWidth;
    shapeStyle.height = newHeight;
    shapeStyle.left = centerX - newWidth / 2;
    shapeStyle.top = centerY - newHeight / 2;

    shapeStyle.transform = `rotate(${rotation}deg)`;
    shapeStyle.transformOrigin = "center center";
  }

  return <div style={shapeStyle} />;
}
