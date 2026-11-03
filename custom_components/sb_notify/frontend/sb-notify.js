/* SB Notify — the sidebar page (/sb-notify).
 *
 * Three lists: open alerts (worst first; dismissed ones dimmed, with when they come back),
 * live notifications (with when they clear) and recently resolved alerts. It reads the
 * attributes of sensor.sb_notify_alerts and sensor.sb_notify_notifications and acts through
 * the sb_notify services, so the integration needs no API of its own for it.
 *
 * Row style: window.SBKit from the SB UI Kit integration (a manifest dependency).
 */
const VERSION = "0.3.0";

const kit = () => (window.SBKit && window.SBKit.api >= 1 ? window.SBKit : null);
let kitPromise = null;
const whenKit = () => kitPromise || (kitPromise = new Promise((resolve) => {
  if (kit()) { resolve(kit()); return; }
  const on = () => { if (kit()) { window.removeEventListener("sb-ui-kit-ready", on); resolve(kit()); } };
  window.addEventListener("sb-ui-kit-ready", on);
  // Same retry as the other SB pages: a page opened while HA restarts can miss the kit.
  setTimeout(() => { if (!kit()) import(`/sb_ui_kit_static/sb-ui-kit.js?v=retry-${Date.now()}`).then(on, () => {}); }, 3000);
  setTimeout(() => resolve(kit()), 15000);
}));

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SEV = {
  critical: { ico: "bad", icon: "mdi:alert-octagon" },
  warning: { ico: "warn", icon: "mdi:alert" },
  info: { ico: "idle", icon: "mdi:information-outline" },
};

// "21:52" today, "Nov 2 21:52" otherwise.
const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso), now = new Date();
  const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === now.toDateString() ? hm : `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${hm}`;
};
// 17 d · 5 h · 12 min
const span = (from, to) => {
  const m = Math.max(0, Math.round((new Date(to) - new Date(from)) / 60000));
  return m >= 2880 ? `${Math.round(m / 1440)} d` : m >= 120 ? `${Math.round(m / 60)} h` : `${m} min`;
};
const dot = `<span class="sbk-dot"></span>`;
const line = (...parts) => parts.filter(Boolean).join(dot);

const STYLE = `
:host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color); }
.bar { display: flex; align-items: center; gap: 4px; height: var(--header-height, 56px); padding: 0 12px; box-sizing: border-box; position: sticky; top: 0; z-index: 2;
       background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); border-bottom: 1px solid var(--divider-color); }
.title { font-size: 20px; flex: 1; margin-left: 4px; }
.bar a { color: inherit; font-size: 14px; opacity: .85; text-decoration: none; padding: 6px 10px; border-radius: 14px; }
.bar a:hover { background: rgba(127,127,127,.2); opacity: 1; }
.page { padding: 16px; } .col, .body { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.body { width: 100%; }
ha-card { position: relative; }
a.sbk-open { text-decoration: none; }
.sbk-row .sbk-open.nolink { cursor: default; }
.sev { text-transform: capitalize; }
.sev.critical { background: color-mix(in srgb, var(--error-color, #db4437) 18%, transparent); color: var(--error-color, #db4437); }
.sev.warning { background: color-mix(in srgb, var(--warning-color, #ffa600) 20%, transparent); color: var(--warning-color, #ffa600); }
.sev.info { background: color-mix(in srgb, var(--primary-text-color) 8%, transparent); color: var(--secondary-text-color); }
.more { display: block; width: 100%; padding: 12px 16px; border: none; border-top: 1px solid var(--divider-color); background: none;
        color: var(--primary-color); font: inherit; font-size: 14px; text-align: left; cursor: pointer; }
.err { color: var(--error-color); font-size: 13px; padding: 8px 16px; border-top: 1px solid var(--divider-color); }
.ver { color: var(--secondary-text-color); font-size: 12px; margin: 0 4px; }
`;

class SbNotifyPanel extends HTMLElement {
  constructor() {
    super();
    this._menu = null;        // "a:<key>" | "n:<key>" | "head" — the open ⋮ menu
    this._allRecent = false;
    this._error = "";
  }
  set hass(h) {
    const prev = this._hass;
    this._hass = h;
    if (!this.shadowRoot) this._build();
    if (this._menuEl) this._menuEl.hass = h;
    const a = this._st("alerts"), n = this._st("notifications");
    if (!prev || a !== this._a || n !== this._n) { this._a = a; this._n = n; this._render(); }
  }
  set narrow(v) { this._narrow = v; if (this._menuEl) this._menuEl.narrow = v; }
  set route(_v) {}
  set panel(_v) {}

  connectedCallback() { this._tick = setInterval(() => this._render(), 60000); }   // keep "in 12 min" honest
  disconnectedCallback() { clearInterval(this._tick); this._unMenu?.(); }

  _st(kind) {
    const s = this._hass?.states || {};
    return s[`sensor.sb_notify_${kind}`] || Object.values(s).find((x) => x.entity_id.startsWith(`sensor.sb_notify_${kind}`));
  }

  _build() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style>
      <div class="bar"><ha-menu-button></ha-menu-button><div class="title">SB Notify</div>
        <a href="/config/integrations/integration/sb_notify">Settings</a></div>
      <div class="page"><div class="col"><div class="body"><div class="sbk-wait">Loading…</div></div>
        <div class="ver">SB Notify ${VERSION}</div></div></div>`;
    this._menuEl = root.querySelector("ha-menu-button");
    this._menuEl.narrow = this._narrow;
    whenKit().then((k) => {
      if (k?.sheet) root.adoptedStyleSheets = [...root.adoptedStyleSheets, k.sheet];
      this._render();
    });
  }

  _render() {
    const root = this.shadowRoot, k = kit();
    if (!root || !this._hass) return;
    const body = root.querySelector(".body");
    if (!k) { body.innerHTML = `<div class="sbk-wait">Waiting for SB UI Kit…</div>`; return; }
    const a = this._a, n = this._n;
    if (!a) { body.innerHTML = `<ha-card><div class="sbk-empty">The SB Notify sensors are not there. Is the integration set up?</div></ha-card>`; return; }
    const alerts = a.attributes.alerts || [], recent = a.attributes.recent || [], notes = n?.attributes.notifications || [];
    const openN = alerts.filter((x) => x.state === "open").length, crit = alerts.filter((x) => x.severity === "critical").length;
    const counts = alerts.length ? [`${alerts.length} open`, crit ? `${crit} critical` : "", alerts.length - openN ? `${alerts.length - openN} dismissed` : ""].filter(Boolean).join(" · ") : "";
    const menu = (id, items) => this._menu === id ? k.menu("Actions", items) : "";
    const kb = (id, label) => `<button class="sbk-kb ${this._menu === id ? "on" : ""}" data-menu="${esc(id)}" aria-label="${esc(label)}" aria-expanded="${this._menu === id}">${k.kbIcon}</button>`;
    const open = (url, inner) => url ? `<a class="sbk-open" href="${esc(url)}" target="_blank" rel="noopener">${inner}</a>` : `<div class="sbk-open nolink">${inner}</div>`;

    const alertRow = (x) => {
      const s = SEV[x.severity] || SEV.warning, dismissed = x.state === "dismissed", id = `a:${x.key}`;
      const third = dismissed
        ? `<div class="sbk-m">Dismissed${x.severity === "info" ? "" : ` · ${x.returns_at ? `back ${when(x.returns_at)} if still open` : "back only if it gets worse"}`}</div>`
        : x.message ? `<div class="sbk-m ${x.severity === "critical" ? "bad" : x.severity === "warning" ? "warn" : ""}">${esc(x.message)}</div>` : "";
      const msg = dismissed && x.message ? `<div class="sbk-m">${esc(x.message)}</div>` : "";
      return `<div class="sbk-row ${dismissed ? "off" : ""}">${open(x.url, `
          <div class="sbk-ico ${s.ico}"><ha-icon icon="${s.icon}"></ha-icon></div>
          <div class="sbk-txt"><div class="sbk-t">${esc(x.title)}</div>
            <div class="sbk-s"><span class="sbk-chip sev ${esc(x.severity)}">${esc(x.severity)}</span>${dot}${line(esc(x.source || ""), `since ${when(x.first_seen)}`, x.count > 1 ? `${x.count.toLocaleString()} times` : "")}</div>
            ${third}${msg}</div>`)}
        ${kb(id, `Actions for ${x.title}`)}
        ${menu(id, [
          ...(dismissed ? [] : [{ act: `dismiss|${x.key}`, icon: "mdi:bell-off-outline", label: "Dismiss" }]),
          { act: `resolve|${x.key}`, icon: "mdi:check-circle-outline", label: "Mark resolved" },
          ...(x.url ? [{ act: `url|${x.url}`, icon: "mdi:open-in-new", label: "Open link" }] : []),
        ])}</div>`;
    };
    const noteRow = (x) => {
      const id = `n:${x.key}`;
      return `<div class="sbk-row dense">${open(x.url, `
          <div class="sbk-ico idle sm"><ha-icon icon="mdi:bell-outline"></ha-icon></div>
          <div class="sbk-txt"><div class="sbk-t">${esc(x.title)}</div>
            <div class="sbk-s">${line(x.message ? esc(x.message) : "", `posted ${when(x.posted_at)}`, x.expires_at ? `clears ${when(x.expires_at)}` : "until cleared")}</div></div>`)}
        ${kb(id, `Actions for ${x.title}`)}
        ${menu(id, [{ act: `clear|${x.key}`, icon: "mdi:close-circle-outline", label: "Clear" },
                    ...(x.url ? [{ act: `url|${x.url}`, icon: "mdi:open-in-new", label: "Open link" }] : [])])}</div>`;
    };
    const recentRow = (x) => `<div class="sbk-row dense"><div class="sbk-open nolink">
        <div class="sbk-ico run sm"><ha-icon icon="mdi:check"></ha-icon></div>
        <div class="sbk-txt"><div class="sbk-t">${esc(x.title)}</div>
          <div class="sbk-s"><span class="sbk-chip sev ${esc(x.severity)}">${esc(x.severity)}</span>${dot}${line(esc(x.source || ""), `resolved ${when(x.resolved_at)}`, `open ${span(x.first_seen, x.resolved_at)}`, x.resolve_message ? esc(x.resolve_message) : "")}</div></div></div></div>`;
    const shown = this._allRecent ? recent : recent.slice(0, 5);

    body.innerHTML = `
      <ha-card>
        <div class="sbk-hwrap"><div class="sbk-head"><h2>Alerts</h2><span class="sbk-count">${counts}</span>${kb("head", "More")}</div>
          ${menu("head", [{ act: "test|alert", icon: "mdi:alert-outline", label: "Send a test alert" },
                          { act: "test|notice", icon: "mdi:bell-outline", label: "Send a test notification" }])}</div>
        ${alerts.length ? alerts.map(alertRow).join("") : `<div class="sbk-empty">Nothing is open.</div>`}
        ${this._error ? `<div class="err">${esc(this._error)}</div>` : ""}
      </ha-card>
      <ha-card>
        <div class="sbk-head"><h2>Notifications</h2><span class="sbk-count">${notes.length || ""}</span></div>
        ${notes.length ? notes.map(noteRow).join("") : `<div class="sbk-empty">None on the phone.</div>`}
      </ha-card>
      ${recent.length ? `<ha-card>
        <div class="sbk-head"><h2>Recently resolved</h2><span class="sbk-count">${recent.length}</span></div>
        ${shown.map(recentRow).join("")}
        ${recent.length > 5 ? `<button class="more">${this._allRecent ? "Show fewer" : `Show all ${recent.length}`}</button>` : ""}
      </ha-card>` : ""}`;

    body.querySelectorAll("[data-menu]").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault(); e.stopPropagation();
      this._setMenu(this._menu === b.dataset.menu ? null : b.dataset.menu);
    }));
    body.querySelectorAll(".sbk-menu button").forEach((b) => b.addEventListener("click", () => this._act(b.dataset.act)));
    body.querySelector(".more")?.addEventListener("click", () => { this._allRecent = !this._allRecent; this._render(); });
  }

  _setMenu(id) {
    this._unMenu?.();
    this._menu = id;
    if (id) { const off = kit().away(() => this._setMenu(null)); this._unMenu = () => { off(); this._unMenu = null; }; }
    this._render();
  }

  async _act(act) {
    const i = act.indexOf("|"), verb = act.slice(0, i), arg = act.slice(i + 1);
    this._setMenu(null);
    if (verb === "url") { window.open(arg, "_blank", "noopener"); return; }
    const call = {
      dismiss: ["dismiss", { key: arg }],
      resolve: ["resolve", { key: arg, message: "Marked resolved on the SB Notify page" }],
      clear: ["clear", { key: arg }],
      test: arg === "alert"
        ? ["raise", { key: "test:page", title: "TEST: alert from the SB Notify page", message: "Dismiss it, or mark it resolved on the page.", severity: "warning", source: "test" }]
        : ["notify", { key: "test:page", title: "TEST: notification from the SB Notify page", ttl: { minutes: 10 } }],
    }[verb];
    if (!call) return;
    try { this._error = ""; await this._hass.callService("sb_notify", call[0], call[1]); }
    catch (e) { this._error = `Could not ${call[0]}: ${e?.message || e}`; this._render(); }
  }
}

// Same re-definition guard as the other SB pages: HA can swap window.customElements for a
// scoped registry after this module ran, losing the definition.
const ensureDefined = () => {
  if (customElements.get("sb-notify-panel")) return;
  try { customElements.define("sb-notify-panel", class extends SbNotifyPanel {}); } catch (e) { /* defined meanwhile */ }
};
ensureDefined();
setInterval(ensureDefined, 2000);
window.addEventListener("location-changed", ensureDefined);
console.info(`%c SB-NOTIFY %c v${VERSION} `, "background:#37474f;color:#fff", "background:#90a4ae;color:#000");
