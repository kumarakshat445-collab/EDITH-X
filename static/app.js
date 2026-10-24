const app = document.querySelector("#app");
let user = null;

const STATUS = {
  draft: "Draft",
  in_review: "In review",
  changes_requested: "Changes requested",
  approved: "Approved",
  rejected: "Returned",
  published: "Published",
};
const ORIGIN = { employee: "Employee", agency: "Agency", ai_tool: "AI-assisted" };
const CATEGORY = {
  tone: "Tone",
  terminology: "Terminology",
  messaging: "Messaging",
  facts: "Facts",
  claims: "Claims",
  visual: "Visual",
  accessibility: "Accessibility",
};

function h(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "checked" || key === "disabled" || key === "selected") node[key] = Boolean(value);
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function stamp(iso) {
  if (!iso) return "";
  const formatted = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
  return `${formatted} IST`;
}

async function api(path, options = {}) {
  const headers = { "X-Inkloom-Request": "1", ...(options.headers || {}) };
  let body = options.body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  const response = await fetch(path, { method: options.method || "GET", headers, body, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data.detail === "string" ? data.detail : "That request did not succeed.");
    error.status = response.status;
    error.payload = data;
    if (response.status === 401 && !path.startsWith("/api/auth/login")) {
      user = null;
      if (!location.hash.startsWith("#/login")) location.hash = "#/login";
    }
    throw error;
  }
  return data;
}

function parseRoute() {
  const raw = (location.hash || "#/queue").replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  return { name: parts[0] || "queue", id: parts[1] || "", query: new URLSearchParams(query) };
}

function pill(kind, text) {
  return h("span", { class: `pill st-${kind}` }, text);
}

function sev(level) {
  return h("span", { class: `pill sev-${level}` }, level);
}

function shell(active, content, counts = {}) {
  const item = (href, label, key) =>
    h("a", { href, class: active === key ? "on" : "" }, [label, counts[key] ? h("span", { class: "count" }, String(counts[key])) : null]);
  const nav = h("nav", { class: "nav", "aria-label": "Workspace" }, [
    h("div", { class: "nav-group" }, [
      h("p", { class: "nav-label" }, "Desk"),
      item("#/queue", "Queue", "queue"),
      item("#/new", "New review", "new"),
      item("#/insights", "Insights", "insights"),
    ]),
    h("div", { class: "nav-group" }, [
      h("p", { class: "nav-label" }, "Approved sources"),
      item("#/guidelines", "Guidelines", "guidelines"),
      item("#/facts", "Facts", "facts"),
      item("#/terms", "Terminology", "terms"),
      item("#/assets", "Assets", "assets"),
    ]),
    h("div", { class: "nav-group" }, [
      h("p", { class: "nav-label" }, "Control"),
      item("#/team", "Team", "team"),
      user.role === "manager" || user.role === "admin" ? item("#/audit", "Audit", "audit") : null,
      item("#/disclosure", "Disclosure", "disclosure"),
    ]),
  ]);
  const side = h("aside", { class: "sidebar" }, [
    h("a", { class: "brand", href: "#/queue" }, [
      h("span", { class: "mark" }, "Ik"),
      h("span", {}, [h("strong", {}, "Inkloom"), h("span", {}, "Vela Collective")]),
    ]),
    nav,
    h("div", { class: "who" }, [
      h("p", { class: "name" }, user.name),
      h("p", { class: "meta" }, `${user.role} · ${user.affiliation}`),
      h("button", { class: "btn ghost", type: "button", onclick: logout }, "Sign out"),
    ]),
  ]);
  const main = h("main", { class: "main", id: "content" }, [
    h("p", { class: "banner" }, "Reviews stay in this workspace. Inkloom does not send drafts to an external AI service. A person approves publication."),
    content,
  ]);
  app.replaceChildren(h("div", { class: "shell" }, [side, main]));
}

function busy(message) {
  app.replaceChildren(h("main", { class: "main", id: "content" }, h("p", {}, message)));
}

function problem(error) {
  return h("p", { class: "alert", role: "alert" }, error.message || "Something went wrong.");
}

async function ask(options) {
  return new Promise((resolve) => {
    const fields = options.fields || [];
    const inputs = {};
    let dialog;
    const form = h("form", { method: "dialog" }, [
      h("h2", {}, options.title),
      options.body ? h("p", {}, options.body) : null,
      ...fields.map((field) => {
        const control = field.multiline
          ? h("textarea", { name: field.name, required: field.required !== false })
          : h("input", { type: "text", name: field.name, required: field.required !== false });
        inputs[field.name] = control;
        return h("div", { class: "field" }, [h("label", {}, field.label), control]);
      }),
      h("div", { class: "row" }, [
        h("button", { class: "btn ghost", type: "button", onclick: () => dialog.close("cancel") }, "Cancel"),
        h("button", { class: options.danger ? "btn danger" : "btn primary", type: "submit", value: "ok" }, options.confirm || "Confirm"),
      ]),
    ]);
    dialog = h("dialog", {}, form);
    dialog.addEventListener("close", () => {
      const values = {};
      for (const [name, control] of Object.entries(inputs)) values[name] = control.value.trim();
      dialog.remove();
      resolve(dialog.returnValue === "ok" ? values : null);
    });
    document.body.append(dialog);
    dialog.showModal();
    const first = form.querySelector("textarea, input");
    if (first) first.focus();
  });
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  user = null;
  location.hash = "#/login";
}

async function viewLogin() {
  const info = await api("/api/disclosure");
  const error = h("div", {});
  const email = h("input", { type: "email", autocomplete: "username", required: true });
  const password = h("input", { type: "password", autocomplete: "current-password", required: true });
  const form = h("form", { class: "stack", onsubmit: async (event) => {
    event.preventDefault();
    error.replaceChildren();
    try {
      user = (await api("/api/auth/login", { method: "POST", json: { email: email.value, password: password.value } })).user;
      location.hash = "#/queue";
    } catch (err) {
      error.replaceChildren(problem(err));
    }
  } }, [
    h("div", { class: "field" }, [h("label", { for: "email" }, "Email"), email]),
    h("div", { class: "field" }, [h("label", { for: "password" }, "Password"), password]),
    error,
    h("button", { class: "btn primary", type: "submit" }, "Enter the workspace"),
  ]);
  email.id = "email";
  password.id = "password";
  const accounts = h("div", {}, info.demo_accounts.map((account) =>
    h("button", { type: "button", class: "account", onclick: () => {
      email.value = account.email;
      password.value = account.password;
      form.requestSubmit();
    } }, [
      h("strong", {}, `${account.name} · ${account.role}`),
      h("span", {}, `${account.affiliation} · ${account.email}`),
    ]),
  ));
  app.replaceChildren(h("div", { class: "login" }, [
    h("section", { class: "login-copy" }, [
      h("p", { class: "kicker" }, "Inkloom"),
      h("h1", {}, "Review the work before it speaks for the brand."),
      h("p", {}, "Drafts are checked against approved guidelines, facts, terminology, and assets. Every flag explains itself. People still decide what publishes."),
      h("p", {}, h("a", { href: "#/disclosure", style: "color:#f3efe6" }, "How reviews, confidentiality, and AI use work")),
    ]),
    h("section", { class: "login-panel", id: "content" }, [
      h("h2", {}, "Vela Collective demo"),
      h("p", { class: "lede" }, "These are fictional accounts in a local workspace. Choose one to see a creator queue, a review desk, or governance insights."),
      accounts,
      form,
    ]),
  ]));
}

async function viewQueue(route) {
  const status = route.query.get("status") || "";
  const data = await api(`/api/submissions${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  const filters = h("div", { class: "filters" }, [
    h("button", { class: `chip ${status ? "" : "on"}`, onclick: () => { location.hash = "#/queue"; } }, "All"),
    ...Object.keys(STATUS).map((key) =>
      h("button", { class: `chip ${status === key ? "on" : ""}`, onclick: () => { location.hash = `#/queue?status=${key}`; } },
        `${STATUS[key]} ${data.counts[key] || 0}`),
    ),
  ]);
  const body = data.items.length
    ? h("div", { class: "table-wrap" }, h("table", { class: "table" }, [
      h("thead", {}, h("tr", {}, ["Draft", "Status", "Open", "From", "Updated"].map((label) => h("th", {}, label)))),
      h("tbody", {}, data.items.map((item) => h("tr", { class: "clickable", onclick: () => { location.hash = `#/review/${item.id}`; } }, [
        h("td", {}, [
          h("div", { class: "title-cell" }, item.title),
          h("div", { class: "small muted" }, `${item.format} · ${item.channel} · ${ORIGIN[item.origin]}`),
        ]),
        h("td", {}, pill(item.status, STATUS[item.status])),
        h("td", {}, item.open_findings ? [String(item.open_findings), " ", item.highest_severity ? sev(item.highest_severity) : null] : "Clear"),
        h("td", {}, [item.author.name, h("div", { class: "small muted" }, item.author.affiliation)]),
        h("td", { class: "small" }, stamp(item.updated_at)),
      ]))),
    ]))
    : h("div", { class: "card empty" }, "Nothing in this filter. Start a review when a draft is ready.");
  const page = h("section", {}, [
    h("div", { class: "page-head" }, [
      h("div", {}, [h("p", { class: "kicker" }, "Queue"), h("h1", {}, "Before it publishes")]),
      h("a", { class: "btn primary", href: "#/new" }, "New review"),
    ]),
    h("p", { class: "lede" }, "Creators send drafts. Reviewers decide findings. A manager who did not write the piece publishes it."),
    filters,
    body,
  ]);
  shell("queue", page, { queue: data.counts.in_review || "" });
}

async function viewNew() {
  const [samples, assets] = await Promise.all([api("/api/samples"), api("/api/assets")]);
  const error = h("div", {});
  const fields = {
    title: h("input", { type: "text", required: true }),
    format: h("select", {}, ["social", "email", "web", "document", "image"].map((value) => h("option", { value }, value))),
    channel: h("input", { type: "text", required: true, placeholder: "Instagram, retailer email, product FAQ" }),
    purpose: h("input", { type: "text", required: true, placeholder: "What this draft is trying to do" }),
    origin: h("select", {}, Object.entries(ORIGIN).map(([value, label]) => h("option", { value }, label))),
    body: h("textarea", { placeholder: "Paste the draft. For a web page, paste the HTML." }),
    alt_text: h("input", { type: "text", placeholder: "What a person who cannot see the image needs to know" }),
    placement_notes: h("textarea", {}),
    decorative: h("input", { type: "checkbox" }),
    asset_id: h("select", {}, [h("option", { value: "" }, "No specific asset"), ...assets.items.filter((item) => item.status === "approved").map((item) => h("option", { value: String(item.id) }, `${item.name} · ${item.kind}`))]),
    file: h("input", { type: "file" }),
  };
  fields.placement_notes.style.minHeight = "80px";
  const form = h("form", { class: "stack", onsubmit: submit }, [
    h("div", { class: "form-grid" }, [
      field("Title", fields.title),
      field("Format", fields.format),
      field("Channel", fields.channel),
      field("Purpose — kept in every suggestion", fields.purpose),
      field("Where the draft came from", fields.origin),
      field("Approved asset in this piece", fields.asset_id),
    ]),
    field("Draft", fields.body),
    h("div", { class: "form-grid" }, [
      field("Text alternative", fields.alt_text),
      h("div", { class: "field" }, [h("label", { class: "check" }, [fields.decorative, " Decorative image"])]),
    ]),
    field("Placement notes", fields.placement_notes),
    field("Image, document, or PDF", fields.file),
    error,
    h("button", { class: "btn primary", type: "submit" }, "Run governance review"),
  ]);
  const samplesRow = h("div", { class: "row" }, samples.items.map((sample) =>
    h("button", { type: "button", class: "chip", onclick: () => loadSample(sample) }, sample.title),
  ));
  function loadSample(sample) {
    fields.title.value = sample.title;
    fields.format.value = sample.format;
    fields.channel.value = sample.channel;
    fields.purpose.value = sample.purpose;
    fields.origin.value = sample.origin;
    fields.body.value = sample.body;
    fields.alt_text.value = sample.alt_text || "";
    fields.placement_notes.value = sample.placement_notes || "";
  }
  async function submit(event) {
    event.preventDefault();
    error.replaceChildren();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      let created;
      if (fields.file.files[0]) {
        const data = new FormData();
        for (const key of ["title", "format", "channel", "purpose", "origin", "body", "alt_text", "placement_notes"]) data.set(key, fields[key].value);
        data.set("decorative", fields.decorative.checked ? "true" : "false");
        if (fields.asset_id.value) data.set("asset_id", fields.asset_id.value);
        data.set("file", fields.file.files[0]);
        created = await api("/api/submissions/upload", { method: "POST", body: data });
      } else {
        created = await api("/api/submissions", { method: "POST", json: {
          title: fields.title.value,
          format: fields.format.value,
          channel: fields.channel.value,
          purpose: fields.purpose.value,
          origin: fields.origin.value,
          body: fields.body.value,
          alt_text: fields.alt_text.value,
          placement_notes: fields.placement_notes.value,
          decorative: fields.decorative.checked,
          asset_id: fields.asset_id.value ? Number(fields.asset_id.value) : null,
        } });
      }
      location.hash = `#/review/${created.submission.id}`;
    } catch (err) {
      error.replaceChildren(problem(err));
      button.disabled = false;
    }
  }
  shell("new", h("section", {}, [
    h("p", { class: "kicker" }, "New review"),
    h("h1", {}, "Check a draft before it goes out"),
    h("p", { class: "lede" }, "Social, email, web, documents, and images are reviewed here. Nothing is published from this screen. Load a sample or bring your own copy."),
    h("p", { class: "small muted" }, "Samples"),
    samplesRow,
    h("div", { class: "card", style: "margin-top:16px" }, form),
  ]));
}

function field(label, control) {
  return h("div", { class: "field" }, [h("label", {}, label), control]);
}

async function viewReview(route) {
  const revision = route.query.get("revision");
  const data = await api(`/api/submissions/${route.id}${revision ? `?revision_id=${encodeURIComponent(revision)}` : ""}`);
  const sub = data.submission;
  const error = h("div", {});
  const actions = h("div", { class: "row" });
  const addAction = (label, className, task) => {
    actions.append(h("button", { class: className, type: "button", onclick: task }, label));
  };
  if (data.can.submit) addAction("Send to review", "btn primary", () => act("submit", "Send this version to a reviewer?", false));
  if (data.can.request_changes) addAction("Request changes", "btn ghost", () => act("request_changes", "Tell the author what still needs a decision.", true));
  if (data.can.approve) addAction("Approve", "btn primary", () => approve());
  if (data.can.reject) addAction("Return", "btn danger", () => act("reject", "Say why this version should not continue.", true));
  if (data.can.publish) addAction("Publish", "btn primary", () => act("publish", "Publish the approved version. Inkloom will not change the copy.", false));
  if (data.can.retract) addAction("Pull back to draft", "btn danger", () => act("retract", "Why is this published piece returning to draft?", true));
  if (data.can.rereview) addAction("Run review again", "btn ghost", async () => {
    try { location.hash = `#/review/${sub.id}`; await api(`/api/submissions/${sub.id}/review`, { method: "POST" }); render(); }
    catch (err) { error.replaceChildren(problem(err)); }
  });

  async function act(action, message, needsNote) {
    const answer = await ask({ title: STATUS[action] || action, body: message, fields: needsNote ? [{ name: "note", label: "Note", multiline: true }] : [], confirm: "Confirm" });
    if (!answer) return;
    try {
      await api(`/api/submissions/${sub.id}/transition`, { method: "POST", json: { action, note: answer.note || "" } });
      render();
    } catch (err) { error.replaceChildren(problem(err)); }
  }
  async function approve() {
    try {
      let override = "";
      if (data.blocking_ids.length) {
        const answer = await ask({
          title: "High findings are still open",
          body: "Decide them, or record why a person is accepting the risk. The reason is stored on the timeline.",
          fields: [{ name: "reason", label: "Override reason", multiline: true }],
        });
        if (!answer) return;
        override = answer.reason;
      }
      await api(`/api/submissions/${sub.id}/transition`, { method: "POST", json: { action: "approve", override_reason: override } });
      render();
    } catch (err) { error.replaceChildren(problem(err)); }
  }

  const prose = h("div", { class: data.submission.format === "web" ? "prose mono" : "prose" });
  highlight(prose, data.revision.body || "", data.findings);
  const frame = data.submission.format === "web"
    ? h("iframe", { class: "preview-frame", sandbox: "", title: "Rendered draft, scripts disabled" })
    : null;
  if (frame) frame.srcdoc = data.revision.body.replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, "");
  const image = data.revision.file_url && (data.revision.mime || "").startsWith("image/")
    ? h("img", { src: data.revision.file_url, alt: data.revision.alt_text || "" })
    : null;
  const revisionSelect = h("select", { onchange: (event) => { location.hash = `#/review/${sub.id}?revision=${event.target.value}`; } },
    data.revisions.map((item) => h("option", { value: String(item.id), selected: item.id === data.revision.id }, `Revision ${item.id} · ${item.note || "Draft"} · ${stamp(item.created_at)}`)));
  const flow = ["draft", "in_review", "approved", "published"];
  const tracker = h("ol", { class: "tracker" }, flow.map((step) => {
    const index = flow.indexOf(sub.status);
    const here = flow.indexOf(step);
    const className = sub.status === step ? "now" : here < index ? "done" : "";
    return h("li", { class: className }, STATUS[step]);
  }));
  const findings = h("div", { class: "stack", id: "findings" });
  const open = data.findings.filter((item) => item.status === "open");
  const decided = data.findings.filter((item) => item.status !== "open");
  if (!data.findings.length) findings.append(h("div", { class: "card" }, "No findings on this revision. A person still has to approve it before publication."));
  for (const finding of open) findings.append(findingCard(data, finding, error));
  if (decided.length) {
    const closed = h("details", {}, [h("summary", {}, `${decided.length} decided`), h("div", { class: "stack" }, decided.map((item) => findingCard(data, item, error)))]);
    findings.append(closed);
  }
  const comments = h("div", { class: "stack" }, data.comments.map((comment) =>
    h("article", { class: "card" }, [
      h("strong", {}, comment.author.name),
      h("span", { class: "small muted" }, ` ${comment.author.role} · ${stamp(comment.created_at)}`),
      h("p", {}, comment.body),
    ]),
  ));
  const commentBox = h("textarea", {});
  commentBox.style.minHeight = "80px";
  const timeline = h("ol", { class: "timeline" }, data.events.map((event) =>
    h("li", {}, [
      h("strong", {}, event.action.replaceAll("_", " ")),
      h("div", { class: "small muted" }, `${event.actor ? event.actor.name : "Inkloom"} · ${stamp(event.created_at)}`),
      event.detail ? h("div", {}, event.detail) : null,
    ]),
  ));
  const diff = h("div", { class: "diff prose" });
  if (!data.diff.length) diff.append("This is the first revision. A comparison appears when someone edits or applies a suggestion.");
  for (const chunk of data.diff) {
    if (chunk.op === "equal") diff.append(chunk.text);
    else diff.append(h(chunk.op === "delete" ? "del" : "ins", {}, chunk.text));
  }
  const editor = data.can.edit ? editForm(data, error) : h("p", { class: "small muted" }, "This version is locked while a reviewer has it. Editing starts again if they request changes.");
  const meta = data.review || {};
  const page = h("section", {}, [
    h("p", { class: "kicker" }, `${sub.format} · ${sub.channel}`),
    h("div", { class: "page-head" }, [
      h("div", {}, [
        h("h1", {}, sub.title),
        h("p", { class: "lede" }, `Purpose: ${sub.purpose}`),
      ]),
      h("div", {}, [pill(sub.status, STATUS[sub.status]), " ", h("span", { class: `pill origin-${sub.origin}` }, ORIGIN[sub.origin])]),
    ]),
    tracker,
    sub.status === "changes_requested" ? h("p", { class: "callout" }, "A reviewer asked for changes. Save a new revision, then send it back.") : null,
    sub.status === "rejected" ? h("p", { class: "callout" }, "This version was returned. Edit it and send it again when it is ready.") : null,
    sub.origin === "ai_tool" ? h("p", { class: "callout" }, "The author marked this draft as AI-assisted. The review still ran in this workspace, and a person has to approve it.") : null,
    error,
    actions,
    h("div", { class: "split", style: "margin-top:16px" }, [
      h("div", { class: "stack" }, [
        h("label", {}, "Revision"),
        revisionSelect,
        image,
        data.revision.alt_text ? h("p", { class: "small" }, `Text alternative: ${data.revision.alt_text}`) : null,
        data.revision.placement_notes ? h("p", { class: "small" }, `Placement: ${data.revision.placement_notes}`) : null,
        prose,
        frame,
        h("h2", {}, "What changed"),
        diff,
        h("h2", {}, "Edit the draft"),
        editor,
      ]),
      h("div", { class: "stack" }, [
        h("div", { class: "card" }, [
          h("h2", {}, "Findings"),
          h("p", { class: "small muted" }, "Suggestions replace only the flagged words, and only after someone saves a revision. The purpose stays with the author."),
          meta.engine ? h("p", { class: "small" }, `Checked by ${meta.engine}. External services: none. Sources consulted: ${(meta.sources_consulted && Object.values(meta.sources_consulted).reduce((sum, value) => sum + value, 0)) || 0}.`) : null,
          (meta.warnings || []).map((warning) => h("p", { class: "small" }, warning)),
        ]),
        findings,
        h("h2", {}, "Comments"),
        comments,
        h("form", { onsubmit: async (event) => {
          event.preventDefault();
          try {
            await api(`/api/submissions/${sub.id}/comments`, { method: "POST", json: { body: commentBox.value } });
            render();
          } catch (err) { error.replaceChildren(problem(err)); }
        } }, [commentBox, h("button", { class: "btn ghost", type: "submit" }, "Add comment")]),
        h("h2", {}, "History"),
        timeline,
      ]),
    ]),
  ]);
  shell("queue", page);
}

function highlight(container, text, findings) {
  const marks = findings
    .filter((item) => item.status === "open" && item.start_pos != null && item.end_pos != null)
    .sort((a, b) => a.start_pos - b.start_pos);
  let cursor = 0;
  for (const finding of marks) {
    if (finding.start_pos < cursor || finding.end_pos > text.length) continue;
    container.append(text.slice(cursor, finding.start_pos));
    const mark = h("mark", { class: `sev-${finding.severity}`, title: finding.explanation }, text.slice(finding.start_pos, finding.end_pos));
    mark.addEventListener("click", () => {
      const card = document.getElementById(`finding-${finding.id}`);
      if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    container.append(mark);
    cursor = finding.end_pos;
  }
  container.append(text.slice(cursor));
}

function findingCard(data, finding, error) {
  const box = finding.suggestion_mode === "replace"
    ? h("textarea", { class: "suggestion" }, finding.suggestion)
    : h("p", {}, finding.suggestion || "Edit the draft yourself. Inkloom has not rewritten it.");
  const buttons = h("div", { class: "row" });
  if (finding.status === "open" && finding.suggestion_mode === "replace" && data.can.apply) {
    buttons.append(h("button", { class: "btn primary", type: "button", onclick: async () => {
      try {
        await api(`/api/findings/${finding.id}/apply`, { method: "POST", json: { suggestion: box.value } });
        render();
      } catch (err) { error.replaceChildren(problem(err)); }
    } }, "Save this wording as a new revision"));
  }
  if (finding.status === "open" && (data.can.decide_high || !["high", "critical"].includes(finding.severity))) {
    buttons.append(h("button", { class: "btn ghost", type: "button", onclick: () => decide(finding, "dismiss") }, "Dismiss"));
    buttons.append(h("button", { class: "btn ghost", type: "button", onclick: () => decide(finding, "resolve") }, "Mark resolved"));
  }
  if (finding.status !== "open" && (data.can.decide_high || data.submission.author.id === user.id)) {
    buttons.append(h("button", { class: "btn ghost", type: "button", onclick: () => decide(finding, "reopen") }, "Reopen"));
  }
  async function decide(item, action) {
    let note = "";
    if (action !== "reopen") {
      const answer = await ask({
        title: action === "dismiss" ? "Dismiss this finding" : "Mark this finding resolved",
        body: action === "dismiss" ? "Say why the rule should not apply. Repeated dismissals show up as unclear guidelines." : "Say what a person decided, especially for a high finding.",
        fields: [{ name: "note", label: "Note", multiline: true, required: action === "dismiss" }],
      });
      if (!answer) return;
      note = answer.note;
    }
    try {
      await api(`/api/findings/${item.id}/decision`, { method: "POST", json: { action, note } });
      render();
    } catch (err) { error.replaceChildren(problem(err)); }
  }
  const source = finding.source_id
    ? h("a", { href: sourceHref(finding) }, finding.source_label)
    : finding.source_label;
  return h("article", { class: `card finding ${finding.severity}`, id: `finding-${finding.id}` }, [
    h("header", {}, [h("div", {}, [CATEGORY[finding.category] || finding.category, " ", sev(finding.severity)]), pill(finding.status === "open" ? "in_review" : finding.status === "dismissed" ? "rejected" : "approved", finding.status)]),
    finding.excerpt ? h("p", { class: "quote" }, finding.excerpt) : null,
    h("p", {}, finding.explanation),
    h("p", { class: "source" }, ["Source: ", source, finding.confidential_source ? " · confidential" : ""]),
    finding.source_excerpt ? h("p", { class: "small" }, finding.source_excerpt) : null,
    finding.replaces === "sentence" ? h("p", { class: "small muted" }, "This replaces the sentence around the flag.") : null,
    finding.replaces === "append" ? h("p", { class: "small muted" }, "This adds words at the end and leaves the rest of the draft.") : null,
    finding.suggestion_mode === "replace" ? h("p", { class: "small muted" }, "Only the flagged words change. Leave the box empty to delete them, or type your own wording.") : null,
    box,
    finding.decision_note ? h("p", { class: "small" }, `Decision: ${finding.decision_note}`) : null,
    buttons,
  ]);
}

function sourceHref(finding) {
  const map = { guideline: "guidelines", fact: "facts", term: "terms", asset: "assets" };
  const section = map[finding.source_type];
  return section ? `#/${section}/${finding.source_id}` : "#/disclosure";
}

function editForm(data, error) {
  const body = h("textarea", {}, data.revision.body || "");
  const alt = h("input", { type: "text", value: data.revision.alt_text || "" });
  const notes = h("textarea", {}, data.revision.placement_notes || "");
  notes.style.minHeight = "70px";
  const decorative = h("input", { type: "checkbox", checked: data.revision.decorative });
  const note = h("input", { type: "text", placeholder: "What changed, in a few words" });
  return h("form", { class: "card stack", onsubmit: async (event) => {
    event.preventDefault();
    try {
      await api(`/api/submissions/${data.submission.id}/revisions`, { method: "POST", json: {
        body: body.value,
        alt_text: alt.value,
        placement_notes: notes.value,
        decorative: decorative.checked,
        note: note.value,
      } });
      render();
    } catch (err) { error.replaceChildren(problem(err)); }
  } }, [
    field("Draft", body),
    field("Text alternative", alt),
    field("Placement notes", notes),
    h("label", { class: "check" }, [decorative, " Decorative image"]),
    field("Revision note", note),
    h("button", { class: "btn primary", type: "submit" }, "Save as a new revision and review again"),
  ]);
}

async function viewLibrary(kind) {
  const config = {
    guidelines: { path: "/api/guidelines", title: "Guidelines", blurb: "Only approved guidelines are used in reviews. Imports land as drafts until a person approves them." },
    facts: { path: "/api/facts", title: "Approved facts", blurb: "A claim that contradicts a fact is explained with that fact. Expired facts flag outdated copy." },
    terms: { path: "/api/terms", title: "Terminology", blurb: "Preferred words and the words to avoid. A suggestion swaps the avoided word and leaves the sentence." },
    assets: { path: "/api/assets", title: "Assets", blurb: "Colors, logos, and the rules for using them. Confidential assets stay off creator accounts." },
  }[kind];
  const data = await api(config.path);
  const route = parseRoute();
  const selected = data.items.find((item) => String(item.id) === route.id) || null;
  const list = h("div", { class: "library-list" });
  for (const item of data.items) {
    const label = item.title || item.topic || item.preferred || item.name;
    list.append(h("button", { class: selected && selected.id === item.id ? "on" : "", type: "button", onclick: () => { location.hash = `#/${kind}/${item.id}`; } }, [
      label,
      h("div", { class: "small muted" }, `${item.status}${item.confidential ? " · confidential" : ""}`),
    ]));
  }
  const editor = h("div", { class: "card" });
  editor.append(selected ? libraryForm(kind, selected) : h("p", {}, user.role === "creator" ? "Open a source to read it. Creators use approved sources and do not edit them." : "Select a source, or import a draft for someone to approve."));
  const page = h("section", {}, [
    h("p", { class: "kicker" }, "Approved sources"),
    h("div", { class: "page-head" }, [
      h("div", {}, [h("h1", {}, config.title), h("p", { class: "lede" }, config.blurb)]),
      user.role === "manager" || user.role === "admin" ? h("button", { class: "btn primary", type: "button", onclick: () => { editor.replaceChildren(libraryForm(kind, blank(kind))); } }, "New draft") : null,
    ]),
    user.role === "manager" || user.role === "admin" ? importPanel(kind) : null,
    h("div", { class: "library" }, [list, editor]),
  ]);
  shell(kind, page);
}

function blank(kind) {
  if (kind === "guidelines") return { category: "messaging", title: "", body: "", severity: "medium", match_type: "keywords", match_value: "", suggestion: "", good_example: "", bad_example: "", confidential: false, status: "draft" };
  if (kind === "facts") return { topic: "", statement: "", source_label: "", severity: "high", contradicts: [], supports: [], covers: [], suggested: "", replacement: "", confidential: false, status: "draft", effective_on: "", review_after: "" };
  if (kind === "terms") return { preferred: "", avoid: [], definition: "", context: "", severity: "medium", confidential: false, status: "draft" };
  return { name: "", kind: "layout", description: "", usage_rules: "", color_hex: "", do_not: [], allow_natural_color: false, confidential: false, status: "draft" };
}

function lines(value) {
  return (value || "").split("\n").map((part) => part.trim()).filter(Boolean);
}

function libraryForm(kind, item) {
  const error = h("div", {});
  const readOnly = user.role === "creator" || (item.confidential && user.role !== "admin");
  const controls = {};
  const put = (name, control) => { controls[name] = control; return control; };
  let form;
  if (kind === "guidelines") {
    const match = humanMatch(item.match_type, item.match_value);
    form = [
      grid([
        field("Title", put("title", h("input", { type: "text", value: item.title || "" }))),
        field("Category", put("category", h("input", { type: "text", value: item.category || "messaging" }))),
        field("Severity", put("severity", select(["info", "low", "medium", "high", "critical"], item.severity))),
        field("Status", put("status", select(["draft", "approved", "retired"], item.status))),
        field("Match type", put("match_type", select(["keywords", "regex", "claims", "accessibility", "visual", "required_when"], item.match_type))),
      ]),
      field("Rule", put("body", h("textarea", {}, item.body || ""))),
      field("Patterns — one per line, or JSON for claim, visual, accessibility, and messaging rules", put("match_value", h("textarea", {}, match))),
      field("Suggestion shown to authors", put("suggestion", h("input", { type: "text", value: item.suggestion || "" }))),
      grid([
        field("Good example", put("good_example", h("textarea", {}, item.good_example || ""))),
        field("Bad example", put("bad_example", h("textarea", {}, item.bad_example || ""))),
      ]),
    ];
  } else if (kind === "facts") {
    form = [
      grid([
        field("Topic", put("topic", h("input", { type: "text", value: item.topic || "" }))),
        field("Source name", put("source_label", h("input", { type: "text", value: item.source_label || "" }))),
        field("Severity", put("severity", select(["info", "low", "medium", "high", "critical"], item.severity || "high"))),
        field("Status", put("status", select(["draft", "approved", "expired", "retired"], item.status))),
      ]),
      field("Approved statement", put("statement", h("textarea", {}, item.statement || ""))),
      field("Contradicting phrases, one per line. Add | replacement to swap that phrase.", put("contradicts", h("textarea", {}, (item.contradicts || []).map((entry) => typeof entry === "string" ? entry : `${entry.phrase}${entry.replacement ? ` | ${entry.replacement}` : ""}`).join("\n")))),
      field("Supporting phrases, one per line", put("supports", h("textarea", {}, (item.supports || []).join("\n")))),
      field("Safe wording", put("suggested", h("textarea", {}, item.suggested || ""))),
      field("Short replacement for outdated mentions", put("replacement", h("input", { type: "text", value: item.replacement || "" }))),
      field("Claim keys this fact may support, one per line", put("covers", h("textarea", {}, (item.covers || []).join("\n")))),
      grid([
        field("Effective on", put("effective_on", h("input", { type: "text", value: item.effective_on || "" }))),
        field("Review after", put("review_after", h("input", { type: "text", value: item.review_after || "" }))),
      ]),
    ];
  } else if (kind === "terms") {
    form = [
      grid([
        field("Preferred", put("preferred", h("input", { type: "text", value: item.preferred || "" }))),
        field("Severity", put("severity", select(["info", "low", "medium", "high", "critical"], item.severity || "medium"))),
        field("Status", put("status", select(["draft", "approved", "retired"], item.status))),
        field("Context", put("context", h("input", { type: "text", value: item.context || "" }))),
      ]),
      field("Avoid, one per line", put("avoid", h("textarea", {}, (item.avoid || []).join("\n")))),
      field("Definition", put("definition", h("textarea", {}, item.definition || ""))),
    ];
  } else {
    form = [
      item.color_hex ? h("p", {}, [h("span", { class: "swatch", style: `background:${item.color_hex}` }), ` ${item.color_hex}`]) : null,
      item.file_url ? h("img", { src: item.file_url, alt: item.name }) : null,
      grid([
        field("Name", put("name", h("input", { type: "text", value: item.name || "" }))),
        field("Kind", put("kind", select(["color", "logo", "photo", "font", "layout"], item.kind || "layout"))),
        field("Status", put("status", select(["draft", "approved", "retired"], item.status))),
        field("Color", put("color_hex", h("input", { type: "text", value: item.color_hex || "" }))),
      ]),
      field("Description", put("description", h("textarea", {}, item.description || ""))),
      field("Usage rules", put("usage_rules", h("textarea", {}, item.usage_rules || ""))),
      field("Do not, one phrase per line", put("do_not", h("textarea", {}, (item.do_not || []).join("\n")))),
      h("label", { class: "check" }, [put("allow_natural_color", h("input", { type: "checkbox", checked: item.allow_natural_color })), " Allow natural color, such as a packshot"]),
    ];
  }
  const confidential = h("input", { type: "checkbox", checked: Boolean(item.confidential), disabled: user.role !== "admin" });
  const buttons = h("div", { class: "row" });
  if (!readOnly && (user.role === "manager" || user.role === "admin")) {
    buttons.append(h("button", { class: "btn primary", type: "submit" }, item.id ? "Save source" : "Create draft"));
  }
  if (item.id && user.role === "admin" && kind === "guidelines") {
    buttons.append(h("button", { class: "btn danger", type: "button", onclick: async () => {
      const answer = await ask({ title: "Delete this guideline?", body: "Past findings keep their explanation. The rule will not run again.", confirm: "Delete", danger: true, fields: [] });
      if (!answer) return;
      await api(`/api/guidelines/${item.id}`, { method: "DELETE" });
      location.hash = "#/guidelines";
    } }, "Delete"));
  }
  const node = h("form", { onsubmit: async (event) => {
    event.preventDefault();
    error.replaceChildren();
    try {
      const payload = collect(kind, controls, confidential.checked);
      const path = item.id ? `${kindPath(kind)}/${item.id}` : kindPath(kind);
      const saved = await api(path, { method: item.id ? "PATCH" : "POST", json: payload });
      location.hash = `#/${kind}/${saved.id}`;
      render();
    } catch (err) { error.replaceChildren(problem(err)); }
  } }, [...form, user.role === "admin" ? h("label", { class: "check" }, [confidential, " Confidential — hidden from creator accounts"]) : null, error, buttons]);
  if (readOnly) node.querySelectorAll("input, textarea, select").forEach((control) => { control.disabled = true; });
  return node;
}

function kindPath(kind) {
  return { guidelines: "/api/guidelines", facts: "/api/facts", terms: "/api/terms", assets: "/api/assets" }[kind];
}

function humanMatch(type, value) {
  if (!value) return "";
  if (type === "keywords") {
    try { const parsed = JSON.parse(value); if (Array.isArray(parsed)) return parsed.join("\n"); } catch { return value; }
  }
  return value;
}

function collect(kind, controls, confidential) {
  const value = (name) => controls[name].value;
  if (kind === "guidelines") {
    return {
      title: value("title"), category: value("category"), body: value("body"), severity: value("severity"),
      match_type: value("match_type"), match_value: value("match_value"), suggestion: value("suggestion"),
      good_example: value("good_example"), bad_example: value("bad_example"), status: value("status"), confidential,
    };
  }
  if (kind === "facts") {
    return {
      topic: value("topic"), statement: value("statement"), source_label: value("source_label"), severity: value("severity"),
      status: value("status"), suggested: value("suggested"), replacement: value("replacement"), confidential,
      contradicts: lines(value("contradicts")).map((line) => {
        const [phrase, replacement] = line.split("|").map((part) => part.trim());
        return replacement ? { phrase, replacement } : { phrase };
      }),
      supports: lines(value("supports")),
      covers: lines(value("covers")),
      effective_on: value("effective_on"),
      review_after: value("review_after"),
    };
  }
  if (kind === "terms") {
    return {
      preferred: value("preferred"), avoid: lines(value("avoid")), definition: value("definition"),
      context: value("context"), severity: value("severity"), status: value("status"), confidential,
    };
  }
  return {
    name: value("name"), kind: value("kind"), description: value("description"), usage_rules: value("usage_rules"),
    color_hex: value("color_hex"), do_not: lines(value("do_not")), allow_natural_color: controls.allow_natural_color.checked,
    status: value("status"), confidential,
  };
}

function select(options, current) {
  return h("select", {}, options.map((option) => h("option", { value: option, selected: option === current }, option)));
}

function grid(children) {
  return h("div", { class: "form-grid" }, children);
}

function importPanel(kind) {
  const help = {
    guidelines: "Paste markdown. Start each guideline with a heading.",
    facts: "Start each block with FACT:. Optional lines: TOPIC, SOURCE, AVOID, SAY, SEVERITY, CONFIDENTIAL.",
    terms: "Start each block with PREFERRED:. Or paste CSV with the header preferred,avoid,definition.",
    assets: "Start each block with ASSET:. Optional lines: KIND, HEX, RULES, DO NOT.",
  }[kind];
  const text = h("textarea", { placeholder: help });
  const preview = h("div", {});
  let items = [];
  return h("details", { class: "card", style: "margin-bottom:16px" }, [
    h("summary", {}, "Import source material"),
    h("p", { class: "small" }, `${help} Imported records stay drafts until someone approves them.`),
    text,
    h("div", { class: "row" }, [
      h("button", { class: "btn ghost", type: "button", onclick: async () => {
        preview.replaceChildren();
        try {
          const result = await api("/api/import/preview", { method: "POST", json: { kind, text: text.value } });
          items = result.items;
          preview.append(h("p", {}, `${items.length} draft${items.length === 1 ? "" : "s"} ready.`));
          for (const item of items) preview.append(h("p", { class: "small" }, item.title || item.topic || item.preferred || item.name));
        } catch (err) { preview.append(problem(err)); }
      } }, "Preview"),
      h("button", { class: "btn primary", type: "button", onclick: async () => {
        try {
          const result = await api("/api/import/commit", { method: "POST", json: { kind, items } });
          preview.replaceChildren(h("p", {}, `Saved ${result.created} draft${result.created === 1 ? "" : "s"}.`));
          render();
        } catch (err) { preview.append(problem(err)); }
      } }, "Save as drafts"),
    ]),
    preview,
  ]);
}

async function viewInsights() {
  const data = await api("/api/insights?days=90");
  const max = Math.max(1, ...data.by_category.map((item) => item.count));
  const page = h("section", {}, [
    h("p", { class: "kicker" }, data.scope === "yours" ? "Your drafts" : "Workspace"),
    h("h1", {}, "Where the brand keeps slipping"),
    h("div", { class: "stack" }, data.summary.map((line) => h("p", { class: "callout" }, line))),
    h("div", { class: "split" }, [
      h("div", { class: "card" }, [
        h("h2", {}, "By check"),
        h("div", { class: "bars" }, data.by_category.map((item) => h("div", { class: "bar" }, [
          h("span", {}, CATEGORY[item.category] || item.category),
          h("span", {}, h("i", { style: `width:${Math.round((item.count / max) * 100)}%` })),
          h("span", {}, String(item.count)),
        ]))),
      ]),
      h("div", { class: "card" }, [
        h("h2", {}, "Repeated"),
        data.recurring.length ? h("ul", {}, data.recurring.map((item) => h("li", {}, `${item.count}× “${item.excerpt}” · ${item.label}`))) : h("p", {}, "Nothing has repeated yet."),
      ]),
    ]),
    h("div", { class: "card", style: "margin-top:16px" }, [
      h("h2", {}, "Guidelines people dismiss"),
      data.unclear_guidelines.length
        ? h("ul", {}, data.unclear_guidelines.map((item) => h("li", {}, [
          h("a", { href: `#/guidelines/${item.id}` }, item.title),
          ` was dismissed ${item.dismissed} of ${item.total} times.`,
        ])))
        : h("p", {}, "No guideline has a high dismissal rate in this window."),
    ]),
    data.gaps.length ? h("div", { class: "card", style: "margin-top:16px" }, [
      h("h2", {}, "Guidelines that are hard to apply"),
      h("ul", {}, data.gaps.map((item) => h("li", {}, [h("a", { href: `#/guidelines/${item.id}` }, item.title), ` — ${item.reasons.join(", ")}.`]))),
    ]) : null,
    data.repeated_by_author.length ? h("div", { class: "card", style: "margin-top:16px" }, [
      h("h2", {}, "Repeated by author"),
      h("ul", {}, data.repeated_by_author.map((item) => h("li", {}, `${item.name} (${item.affiliation}) · ${item.count}× ${item.label}`))),
    ]) : null,
    h("div", { class: "card", style: "margin-top:16px" }, [
      h("h2", {}, "Where the work came from"),
      h("ul", {}, data.by_origin.map((item) => h("li", {}, `${ORIGIN[item.origin] || item.origin}: ${item.submissions} drafts, ${item.findings} findings`))),
      h("p", { class: "small muted" }, `Window starts ${stamp(data.since)}. Decisions: ${JSON.stringify(data.decisions)}.`),
    ]),
  ]);
  shell("insights", page);
}

async function viewTeam() {
  const data = await api("/api/team");
  const rows = data.items.map((person) => h("tr", {}, [
    h("td", {}, [h("div", { class: "title-cell" }, person.name), h("div", { class: "small muted" }, person.affiliation)]),
    h("td", {}, person.email || "Hidden"),
    h("td", {}, user.role === "admin" && person.id !== user.id
      ? h("select", { onchange: async (event) => {
        await api(`/api/team/${person.id}`, { method: "PATCH", json: { role: event.target.value } });
        render();
      } }, ["creator", "reviewer", "manager", "admin"].map((role) => h("option", { value: role, selected: role === person.role }, role)))
      : person.role),
  ]));
  shell("team", h("section", {}, [
    h("p", { class: "kicker" }, "Roles"),
    h("h1", {}, "Who can decide"),
    h("p", { class: "lede" }, "Creators draft. Reviewers decide high findings and approvals, except on their own work. Managers publish. Admins also hold confidential sources and the audit trail."),
    h("div", { class: "table-wrap" }, h("table", { class: "table" }, [
      h("thead", {}, h("tr", {}, ["Person", "Email", "Role"].map((label) => h("th", {}, label)))),
      h("tbody", {}, rows),
    ])),
  ]));
}

async function viewAudit() {
  const data = await api("/api/audit");
  shell("audit", h("section", {}, [
    h("p", { class: "kicker" }, "Confidentiality"),
    h("h1", {}, "Who opened protected material"),
    h("div", { class: "table-wrap" }, h("table", { class: "table" }, [
      h("thead", {}, h("tr", {}, ["When", "Who", "Action", "Detail"].map((label) => h("th", {}, label)))),
      h("tbody", {}, data.items.map((item) => h("tr", {}, [
        h("td", { class: "small" }, stamp(item.created_at)),
        h("td", {}, item.actor ? item.actor.name : "Unknown"),
        h("td", {}, item.action.replaceAll("_", " ")),
        h("td", {}, item.detail),
      ]))),
    ])),
  ]));
}

async function viewDisclosure() {
  const info = await api("/api/disclosure");
  const page = h("section", {}, [
    h("p", { class: "kicker" }, "How this works"),
    h("h1", {}, "Automation with a person at the end"),
    h("div", { class: "stack" }, [
      h("article", { class: "card" }, [h("h2", {}, "AI and external services"), h("p", {}, info.ai_disclosure)]),
      h("article", { class: "card" }, [h("h2", {}, "Confidential material"), h("p", {}, info.confidentiality)]),
      h("article", { class: "card" }, [h("h2", {}, "Human control"), h("p", {}, info.human_control)]),
      h("article", { class: "card" }, [
        h("h2", {}, "What a review checks"),
        h("ul", {}, [
          "Tone and terminology against approved language",
          "Messaging that is required when a result is mentioned",
          "Facts, including facts that have expired",
          "Promotional claims that no approved fact supports",
          "Logo use, palette distance, and image size",
          "Text alternatives, contrast, type size, link text, and reading grade",
        ].map((line) => h("li", {}, line))),
      ]),
      h("article", { class: "card" }, [
        h("h2", {}, "Formats"),
        h("p", {}, "Social posts, email, web pages (including HTML), documents (.txt, .md, .html, .docx, .pdf), and PNG, JPEG, WebP, or GIF images. SVG uploads are refused because they can carry scripts."),
      ]),
    ]),
  ]);
  if (!user) {
    app.replaceChildren(h("main", { class: "main", id: "content" }, [
      h("p", {}, h("a", { href: "#/login" }, "Back to sign in")),
      page,
    ]));
    return;
  }
  shell("disclosure", page);
}

const views = {
  login: viewLogin,
  queue: viewQueue,
  new: viewNew,
  review: viewReview,
  guidelines: () => viewLibrary("guidelines"),
  facts: () => viewLibrary("facts"),
  terms: () => viewLibrary("terms"),
  assets: () => viewLibrary("assets"),
  insights: viewInsights,
  team: viewTeam,
  audit: viewAudit,
  disclosure: viewDisclosure,
};

async function render() {
  document.querySelectorAll("dialog").forEach((node) => node.remove());
  const route = parseRoute();
  if (!user && route.name !== "login" && route.name !== "disclosure") {
    location.hash = "#/login";
    return;
  }
  if (user && route.name === "login") {
    location.hash = "#/queue";
    return;
  }
  busy("Opening the desk…");
  try {
    await (views[route.name] || viewQueue)(route);
  } catch (error) {
    app.replaceChildren(h("main", { class: "main", id: "content" }, [
      problem(error),
      h("p", {}, h("a", { href: "#/queue" }, "Back to the queue")),
    ]));
  }
}

async function boot() {
  try { user = (await api("/api/me")).user; } catch { user = null; }
  window.addEventListener("hashchange", render);
  if (!location.hash) location.hash = user ? "#/queue" : "#/login";
  else render();
}

boot();
