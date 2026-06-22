# Tushare Financial Data API Reference

## income - 利润表

获取上市公司利润表数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| f_ann_date | str | No | 实际公告日期 |
| start_date | str | No | 报告期开始日期 |
| end_date | str | No | 报告期结束日期 |
| period | str | No | 报告期（20181231/20181230/20181229） |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| f_ann_date | 实际公告日期 |
| end_date | 报告期 |
| report_type | 报告类型（1合并报表2母公司报表） |
| comp_type | 公司类型（1一般工商业2银行3保险4证券） |
| basic_eps | 基本每股收益 |
| diluted_eps | 稀释每股收益 |
| total_revenue | 营业总收入 |
| revenue | 营业收入 |
| int_income | 利息收入 |
| prem_earned | 已赚保费 |
| comm_income | 手续费及佣金收入 |
| n_commis_income | 手续费及佣金净收入 |
| n_oth_income | 其他经营收益 |
| n_oth_b_income | 加:其他业务收入 |
| prem_income | 保险业务收入 |
| out_prem | 减:分出保费 |
| une_prem_rea | 未到期责任准备金 |
| reins_income | 分保费收入 |
| n_sec_tb_income | 代理买卖证券业务净收入 |
| n_sec_uw_income | 证券承销业务净收入 |
| n_asset_mg_income | 受托客户资产管理业务净收入 |
| oth_b_income | 其他业务收入 |
| fv_value_chg_gain | 加:公允价值变动收益 |
| invest_income | 加:投资收益 |
| ass_invest_income | 其中:对联营企业和合营企业的投资收益 |
| forex_gain | 加:汇兑收益 |
| total_cogs | 营业总成本 |
| oper_cost | 减:营业成本 |
| int_exp | 减:利息支出 |
| comm_exp | 减:手续费及佣金支出 |
| biz_tax_surchg | 减:税金及附加 |
| sell_exp | 减:销售费用 |
| admin_exp | 减:管理费用 |
| fin_exp | 减:财务费用 |
| assets_impair_loss | 加:资产减值损失 |
| prem_refund | 减:赔付支出 |
| compens_payout | 减:赔付支出 |
| reser_incre | 减:提取保险合同准备金 |
| div_payt | 减:保单红利支出 |
| reins_exp | 减:分保费用 |
| oper_exp | 减:营业支出 |
| compens_payout_refu | 减:分保赔付支出 |
| insur_reser_refu | 减:摊回保险合同准备金 |
| insur_cost | 减:保险业务费用 |
| n_sec_brk_income | 减:证券承销业务支出 |
| n_sec_bb_income | 减:证券经纪业务支出 |
| oper_revenue | 营业利润 |
| non_oper_income | 加:营业外收入 |
| non_oper_exp | 减:营业外支出 |
| nca_disploss | 其中:减:非流动资产处置损失 |
| total_profit | 利润总额 |
| income_tax | 减:所得税费用 |
| n_income | 净利润 |
| n_income_attr_p | 归属于母公司所有者的净利润 |
| minority_gain | 少数股东损益 |
| oth_compr_income | 其他综合收益 |
| t_compr_income | 综合收益总额 |
| compr_inc_attr_p | 归属于母公司所有者的综合收益总额 |
| compr_inc_attr_m_s | 归属于少数股东的综合收益总额 |
| ebit | 息税前利润 |
| ebitda | 息税折旧摊销前利润 |
| insurance_exp | 保险业务支出 |
| undist_profit | 未分配利润 |
| distable_profit | 可分配利润 |

### Example
```python
df = pro.income(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20231231'
)
```

---

## balancesheet - 资产负债表

获取上市公司资产负债表数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| f_ann_date | str | No | 实际公告日期 |
| start_date | str | No | 报告期开始日期 |
| end_date | str | No | 报告期结束日期 |
| period | str | No | 报告期 |

### Return Fields (Key Fields)
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| f_ann_date | 实际公告日期 |
| end_date | 报告期 |
| total_assets | 资产总计 |
| total_hldr_eqy_exc_min_int | 负债合计 |
| total_liab | 所有者权益合计 |
| total_hldr_eqy_inc_min_int | 归属母公司所有者权益 |
| equ_frgn_curr | 少数股东权益 |
| cash_equivalents | 货币资金 |
| trading_assts | 交易性金融资产 |
| note_receivable | 应收票据 |
| accounts_receivable | 应收账款 |
| oth_receivable | 其他应收款 |
| prepayment | 预付款项 |
| div_receivable | 应收股利 |
| int_receivable | 应收利息 |
| inventories | 存货 |
| amor_exp_of_intang_assets | 存货跌价准备 |
| total_current_assets | 流动资产合计 |
| fa_avail_for_sale | 可供出售金融资产 |
| lt_eqt_invest | 长期股权投资 |
| invest_real_estate | 投资性房地产 |
| fixed_assets | 固定资产 |
| cip_in_process | 在建工程 |
| const_materials | 工程物资 |
| fixed_assets_disp | 固定资产清理 |
| prod biolog_assets | 生产性生物资产 |
| oil_and_gas_assets | 油气资产 |
| intangible_assets | 无形资产 |
| goodwill | 商誉 |
| long_defer_exp | 长期待摊费用 |
| defer_tax_assets | 递延所得税资产 |
| total_non_current_assets | 非流动资产合计 |
| accounts_payable | 应付账款 |
| adv_receipts | 预收款项 |
| sold_for_repur_p | 卖出回购金融资产款 |
| emp_ben_pay | 应付职工薪酬 |
| taxes_payable | 应交税费 |
| int_payable | 应付利息 |
| div_payable | 应付股利 |
| oth_payable | 其他应付款 |
| non_current_liab | 非流动负债合计 |
| total_current_liab | 流动负债合计 |

### Example
```python
df = pro.balancesheet(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20231231'
)
```

---

## cashflow - 现金流量表

获取上市公司现金流量表数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| f_ann_date | str | No | 实际公告日期 |
| start_date | str | No | 报告期开始日期 |
| end_date | str | No | 报告期结束日期 |
| period | str | No | 报告期 |

### Return Fields (Key Fields)
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| f_ann_date | 实际公告日期 |
| end_date | 报告期 |
| net_profit | 净利润 |
| fina_exp_of_depreciation | 资产减值准备 |
| depr_cog_and_fa | 固定资产折旧、油气资产折耗、生产性生物资产折旧 |
| intangible_assets_amor | 无形资产摊销 |
| long_prep_exp_amor | 长期待摊费用摊销 |
| disp_loss_of_fAssets | 处置固定资产、无形资产和其他长期资产的损失 |
| scrap_loss | 固定资产报废损失 |
| loss_of_fv_chg | 公允价值变动损失 |
| invest_income | 投资损失 |
| loss_of_credit | 减:递延所得税资产增加 |
| incr_defer_income | 加:递延所得税负债增加 |
| decr_inventories | 减:存货的减少 |
| incr_accounts_receivable | 加:经营性应收项目的减少 |
| incr_accounts_payable | 减:经营性应付项目的增加 |
| others | 其他 |
| net_cash_flows_from_act | 经营活动产生的现金流量净额 |
| cash_rece_from_cap_invest | 投资活动产生的现金流量净额 |
| cash_rece_from_return_invest | 取得投资收益收到的现金 |
| net_cash_recv_from_disp | 处置固定资产、无形资产和其他长期资产收回的现金净额 |
| cfa_sub_total_pay_for_assets | 购建固定资产、无形资产和其他长期资产支付的现金 |
| int_cash_paid | 投资支付的现金 |
| cfa_sub_total | 投资活动产生的现金流量净额 |
| cfc_cash_rece_from_fina | 筹资活动产生的现金流量净额 |
| proc_from_invest | 吸收投资收到的现金 |
| cash_rece_from_fina_invest | 取得借款收到的现金 |
| cfc_repay_debt | 偿还债务支付的现金 |
| cfc_pay_dist_div_int_prof | 分配股利、利润或偿付利息支付的现金 |
| cfc_sub_total | 筹资活动产生的现金流量净额 |
| eff_fx_flu | 汇率变动对现金的影响 |
| net_incr_cash_cash_equ | 现金及现金等价物净增加额 |
| incr_cash_cash_equ | 期初现金及现金等价物余额 |
| cfc_balance_cash_equ | 期末现金及现金等价物余额 |

### Example
```python
df = pro.cashflow(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20231231'
)
```

---

## fina_indicator - 财务指标

获取上市公司财务指标数据

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| start_date | str | No | 报告期开始日期 |
| end_date | str | No | 报告期结束日期 |
| period | str | No | 报告期 |

### Return Fields (Key Fields)
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| end_date | 报告期 |
| roe | 净资产收益率 |
| roe_waa | 加权平均净资产收益率 |
| roe_dt | 扣除非经常损益后的净资产收益率 |
| roa | 总资产净利率(ROA) |
| npta | 总资产周转率 |
| op_of_gr | 营业毛利率 |
| ebit_of_gr | 销售净利率 |
| netprofit_margin | 销售毛利率 |
| grossprofit_margin | 销售净利率 |
| exp_to_sales | 销售期间费用率 |
| profit_to_gr | 成本费用利润率 |
| n_op_profit_of_gr | 销售税金及附加率 |
| sgpr_rate | 销售费用率 |
| ga_exp_rate | 管理费用率 |
| fin_exp_rate | 财务费用率 |
| op_exp_to_sales | 营业利润/营业总收入 |
| ebit_to_rev | EBIDTA/营业总收入 |
| operating_profit_to_revenue | 经营净收益/营业总收入 |
| invest_income_to_revenue | 价值变动净收益/营业总收入 |
| n_op_profit_to_revenue | 营业总成本/营业总收入 |
| operating_revenue_to_revenue | 营业外收支净额/营业总收入 |
| total_operate_revenue_to_rev | 扣除非经常损益后的净利润/净利润 |
| taxable_income_to_n_profit | 所得税/利润总额 |
| salescash_to_or | 销售商品提供劳务收到的现金/营业收入 |
| ocf_to_or | 经营活动产生的现金流量净额/营业收入 |
| ocf_to_op | 经营活动产生的现金流量净额/经营活动收益 |
| capitalized_to_da | 资本化支出/折旧和摊销 |
| capitalized_to_da_lt | 资本化支出/折旧和摊销(长期) |
| capex_to_depr | 资本性支出/折旧和摊销 |
| ca_turn | 流动资产周转率 |
| ca_turn_days | 流动资产周转天数 |
| fa_turn | 固定资产周转率 |
| fa_turn_days | 固定资产周转天数 |
| total_asset_turn | 总资产周转率 |
| total_asset_turn_days | 总资产周转天数 |
| invoice_rece_turn_days | 应收账款周转天数 |
| inventories_turn_days | 存货周转天数 |
| current | 流动比率 |
| quick | 速动比率 |
| cash_ratio | 保守速动比率 |
| current_to_debt | 流动负债/总负债 |
| debt_to_eqt | 资产负债率 |
| eqt_to_debt | 负债权益比 |
| eqt_to_int_debt | 有形资产/净债务 |
| eqt_to_fdebt | 有形资产/总债务 |
| tangibleasset_to_debt | 有形资产/净债务 |
| int_to_talcap | 利息保障倍数 |
| long_debt_to_debt | 长期债务与营运资金比率 |
| ebitda_to_debt | EBITDA/债务合计 |
| turnover_days_to_pay | 应付账款周转天数 |
| arc_to_arc | 营业周期 |
| ar_to_arc | 现金循环周期 |

### Example
```python
df = pro.fina_indicator(
    ts_code='600000.SH',
    start_date='20230101',
    end_date='20231231'
)
```

---

## fina_audit - 财务审计意见

获取上市公司财务审计意见

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| start_date | str | No | 报告期开始日期 |
| end_date | str | No | 报告期结束日期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| end_date | 报告期 |
| audit_result | 审计意见 |
| audit_fees | 审计费用 |
| audit_agency | 审计机构 |
| audit_sign | 审计签字人 |

### Example
```python
df = pro.fina_audit(
    ts_code='600000.SH',
    start_date='20230101'
)
```

---

## forecast - 业绩预告

获取上市公司业绩预告

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| end_date | str | No | 报告期 |
| period | str | No | 报告期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| end_date | 报告期 |
| type | 业绩预告类型 |
| p_change_min | 预告净利润变动幅度下限(%) |
| p_change_max | 预告净利润变动幅度上限(%) |
| net_profit_min | 预告净利润下限（万元） |
| net_profit_max | 预告净利润上限（万元） |

### Example
```python
df = pro.forecast(
    ts_code='600000.SH',
    ann_date='20240101'
)
```

---

## express - 业绩快报

获取上市公司业绩快报

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ts_code | str | No | 股票代码 |
| ann_date | str | No | 公告日期 |
| end_date | str | No | 报告期 |
| period | str | No | 报告期 |

### Return Fields
| Field | Description |
|-------|-------------|
| ts_code | 股票代码 |
| ann_date | 公告日期 |
| end_date | 报告期 |
| revenue | 营业收入 |
| operate_profit | 营业利润 |
| total_profit | 利润总额 |
| n_income | 净利润 |
| total_assets | 总资产 |
| total_hldr_eqy_exc_min_int | 股东权益合计 |

### Example
```python
df = pro.express(
    ts_code='600000.SH',
    ann_date='20240101'
)
```

---

## 财务数据使用建议

### 财务分析指标计算

```python
# ROE分析
roe = df['roe'].mean()

# 盈利能力分析
gross_margin = df['grossprofit_margin'].mean()
net_margin = df['netprofit_margin'].mean()

# 偿债能力分析
debt_ratio = df['debt_to_eqt'].mean()
current_ratio = df['current'].mean()

# 运营能力分析
asset_turnover = df['total_asset_turn'].mean()
inventory_days = df['inventories_turn_days'].mean()
```

### 财务数据获取策略

1. **季度数据：** 使用`period`参数获取季度报告
2. **年报数据：** 使用`end_date`筛选年报
3. **多股票对比：** 批量获取后按`end_date`分组对比
4. **趋势分析：** 连续获取多个报告期数据
