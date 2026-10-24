const STATUS = {
  draft: "Draft",
  in_review: "In review",
  changes_requested: "Changes requested",
  approved: "Approved",
  published: "Published",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};
const FORMATS = {
  social: "Social post",
  email: "Email",
  web: "Web page",
  ad: "Advertisement",
  document: "Document",
  image: "Image",
};
const STEPS = ["draft", "in_review", "changes_requested", "approved", "published"];

const state = {
  token: localStorage.getItem("inkloom_token") || "",
  user: null,
  users: [],
  route: "queue",
  reviewId: null,
  review: null,
  version: null,
  library: null,
  libraryTab: "guidelines",
  insights: null,
  audit: null,
  disclosure: null,
  queue: [],
  filter: "active",
  query: "",
  error: "",
};

const app = document.getElementById("app");

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function fmtTime(iso) {
  if (!iso) return "";
  const formatted = new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${formatted} IST`;
}

function statusPill(status) {
  return `<span class="status status-${esc(status)}">${esc(STATUS[status] || status)}</span>`;
}

function sevPill(severity) {
  const label = severity === "critical" ? "Critical" : severity === "warning" ? "Warning" : "Note";
  return `<span class="sev sev-${esc(severity)}">${label}</span>`;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.body !== undefined) {
    body = options.body;
  }
  const response = await fetch(path, { method: options.method || "GET", headers, body });
  if (response.status === 401) {
    state.token = "";
    state.user = null;
    localStorage.removeItem("inkloom_token");
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : "The workspace couldn't complete that.");
  }
  return data;
}

function parseRoute() {
  const parts = (location.hash.replace(/^#\/?/, "") || "queue").split("/").filter(Boolean);
  state.route = parts[0] || "queue";
  state.reviewId = state.route === "review" ? parts[1] : null;
}

async function load() {
  state.error = "";
  if (!state.users.length) {
    state.users = (await api("/api/users")).users;
  }
  if (state.token && !state.user) {
    try {
      state.user = (await api("/api/me")).user;
    } catch (error) {
      state.error = error.message;
    }
  }
  if (!state.user) return;
  if (!state.disclosure) state.disclosure = await api("/api/disclosure");
  if (state.route === "queue") state.queue = (await api("/api/reviews")).reviews;
  if (state.route === "review" && state.reviewId) {
    state.review = await api(`/api/reviews/${state.reviewId}`);
    const versions = state.review.versions.map((item) => item.version);
    if (!versions.includes(state.version)) state.version = state.review.submission.current_version;
  }
  if (state.route === "library") state.library = await api("/api/library");
  if (state.route === "insights") state.insights = await api("/api/insights");
  if (state.route === "access") {
    state.disclosure = await api("/api/disclosure");
    if (["manager", "admin"].includes(state.user.role)) {
      try {
        state.audit = await api("/api/audit");
      } catch (error) {
        state.audit = { entries: [], error: error.message };
      }
    }
  }
}

function shell(content) {
  const user = state.user;
  const links = [
    ["queue", "Queue"],
    ["new", "New review"],
    ["library", "Library"],
    ["insights", "Insights"],
    ["access", "Access"],
  ];
  return `
    <div class="shell">
      <aside class="nav">
        <div>
          <p class="wordmark">Inkloom<small>Lumen &amp; Grove</small></p>
        </div>
        <nav aria-label="Workspace">
          ${links.map(([id, label]) => `
            <button class="navlink" data-go="${id}" aria-current="${state.route === id ? "page" : "false"}">${label}</button>
          `).join("")}
        </nav>
        <div class="nav-user">
          <div>
            <strong>${esc(user.name)}</strong>
            <div class="meta">${esc(user.title)}</div>
            <span class="role-pill role-${esc(user.role)}">${esc(user.role)}</span>
          </div>
          <button type="button" data-action="switch">Switch role</button>
        </div>
      </aside>
      <main id="main" class="main">
        ${state.error ? `<div class="error" role="alert">${esc(state.error)}</div>` : ""}
        ${content}
        <p class="footer-note">${esc(state.disclosure.external_services)} Suggestions stay proposals until a person applies them.</p>
      </main>
    </div>
  `;
}

function gate() {
  return `
    <div class="gate">
      <section class="gate-intro">
        <p class="eyebrow">Inkloom</p>
        <h1>Review the work before it represents the brand.</h1>
        <p>Guidelines, facts, and assets stay in this workspace. The checker explains every flag and never publishes on its own.</p>
        <p class="meta">Demo workspace for Lumen &amp; Grove. Pick a role. The server enforces what that role can do.</p>
      </section>
      <section class="gate-people">
        ${state.error ? `<div class="error" role="alert">${esc(state.error)}</div>` : ""}
        <h2>Enter as</h2>
        ${state.users.map((user) => `
          <button class="person" data-action="signin" data-user="${esc(user.id)}">
            <strong>${esc(user.name)}</strong>
            <span class="role-pill role-${esc(user.role)}">${esc(user.role)}</span>
            <span>${esc(user.title)}</span>
          </button>
        `).join("")}
      </section>
    </div>
  `;
}

function queueView() {
  const filtered = state.queue.filter((item) => {
    const haystack = `${item.title} ${item.purpose} ${item.channel}`.toLowerCase();
    if (state.query && !haystack.includes(state.query.toLowerCase())) return false;
    if (state.filter === "active") return ["in_review", "changes_requested", "approved"].includes(item.status);
    if (state.filter === "mine") return item.owner_id === state.user.id || item.assignee_id === state.user.id;
    if (state.filter === "all") return true;
    return item.status === state.filter;
  });
  const criticals = state.queue.reduce((sum, item) => sum + (item.open_counts.critical || 0), 0);
  const waiting = state.queue.filter((item) => item.status === "in_review").length;
  return shell(`
    <p class="eyebrow">Review queue</p>
    <h1>Before it ships</h1>
    <p class="lede">Creators draft. Reviewers decide. Managers publish. Nothing in this list has been changed by the checker on its own.</p>
    <div class="stats">
      <div class="stat card"><strong>${state.queue.length}</strong><span class="meta">Visible reviews</span></div>
      <div class="stat card"><strong>${waiting}</strong><span class="meta">In review</span></div>
      <div class="stat card"><strong>${criticals}</strong><span class="meta">Open critical flags</span></div>
    </div>
    <div class="toolbar">
      <div class="filters" role="group" aria-label="Filter reviews">
        ${[["active", "Active"], ["in_review", "In review"], ["changes_requested", "Changes"], ["approved", "Approved"], ["mine", "Mine"], ["all", "All"]].map(([id, label]) => `
          <button type="button" data-action="filter" data-filter="${id}" aria-pressed="${state.filter === id}">${label}</button>
        `).join("")}
      </div>
      <label style="min-width:220px">Search
        <input id="queue-search" type="search" value="${esc(state.query)}" placeholder="Title or purpose" />
      </label>
    </div>
    <div class="list">
      ${filtered.length ? filtered.map(queueCard).join("") : `<div class="card">Nothing in this filter. Submit a draft from New review, or clear the search.</div>`}
    </div>
  `);
}

function queueCard(item) {
  const counts = item.open_counts || {};
  const chips = ["critical", "warning", "note"]
    .filter((key) => counts[key])
    .map((key) => sevPill(key) + ` ${counts[key]}`)
    .join(" ");
  return `
    <button class="review-link" data-go="review/${esc(item.id)}">
      <div class="row">
        ${statusPill(item.status)}
        <span class="chip">${esc(FORMATS[item.format] || item.format)}</span>
        <span class="meta">${esc(item.channel || "No channel")}</span>
      </div>
      <strong>${esc(item.title)}</strong>
      <div class="meta">${esc(item.purpose)}</div>
      <div class="row meta">
        <span>${esc(item.owner_name)}</span>
        <span>${item.assignee_name ? `Assigned to ${esc(item.assignee_name)}` : "Unassigned"}</span>
        <span>${fmtTime(item.updated_at)}</span>
      </div>
      <div class="counts">${chips || `<span class="meta">No open flags on the current version</span>`}</div>
    </button>
  `;
}

function newView() {
  const reviewers = state.users.filter((user) => ["reviewer", "manager"].includes(user.role));
  return shell(`
    <p class="eyebrow">New review</p>
    <h1>Check a draft before publication</h1>
    <p class="lede">Add the purpose first. Suggestions are written to protect it. Supported files: .txt, .md, .html, PNG, JPEG, WEBP, GIF. PDF is not decoded.</p>
    <form id="new-review" class="card split-form">
      <div class="grid-2">
        <label>Title <input name="title" type="text" required minlength="3" placeholder="Spring launch caption" /></label>
        <label>Format
          <select name="format" id="format-select">
            ${Object.entries(FORMATS).map(([id, label]) => `<option value="${id}">${label}</option>`).join("")}
          </select>
        </label>
      </div>
      <label>Purpose <input name="purpose" type="text" required minlength="8" placeholder="What this piece is trying to do" /></label>
      <div class="grid-2">
        <label>Channel <input name="channel" type="text" placeholder="Instagram, email, site…" /></label>
        <label>Assign a reviewer
          <select name="assignee_id">
            <option value="">Unassigned</option>
            ${reviewers.map((user) => `<option value="${esc(user.id)}">${esc(user.name)} · ${esc(user.title)}</option>`).join("")}
          </select>
        </label>
      </div>
      <label>Asset intent
        <select name="asset_intent">
          <option value="none">Not an image</option>
          <option value="logo">Logo / wordmark</option>
          <option value="graphic">Graphic</option>
          <option value="photo">Photograph</option>
          <option value="decorative">Decorative</option>
        </select>
      </label>
      <label>Alt text <input name="alt_text" type="text" placeholder="Required for meaningful images" /></label>
      <label>Draft <textarea name="body" placeholder="Paste the caption, email, page, or document"></textarea></label>
      <label>Or upload a file <input name="file" type="file" accept=".txt,.md,.html,.htm,.png,.jpg,.jpeg,.webp,.gif" /></label>
      <label class="row"><input type="checkbox" name="send_now" checked style="width:auto" /> Submit for review now</label>
      <div class="row">
        <button class="primary" type="submit">Run the check</button>
      </div>
    </form>
  `);
}

function highlight(text, findings) {
  const marks = findings
    .filter((item) => item.status === "open" && item.span_start != null && item.span_end != null)
    .sort((a, b) => a.span_start - b.span_start);
  let cursor = 0;
  let html = "";
  marks.forEach((mark) => {
    if (mark.span_start < cursor) return;
    html += esc(text.slice(cursor, mark.span_start));
    html += `<mark class="sev-${esc(mark.severity)}" data-go-finding="${esc(mark.id)}">${esc(text.slice(mark.span_start, mark.span_end))}</mark>`;
    cursor = mark.span_end;
  });
  html += esc(text.slice(cursor));
  return html || `<span class="meta">No text on this version.</span>`;
}

function reviewView() {
  const payload = state.review;
  const submission = payload.submission;
  const version = payload.versions.find((item) => item.version === state.version) || payload.versions.at(-1);
  const findings = payload.findings.filter((item) => item.version === version.version);
  const open = findings.filter((item) => item.status === "open");
  const closed = findings.filter((item) => item.status !== "open");
  const perms = payload.permissions;
  const current = version.version === submission.current_version;
  return shell(`
    <button class="ghost" type="button" data-go="queue">Back to queue</button>
    <div class="row" style="margin-top:12px">
      ${statusPill(submission.status)}
      <span class="chip">${esc(FORMATS[submission.format] || submission.format)}</span>
      <span class="meta">${esc(submission.channel || "")}</span>
    </div>
    <h1>${esc(submission.title)}</h1>
    <p class="lede"><strong>Purpose.</strong> ${esc(submission.purpose)}</p>
    <p class="meta">${esc(submission.owner_name)} · ${esc(submission.owner_title)} · ${submission.assignee_name ? `Assigned to ${esc(submission.assignee_name)}` : "Unassigned"} · Updated ${fmtTime(submission.updated_at)}</p>
    <ol class="stepper">
      ${STEPS.map((step) => `<li class="${submission.status === step ? "on" : ""}">${esc(STATUS[step])}</li>`).join("")}
    </ol>
    ${payload.open_critical && current ? `<div class="banner">Open critical findings block approval. Correct them, or a different reviewer can dismiss one with a written reason.</div>` : ""}
    <div class="studio-grid">
      <section class="panel">
        <div class="row">
          <h2>Version ${version.version}</h2>
          ${payload.versions.map((item) => `
            <button type="button" class="ghost" data-action="version" data-version="${item.version}" aria-pressed="${item.version === version.version}">v${item.version}</button>
          `).join("")}
        </div>
        <p class="meta">${esc(version.note)} · ${esc(version.author_name)} · ${fmtTime(version.created_at)}</p>
        ${version.image_path ? `<img id="review-image" alt="${esc(version.alt_text || "Uploaded image")}" />` : ""}
        ${submission.format === "image" ? `<p class="meta">Alt text: ${version.alt_text ? esc(version.alt_text) : "None"}</p>` : ""}
        <div class="content-view">${highlight(version.body || "", findings)}</div>
        ${perms.can_edit && current ? editForm(submission, version) : ""}
      </section>
      <section>
        <h2>${open.length} open</h2>
        <p class="banner">A suggestion is not applied until ${esc(submission.owner_name)} or a manager chooses it. Dismissals are recorded by a different reviewer.</p>
        ${open.length ? open.map((item) => findingCard(item, perms, current)).join("") : `<div class="card">${esc(clearCopy(submission))}</div>`}
        ${closed.length ? `<h3>Decided</h3>${closed.map((item) => findingCard(item, perms, false)).join("")}` : ""}
      </section>
    </div>
    <div class="studio-grid">
      <section class="panel">
        <h2>Comments</h2>
        <ul class="timeline">
          ${payload.comments.map((item) => `
            <li>
              <strong>${esc(item.author_name)}</strong>
              <span class="role-pill role-${esc(item.author_role)}">${esc(item.author_role)}</span>
              <div>${esc(item.body)}</div>
              <div class="meta">${fmtTime(item.created_at)}</div>
            </li>
          `).join("") || `<li class="meta">No comments yet.</li>`}
        </ul>
        <form data-action="comment" class="split-form" style="margin-top:12px">
          <label>Comment <textarea name="body" required minlength="2" placeholder="Say what should change, without rewriting it for them"></textarea></label>
          <button class="primary" type="submit">Add comment</button>
        </form>
      </section>
      <section class="panel">
        <h2>Decision</h2>
        ${decisionPanel(perms, submission)}
        <h3>History</h3>
        <ul class="timeline">
          ${payload.decisions.map((item) => `
            <li>
              <strong>${esc(item.action)}</strong> · ${esc(item.actor_name)}
              <div>${esc(item.note || "")}</div>
              <div class="meta">${fmtTime(item.created_at)}</div>
            </li>
          `).join("") || `<li class="meta">No decisions yet.</li>`}
          ${payload.versions.map((item) => `
            <li>
              <strong>Version ${item.version}</strong> · ${esc(item.author_name)}
              <div>${esc(item.note)}</div>
              <div class="meta">${fmtTime(item.created_at)}</div>
            </li>
          `).join("")}
        </ul>
      </section>
    </div>
  `);
}

function clearCopy(submission) {
  if (submission.status === "published") return "No open issues. A manager has published this version.";
  if (submission.status === "approved") return "No open issues. A reviewer approved this version. A manager can publish it.";
  return "No open issues on this version. A person still has to approve it before publication.";
}

function editForm(submission, version) {
  return `
    <form data-action="revise" class="split-form" style="margin-top:12px">
      <h3>Edit without losing the previous version</h3>
      <label>Content <textarea name="body">${esc(version.body || "")}</textarea></label>
      ${submission.format === "image" ? `<label>Alt text <input name="alt_text" type="text" value="${esc(version.alt_text || "")}" /></label>` : ""}
      <label>Note for the history <input name="note" type="text" placeholder="What changed" /></label>
      <div class="row">
        <button class="ghost" type="submit" name="mode" value="save">Save version</button>
        ${["draft", "changes_requested"].includes(submission.status) ? `<button class="primary" type="submit" name="mode" value="submit">Submit for review</button>` : ""}
      </div>
    </form>
  `;
}

function findingCard(item, perms, actionable) {
  const confidence = item.confidence >= 0.85 ? "High confidence" : "Needs a look";
  const canApply = actionable && perms.can_apply && item.status === "open" && item.apply_mode !== "advisory" && item.replacement != null;
  return `
    <article class="finding" id="finding-${esc(item.id)}">
      <header>
        <h3>${esc(item.title)}</h3>
        ${sevPill(item.severity)}
      </header>
      <div class="meta">${esc(item.category)} · ${confidence} · <code>${esc(item.rule_id)}</code> · ${esc(item.status)}</div>
      ${item.excerpt ? `<p><strong>Flagged:</strong> “${esc(item.excerpt)}”</p>` : ""}
      <p>${esc(item.explanation)}</p>
      <p><strong>Suggestion.</strong> ${esc(item.suggestion)}</p>
      ${item.replacement != null && item.apply_mode !== "advisory" ? `<p class="meta">Proposed change: ${item.replacement === "" ? "remove this" : `“${esc(item.replacement)}”`}</p>` : `<p class="meta">No safe one-step rewrite. Edit the draft so the purpose stays intact.</p>`}
      <div class="source">
        <div>${item.source_confidential ? "Restricted source · " : "Source · "}${esc(item.source_label)}</div>
        ${item.source_restricted ? `<div class="lock">The full source is hidden for this role. A reviewer can open it. The suggestion above is the public correction.</div>` : item.source_body ? `<div>${esc(item.source_body)}</div>` : ""}
      </div>
      ${item.decision_note ? `<p class="meta">Decision: ${esc(item.decision_note)}</p>` : ""}
      ${canApply ? `<button class="primary" type="button" data-action="apply" data-id="${esc(item.id)}">Apply this wording</button>` : ""}
      ${actionable && perms.can_dismiss && item.status === "open" ? `
        <form data-action="dismiss" data-id="${esc(item.id)}" class="split-form">
          <label>Dismiss with a reason another person can audit
            <input name="reason" type="text" required minlength="8" placeholder="Why the original wording should stand" />
          </label>
          <button class="ghost" type="submit">Dismiss finding</button>
        </form>
      ` : ""}
    </article>
  `;
}

function decisionPanel(perms, submission) {
  const assign = ["reviewer", "manager", "admin"].includes(state.user.role) ? `
    <form data-action="assign" class="split-form">
      <label>Assign
        <select name="assignee_id">
          ${state.users.map((user) => `<option value="${esc(user.id)}" ${user.id === submission.assignee_id ? "selected" : ""}>${esc(user.name)} · ${esc(user.role)}</option>`).join("")}
        </select>
      </label>
      <button class="ghost" type="submit">Update assignment</button>
    </form>
  ` : "";
  const decide = perms.can_decide ? `
    <form data-action="decide" class="split-form">
      <label>Note ${perms.needs_warning_note ? "(required while warnings are open)" : ""}
        <textarea name="note" placeholder="What you decided and why"></textarea>
      </label>
      <div class="row">
        <button class="primary" type="submit" name="decision" value="approve" ${perms.blocked_by_critical ? "disabled" : ""}>Approve</button>
        <button class="ghost" type="submit" name="decision" value="request_changes">Request changes</button>
        <button class="danger" type="submit" name="decision" value="reject">Reject</button>
      </div>
      ${perms.blocked_by_critical ? `<p class="meta">Approval stays disabled while a critical finding is open.</p>` : ""}
    </form>
  ` : `<p class="meta">${submission.owner_id === state.user.id ? "You can't approve your own work." : "This role can't decide the current state."}</p>`;
  const publish = perms.can_publish ? `
    <form data-action="publish" class="split-form">
      <label>Publish note <input name="note" type="text" placeholder="Where this is going" /></label>
      <button class="primary" type="submit">Publish</button>
    </form>
  ` : "";
  const withdraw = perms.can_withdraw ? `<button class="ghost" type="button" data-action="withdraw">Withdraw</button>` : "";
  const rerun = `<button class="ghost" type="button" data-action="rerun">Run the check again</button>`;
  return `${decide}${publish}<div class="row">${withdraw}${rerun}</div>${assign}`;
}

function libraryView() {
  const library = state.library;
  const tabs = ["guidelines", "facts", "terms", "assets"];
  const manage = ["manager", "admin"].includes(state.user.role);
  return shell(`
    <p class="eyebrow">Approved sources</p>
    <h1>Library</h1>
    <p class="lede">Reviews cite these records. Confidential material is stored here and shown only to reviewers, managers, and admins.</p>
    <div class="filters" style="margin:12px 0">
      ${tabs.map((tab) => `<button type="button" data-action="tab" data-tab="${tab}" aria-pressed="${state.libraryTab === tab}">${tab}</button>`).join("")}
    </div>
    <div class="list">${libraryItems(library)}</div>
    ${manage ? libraryForms() : `<p class="meta">Only managers and admins add guidelines, facts, terms, and assets.</p>`}
  `);
}

function libraryItems(library) {
  if (state.libraryTab === "guidelines") {
    return library.guidelines.map((item) => `
      <article class="card">
        <div class="row"><strong>${esc(item.code)}</strong><span class="chip">${esc(item.category)}</span>${item.confidential ? `<span class="lock">Confidential</span>` : ""}</div>
        <h3>${esc(item.title)}</h3>
        ${item.redacted ? `<p class="lock">Restricted. The body is not included for your role.</p>` : `<p>${esc(item.body)}</p>`}
      </article>
    `).join("");
  }
  if (state.libraryTab === "facts") {
    return library.facts.map((item) => `
      <article class="card">
        <div class="row"><strong>${esc(item.title)}</strong>${item.confidential ? `<span class="lock">Confidential</span>` : ""}<span class="meta">as of ${esc(item.as_of)}</span></div>
        ${item.redacted ? `<p class="lock">Restricted source. The statement and the figures stay with reviewers.</p>` : `<p>${esc(item.statement)}</p><p class="meta">${esc(item.source)} · ${esc(item.guideline_code)}</p>`}
      </article>
    `).join("");
  }
  if (state.libraryTab === "terms") {
    return library.terms.map((item) => `
      <article class="card">
        <strong>${esc(item.phrase)}</strong> → ${item.replacement ? esc(item.replacement) : "remove"}
        <div class="meta">${esc(item.kind)} · ${esc(item.severity)} · ${esc(item.guideline_code)}</div>
        <p>${esc(item.rationale)}</p>
      </article>
    `).join("");
  }
  return library.assets.map((item) => `
    <article class="card">
      <div class="row">
        ${item.hex ? `<span style="width:18px;height:18px;border-radius:99px;background:${esc(item.hex)};border:1px solid #ccc"></span>` : ""}
        <strong>${esc(item.name)}</strong>
        <span class="chip">${esc(item.kind)}</span>
        ${item.confidential ? `<span class="lock">Confidential</span>` : ""}
      </div>
      ${item.hex ? `<div class="meta">${esc(item.hex)} · ${esc(item.role || "")}</div>` : ""}
      ${item.redacted ? `<p class="lock">Usage notes are restricted.</p>` : `<p>${esc(item.usage_text)}</p>`}
    </article>
  `).join("");
}

function libraryForms() {
  return `
    <div class="studio-grid" style="margin-top:16px">
      <form data-action="add-guideline" class="card split-form">
        <h3>Add a guideline</h3>
        <label>Code <input name="code" required placeholder="VOICE-09" /></label>
        <label>Title <input name="title" required /></label>
        <label>Category
          <select name="category">${["tone","terminology","messaging","visual","accessibility","claims","facts"].map((item) => `<option>${item}</option>`).join("")}</select>
        </label>
        <label>Body <textarea name="body" required minlength="20"></textarea></label>
        <label class="row"><input style="width:auto" type="checkbox" name="confidential" /> Confidential</label>
        <button class="primary" type="submit">Save guideline</button>
      </form>
      <form data-action="add-term" class="card split-form">
        <h3>Add a term</h3>
        <label>Phrase <input name="phrase" required /></label>
        <label>Replacement <input name="replacement" /></label>
        <div class="grid-2">
          <label>Kind <select name="kind"><option>avoid</option><option>banned</option><option>fear</option></select></label>
          <label>Severity <select name="severity"><option>warning</option><option>critical</option><option>note</option></select></label>
        </div>
        <label>Guideline code <input name="guideline_code" required value="TONE-02" /></label>
        <label>Rationale <input name="rationale" required minlength="8" /></label>
        <button class="primary" type="submit">Save term</button>
      </form>
      <form data-action="import-library" class="card split-form">
        <h3>Import a JSON bundle</h3>
        <p class="meta">Keys: guidelines, facts, terms, assets. A starter file is available from the template endpoint.</p>
        <label>Bundle <input name="file" type="file" accept="application/json,.json" required /></label>
        <div class="row">
          <button class="primary" type="submit">Import</button>
          <button class="ghost" type="button" data-action="template">Load template</button>
        </div>
      </form>
      <form data-action="add-fact" class="card split-form">
        <h3>Add an approved fact</h3>
        <label>Title <input name="title" required /></label>
        <label>Statement <textarea name="statement" required minlength="8"></textarea></label>
        <div class="grid-2">
          <label>Source <input name="source" required /></label>
          <label>As of <input name="as_of" required placeholder="2026-03-01" /></label>
        </div>
        <label>Guideline code <input name="guideline_code" required value="FACT-01" /></label>
        <div class="grid-2">
          <label>Check label <input name="label" required placeholder="member count" /></label>
          <label>Value <input name="value" required placeholder="48000" /></label>
        </div>
        <label>Terms that signal this fact, comma-separated <input name="terms" required placeholder="members, users" /></label>
        <label>Unit <input name="unit" placeholder="Leave blank, or %" /></label>
        <label class="row"><input style="width:auto" type="checkbox" name="confidential" /> Confidential</label>
        <button class="primary" type="submit">Save fact</button>
      </form>
      <form data-action="add-asset" class="card split-form">
        <h3>Add an asset or color</h3>
        <label>Name <input name="name" required /></label>
        <label>Kind <input name="kind" required placeholder="color, logo, photography" /></label>
        <label>Hex <input name="hex" placeholder="#1B4332" /></label>
        <label>Usage <textarea name="usage" required minlength="8"></textarea></label>
        <label class="row"><input style="width:auto" type="checkbox" name="confidential" /> Confidential</label>
        <button class="primary" type="submit">Save asset</button>
      </form>
    </div>
  `;
}

function insightsView() {
  const report = state.insights;
  const max = Math.max(1, ...report.by_category.map((item) => item.count));
  return shell(`
    <p class="eyebrow">Governance insights</p>
    <h1>Where the brand keeps slipping</h1>
    <p class="lede">${esc(report.lede)}</p>
    <div class="stats">
      <div class="stat card"><strong>${report.totals.reviews}</strong><span class="meta">Reviews in view</span></div>
      <div class="stat card"><strong>${report.totals.findings}</strong><span class="meta">Distinct findings</span></div>
      <div class="stat card"><strong>${report.suggestion_acceptance.rate == null ? "—" : Math.round(report.suggestion_acceptance.rate * 100) + "%"}</strong><span class="meta">Suggestions people accepted</span></div>
    </div>
    <section class="panel">
      <h2>By category</h2>
      <div class="bars">
        ${report.by_category.map((item) => `
          <div class="bar"><span>${esc(item.category)}</span><i style="width:${Math.round((item.count / max) * 100)}%"></i><span>${item.count}</span></div>
        `).join("") || `<p class="meta">No findings yet.</p>`}
      </div>
    </section>
    <div class="studio-grid">
      <section class="panel">
        <h2>Repeated signals</h2>
        <table>
          <thead><tr><th>Signal</th><th>Count</th><th>Dismissed</th><th>Accepted</th></tr></thead>
          <tbody>
            ${report.rules.map((item) => `<tr><td>${esc(item.title)}<div class="meta">${esc(item.rule_id)}</div></td><td>${item.count}</td><td>${item.dismissed}</td><td>${item.accepted}</td></tr>`).join("")}
          </tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Guidelines that may be unclear</h2>
        ${report.unclear_guidelines.length ? report.unclear_guidelines.map((item) => `
          <article class="card">
            <strong>${esc(item.code)}</strong>
            <div class="meta">${item.count} citations · ${Math.round(item.dismiss_rate * 100)}% dismissed</div>
            ${item.reasons.map((reason) => `<p>${esc(reason)}</p>`).join("")}
          </article>
        `).join("") : `<p class="meta">No guideline is both heavily cited and thin, or often overridden.</p>`}
        ${report.repeated_by_author.length ? `
          <h3>Repeated by author</h3>
          <ul>${report.repeated_by_author.map((item) => `<li>${esc(item.name)} · ${esc(item.rule_id)} · ${item.n}</li>`).join("")}</ul>
        ` : ""}
      </section>
    </div>
    <section class="panel" style="margin-top:16px">
      <h2>Workflow</h2>
      <div class="row">${report.by_status.map((item) => `${statusPill(item.status)} ${item.count}`).join(" ")}</div>
    </section>
  `);
}

function accessView() {
  const info = state.disclosure;
  return shell(`
    <p class="eyebrow">Access and disclosure</p>
    <h1>People decide. The checker explains.</h1>
    <div class="list">
      ${["automation", "external_services", "human_control", "confidentiality", "identity"].map((key) => `
        <article class="card"><h3>${esc(key.replaceAll("_", " "))}</h3><p>${esc(info[key])}</p></article>
      `).join("")}
      <article class="card">
        <h3>Formats</h3>
        <ul>${info.formats.map((item) => `<li><strong>${esc(item.label)}</strong> — ${esc(item.input)}</li>`).join("")}</ul>
        <p class="meta">${esc(info.not_supported)}</p>
      </article>
      <article class="card">
        <h3>Who can do what</h3>
        <table>
          <thead><tr><th>Action</th><th>Creator</th><th>Reviewer</th><th>Manager</th><th>Admin</th></tr></thead>
          <tbody>
            ${[
              ["Create and edit own drafts", "Yes", "No", "Yes", "Yes"],
              ["See confidential sources", "No", "Yes", "Yes", "Yes"],
              ["Comment", "Yes", "Yes", "Yes", "Yes"],
              ["Apply a suggestion", "Own work", "No", "Yes", "Yes"],
              ["Dismiss a finding", "No", "Not own", "Not own", "Not own"],
              ["Approve or request changes", "No", "Not own", "Not own", "Not own"],
              ["Publish", "No", "No", "Not own", "Not own"],
              ["Edit the library", "No", "No", "Yes", "Yes"],
              ["Read the audit log", "No", "No", "Yes", "Yes"],
            ].map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </article>
      ${state.audit ? auditTable() : `<article class="card"><h3>Audit log</h3><p class="meta">Managers and admins can read who opened confidential material and who approved or published.</p></article>`}
    </div>
  `);
}

function auditTable() {
  return `
    <article class="card">
      <h3>Audit log</h3>
      <table>
        <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
        <tbody>
          ${(state.audit.entries || []).map((item) => `
            <tr>
              <td>${fmtTime(item.at)}</td>
              <td>${esc(item.actor_name)}</td>
              <td><code>${esc(item.action)}</code></td>
              <td>${esc(item.detail)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </article>
  `;
}

async function paint(options = {}) {
  const reload = options.reload !== false;
  const searchFocus = document.activeElement && document.activeElement.id === "queue-search";
  const caret = searchFocus ? document.activeElement.selectionStart : null;
  parseRoute();
  if (reload) {
    try {
      await load();
    } catch (error) {
      state.error = error.message;
    }
  }
  let view = "";
  if (!state.user) view = gate();
  else if (state.route === "new") view = newView();
  else if (state.route === "review" && state.review) view = reviewView();
  else if (state.route === "library" && state.library) view = libraryView();
  else if (state.route === "insights" && state.insights) view = insightsView();
  else if (state.route === "access") view = accessView();
  else view = queueView();
  app.innerHTML = view;
  const search = document.getElementById("queue-search");
  if (search) {
    search.addEventListener("input", (event) => {
      state.query = event.target.value;
      paint({ reload: false });
    });
    if (searchFocus) {
      search.focus();
      if (caret != null) search.setSelectionRange(caret, caret);
    }
  }
  await hydrateImage();
}

async function hydrateImage() {
  const image = document.getElementById("review-image");
  if (!image || !state.review) return;
  try {
    const response = await fetch(`/api/reviews/${state.reviewId}/image?version=${state.version}`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!response.ok) return;
    const blob = await response.blob();
    image.src = URL.createObjectURL(blob);
  } catch (_error) {
    image.alt = "The image could not be loaded";
  }
}

async function signIn(userId) {
  const session = await api("/api/session", { method: "POST", json: { user_id: userId } });
  state.token = session.token;
  state.user = session.user;
  localStorage.setItem("inkloom_token", state.token);
  if (location.hash !== "#/queue") location.hash = "#/queue";
  else await paint();
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function onClick(event) {
  const go = event.target.closest("[data-go]");
  if (go) {
    location.hash = `#/${go.dataset.go}`;
    return;
  }
  const finding = event.target.closest("[data-go-finding]");
  if (finding) {
    document.getElementById(`finding-${finding.dataset.goFinding}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  try {
    if (button.dataset.action === "signin") await signIn(button.dataset.user);
    if (button.dataset.action === "switch") {
      state.token = "";
      state.user = null;
      state.review = null;
      localStorage.removeItem("inkloom_token");
      await paint();
    }
    if (button.dataset.action === "filter") {
      state.filter = button.dataset.filter;
      await paint({ reload: false });
    }
    if (button.dataset.action === "tab") {
      state.libraryTab = button.dataset.tab;
      await paint({ reload: false });
    }
    if (button.dataset.action === "version") {
      state.version = Number(button.dataset.version);
      await paint({ reload: false });
    }
    if (button.dataset.action === "apply") {
      state.review = await api(`/api/reviews/${state.reviewId}/findings/${button.dataset.id}/accept`, { method: "POST" });
      state.version = state.review.submission.current_version;
      await paint();
    }
    if (button.dataset.action === "withdraw") {
      state.review = await api(`/api/reviews/${state.reviewId}/withdraw`, { method: "POST" });
      await paint();
    }
    if (button.dataset.action === "rerun") {
      state.review = await api(`/api/reviews/${state.reviewId}/rerun`, { method: "POST" });
      await paint();
    }
    if (button.dataset.action === "template") {
      const template = await api("/api/library/template");
      const blob = new Blob([JSON.stringify(template, null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "inkloom-library-template.json";
      link.click();
    }
  } catch (error) {
    state.error = error.message;
    await paint();
  }
}

async function onSubmit(event) {
  const form = event.target.closest("form");
  if (!form) return;
  event.preventDefault();
  const action = form.dataset.action || form.id;
  try {
    if (action === "new-review") {
      const data = new FormData(form);
      const file = form.file.files[0];
      data.set("submit", form.send_now.checked ? "true" : "false");
      if (file) {
        state.review = await api("/api/reviews/upload", { method: "POST", body: data });
      } else {
        state.review = await api("/api/reviews", {
          method: "POST",
          json: {
            title: data.get("title"),
            format: data.get("format"),
            purpose: data.get("purpose"),
            channel: data.get("channel"),
            alt_text: data.get("alt_text"),
            asset_intent: data.get("asset_intent"),
            assignee_id: data.get("assignee_id") || null,
            body: data.get("body"),
            submit: form.send_now.checked,
          },
        });
      }
      state.version = state.review.submission.current_version;
      location.hash = `#/review/${state.review.submission.id}`;
      return;
    }
    if (action === "revise") {
      const submitter = event.submitter;
      const mode = submitter ? submitter.value : "save";
      const data = formData(form);
      state.review = await api(`/api/reviews/${state.reviewId}/revisions`, {
        method: "POST",
        json: {
          body: data.body,
          alt_text: data.alt_text,
          note: data.note || "",
          submit: mode === "submit",
        },
      });
      state.version = state.review.submission.current_version;
    }
    if (action === "dismiss") {
      const data = formData(form);
      state.review = await api(`/api/reviews/${state.reviewId}/findings/${form.dataset.id}/dismiss`, {
        method: "POST",
        json: { reason: data.reason },
      });
    }
    if (action === "comment") {
      const data = formData(form);
      state.review = await api(`/api/reviews/${state.reviewId}/comments`, {
        method: "POST",
        json: { body: data.body },
      });
    }
    if (action === "decide") {
      const data = formData(form);
      const decision = event.submitter ? event.submitter.value : "request_changes";
      state.review = await api(`/api/reviews/${state.reviewId}/decision`, {
        method: "POST",
        json: { action: decision, note: data.note || "" },
      });
    }
    if (action === "publish") {
      const data = formData(form);
      state.review = await api(`/api/reviews/${state.reviewId}/publish`, {
        method: "POST",
        json: { note: data.note || "" },
      });
    }
    if (action === "assign") {
      const data = formData(form);
      state.review = await api(`/api/reviews/${state.reviewId}/assign`, {
        method: "POST",
        json: { assignee_id: data.assignee_id },
      });
    }
    if (action === "add-fact") {
      const data = formData(form);
      state.library = await api("/api/library/facts", {
        method: "POST",
        json: {
          title: data.title,
          statement: data.statement,
          source: data.source,
          as_of: data.as_of,
          guideline_code: data.guideline_code,
          confidential: Boolean(form.confidential && form.confidential.checked),
          checks: [
            {
              label: data.label,
              value: Number(data.value),
              tolerance: 0,
              terms: data.terms.split(",").map((term) => term.trim()).filter(Boolean),
              unit: data.unit || null,
              min_abs: null,
              max_abs: null,
            },
          ],
        },
      });
    }
    if (action === "add-guideline" || action === "add-term" || action === "add-asset") {
      const data = formData(form);
      const path = {
        "add-guideline": "/api/library/guidelines",
        "add-term": "/api/library/terms",
        "add-asset": "/api/library/assets",
      }[action];
      const payload = { ...data, confidential: Boolean(form.confidential && form.confidential.checked) };
      state.library = await api(path, { method: "POST", json: payload });
    }
    if (action === "import-library") {
      const data = new FormData();
      data.append("file", form.file.files[0]);
      state.library = await api("/api/library/import", { method: "POST", body: data });
    }
    await paint();
  } catch (error) {
    state.error = error.message;
    await paint();
  }
}

app.addEventListener("click", (event) => {
  onClick(event);
});
app.addEventListener("submit", (event) => {
  onSubmit(event);
});
window.addEventListener("hashchange", () => {
  state.review = null;
  paint();
});
paint();
