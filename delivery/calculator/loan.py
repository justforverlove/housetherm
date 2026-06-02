"""
loan.py — 新青安（新青年安心成家購屋優惠貸款）月付試算

新青安 2023/08 擴大方案重點（以官方/承貸行庫最新公告為準）：
  · 貸款額度上限 1,000 萬元
  · 貸款年限 最長 40 年
  · 寬限期（只繳息）最長 5 年
  · 一段式機動利率約 1.775%（郵儲利率 + 加碼 − 政府補貼）

月付採本息平均攤還 (annuity)；寬限期內只繳息。
"""
from __future__ import annotations

DEFAULTS = {"annual_rate": 0.01775, "years": 30, "grace_years": 0, "loan_cap_wan": 1000}

# 各貸款方案的示意預設（2026，利率/條件以承貸行庫公告為準）
# rate=年利率, years=年限, grace=寬限年, cap_wan=額度上限(萬,None=無), ltv=最高貸款成數(None=非擔保)
PRODUCTS = {
    "新青安": {"rate": 0.01775, "years": 40, "grace": 5, "cap_wan": 1000, "ltv": 0.8,
             "note": "政府補貼；額度上限 1000 萬、最長 40 年、寬限最長 5 年。限首購且家庭成員無自有住宅。"},
    "一般首購房貸": {"rate": 0.0220, "years": 30, "grace": 3, "cap_wan": None, "ltv": 0.8,
               "note": "自住首購；利率約 2.1–2.4%、最長 30–40 年、寬限約 0–3 年、最高約 8 成。"},
    "第二屋房貸(信用管制)": {"rate": 0.0250, "years": 30, "grace": 0, "cap_wan": None, "ltv": 0.6,
               "note": "央行選擇性信用管制：特定地區第二戶最高貸 6 成、無寬限期。"},
    "信用貸款(補自備款)": {"rate": 0.0400, "years": 7, "grace": 0, "cap_wan": 300, "ltv": None,
               "note": "無擔保、利率約 3–6%+、年限短(約 5–7 年)、額度有限(常見 ≤ 月薪 22 倍)。多用於補自備款。"},
}


def monthly_payment(principal: float, annual_rate: float, years: int, grace_years: int = 0) -> dict:
    """回傳寬限期月付（只繳息）、正常期月付（本息均攤）、總利息。principal 單位：元。"""
    r = annual_rate / 12
    n = years * 12
    g = grace_years * 12
    amort_n = n - g
    if r == 0:
        normal = principal / amort_n
    else:
        normal = principal * r * (1 + r) ** amort_n / ((1 + r) ** amort_n - 1)
    grace = principal * r  # 寬限期只繳息
    total_interest = grace * g + normal * amort_n - principal
    return {
        "grace_monthly": round(grace),
        "normal_monthly": round(normal),
        "months": n,
        "grace_months": g,
        "total_interest_wan": round(total_interest / 10000, 1),
    }


def max_loan_from_payment(monthly: float, rate: float, years: int) -> float:
    """由可負擔月付反推最高本金（元）。本息平均攤還、無寬限。"""
    r = rate / 12
    n = years * 12
    if r == 0:
        return monthly * n
    return monthly * ((1 + r) ** n - 1) / (r * (1 + r) ** n)


def mortgage(total_price_wan: float, down_ratio: float = 0.2, rate: float = 0.0225,
             years: int = 30, grace: int = 0, cap_wan=None, ltv=None) -> dict:
    """擔保型房貸試算：套用最高成數 (ltv) 與額度上限 (cap_wan)。"""
    requested = total_price_wan * (1 - down_ratio)
    loan_wan = requested
    capped_ltv = ltv is not None and (1 - down_ratio) > ltv
    if ltv is not None:
        loan_wan = min(loan_wan, total_price_wan * ltv)
    capped_amt = cap_wan is not None and loan_wan > cap_wan
    if cap_wan is not None:
        loan_wan = min(loan_wan, cap_wan)
    pay = monthly_payment(loan_wan * 10000, rate, years, grace)
    return {
        "loan_wan": round(loan_wan),
        "down_payment_wan": round(total_price_wan - loan_wan),
        "capped_ltv": capped_ltv, "capped_amt": capped_amt,
        "rate": rate, "years": years, "grace_years": grace, **pay,
    }


def loan_from_price(total_price_wan: float, down_ratio: float = 0.2, **kw) -> dict:
    """由總價(萬)與自備款成數推貸款，套用新青安額度上限。"""
    p = {**DEFAULTS, **kw}
    requested = total_price_wan * (1 - down_ratio)
    loan_wan = min(requested, p["loan_cap_wan"])
    over_cap = requested > p["loan_cap_wan"]
    down_payment_wan = total_price_wan - loan_wan
    pay = monthly_payment(loan_wan * 10000, p["annual_rate"], p["years"], p["grace_years"])
    return {
        "total_price_wan": total_price_wan,
        "loan_wan": round(loan_wan),
        "down_payment_wan": round(down_payment_wan),
        "over_cap": over_cap,
        "annual_rate": p["annual_rate"],
        "years": p["years"],
        "grace_years": p["grace_years"],
        **pay,
    }


if __name__ == "__main__":
    # 範例：2000 萬物件、自備 2 成、新青安 30 年
    import json
    print(json.dumps(loan_from_price(2000, down_ratio=0.2), ensure_ascii=False, indent=2))
