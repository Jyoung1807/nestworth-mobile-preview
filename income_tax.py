"""Annual Australian resident estimates, never payroll withholding or tax advice.

Sources: ATO resident tax rates and low income tax offset (verified 18 Nov 2026).
Medicare is an optional conservative flat 2%; reductions/exemptions, MLS, HELP,
deductions, super and other offsets are excluded. Override with payslip net pay.
"""
from decimal import Decimal
from finance import money

PER_YEAR={'Weekly':52,'Fortnightly':26,'Monthly':12,'Quarterly':4,'Six-monthly':2,'Annual':1}
FIRST_RATE={'2024–25':Decimal('.16'),'2025–26':Decimal('.16'),'2026–27':Decimal('.15'),'2027–28':Decimal('.14')}


def tax_year(day):
    year=day.year if day.month>=7 else day.year-1
    return f'{year}–{str(year+1)[-2:]}'


def estimate_net(amount,frequency,year,medicare=True):
    if year not in FIRST_RATE:raise ValueError('Choose a supported Australian tax year or enter net income.')
    if frequency not in PER_YEAR:raise ValueError('Choose a regular income frequency.')
    annual=money(amount)*PER_YEAR[frequency]
    tax=Decimal(0)
    for left,right,rate in [(18200,45000,FIRST_RATE[year]),(45000,135000,Decimal('.30')),(135000,190000,Decimal('.37')),(190000,None,Decimal('.45'))]:
        tax+=max(Decimal(0),(min(annual,Decimal(right)) if right else annual)-left)*rate
    lito=max(Decimal(0),Decimal(700) if annual<=37500 else Decimal(700)-(annual-37500)*Decimal('.05') if annual<=45000 else Decimal(325)-(annual-45000)*Decimal('.015'))
    tax=money(max(Decimal(0),tax-lito));levy=money(annual*Decimal('.02')) if medicare else money(0)
    net=money(max(Decimal(0),annual-tax-levy))
    return dict(annual_gross=money(annual),income_tax=tax,medicare=levy,annual_net=net,net_per_payment=money(net/PER_YEAR[frequency]),tax_year=year)
