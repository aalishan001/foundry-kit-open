#!/usr/bin/env python3
"""Estimate monthly in-hand pay from annual CTC (India, new tax regime). Every assumption is printed.
Usage: inhand.py <ctc_lpa> [--basic-pct 40] [--variable-pct 0] [--no-gratuity] [--pf-cap] [--state <name> | --pt <rupees/yr>]
  --pf-cap   PF on the statutory wage ceiling (15,000/month) instead of full basic
  --state    professional tax from the small table below (states without one: 0); otherwise --pt, otherwise none
Slabs and rebate reflect the new regime for FY2025-26; check them each year and edit SLABS if they change.
"""
import sys

SLABS = [(400000, 0.0), (800000, .05), (1200000, .10), (1600000, .15), (2000000, .20), (2400000, .25), (float("inf"), .30)]
STD_DEDUCTION = 75000
REBATE_LIMIT = 1200000   # 87A: zero tax up to this taxable income (with marginal relief)
CESS = .04
# Professional tax per year, only where it is a flat, well-known amount at these salary levels. Anything else: --pt.
PROF_TAX = {"karnataka": 2400, "maharashtra": 2500, "west bengal": 2400, "gujarat": 2400, "telangana": 2400,
            "andhra pradesh": 2400, "delhi": 0, "uttar pradesh": 0, "haryana": 0, "rajasthan": 0, "punjab": 2400}

def slab_tax(t):
    tax, lo = 0.0, 0
    for hi, r in SLABS:
        if t > lo: tax += (min(t, hi) - lo) * r
        lo = hi
    return tax

def income_tax(taxable):
    tax = slab_tax(taxable)
    if taxable <= REBATE_LIMIT: tax = 0
    else: tax = min(tax, taxable - REBATE_LIMIT)  # marginal relief
    sur = .25 if taxable > 2e7 else .15 if taxable > 1e7 else .10 if taxable > 5e6 else 0
    return tax * (1 + sur) * (1 + CESS)

def main(a):
    if not a or a[0].startswith("-"): print(__doc__); return 1
    try: ctc = float(a[0]) * 1e5
    except ValueError: print(f"REJECTED: {a[0]!r} is not a number of lakhs"); return 1
    opt = lambda k, d: float(a[a.index(k) + 1]) if k in a else d
    basic_pct, var_pct = opt("--basic-pct", 40), opt("--variable-pct", 0)
    state = a[a.index("--state") + 1] if "--state" in a else None
    if state is not None:
        if state.lower() not in PROF_TAX: print(f"REJECTED: no professional-tax figure for {state!r}; pass --pt <rupees per year>"); return 1
        pt, pt_note = PROF_TAX[state.lower()], f"{state} professional tax {PROF_TAX[state.lower()]:,}/yr"
    elif "--pt" in a: pt = opt("--pt", 0); pt_note = f"professional tax {pt:,.0f}/yr (given)"
    else: pt, pt_note = 0, "no professional tax (pass --state or --pt)"
    basic = ctc * basic_pct / 100
    pf_base = min(basic, 15000 * 12) if "--pf-cap" in a else basic
    emp_pf = er_pf = .12 * pf_base
    gratuity = 0 if "--no-gratuity" in a else .0481 * basic
    variable = ctc * var_pct / 100
    gross_fixed = ctc - er_pf - gratuity - variable
    taxable = max(gross_fixed + variable - STD_DEDUCTION, 0)
    tax = income_tax(taxable)
    fixed_tax = tax * (gross_fixed / (gross_fixed + variable)) if gross_fixed + variable else 0
    monthly = (gross_fixed - emp_pf - pt - fixed_tax) / 12
    r = lambda x: f"{x:,.0f}"
    print(f"CTC: {r(ctc)}  |  monthly in-hand (fixed, excl. variable): {r(monthly)}")
    print(f"Annual tax incl. cess (on fixed + variable): {r(tax)}")
    print("Assumptions: new regime FY2025-26 slabs; std deduction 75k; 87A rebate to 12L;"
          f" basic {basic_pct:.0f}% of CTC; employer+employee PF 12% of {'capped wage' if '--pf-cap' in a else 'basic'};"
          f" gratuity {'excluded' if '--no-gratuity' in a else '4.81% of basic inside CTC'}; variable {var_pct:.0f}% paid separately;"
          f" {pt_note}; no other deductions or allowances.")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
