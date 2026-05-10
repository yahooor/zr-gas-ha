"""Data models for the 中燃在线 (ZR Gas) integration."""

from __future__ import annotations

from dataclasses import dataclass


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
