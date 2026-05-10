/**
 * zr-gas-card — Home Assistant custom card for 中燃在线 (ZR Gas) integration
 *
 * Displays gas balance, usage, meter info with SVG icons.
 * Add to resources: /local/zr_gas_card/zr-gas-card.js
 * Usage:
 *   type: custom:zr-gas-card
 *   entity: sensor.zhong_ran_ran_qi_XXXX_balance
 *   show_usage: true
 *   show_meter: true
 */

class ZrGasCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("entity is required");
    this._config = config;
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  render() {
    if (!this._hass || !this._config) return;

    const entity = this._hass.states[this._config.entity];
    if (!entity) {
      this.innerHTML = `<ha-card><div class="not-found">实体 ${this._config.entity} 未找到</div></ha-card>`;
      return;
    }

    const state = parseFloat(entity.state) || 0;
    const attrs = entity.attributes || {};
    const code = attrs.cust_code || "";
    const codeShort = code.slice(-4) || "----";
    const address = attrs.cust_address || "";
    const compName = attrs.comp_name || "中燃在线";
    const meterNo = attrs.meter_no || "";
    const meterForm = attrs.meter_form_name || "";
    const period = attrs.period || "";
    const showUsage = this._config.show_usage !== false;
    const showMeter = this._config.show_meter !== false;

    // Find related sensors
    const prefix = code ? `sensor.zhong_ran_ran_qi_${codeShort}` : "";
    const usageEntity = this._hass.states[`${prefix}_monthly_usage`];
    const costEntity = this._hass.states[`${prefix}_monthly_cost`];
    const oweEntity = this._hass.states[`${prefix}_owe_money`];
    const meterEntity = this._hass.states[`${prefix}_last_record`];
    const balanceGasEntity = this._hass.states[`${prefix}_qty_meter_balance`];
    const purchEntity = this._hass.states[`${prefix}_purch_times`];
    const lastDateEntity = this._hass.states[`${prefix}_last_record_time`];

    const usage = usageEntity ? parseFloat(usageEntity.state) || 0 : 0;
    const cost = costEntity ? parseFloat(costEntity.state) || 0 : 0;
    const owe = oweEntity ? parseFloat(oweEntity.state) || 0 : 0;
    const meterReading = meterEntity ? parseFloat(meterEntity.state) || 0 : 0;
    const balanceGas = balanceGasEntity ? parseFloat(balanceGasEntity.state) || 0 : 0;
    const purchTimes = purchEntity ? parseInt(purchEntity.state) || 0 : 0;
    const lastDate = lastDateEntity ? lastDateEntity.state : "";

    const isLow = state < (this._config.low_threshold || 50);
    const isOwe = owe > 0;

    this.innerHTML = `
      <ha-card>
        <style>
          .zg-card { padding: 16px; font-family: var(--card-primary-font-family, inherit); }
          .zg-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
          .zg-title { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
          .zg-subtitle { font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
          .zg-badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; background: var(--primary-color, #03a9f4); color: #fff; }
          .zg-badge.warn { background: #ff9800; }
          .zg-badge.danger { background: #f44336; }
          .zg-balance { text-align: center; padding: 16px 0; }
          .zg-balance-value { font-size: 36px; font-weight: 300; color: ${isLow ? '#f44336' : 'var(--primary-text-color)'}; }
          .zg-balance-unit { font-size: 14px; color: var(--secondary-text-color); margin-left: 4px; }
          .zg-balance-label { font-size: 12px; color: var(--secondary-text-color); margin-top: 4px; }
          .zg-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 12px; }
          .zg-stat { text-align: center; padding: 8px 4px; border-radius: 8px; background: var(--secondary-background-color, #f5f5f5); }
          .zg-stat-value { font-size: 16px; font-weight: 500; color: var(--primary-text-color); }
          .zg-stat-label { font-size: 10px; color: var(--secondary-text-color); margin-top: 2px; }
          .zg-meter { display: flex; justify-content: space-between; padding: 8px 0; border-top: 1px solid var(--divider-color, #e0e0e0); margin-top: 12px; font-size: 11px; color: var(--secondary-text-color); }
          .zg-meter-item { text-align: center; }
          .zg-icon { width: 20px; height: 20px; vertical-align: middle; margin-right: 4px; fill: var(--primary-text-color); }
        </style>
        <div class="zg-card">
          <div class="zg-header">
            <div>
              <div class="zg-title">${compName}</div>
              <div class="zg-subtitle">${address || code}</div>
            </div>
            ${isOwe ? '<span class="zg-badge danger">欠费</span>' : isLow ? '<span class="zg-badge warn">余额不足</span>' : '<span class="zg-badge">正常</span>'}
          </div>

          <div class="zg-balance">
            <span class="zg-balance-value">${state.toFixed(2)}</span>
            <span class="zg-balance-unit">元</span>
            <div class="zg-balance-label">账户余额</div>
          </div>

          ${showUsage ? `
          <div class="zg-grid">
            <div class="zg-stat">
              <div class="zg-stat-value">${usage.toFixed(1)}</div>
              <div class="zg-stat-label">月用量 m³</div>
            </div>
            <div class="zg-stat">
              <div class="zg-stat-value">${cost.toFixed(2)}</div>
              <div class="zg-stat-label">月费用 元</div>
            </div>
            <div class="zg-stat">
              <div class="zg-stat-value">${balanceGas}</div>
              <div class="zg-stat-label">气量余额 m³</div>
            </div>
          </div>
          ` : ''}

          ${showMeter ? `
          <div class="zg-meter">
            <div class="zg-meter-item">
              <div>表读数</div>
              <div style="font-size:13px;color:var(--primary-text-color)">${meterReading}</div>
            </div>
            <div class="zg-meter-item">
              <div>购气次数</div>
              <div style="font-size:13px;color:var(--primary-text-color)">${purchTimes}次</div>
            </div>
            <div class="zg-meter-item">
              <div>抄表日期</div>
              <div style="font-size:13px;color:var(--primary-text-color)">${lastDate || '--'}</div>
            </div>
          </div>
          ` : ''}
        </div>
      </ha-card>
    `;
  }

  getCardSize() {
    return 4;
  }
}

customElements.define("zr-gas-card", ZrGasCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "zr-gas-card",
  name: "中燃在线燃气卡片",
  description: "显示中燃在线燃气余额、用量和表信息",
});
