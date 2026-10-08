#!/usr/bin/env bash
# Пересборка PDF документации из documentation.html (headless Google Chrome).
# Использование: bash docs/build_pdf.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/documentation.html"
OUT="$HERE/FSP-documentation.pdf"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME" ]; then
  CHROME="$(command -v google-chrome || command -v chromium || true)"
fi
if [ -z "$CHROME" ]; then
  echo "Не найден Google Chrome / Chromium — установите его или сконвертируйте HTML в PDF другим способом." >&2
  exit 1
fi

"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$OUT" "file://$SRC"

echo "OK: $OUT"
