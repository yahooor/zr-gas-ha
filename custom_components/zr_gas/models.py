"""Data models for the 中燃在线 (ZR Gas) integration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ZrGasCustomer:
    """绑定的燃气客户摘要信息。

    从 getBindGasCustList 接口返回。
    """

    cust_code: str
    cust_name: str


@dataclass
class ZrGasCustomerDetail:
    """客户详细信息。

    从 findCustInfoByCustCodeAndCustName 接口返回。
    """

    cust_code: str
    cust_name: str
    cust_address: str
    balance: float
    owe_money: float = 0.0
    last_record: float = 0.0
    qty_meter_balance: float = 0.0
    purch_times: int = 0
    last_record_time: str = ""
    meter_no: str = ""
    meter_form_name: str = ""
    card_no: str = ""
    comp_name: str = ""
    cust_status: str = ""
    fee: str = ""


@dataclass
class ZrGasBill:
    """单条缴费/账单记录。

    从 getCustomerMoneyList 接口返回。
    """

    period: str  # 账期，格式 YYYYMM
    usage_volume: float  # 用气量 (m³)
    usage_amount: float  # 费用金额 (CNY)
    unit_price: float  # 单价 (CNY/m³)


@dataclass
class TierConfig:
    """阶梯气价配置。

    三档年度阶梯计价：
    - 第一档: 0 ~ tier_2_start m³，价格 tier_1_price
    - 第二档: tier_2_start ~ tier_3_start m³，价格 tier_2_price
    - 第三档: tier_3_start 以上，价格 tier_3_price
    - 阶梯周期起始日: tier_cycle_start_md (MM-DD 格式)
    """

    tier_2_start: float = 400.0
    tier_3_start: float = 1680.0
    tier_1_price: float = 2.99
    tier_2_price: float = 3.44
    tier_3_price: float = 4.34
    tier_cycle_start_md: str = "01-01"

    def get_tier_info(self, annual_usage: float) -> tuple[int, float, float]:
        """根据年度累计用量返回当前阶梯信息。

        Args:
            annual_usage: 年度累计用气量 (m³)

        Returns:
            (tier_number, current_price, remaining_in_tier)
            tier_number: 1/2/3
            current_price: 当前阶梯单价
            remaining_in_tier: 当前阶梯剩余量 (inf 表示无上限)
        """
        if annual_usage < self.tier_2_start:
            return (1, self.tier_1_price, self.tier_2_start - annual_usage)
        elif annual_usage < self.tier_3_start:
            return (2, self.tier_2_price, self.tier_3_start - annual_usage)
        else:
            return (3, self.tier_3_price, float("inf"))

    def calculate_usage_from_cost(
        self, start_usage: float, cost: float
    ) -> float:
        """根据费用反算用气量（处理跨阶梯场景）。

        当 API 只返回费用 (cost) 但不返回气量时，
        根据当前阶梯价格反算实际用气量。

        Args:
            start_usage: 本次计费前年度累计用量 (m³)
            cost: 本次费用 (CNY)

        Returns:
            反算的用气量 (m³)
        """
        usage = 0.0
        remaining_cost = cost
        current_base = start_usage

        for _ in range(3):  # 最多跨3个阶梯
            if remaining_cost <= 0.001:
                break

            _tier, current_price, remaining_in_tier = self.get_tier_info(
                current_base
            )

            if current_price <= 0:
                break

            cost_to_finish_tier = remaining_in_tier * current_price

            if remaining_cost <= cost_to_finish_tier:
                # 费用在当前阶梯内即可消化
                usage_in_step = remaining_cost / current_price
                usage += usage_in_step
                remaining_cost = 0
                current_base += usage_in_step
            else:
                # 消耗完当前阶梯剩余量
                usage += remaining_in_tier
                remaining_cost -= cost_to_finish_tier
                current_base += remaining_in_tier

        return usage


@dataclass
class MonthlyStat:
    """自然月统计数据。"""

    month: str  # YYYY-MM
    gas_num: float  # 用气量 (m³)
    gas_cost: float  # 费用 (CNY)


@dataclass
class YearlyStat:
    """年度统计数据。"""

    year: str  # YYYY
    gas_num: float  # 用气量 (m³)
    gas_cost: float  # 费用 (CNY)


@dataclass
class ZrGasDeviceData:
    """聚合后的设备数据，用于传感器状态更新。

    由 Coordinator 组合 customerDetail 和 bills 信息生成。
    """

    balance: float  # 账户余额 (CNY)
    cust_code: str
    cust_name: str
    cust_address: str
    monthly_usage: float  # 当月用气量 (m³)
    monthly_cost: float  # 当月费用 (CNY)
    period: str  # 当前账期 YYYYMM
    unit_price: float  # 当月单价 (CNY/m³)
    owe_money: float = 0.0
    last_record: float = 0.0
    qty_meter_balance: float = 0.0
    purch_times: int = 0
    last_record_time: str = ""
    meter_no: str = ""
    meter_form_name: str = ""
    card_no: str = ""
    comp_name: str = ""
    cust_status: str = ""
    fee: str = ""
    # 阶梯气价
    annual_usage: float = 0.0  # 年度累计用气量 (m³)
    current_tier: int = 1  # 当前阶梯 1/2/3
    current_tier_price: float = 0.0  # 当前阶梯单价 (CNY/m³)
    tier_cycle_start: str = ""  # 当前阶梯周期起始日 YYYY-MM-DD
    # 统计
    monthly_stats: list[MonthlyStat] = field(default_factory=list)
    yearly_stats: list[YearlyStat] = field(default_factory=list)
