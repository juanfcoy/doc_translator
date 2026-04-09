/* Healthcare Translation QA — Review Page JS
 *
 * Depends on:
 *   - PDF.js 3.11.174 loaded via CDN (window['pdfjs-dist/build/pdf'])
 *   - DOC_NAME, PDF_ORIGINAL_URL, PDF_TRANSLATED_URL injected by the template
 */

(function () {
  "use strict";

  const pdfjsLib = window["pdfjs-dist/build/pdf"];
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

  const SCALE = 1.4;

  /* ── PDF rendering ──────────────────────────────────────── */

  async function renderPDF(url, containerId) {
    let pdf;
    try {
      pdf = await pdfjsLib.getDocument(url).promise;
    } catch (err) {
      const container = document.getElementById(containerId);
      container.innerHTML =
        '<p style="color:#fca5a5;padding:16px;font-size:13px;">Could not load PDF. ' +
        "Make sure the file exists in the translations folder.</p>";
      console.error("PDF load error (" + url + "):", err);
      return;
    }

    const container = document.getElementById(containerId);

    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale: SCALE });

      // Wrapper div for canvas + text layer
      const wrapper = document.createElement("div");
      wrapper.className = "pdf-page-wrapper";
      wrapper.style.width = viewport.width + "px";
      wrapper.style.height = viewport.height + "px";

      // Canvas
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      wrapper.appendChild(canvas);

      // Text layer div
      const textLayerDiv = document.createElement("div");
      textLayerDiv.className = "textLayer";
      textLayerDiv.style.width = viewport.width + "px";
      textLayerDiv.style.height = viewport.height + "px";
      wrapper.appendChild(textLayerDiv);

      container.appendChild(wrapper);

      // Render canvas
      await page.render({
        canvasContext: canvas.getContext("2d"),
        viewport: viewport,
      }).promise;

      // Render text layer
      const textContent = await page.getTextContent();
      pdfjsLib.renderTextLayer({
        textContent: textContent,
        container: textLayerDiv,
        viewport: viewport,
        textDivs: [],
      });
    }
  }

  /* ── Annotation popup ───────────────────────────────────── */

  const popup = document.getElementById("annotation-popup");
  const overlay = document.getElementById("popup-overlay");
  const popupSelection = document.getElementById("popup-selection");
  const popupNote = document.getElementById("popup-note");
  const submitBtn = document.getElementById("popup-submit");
  const cancelBtn = document.getElementById("popup-cancel");
  const feedbackList = document.getElementById("feedback-list");
  const emptyNotice = document.getElementById("feedback-empty");

  let pendingSelection = "";

  function openPopup(selectedText) {
    pendingSelection = selectedText;
    popupSelection.textContent = selectedText;
    popupNote.value = "";
    popup.classList.remove("hidden");
    overlay.classList.remove("hidden");
    popupNote.focus();
  }

  function closePopup() {
    popup.classList.add("hidden");
    overlay.classList.add("hidden");
    pendingSelection = "";
    window.getSelection().removeAllRanges();
  }

  cancelBtn.addEventListener("click", closePopup);
  overlay.addEventListener("click", closePopup);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closePopup();
  });

  /* ── Text selection listener ────────────────────────────── */

  ["pane-original", "pane-translated"].forEach(function (paneId) {
    document.getElementById(paneId).addEventListener("mouseup", function () {
      // Small delay to ensure selection is finalised
      setTimeout(function () {
        const sel = window.getSelection();
        const text = sel ? sel.toString().trim() : "";
        if (text.length > 0) {
          openPopup(text);
        }
      }, 50);
    });
  });

  /* ── Submit feedback ─────────────────────────────────────── */

  submitBtn.addEventListener("click", function () {
    const note = popupNote.value.trim();
    if (!note) {
      popupNote.focus();
      popupNote.style.borderColor = "#ef4444";
      return;
    }
    popupNote.style.borderColor = "";

    submitBtn.disabled = true;
    submitBtn.textContent = "Saving…";

    fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doc_name: DOC_NAME,
        section: pendingSelection.substring(0, 500),
        note: note,
      }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Server error " + res.status);
        return res.json();
      })
      .then(function (data) {
        appendFeedbackItem(pendingSelection.substring(0, 500), note);
        closePopup();
      })
      .catch(function (err) {
        alert("Failed to save feedback: " + err.message);
      })
      .finally(function () {
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit";
      });
  });

  /* ── Add feedback item to sidebar ───────────────────────── */

  function appendFeedbackItem(section, note) {
    if (emptyNotice) emptyNotice.remove();

    const li = document.createElement("li");
    li.className = "feedback-item";

    const now = new Date().toISOString().replace("T", " ").substring(0, 19);

    li.innerHTML =
      '<div class="feedback-section">\u201c' +
      escapeHtml(section.length > 80 ? section.substring(0, 80) + "\u2026" : section) +
      '\u201d</div>' +
      '<div class="feedback-note">' + escapeHtml(note) + "</div>" +
      '<div class="feedback-time">' + now + "</div>";

    feedbackList.appendChild(li);
    li.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ── Enter key submits popup ────────────────────────────── */

  popupNote.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      submitBtn.click();
    }
  });

  /* ── Init ────────────────────────────────────────────────── */

  renderPDF(PDF_ORIGINAL_URL, "pdf-original");
  renderPDF(PDF_TRANSLATED_URL, "pdf-translated");
})();
