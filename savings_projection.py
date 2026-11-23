"""Explicit planning savings pot, separate from cash or verified bank balances.

Owner-approved identity: identified opening savings + period income − expenses.
Reserve earmarks reduce unallocated savings, never total savings or cash twice.
Legacy opening cash is never silently classified as opening savings.
"""
from decimal import Decimal
from finance import money

def project(plan,summary,cash=None):
    opening=plan.get('opening_savings')
    opening=None if opening is None else money(opening)
    if opening is not None and opening<0:raise ValueError('Opening savings cannot be negative.')
    additional=summary['income']-summary['expenses']
    total=None if opening is None else opening+additional
    reserve=summary['contingency']
    target=plan.get('target');outcome=None
    if target:
        kind=target['kind'];amount=money(target['amount'])
        if amount<0:raise ValueError('Target cannot be negative.')
        if kind not in ('additional_savings','total_savings','closing_cash'):raise ValueError('Choose an additional-savings, total-savings or closing-cash target.')
        projected={'additional_savings':additional,'total_savings':total,'closing_cash':cash}[kind]
        outcome=dict(kind=kind,amount=amount,projected=projected,variance=None if projected is None else projected-amount,realised=None)
    return dict(opening=opening,additional=additional,total=total,reserve=reserve,unallocated=None if total is None else total-reserve,target=outcome,realised=None)
