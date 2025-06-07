const form = document.getElementById("extract-form");
const statusEl = document.getElementById("status");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  statusEl.textContent = "Processing… this may take a moment";

  const query = document.getElementById("query").value.trim();
  const columns = document.getElementById("columns").value
    .split(",")
    .map((c) => c.trim())
    .filter(Boolean);

  try {
    const response = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, columns }),
    });

    if (!response.ok) {
      const { detail } = await response.json();
      statusEl.textContent = `❌ ${detail || "Unknown error"}`;
      return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "patent_tables.csv";
    a.click();
    window.URL.revokeObjectURL(url);
    statusEl.textContent = "✅ CSV downloaded!";
  } catch (err) {
    console.error(err);
    statusEl.textContent = "❌ Failed to reach backend";
  }
});