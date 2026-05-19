(function () {
  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function words(text) {
    return String(text || "").trim().match(/\b[\w'-]+\b/g) || [];
  }

  function percent(value) {
    return `${Math.round(Number(value || 0) * 100)}%`;
  }

  function titleCase(value) {
    return String(value || "")
      .replace(/[-_]/g, " ")
      .replace(/\w\S*/g, (word) => word[0].toUpperCase() + word.slice(1).toLowerCase());
  }

  function localStats(text) {
    const wordList = words(text);
    const punctuation = (text.match(/[^\w\s]/g) || []).length;
    const characters = text.length;
    const sentences = text.split(/[.!?]+/).filter((part) => part.trim()).length || 1;
    const avgSentence = wordList.length ? wordList.length / sentences : 0;
    return {
      words: wordList.length,
      characters,
      sentences,
      punctuation_density: characters ? punctuation / characters : 0,
      reading_level: avgSentence < 12 ? "Plain" : avgSentence < 20 ? "Moderate" : "Dense",
    };
  }

  function todayKey() {
    return new Date().toISOString().slice(0, 10);
  }

  window.TextTraitsUtils = {
    escapeHtml,
    words,
    percent,
    titleCase,
    localStats,
    todayKey,
  };
})();
