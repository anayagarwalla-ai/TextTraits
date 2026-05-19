(function () {
  function parseCsvLine(line) {
    const cells = [];
    let current = "";
    let quoted = false;
    for (let index = 0; index < line.length; index += 1) {
      const char = line[index];
      const next = line[index + 1];
      if (char === '"' && quoted && next === '"') {
        current += '"';
        index += 1;
      } else if (char === '"') {
        quoted = !quoted;
      } else if (char === "," && !quoted) {
        cells.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    cells.push(current.trim());
    return {cells, malformed: quoted};
  }

  function csvCell(cell) {
    let value = String(cell ?? "");
    if (/^[=+\-@]/.test(value.trim())) value = `'${value}`;
    return `"${value.replaceAll('"', '""')}"`;
  }

  window.TextTraitsCsv = {
    parseCsvLine,
    csvCell,
  };
})();
