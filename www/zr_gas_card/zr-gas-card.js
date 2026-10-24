/**
 * zr-gas-card — Home Assistant custom card for 中燃在线 (ZR Gas) integration
 *
 * Displays gas balance, usage, cost, meter info and tiered pricing.
 * Works with both data sources (在线端/缴费端) — sibling entities are
 * derived from the configured main entity ID, so no global state
 * scanning is needed.
 *
 * Usage:
 *   type: custom:zr-gas-card
 *   entity: sensor.zhong_ran_xxx_balance
 *
 * Optional:
 *   title: 我的燃气          # card title (default: 中燃在线)
 *   low_threshold: 50       # balance warning threshold (CNY, default 50)
 *   show_usage: true        # show usage/tier grid (default true)
 *   show_meter: true        # show meter info footer (default true)
 */

const CARD_VERSION = '2.1.0';

class ZrGasCard extends HTMLElement {
  static get styles() {
    return `
      :host {
        display: block;
        background: var(--card-background-color, #fff);
        border-radius: var(--ha-card-border-radius, 12px);
        padding: 16px;
        box-shadow: var(--card-box-shadow, 0 2px 8px rgba(0,0,0,0.1));
      }
      .card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 14px;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }
      .card-title {
        font-size: 16px;
        font-weight: 600;
        color: var(--primary-text-color, #212121);
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .card-icon {
        width: 24px;
        height: 24px;
        color: #ff6b35;
        flex: none;
      }
      .source-badge {
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 10px;
        background: var(--chip-background-color, #f0f0f0);
        color: var(--secondary-text-color, #757575);
        margin-left: 6px;
        font-weight: normal;
      }
      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--success-color, #4caf50);
        flex: none;
      }
      .status-dot.offline {
        background: var(--error-color, #f44336);
      }
      .balance-row {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin-bottom: 14px;
      }
      .balance-value {
        font-size: 34px;
        font-weight: 700;
        color: var(--primary-text-color, #212121);
      }
      .balance-value.negative {
        color: var(--error-color, #f44336);
      }
      .balance-unit {
        font-size: 14px;
        color: var(--secondary-text-color, #757575);
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
        gap: 10px;
      }
      .item {
        text-align: center;
        padding: 10px 6px;
        background: var(--secondary-background-color, #f5f5f5);
        border-radius: 8px;
      }
      .item-label {
        font-size: 12px;
        color: var(--secondary-text-color, #757575);
        margin-bottom: 4px;
      }
      .item-value {
        font-size: 17px;
        font-weight: 600;
        color: var(--primary-text-color, #212121);
      }
      .item-value.owe {
        color: #ff9800;
      }
      .item-unit {
        font-size: 11px;
        color: var(--secondary-text-color, #757575);
        font-weight: normal;
      }
      .tier-box {
        margin-top: 10px;
        padding: 10px 12px;
        border-radius: 8px;
        background: var(--secondary-background-color, #f5f5f5);
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 13px;
      }
      .tier-badge {
        padding: 2px 10px;
        border-radius: 10px;
        background: #ff6b35;
        color: #fff;
        font-weight: 600;
        font-size: 12px;
      }
      .warning {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 12px;
        background: rgba(255, 152, 0, 0.12);
        border-radius: 8px;
        color: #e65100;
        font-size: 13px;
        margin-top: 10px;
      }
      .warning svg {
        width: 18px;
        height: 18px;
        flex: none;
      }
      .info-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px 16px;
        padding: 10px 0 0;
        border-top: 1px solid var(--divider-color, #eee);
        margin-top: 12px;
        font-size: 12px;
        color: var(--secondary-text-color, #757575);
      }
      .footer {
        display: flex;
        justify-content: space-between;
        margin-top: 10px;
        font-size: 11px;
        color: var(--secondary-text-color, #9e9e9e);
      }
    `;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('请配置 entity（余额传感器）');
    }
    this.config = config;
    if (!this._hass) {
      this.attachShadow({ mode: 'open' });
      this._renderSkeleton();
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  getCardSize() {
    return 4;
  }

  // 从主实体 ID 推导同设备兄弟实体：
  // sensor.zhong_ran_xx_balance → sensor.zhong_ran_xx_<key>
  _sibling(key) {
    const base = this.config.entity.replace(/_balance$/, '');
    return this._hass.states[`${base}_${key}`];
  }

  _fmt(state, digits = 2, unit = '') {
    if (!state || state.state === 'unavailable' || state.state === 'unknown') {
      return `<span class="item-unit">--</span>`;
    }
    const val = parseFloat(state.state);
    if (Number.isNaN(val)) return state.state;
    return `${val.toFixed(digits)}${unit ? `<span class="item-unit"> ${unit}</span>` : ''}`;
  }

  _renderSkeleton() {
    this.shadowRoot.innerHTML = `
      <style>${ZrGasCard.styles()}</style>
      <div class="card-title">中燃在线</div>
      <div style="color:var(--secondary-text-color,#757575);padding:16px 0;">加载中…</div>
    `;
  }

  _update() {
    if (!this._hass || !this.config) return;

    const main = this._hass.states[this.config.entity];
    if (!main) {
      this.shadowRoot.innerHTML = `
        <style>${ZrGasCard.styles()}</style>
        <div class="card-title">中燃在线</div>
        <div style="color:var(--error-color,#f44336);padding:16px 0;">未找到实体 ${this.config.entity}</div>
      `;
      return;
    }

    const attrs = main.attributes || {};
    const source = attrs.source === 'pay' ? '缴费端' : '在线端';
    const title = this.config.title || '中燃在线';
    const threshold = this.config.low_threshold || 50;
    const showUsage = this.config.show_usage !== false;
    const showMeter = this.config.show_meter !== false;

    const balVal = parseFloat(main.state);
    const balInvalid = Number.isNaN(balVal);
    const negative = !balInvalid && balVal < 0;

    const owe = this._sibling('owe_money');
    const oweVal = owe ? parseFloat(owe.state) || 0 : 0;

    const monthlyUsage = this._sibling('monthly_usage');
    const monthlyCost = this._sibling('monthly_cost');
    const gasBalance = this._sibling('qty_meter_balance');
    const lastRecord = this._sibling('last_record');
    const gasPrice = this._sibling('gas_price');
    const purchTimes = this._sibling('purch_times');
    const annualUsage = this._sibling('annual_usage');
    const annualAttrs = annualUsage ? annualUsage.attributes || {} : {};

    const online = main.state !== 'unavailable';

    let gridHtml = '';
    if (showUsage) {
      gridHtml = `
        <div class="grid">
          <div class="item">
            <div class="item-label">月用量</div>
            <div class="item-value">${this._fmt(monthlyUsage, 2, 'm³')}</div>
          </div>
          <div class="item">
            <div class="item-label">月费用</div>
            <div class="item-value">${this._fmt(monthlyCost, 2, '元')}</div>
          </div>
          <div class="item">
            <div class="item-label">气量余额</div>
            <div class="item-value">${this._fmt(gasBalance, 1, 'm³')}</div>
          </div>
          <div class="item">
            <div class="item-label">欠费</div>
            <div class="item-value owe">${this._fmt(owe, 2, '元')}</div>
          </div>
          ${gasPrice ? `
          <div class="item">
            <div class="item-label">单价</div>
            <div class="item-value">${this._fmt(gasPrice, 2, '元/m³')}</div>
          </div>` : ''}
          <div class="item">
            <div class="item-label">购气次数</div>
            <div class="item-value">${purchTimes ? purchTimes.state : '--'}</div>
          </div>
        </div>`;

      if (annualUsage && annualUsage.state !== 'unavailable') {
        const tier = annualAttrs.current_tier || 1;
        const tierPrice = annualAttrs.current_tier_price;
        const remaining = annualAttrs.tier_remaining;
        const avg = annualAttrs.monthly_avg;
        const cycle = annualAttrs.tier_cycle_start || '';
        const remainTxt = Number.isFinite(remaining) ? ` · 余 ${remaining} m³` : '';
        const avgTxt = Number.isFinite(avg) ? ` · 均衡 ${avg} m³/月` : '';
        gridHtml += `
        <div class="tier-box">
          <span>年度累计 <b>${parseFloat(annualUsage.state).toFixed(1)}</b> m³${avgTxt}${cycle ? `<span class="item-unit">（自 ${cycle}）</span>` : ''}</span>
          <span>第${tier}档${tierPrice ? ` · ${tierPrice}元/m³` : ''}${remainTxt} <span class="tier-badge">阶梯</span></span>
        </div>`;
      }
    }

    let warningHtml = '';
    if (!balInvalid && oweVal > 0) {
      warningHtml = `
        <div class="warning">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
          <span>已欠费 ¥${oweVal.toFixed(2)} 元，请及时缴费</span>
        </div>`;
    } else if (!balInvalid && !negative && balVal < threshold) {
      warningHtml = `
        <div class="warning">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
          <span>余额 ¥${balVal.toFixed(2)} 元，低于预警值 ${threshold} 元</span>
        </div>`;
    }

    let meterHtml = '';
    if (showMeter) {
      const infoParts = [];
      if (attrs.meter_no) infoParts.push(`表号: ${attrs.meter_no}`);
      if (attrs.meter_form_name) infoParts.push(`型号: ${attrs.meter_form_name}`);
      if (attrs.card_no) infoParts.push(`卡号: ${attrs.card_no}`);
      if (attrs.meter_loc) infoParts.push(`位置: ${attrs.meter_loc}`);
      if (lastRecord && lastRecord.state !== 'unavailable') {
        infoParts.push(`读数: ${parseFloat(lastRecord.state).toFixed(0)} m³`);
      }
      if (infoParts.length) {
        meterHtml = `<div class="info-row">${infoParts.map(p => `<span>${p}</span>`).join('')}</div>`;
      }
    }

    this.shadowRoot.innerHTML = `
      <style>${ZrGasCard.styles()}</style>
      <div class="card-header">
        <div class="card-title">
          <svg class="card-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.1.8-1.3-4.5-2.7V7z"/>
          </svg>
          ${title}<span class="source-badge">${source}</span>
        </div>
        <div class="status-dot ${online ? '' : 'offline'}" title="${online ? '在线' : '离线'}"></div>
      </div>
      <div class="balance-row">
        <div class="balance-value ${negative ? 'negative' : ''}">
          ${balInvalid ? '--' : `${negative ? '-' : ''}¥${Math.abs(balVal).toFixed(2)}`}
        </div>
        <div class="balance-unit">账户余额</div>
      </div>
      ${gridHtml}
      ${warningHtml}
      ${meterHtml}
      <div class="footer">
        <span>${attrs.cust_code ? `编号 ${attrs.cust_code}` : ''}</span>
        <span>zr-gas-card v${CARD_VERSION}</span>
      </div>
    `;
  }
}

customElements.define('zr-gas-card', ZrGasCard);

// HA card editor registration (optional, improves UI config experience)
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'zr-gas-card',
  name: '中燃在线燃气卡片',
  description: '展示中燃在线余额、用量、阶梯气价和表具信息',
});
