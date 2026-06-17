// Goodwill Gold — front-end logic
// Keeps state across iterative re-submits: photos accumulate, and the accessories
// answer is remembered once given, so the backend can advance to pricing.

const MAX_EDGE = 1280; // px — resize cap before base64 to keep payloads small
const JPEG_QUALITY = 0.8;

const state = {
  images: [], // base64 data URLs
  accessoriesIncluded: null, // null | true | false
};

const $ = (id) => document.getElementById(id);
const els = {
  captureCard: $("capture-card"),
  camera: $("camera"),
  thumbs: $("thumbs"),
  makeModel: $("make-model"),
  notes: $("notes"),
  analyzeBtn: $("analyze-btn"),
  followupCard: $("followup-card"),
  followupTitle: $("followup-title"),
  followupBody: $("followup-body"),
  accessoryButtons: $("accessory-buttons"),
  followupContinue: $("followup-continue"),
  resultCard: $("result-card"),
  loading: $("loading"),
  loadingText: $("loading-text"),
  error: $("error"),
};

// ---- Image capture + resize ------------------------------------------------
els.camera.addEventListener("change", async (e) => {
  const files = Array.from(e.target.files || []);
  for (const file of files) {
    try {
      const dataUrl = await resizeToDataUrl(file);
      state.images.push(dataUrl);
    } catch (err) {
      showError("Couldn't read that photo. Try again.");
    }
  }
  els.camera.value = ""; // allow re-selecting the same file
  renderThumbs();
});

function resizeToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => {
      img.onerror = reject;
      img.onload = () => {
        let { width, height } = img;
        const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
        width = Math.round(width * scale);
        height = Math.round(height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        canvas.getContext("2d").drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL("image/jpeg", JPEG_QUALITY));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

function renderThumbs() {
  els.thumbs.innerHTML = "";
  state.images.forEach((src, i) => {
    const wrap = document.createElement("div");
    wrap.className = "thumb";
    const img = document.createElement("img");
    img.src = src;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.textContent = "×";
    rm.setAttribute("aria-label", "Remove photo");
    rm.onclick = () => {
      state.images.splice(i, 1);
      renderThumbs();
    };
    wrap.append(img, rm);
    els.thumbs.appendChild(wrap);
  });
}

// ---- Analyze flow ----------------------------------------------------------
els.analyzeBtn.addEventListener("click", () => analyze());
els.followupContinue.addEventListener("click", () => analyze());

els.accessoryButtons.querySelectorAll("button").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.accessoriesIncluded = btn.dataset.acc === "yes";
    analyze();
  });
});

async function analyze() {
  const makeModel = els.makeModel.value.trim();
  if (state.images.length === 0 && !makeModel) {
    showError("Add a photo or type a make/model first.");
    return;
  }
  hide(els.error);
  hide(els.followupCard);
  hide(els.resultCard);
  show(els.loading);
  els.loadingText.textContent =
    state.accessoriesIncluded === null
      ? "Identifying & searching the lines…"
      : "Pricing it out…";

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        images: state.images,
        make_model: makeModel || null,
        notes: els.notes.value.trim() || null,
        accessories_included: state.accessoriesIncluded,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Something went wrong.");

    if (data.status === "need_more_info") {
      renderFollowUp(data);
    } else {
      renderResult(data);
    }
  } catch (err) {
    showError(err.message || "Request failed.");
  } finally {
    hide(els.loading);
  }
}

// ---- Render: follow-up -----------------------------------------------------
function renderFollowUp(data) {
  const fu = data.follow_ups || {};
  els.followupBody.innerHTML = "";

  const itemLine = document.createElement("p");
  itemLine.className = "sub";
  itemLine.textContent = `Looks like: ${data.item?.title || "this item"}`;
  els.followupBody.appendChild(itemLine);

  if (fu.photos) {
    els.followupTitle.textContent = "Add a couple more photos";
    const msg = document.createElement("p");
    msg.textContent = fu.photos.message || "More photos would help me grade it.";
    els.followupBody.appendChild(msg);
    const ul = document.createElement("ul");
    (fu.photos.requested_angles || []).forEach((a) => {
      const li = document.createElement("li");
      li.textContent = a;
      ul.appendChild(li);
    });
    els.followupBody.appendChild(ul);
    show(els.followupContinue);
    hide(els.accessoryButtons);
    show(els.captureCard); // keep capture visible so the user can add the photos
  } else if (fu.accessories) {
    els.followupTitle.textContent = "Quick question";
    const q = document.createElement("p");
    q.textContent = fu.accessories.question;
    els.followupBody.appendChild(q);
    if ((fu.accessories.items_to_check || []).length) {
      const ul = document.createElement("ul");
      fu.accessories.items_to_check.forEach((a) => {
        const li = document.createElement("li");
        li.textContent = a;
        ul.appendChild(li);
      });
      els.followupBody.appendChild(ul);
    }
    show(els.accessoryButtons);
    hide(els.followupContinue);
    hide(els.captureCard); // accessories-only: just need the yes/no answer
  }
  show(els.followupCard);
  els.followupCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- Render: result --------------------------------------------------------
function fmtMoney(n, currency) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `$${Math.round(n)}`;
  }
}

function renderResult(data) {
  const cur = data.currency || "USD";
  const pr = data.price_range || {};
  const v = data.verdict || {};
  const cond = data.condition || {};

  // Verdict tone based on where fair sits relative to walk_over.
  let tone = "fair";
  if (typeof v.buy_under === "number") tone = "steal";
  const banner = `
    <div class="verdict-banner ${tone}">
      <div class="one-liner">${escapeHtml(v.one_liner || "See prices below")}</div>
    </div>`;

  const tiers = `
    <div class="tiers">
      <div class="tier steal"><div class="label">Steal at</div><div class="value">${fmtMoney(pr.steal_deal, cur)}</div></div>
      <div class="tier fair"><div class="label">Fair</div><div class="value">${fmtMoney(pr.fair_market, cur)}</div></div>
      <div class="tier top"><div class="label">Top resale</div><div class="value">${fmtMoney(pr.top_resale, cur)}</div></div>
    </div>`;

  const condPct = cond.confidence != null ? ` · ${Math.round(cond.confidence * 100)}% sure` : "";
  const buyWalk = [];
  if (typeof v.buy_under === "number") buyWalk.push(`Buy under ${fmtMoney(v.buy_under, cur)}`);
  if (typeof v.walk_over === "number") buyWalk.push(`Walk over ${fmtMoney(v.walk_over, cur)}`);
  const meta = `
    <div class="meta-row">
      <span><span class="badge">${escapeHtml(prettyGrade(cond.grade))}</span>${condPct}</span>
      <span>${buyWalk.map(escapeHtml).join(" · ")}</span>
    </div>`;

  const sources = (data.sources || []).filter((s) => s.url);
  let sourcesHtml = "";
  if (sources.length) {
    const items = sources
      .map(
        (s) => `
        <a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">
          ${escapeHtml(s.title || s.url)}
          <div class="src-meta">${escapeHtml(s.marketplace || "")}${
            s.price ? " · " + escapeHtml(s.price) : ""
          }</div>
        </a>`
      )
      .join("");
    sourcesHtml = `<div class="sources"><h3>Comps &amp; sources</h3>${items}</div>`;
  }

  els.resultCard.innerHTML = `
    <h2>${escapeHtml(data.item?.title || "Result")}</h2>
    <p class="sub">${escapeHtml(data.item?.brand || "")} ${escapeHtml(data.item?.model || "")}</p>
    ${banner}
    ${tiers}
    ${meta}
    ${cond.rationale ? `<p class="sub">${escapeHtml(cond.rationale)}</p>` : ""}
    ${sourcesHtml}
    <button class="again-btn" type="button" id="reset-btn">Scan another item</button>
  `;
  $("reset-btn").addEventListener("click", resetAll);
  hide(els.captureCard); // declutter — verdict is the focus
  hide(els.followupCard);
  show(els.resultCard);
  els.resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetAll() {
  state.images = [];
  state.accessoriesIncluded = null;
  els.makeModel.value = "";
  els.notes.value = "";
  renderThumbs();
  hide(els.resultCard);
  hide(els.followupCard);
  show(els.captureCard);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---- Helpers ---------------------------------------------------------------
function prettyGrade(g) {
  if (!g) return "Condition?";
  return g.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }
function showError(msg) {
  els.error.textContent = msg;
  show(els.error);
  setTimeout(() => hide(els.error), 4500);
}
function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
function escapeAttr(s) {
  return escapeHtml(s);
}

// ---- PWA service worker ----------------------------------------------------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}
