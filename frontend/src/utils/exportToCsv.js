// Plain CSV, not a real .xlsx -- Excel opens CSV natively (double-click,
// no import wizard needed for a simple flat table), and it avoids adding a
// spreadsheet-writing dependency for what's otherwise a one-line export.
function csvEscape(value) {
  const str = value === null || value === undefined ? "" : String(value);
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function exportToCsv(filename, rows, columns) {
  const header = columns.map((c) => csvEscape(c.label)).join(",");
  const body = rows
    .map((row) => columns.map((c) => csvEscape(c.value(row))).join(","))
    .join("\n");
  // Leading BOM so Excel (Windows especially) detects UTF-8 correctly
  // instead of misreading non-ASCII characters.
  const blob = new Blob(["﻿" + header + "\n" + body], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
