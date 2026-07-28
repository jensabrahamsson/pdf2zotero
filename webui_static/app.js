(() => {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const noDoi = document.getElementById("noDoi");
  const progress = document.getElementById("progress");
  const progressText = document.getElementById("progressText");
  const errorEl = document.getElementById("error");
  const result = document.getElementById("result");
  const resultTitle = document.getElementById("resultTitle");
  const resultSource = document.getElementById("resultSource");
  const bibPreview = document.getElementById("bibPreview");
  const pdfPath = document.getElementById("pdfPath");
  const bibPath = document.getElementById("bibPath");
  const downloadBtn = document.getElementById("downloadBtn");
  const copyBtn = document.getElementById("copyBtn");
  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");
  const statusMeta = document.getElementById("statusMeta");
  const outDirHint = document.getElementById("outDirHint");

  let lastResult = null;
  let busy = false;

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove("hidden");
  }

  function clearError() {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
  }

  function setBusy(isBusy) {
    busy = isBusy;
    dropzone.classList.toggle("busy", isBusy);
    dropzone.classList.toggle("disabled", isBusy);
    dropzone.setAttribute("aria-busy", isBusy ? "true" : "false");
    dropzone.tabIndex = isBusy ? -1 : 0;
    fileInput.disabled = isBusy;
    noDoi.disabled = isBusy;
    progress.classList.toggle("hidden", !isBusy);
    progress.setAttribute("aria-hidden", isBusy ? "false" : "true");
    if (isBusy) {
      progressText.textContent = "Reading PDF → GROBID → metadata…";
      result.classList.add("hidden");
    }
  }

  async function refreshHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      if (data.grobid_alive) {
        statusDot.dataset.state = "ok";
        statusText.textContent = "GROBID is online";
      } else {
        statusDot.dataset.state = "bad";
        statusText.textContent = "GROBID is offline — start it before converting";
      }
      statusMeta.textContent = data.grobid_url || "";
      if (data.output_dir) {
        outDirHint.textContent = `Saves to ${data.output_dir}`;
      }
      // Initialize offline checkbox from server default once (not while busy).
      if (!busy && typeof data.no_doi_lookup === "boolean" && !noDoi.dataset.userTouched) {
        noDoi.checked = !!data.no_doi_lookup;
      }
    } catch {
      statusDot.dataset.state = "bad";
      statusText.textContent = "Web UI unreachable";
      statusMeta.textContent = "";
    }
  }

  noDoi.addEventListener("change", () => {
    noDoi.dataset.userTouched = "1";
  });

  function showResult(data) {
    lastResult = data;
    result.classList.remove("hidden");
    resultTitle.textContent = data.bib_filename || "result.bib";
    const offlineNote =
      typeof data.no_doi_lookup === "boolean"
        ? data.no_doi_lookup
          ? " · offline (no doi.org/Crossref)"
          : " · online metadata"
        : "";
    resultSource.textContent = data.source
      ? `Source: ${data.source}${offlineNote}`
      : offlineNote.trim();
    bibPreview.textContent = data.bibtex || "";
    pdfPath.textContent = data.pdf_path || "—";
    bibPath.textContent = data.bib_path || "—";
  }

  async function convertFile(file) {
    if (!file || busy) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showError("Only PDF files are accepted.");
      return;
    }

    clearError();
    setBusy(true);

    const body = new FormData();
    body.append("file", file, file.name);
    // Always send explicit override so server default is never ambiguous.
    body.append("no_doi_lookup", noDoi.checked ? "true" : "false");

    try {
      const res = await fetch("/api/convert", { method: "POST", body });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        const hint = data.hint ? `\n\n${data.hint}` : "";
        throw new Error((data.error || `HTTP ${res.status}`) + hint);
      }
      showResult(data);
    } catch (err) {
      showError(err.message || String(err));
    } finally {
      setBusy(false);
      await refreshHealth();
    }
  }

  dropzone.addEventListener("click", () => {
    if (busy) return;
    fileInput.click();
  });
  dropzone.addEventListener("keydown", (e) => {
    if (busy) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    convertFile(file);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!busy) dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    if (busy) return;
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    convertFile(file);
  });

  // Prevent the browser from opening the PDF if dropped outside the zone.
  ["dragover", "drop"].forEach((evt) => {
    window.addEventListener(evt, (e) => {
      e.preventDefault();
    });
  });

  downloadBtn.addEventListener("click", () => {
    if (!lastResult || !lastResult.bibtex) return;
    const blob = new Blob([lastResult.bibtex], { type: "application/x-bibtex" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = lastResult.bib_filename || "reference.bib";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });

  copyBtn.addEventListener("click", async () => {
    if (!lastResult || !lastResult.bibtex) return;
    try {
      await navigator.clipboard.writeText(lastResult.bibtex);
      copyBtn.textContent = "Copied";
      setTimeout(() => {
        copyBtn.textContent = "Copy BibTeX";
      }, 1400);
    } catch {
      showError("Could not copy to clipboard.");
    }
  });

  refreshHealth();
  setInterval(refreshHealth, 15000);
})();
