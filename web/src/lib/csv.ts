/** Parses CSV text (RFC 4180: quoted fields, doubled quotes, line breaks inside quotes). */
export function parseCsv(text: string, delimiter = ","): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  let fieldStarted = false;
  const source = text.startsWith("﻿") ? text.slice(1) : text;

  const endField = (): void => {
    row.push(field);
    field = "";
    fieldStarted = false;
  };
  const endRow = (): void => {
    endField();
    rows.push(row);
    row = [];
  };

  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (quoted) {
      if (char === '"') {
        if (source[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"' && !fieldStarted) {
      quoted = true;
      fieldStarted = true;
    } else if (char === delimiter) {
      endField();
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && source[i + 1] === "\n") i += 1;
      endRow();
    } else {
      field += char;
      fieldStarted = true;
    }
  }
  if (field !== "" || fieldStarted || row.length > 0) endRow();
  return rows;
}
