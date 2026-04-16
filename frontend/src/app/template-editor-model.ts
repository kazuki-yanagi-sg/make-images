export type TemplateElementStyle = Record<string, unknown>;

export type TemplateElement = {
  id: string;
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  content?: string;
  src?: string;
  crop?: {
    left?: number;
    right?: number;
    top?: number;
    bottom?: number;
  };
  shape_type?: string;
  is_vertical?: boolean;
  rotation?: number;
  z_index?: number;
  style?: TemplateElementStyle;
};

export type TemplateCanvas = {
  width: number;
  height: number;
};

export type TemplateStructure = {
  canvas: TemplateCanvas;
  elements: TemplateElement[];
  coordinate_type?: 'pixel' | 'percent';
};

export type TemplateDetail = {
  id: string;
  name?: string | null;
  manual_tags: string[];
  auto_tags: string[];
  structure_json: TemplateStructure;
  preview_html: string;
  preview_css: string;
  atmosphere?: string | null;
};

export type TemplateSummary = {
  id: string;
  name?: string | null;
  manual_tags: string[];
  auto_tags: string[];
  created_at?: string | null;
};

export type ElementStylePatch = {
  color?: string;
  backgroundColor?: string;
  borderColor?: string;
};

export type ElementTableRow = {
  id: string;
  type: string;
  tagLabel: string;
  content: string;
  zIndex: number;
  styleMap: Record<string, string>;
  styleText: string;
};

function toFiniteNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function toObject(value: unknown) {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function formatPercentage(value: number, total: number) {
  if (total <= 0) {
    return '0.0000%';
  }

  return `${((value / total) * 100).toFixed(4)}%`;
}

export function getStyleValue(
  style: Record<string, unknown> | undefined,
  ...keys: string[]
) {
  const source = toObject(style);
  for (const key of keys) {
    if (source[key] != null) {
      return source[key];
    }
  }
  return undefined;
}

export function buildPreviewSrcDoc(template: Pick<TemplateDetail, 'preview_html' | 'preview_css'> | null) {
  if (!template) {
    return '';
  }

  return `<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      html, body {
        margin: 0;
        padding: 0;
        background: transparent;
      }
      body {
        min-height: 100vh;
      }
      ${template.preview_css}
    </style>
  </head>
  <body>
    ${template.preview_html}
  </body>
</html>`;
}

export function toElementTableRow(element: TemplateElement): ElementTableRow {
  const styleMap = Object.entries(element.style ?? {}).reduce<Record<string, string>>((acc, [key, value]) => {
    if (value == null) {
      return acc;
    }

    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      acc[key] = String(value);
      return acc;
    }

    acc[key] = JSON.stringify(value);

    return acc;
  }, {});

  const orderedEntries = Object.entries(styleMap).sort(([left], [right]) => left.localeCompare(right));

  return {
    id: element.id,
    type: element.type,
    tagLabel: `${element.type}#${element.id}`,
    content: element.content ?? '',
    zIndex: toFiniteNumber(element.z_index),
    styleMap,
    styleText: orderedEntries.map(([key, value]) => `${key}: ${value}`).join(' | '),
  };
}

export function buildOverlayStyle(element: TemplateElement, canvas: TemplateCanvas) {
  return {
    left: formatPercentage(toFiniteNumber(element.x), canvas.width),
    top: formatPercentage(toFiniteNumber(element.y), canvas.height),
    width: formatPercentage(toFiniteNumber(element.width), canvas.width),
    height: formatPercentage(toFiniteNumber(element.height), canvas.height),
  };
}

export function buildFrameStylePx(element: TemplateElement) {
  return {
    position: 'absolute' as const,
    left: toFiniteNumber(element.x),
    top: toFiniteNumber(element.y),
    width: toFiniteNumber(element.width),
    height: toFiniteNumber(element.height),
    zIndex: toFiniteNumber(element.z_index),
    overflow: 'hidden' as const,
  };
}

export type ElementPropsPatch = {
  rotation?: number;
  is_vertical?: boolean;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  content?: string;
};

export function applyStylePatchToStructure(
  structure: TemplateStructure,
  elementId: string,
  stylePatch: ElementStylePatch,
  propsPatch?: ElementPropsPatch,
): TemplateStructure {
  return {
    ...structure,
    elements: structure.elements.map((element) => {
      if (element.id !== elementId) {
        return element;
      }

      const updatedElement = {
        ...element,
        style: {
          ...(element.style ?? {}),
          ...stylePatch,
        },
      };

      if (propsPatch?.rotation !== undefined) {
        updatedElement.rotation = propsPatch.rotation;
      }
      if (propsPatch?.is_vertical !== undefined) {
        updatedElement.is_vertical = propsPatch.is_vertical;
      }
      if (propsPatch?.x !== undefined) {
        updatedElement.x = propsPatch.x;
      }
      if (propsPatch?.y !== undefined) {
        updatedElement.y = propsPatch.y;
      }
      if (propsPatch?.width !== undefined) {
        updatedElement.width = propsPatch.width;
      }
      if (propsPatch?.height !== undefined) {
        updatedElement.height = propsPatch.height;
      }
      if (propsPatch?.content !== undefined) {
        updatedElement.content = propsPatch.content;
      }

      return updatedElement;
    }),
  };
}

export function normalizeColorInput(value: string | undefined, fallback: string) {
  if (!value) {
    return fallback;
  }

  if (/^#[0-9a-fA-F]{6}$/.test(value)) {
    return value;
  }

  const shortHex = /^#[0-9a-fA-F]{3}$/;
  if (shortHex.test(value)) {
    const [, r, g, b] = value;
    return `#${r}${r}${g}${g}${b}${b}`;
  }

  return fallback;
}

export function buildTemplateOptionLabel(template: TemplateSummary) {
  const name = template.name?.trim() || template.id;
  const manualTags = template.manual_tags.length ? template.manual_tags.join(", ") : "タグなし";

  return `${name} | ${manualTags}`;
}

export function sortElementsByZIndex(elements: TemplateElement[]) {
  return [...elements].sort((left, right) => {
    const leftZ = toFiniteNumber(left.z_index);
    const rightZ = toFiniteNumber(right.z_index);

    if (leftZ !== rightZ) {
      return leftZ - rightZ;
    }

    return left.id.localeCompare(right.id);
  });
}

export function buildCanvasBackground(canvas: Record<string, unknown>) {
  return (
    (typeof canvas.background === 'string' && canvas.background) ||
    (typeof canvas.backgroundColor === 'string' && canvas.backgroundColor) ||
    (typeof canvas.background_color === 'string' && canvas.background_color) ||
    '#ffffff'
  );
}

export function buildGradientCss(gradient: unknown) {
  const source = toObject(gradient);
  const direction = source.direction === 'horizontal'
    ? 'to right'
    : source.direction === 'vertical'
      ? 'to bottom'
      : '135deg';

  const stops = Array.isArray(source.stops) ? source.stops : [];
  if (stops.length) {
    const colorStops = stops
      .map((stop) => {
        const stopObj = toObject(stop);
        const color = typeof stopObj.color === 'string' ? stopObj.color : '#000000';
        const offset = typeof stopObj.offset === 'number' ? ` ${Math.round(stopObj.offset * 100)}%` : '';
        return `${color}${offset}`;
      })
      .join(', ');

    return `linear-gradient(${direction}, ${colorStops})`;
  }

  if (typeof source.start === 'string' && typeof source.end === 'string') {
    return `linear-gradient(${direction}, ${source.start}, ${source.end})`;
  }

  return undefined;
}

export function buildCroppedImageStyle(crop: TemplateElement['crop']) {
  const left = Math.max(0, Math.min(1, toFiniteNumber(crop?.left)));
  const right = Math.max(0, Math.min(1, toFiniteNumber(crop?.right)));
  const top = Math.max(0, Math.min(1, toFiniteNumber(crop?.top)));
  const bottom = Math.max(0, Math.min(1, toFiniteNumber(crop?.bottom)));
  const visibleWidth = Math.max(0.0001, 1 - left - right);
  const visibleHeight = Math.max(0.0001, 1 - top - bottom);

  return {
    position: 'absolute' as const,
    left: `${((-left / visibleWidth) * 100).toFixed(4)}%`,
    top: `${((-top / visibleHeight) * 100).toFixed(4)}%`,
    width: `${((1 / visibleWidth) * 100).toFixed(4)}%`,
    height: `${((1 / visibleHeight) * 100).toFixed(4)}%`,
    maxWidth: 'none' as const,
  };
}

// ==============================================================================
// HTML生成関数（structure_jsonからHTML文字列を生成）
// ==============================================================================

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function styleToString(style: Record<string, string | number | undefined>): string {
  return Object.entries(style)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => {
      // camelCase to kebab-case
      const kebabKey = key.replace(/([A-Z])/g, '-$1').toLowerCase();
      return `${kebabKey}: ${value}`;
    })
    .join('; ');
}

function generateTextElementHtml(element: TemplateElement): string {
  const frameStyle = buildFrameStylePx(element);
  const style = element.style ?? {};
  const fontSize = getStyleValue(style, 'fontSize', 'font_size') ?? getStyleValue(element as Record<string, unknown>, 'font_size');
  const fontWeight = getStyleValue(style, 'fontWeight', 'font_weight');
  const fontFamily = getStyleValue(style, 'fontFamily', 'font_family');
  const color = getStyleValue(style, 'color') ?? '#111111';
  const textAlign = getStyleValue(style, 'textAlign', 'text_align', 'align') ?? 'left';
  const lineHeight = getStyleValue(style, 'lineHeight', 'line_height');
  const backgroundColor = getStyleValue(style, 'backgroundColor', 'background_color');
  const borderColor = getStyleValue(style, 'borderColor', 'border_color');
  const borderWidth = getStyleValue(style, 'borderWidth', 'border_width') ?? 1;

  const baseStyle: Record<string, string | number | undefined> = {
    position: 'absolute',
    left: `${frameStyle.left}px`,
    top: `${frameStyle.top}px`,
    width: `${frameStyle.width}px`,
    height: `${frameStyle.height}px`,
    zIndex: frameStyle.zIndex,
    color: typeof color === 'string' ? color : '#111111',
    fontSize: typeof fontSize === 'number' ? `${fontSize}px` : undefined,
    fontWeight: typeof fontWeight === 'string' || typeof fontWeight === 'number' ? String(fontWeight) : undefined,
    fontFamily: typeof fontFamily === 'string' ? fontFamily : undefined,
    textAlign: typeof textAlign === 'string' ? textAlign : undefined,
    lineHeight: typeof lineHeight === 'number' || typeof lineHeight === 'string' ? String(lineHeight) : undefined,
    whiteSpace: 'pre-wrap',
    overflow: 'hidden',
    backgroundColor: typeof backgroundColor === 'string' ? backgroundColor : undefined,
    border: typeof borderColor === 'string' ? `${borderWidth}px solid ${borderColor}` : undefined,
    boxSizing: 'border-box',
  };

  const rotation = typeof element.rotation === 'number' ? element.rotation : 0;
  const isVertical = element.is_vertical === true;
  const w = frameStyle.width;
  const h = frameStyle.height;

  if (rotation !== 0) {
    const left = frameStyle.left;
    const top = frameStyle.top;
    const centerX = left + w / 2;
    const centerY = top + h / 2;

    baseStyle.width = `${h}px`;
    baseStyle.height = `${w}px`;
    baseStyle.left = `${centerX - h / 2}px`;
    baseStyle.top = `${centerY - w / 2}px`;
    baseStyle.transform = `rotate(${rotation}deg)`;
    baseStyle.transformOrigin = 'center center';
    baseStyle.writingMode = 'horizontal-tb';
  } else {
    baseStyle.writingMode = isVertical ? 'vertical-rl' : 'horizontal-tb';
  }

  const content = escapeHtml(element.content ?? '').replace(/\n/g, '<br>');
  return `<div style="${styleToString(baseStyle)}">${content}</div>`;
}

function generateImageElementHtml(element: TemplateElement): string {
  const frameStyle = buildFrameStylePx(element);
  const src = typeof element.src === 'string'
    ? element.src
    : typeof element.content === 'string' && element.content.startsWith('data:image')
      ? element.content
      : undefined;

  const rotation = typeof element.rotation === 'number' ? element.rotation : 0;

  let containerStyle: Record<string, string | number | undefined> = {
    position: 'absolute',
    left: `${frameStyle.left}px`,
    top: `${frameStyle.top}px`,
    width: `${frameStyle.width}px`,
    height: `${frameStyle.height}px`,
    zIndex: frameStyle.zIndex,
    overflow: 'hidden',
    background: '#ffffff',
  };

  if (rotation !== 0) {
    const originalWidth = frameStyle.width;
    const originalHeight = frameStyle.height;
    const originalLeft = frameStyle.left;
    const originalTop = frameStyle.top;
    const centerX = originalLeft + originalWidth / 2;
    const centerY = originalTop + originalHeight / 2;
    const newWidth = originalHeight;
    const newHeight = originalWidth;

    containerStyle = {
      ...containerStyle,
      width: `${newWidth}px`,
      height: `${newHeight}px`,
      left: `${centerX - newWidth / 2}px`,
      top: `${centerY - newHeight / 2}px`,
      transform: `rotate(${rotation}deg)`,
      transformOrigin: 'center center',
    };
  }

  if (!src) {
    const placeholderStyle: Record<string, string | number | undefined> = {
      ...containerStyle,
      display: 'grid',
      placeItems: 'center',
      background: 'linear-gradient(135deg, #dbeafe, #c7d2fe)',
      color: 'rgba(15, 23, 42, 0.55)',
      fontSize: '14px',
    };
    return `<div style="${styleToString(placeholderStyle)}">image</div>`;
  }

  const cropStyle = buildCroppedImageStyle(element.crop);
  const imgStyle: Record<string, string | number | undefined> = {
    position: 'absolute',
    left: cropStyle.left,
    top: cropStyle.top,
    width: cropStyle.width,
    height: cropStyle.height,
    maxWidth: 'none',
    objectFit: 'cover',
  };

  return `<div style="${styleToString(containerStyle)}"><img src="${escapeHtml(src)}" alt="" style="${styleToString(imgStyle)}" /></div>`;
}

function generateShapeElementHtml(element: TemplateElement): string {
  const frameStyle = buildFrameStylePx(element);
  const style = element.style ?? {};
  const backgroundColor =
    getStyleValue(style, 'backgroundColor', 'background_color') ??
    getStyleValue(element as Record<string, unknown>, 'fill_color');
  const borderColor =
    getStyleValue(style, 'borderColor', 'border_color') ??
    getStyleValue(element as Record<string, unknown>, 'stroke_color');
  const borderWidth =
    getStyleValue(style, 'borderWidth', 'border_width') ??
    getStyleValue(element as Record<string, unknown>, 'stroke_width') ??
    1;
  const gradientCss = buildGradientCss(getStyleValue(style, 'gradient'));
  const pathPoints = Array.isArray(getStyleValue(element as Record<string, unknown>, 'path_points'))
    ? (getStyleValue(element as Record<string, unknown>, 'path_points') as Array<Record<string, unknown>>)
    : [];
  const fillImage = getStyleValue(element as Record<string, unknown>, 'fill_image');
  const fillImageSrc =
    fillImage && typeof fillImage === 'object' && typeof (fillImage as Record<string, unknown>).src === 'string'
      ? ((fillImage as Record<string, unknown>).src as string)
      : undefined;

  let shapeStyle: Record<string, string | number | undefined> = {
    position: 'absolute',
    left: `${frameStyle.left}px`,
    top: `${frameStyle.top}px`,
    width: `${frameStyle.width}px`,
    height: `${frameStyle.height}px`,
    zIndex: frameStyle.zIndex,
    boxSizing: 'border-box',
    overflow: 'hidden',
    background: typeof gradientCss === 'string' ? gradientCss : undefined,
    backgroundColor: typeof backgroundColor === 'string' ? backgroundColor : undefined,
    border: typeof borderColor === 'string' ? `${borderWidth}px solid ${borderColor}` : undefined,
    backgroundImage: fillImageSrc ? `url(${fillImageSrc})` : undefined,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
  };

  if (pathPoints.length) {
    shapeStyle.clipPath = `polygon(${pathPoints
      .map((point) => `${Number(point.x ?? 0).toFixed(2)}% ${Number(point.y ?? 0).toFixed(2)}%`)
      .join(', ')})`;
  }

  const rotation = typeof element.rotation === 'number' ? element.rotation : 0;
  if (rotation !== 0) {
    const originalWidth = frameStyle.width;
    const originalHeight = frameStyle.height;
    const originalLeft = frameStyle.left;
    const originalTop = frameStyle.top;
    const centerX = originalLeft + originalWidth / 2;
    const centerY = originalTop + originalHeight / 2;
    const newWidth = originalHeight;
    const newHeight = originalWidth;

    shapeStyle = {
      ...shapeStyle,
      width: `${newWidth}px`,
      height: `${newHeight}px`,
      left: `${centerX - newWidth / 2}px`,
      top: `${centerY - newHeight / 2}px`,
      transform: `rotate(${rotation}deg)`,
      transformOrigin: 'center center',
    };
  }

  return `<div style="${styleToString(shapeStyle)}"></div>`;
}

function generateElementHtml(element: TemplateElement): string {
  if (element.type === 'image') {
    return generateImageElementHtml(element);
  }
  if (element.type === 'shape') {
    return generateShapeElementHtml(element);
  }
  return generateTextElementHtml(element);
}

export function generateHtmlFromStructure(structure: TemplateStructure, title?: string): string {
  const canvas = structure.canvas;
  const sortedElements = sortElementsByZIndex(structure.elements);
  const canvasBackground = buildCanvasBackground(canvas as Record<string, unknown>);

  const elementsHtml = sortedElements.map(generateElementHtml).join('\n    ');

  const containerStyle: Record<string, string | number> = {
    position: 'relative',
    width: `${canvas.width}px`,
    height: `${canvas.height}px`,
    background: canvasBackground,
    overflow: 'hidden',
  };

  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title ?? 'Template')}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f5f5f5; }
  </style>
</head>
<body>
  <div style="${styleToString(containerStyle)}">
    ${elementsHtml}
  </div>
</body>
</html>`;
}
