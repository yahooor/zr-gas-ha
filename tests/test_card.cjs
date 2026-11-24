/* Real card execution with a minimal custom-element host, no HA server needed. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

let Card;
const context = {
  HTMLElement: class {
    attachShadow() { this.shadowRoot = { innerHTML: '' }; }
  },
  customElements: { define(name, value) { Card = value; } },
  window: {},
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../www/zr_gas_card/zr-gas-card.js'), 'utf8'), context);

function state(value, attributes = {}) {
  return { state: String(value), attributes };
}

function render(states, config = {}) {
  const card = new Card();
  card.setConfig({ entity: 'sensor.gas_balance', ...config });
  card.hass = { states };
  return card;
}

test('legacy and renamed suffixes preserve in-meter precision and derived price label', () => {
  for (const suffix of ['gas_volume_balance', 'qty_meter_balance', 'in_meter_gas_volume']) {
    const card = render({
      'sensor.gas_balance': state(10),
      [`sensor.gas_${suffix}`]: state(39.42, { data_source: 'queryLatestMeterInfo.effeGas' }),
      'sensor.gas_gas_price': state(3.011, { price_source: 'derived' }),
      'sensor.gas_annual_usage': state('unknown'),
      'sensor.gas_meter_reading': state('unknown'),
      'sensor.gas_data_cutoff_time': state('2041-02-12T04:05:06+08:00', { data_source: 'queryLatestMeterInfo.dataTime' }),
    });
    assert.match(card.shadowRoot.innerHTML, /39\.42/);
    assert.match(card.shadowRoot.innerHTML, /表内气量/);
    assert.match(card.shadowRoot.innerHTML, /推算单价/);
    assert.match(card.shadowRoot.innerHTML, /截止时间/);
    assert.doesNotMatch(card.shadowRoot.innerHTML, /NaN/);
  }
});

test('custom entity IDs resolve by exact customer, source and sensor key', () => {
  const card = render({
    'sensor.my_custom_balance': state(0, { cust_code: 'C01', source: 'mp' }),
    'sensor.my_custom_volume': state(39.42, { cust_code: 'C01', source: 'mp', sensor_key: 'qty_meter_balance' }),
    'sensor.other_source': state(999, { cust_code: 'C01', source: 'pay', sensor_key: 'qty_meter_balance' }),
  }, { entity: 'sensor.my_custom_balance', low_threshold: 0 });
  assert.match(card.shadowRoot.innerHTML, /39\.42/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /999|低于预警值/);
});

test('zero is displayed; unknown is not fabricated as zero or tier one', () => {
  const card = render({
    'sensor.gas_balance': state(0),
    'sensor.gas_qty_meter_balance': state(0),
    'sensor.gas_gas_price': state(0),
    'sensor.gas_annual_usage': state('unknown'),
  });
  assert.match(card.shadowRoot.innerHTML, /0\.00/);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /NaN|第1档/);
  assert.match(card._fmt(state('unknown')), /--/);
  assert.match(card._fmt(state('unavailable')), /--/);
});

test('explicit sibling mapping supports arbitrary legacy names', () => {
  const volume = state(39.42);
  const card = render({ 'sensor.gas_balance': state(10), 'sensor.custom': volume }, {
    entities: { qty_meter_balance: 'sensor.custom' },
  });
  assert.equal(card._sibling('qty_meter_balance'), volume);
});

test('QA cutoff uses only the independent snapshot entity when legacy reading time coexists', () => {
  for (const suffix of ['data_cutoff_time', 'meter_snapshot_time']) {
    for (const cutoff of ['2041-02-12T04:05:06+08:00', 'unknown']) {
      const card = render({
        'sensor.gas_balance': state(10),
        'sensor.gas_last_reading_date': state('2040-01-01T00:00:00+08:00'),
        [`sensor.gas_${suffix}`]: state(cutoff, { data_source: 'queryLatestMeterInfo.dataTime' }),
      });
      assert.doesNotMatch(card.shadowRoot.innerHTML, /2040-01-01|NaN/);
      if (cutoff === 'unknown') {
        assert.doesNotMatch(card.shadowRoot.innerHTML, /截止时间/);
      } else {
        assert.match(card.shadowRoot.innerHTML, /截止时间: 2041-02-12T04:05:06/);
      }
    }
  }
});

test('old integration reading date is never relabelled as snapshot cutoff', () => {
  for (const suffix of ['last_reading_date', 'last_record_time']) {
    const card = render({
      'sensor.gas_balance': state(10),
      [`sensor.gas_${suffix}`]: state('2040-01-01T00:00:00+08:00'),
    });
    assert.doesNotMatch(card.shadowRoot.innerHTML, /截止时间|2040-01-01|NaN/);
  }
});
