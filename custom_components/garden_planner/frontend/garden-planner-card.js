// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Garden Planner card — a combined season "Gantt" timeline for the whole
 * garden. Each planting is a bar on a shared calendar axis, coloured by phase
 * (start → growing → harvest), grouped by bed, with a "today" marker.
 *
 * No build step: a plain custom element that reads one entity per planting
 * (the `sensor.*` stage sensor, which carries the schedule as attributes).
 *
 * Usage:
 *   type: custom:garden-planner-card
 *   title: My Garden        # optional
 *   year: 2026              # optional; otherwise the range is derived from data
 */

const PHASE_COLORS = {
  start: "var(--gp-start-color, #8d6e63)",
  grow: "var(--gp-grow-color, #66bb6a)",
  harvest: "var(--gp-harvest-color, #ffa726)",
};

const LABEL_W = 200;
const PAD_R = 16;
const ROW_H = 34;
const AXIS_H = 26;
const BED_H = 24;
const WIDTH = 1000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const parseISO = (s) => (s ? new Date(`${s}T00:00:00`) : null);
const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);
const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

class GardenPlannerCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    const plantings = this._collect(hass);
    const sig = JSON.stringify(plantings) + (this._config.year || "");
    if (sig === this._sig) return; // avoid re-rendering on unrelated state changes
    this._sig = sig;
    this._plantings = plantings;
    this._render();
  }

  getCardSize() {
    const beds = new Set((this._plantings || []).map((p) => p.bedId)).size;
    return 2 + Math.ceil(((this._plantings || []).length * ROW_H + beds * BED_H) / 50);
  }

  _collect(hass) {
    const out = [];
    for (const [entityId, st] of Object.entries(hass.states)) {
      const a = st.attributes || {};
      if (a.gp_role !== "planting") continue;
      out.push({
        entityId,
        plant: a.plant || st.state,
        bed: a.bed || "Unassigned",
        bedId: a.bed_id || "",
        season: a.season || "",
        stage: st.state,
        sow: a.sow_date || null,
        transplant: a.transplant_date || null,
        firstHarvest: a.first_harvest_date || null,
        harvestEnd: a.harvest_end_date || null,
        nextTask: a.next_task || null,
        nextTaskDate: a.next_task_date || null,
      });
    }
    out.sort((x, y) => (x.bed || "").localeCompare(y.bed || "") || (x.sow || "").localeCompare(y.sow || ""));
    return out;
  }

  _range(plantings) {
    if (this._config.year) {
      const y = Number(this._config.year);
      return [new Date(y, 0, 1), new Date(y, 11, 31)];
    }
    let min = null;
    let max = null;
    for (const p of plantings) {
      const s = parseISO(p.sow);
      const e = parseISO(p.harvestEnd) || parseISO(p.firstHarvest) || s;
      if (s && (!min || s < min)) min = s;
      if (e && (!max || e > max)) max = e;
    }
    const now = new Date();
    if (!min) min = new Date(now.getFullYear(), 0, 1);
    if (!max) max = new Date(now.getFullYear(), 11, 31);
    return [startOfMonth(min), addMonths(startOfMonth(max), 1)];
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const plantings = this._plantings || [];
    const title = this._config.title;

    if (!plantings.length) {
      this.shadowRoot.innerHTML = `
        <ha-card ${title ? `header="${esc(title)}"` : ""}>
          <div class="empty">No plantings yet. Add a bed and a planting to see your season timeline.</div>
          ${STYLE}
        </ha-card>`;
      return;
    }

    const [start, end] = this._range(plantings);
    const span = end - start || 1;
    const chartX0 = LABEL_W;
    const chartW = WIDTH - LABEL_W - PAD_R;
    const x = (d) => chartX0 + ((d - start) / span) * chartW;

    // Group rows by bed.
    const groups = [];
    let cur = null;
    for (const p of plantings) {
      if (!cur || cur.bed !== p.bed) {
        cur = { bed: p.bed, rows: [] };
        groups.push(cur);
      }
      cur.rows.push(p);
    }

    let y = AXIS_H;
    const parts = [];

    // Month gridlines + labels.
    for (let m = new Date(start); m <= end; m = addMonths(m, 1)) {
      const mx = x(m);
      const label = m.getMonth() === 0 ? `${MONTHS[0]} ${m.getFullYear()}` : MONTHS[m.getMonth()];
      parts.push(`<line class="grid" x1="${mx}" y1="${AXIS_H - 6}" x2="${mx}" y2="__H__"></line>`);
      parts.push(`<text class="axis" x="${mx + 3}" y="${AXIS_H - 10}">${esc(label)}</text>`);
    }

    // Rows.
    for (const g of groups) {
      parts.push(`<rect class="bedband" x="0" y="${y}" width="${WIDTH}" height="${BED_H}"></rect>`);
      parts.push(`<text class="bed" x="10" y="${y + BED_H - 8}">${esc(g.bed)}</text>`);
      y += BED_H;
      for (const p of g.rows) {
        const rowY = y;
        parts.push(
          `<text class="plant" x="18" y="${rowY + ROW_H / 2 + 4}">${esc(p.plant)}` +
            `${p.season ? `<tspan class="season"> · ${esc(p.season)}</tspan>` : ""}</text>`
        );
        parts.push(this._bar(p, x, rowY));
        y += ROW_H;
      }
    }

    const H = y + 8;

    // Today marker.
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    let todayLine = "";
    if (today >= start && today <= end) {
      const tx = x(today);
      todayLine = `<line class="today" x1="${tx}" y1="${AXIS_H - 6}" x2="${tx}" y2="${H}"></line>`;
    }

    const svg =
      `<svg viewBox="0 0 ${WIDTH} ${H}" width="100%" preserveAspectRatio="xMidYMid meet">` +
      parts.join("").replaceAll("__H__", H) +
      todayLine +
      `</svg>`;

    this.shadowRoot.innerHTML = `
      <ha-card ${title ? `header="${esc(title)}"` : ""}>
        <div class="wrap">${svg}</div>
        <div class="legend">
          <span><i style="background:${PHASE_COLORS.start}"></i>Sow/start</span>
          <span><i style="background:${PHASE_COLORS.grow}"></i>Growing</span>
          <span><i style="background:${PHASE_COLORS.harvest}"></i>Harvest</span>
          <span><i class="todaykey"></i>Today</span>
        </div>
        ${STYLE}
      </ha-card>`;

    // Click a bar/label to open the planting's more-info dialog.
    this.shadowRoot.querySelectorAll("[data-entity]").forEach((el) => {
      el.addEventListener("click", () => this._moreInfo(el.getAttribute("data-entity")));
    });
  }

  _bar(p, x, rowY) {
    const sow = parseISO(p.sow);
    const end = parseISO(p.harvestEnd) || parseISO(p.firstHarvest);
    if (!sow || !end) return "";
    const transplant = parseISO(p.transplant);
    const firstHarvest = parseISO(p.firstHarvest);
    const barY = rowY + 8;
    const barH = ROW_H - 16;

    const seg = (a, b, color) => {
      if (!a || !b || b <= a) return "";
      const xa = x(a);
      const w = Math.max(2, x(b) - xa);
      return `<rect class="seg" x="${xa}" y="${barY}" width="${w}" height="${barH}" rx="3" fill="${color}"></rect>`;
    };

    let segs = "";
    if (transplant && transplant > sow) {
      segs += seg(sow, transplant, PHASE_COLORS.start);
      segs += seg(transplant, firstHarvest || end, PHASE_COLORS.grow);
    } else {
      segs += seg(sow, firstHarvest || end, PHASE_COLORS.grow);
    }
    if (firstHarvest) segs += seg(firstHarvest, end, PHASE_COLORS.harvest);

    const tip = `${p.plant} — ${p.bed}\nStage: ${p.stage}` +
      `\nSow: ${p.sow || "?"}${p.transplant ? `\nTransplant: ${p.transplant}` : ""}` +
      `\nHarvest: ${p.firstHarvest || "?"}${p.nextTask ? `\nNext: ${p.nextTask} ${p.nextTaskDate || ""}` : ""}`;

    return `<g class="row" data-entity="${esc(p.entityId)}"><title>${esc(tip)}</title>${segs}</g>`;
  }

  _moreInfo(entityId) {
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId };
    this.dispatchEvent(ev);
  }
}

const STYLE = `
  <style>
    ha-card { padding: 8px 4px 12px; }
    .wrap { overflow-x: auto; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
    svg { display: block; }
    .grid { stroke: var(--divider-color, #e0e0e0); stroke-width: 1; }
    .today { stroke: var(--error-color, #db4437); stroke-width: 1.5; stroke-dasharray: 4 3; }
    .axis { fill: var(--secondary-text-color); font-size: 12px; }
    .bedband { fill: var(--secondary-background-color, rgba(0,0,0,.04)); }
    .bed { fill: var(--primary-text-color); font-size: 12.5px; font-weight: 600; }
    .plant { fill: var(--primary-text-color); font-size: 13px; }
    .season { fill: var(--secondary-text-color); font-size: 11px; }
    .row { cursor: pointer; }
    .row:hover .seg { opacity: .85; }
    .legend { display: flex; gap: 14px; flex-wrap: wrap; padding: 6px 16px 0; color: var(--secondary-text-color); font-size: 12px; }
    .legend span { display: inline-flex; align-items: center; gap: 5px; }
    .legend i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
    .legend .todaykey { width: 2px; height: 14px; border-radius: 0; background: var(--error-color, #db4437); }
  </style>`;

customElements.define("garden-planner-card", GardenPlannerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "garden-planner-card",
  name: "Garden Planner Card",
  description: "A season timeline (Gantt) of your garden's plantings.",
});

console.info("%c GARDEN-PLANNER-CARD %c loaded ", "background:#66bb6a;color:#fff;border-radius:3px 0 0 3px;padding:2px 4px", "background:#333;color:#fff;border-radius:0 3px 3px 0;padding:2px 4px");
