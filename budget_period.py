"""One explicit, household-local date contract. Stored end is exclusive.

Missing end_exclusive means the exact legacy twelve-month interval. Reading an
old plan never adds fields to it or changes an approved snapshot.
"""
from dataclasses import dataclass
from datetime import date,timedelta
from finance import add_months


@dataclass(frozen=True)
class BudgetPeriod:
    start:date
    end:date

    def __post_init__(self):
        if self.end<=self.start:raise ValueError('Budget end must be after its start (exclusive boundary).')

    @classmethod
    def from_plan(cls,plan):
        if 'draft' in plan:plan=plan['draft']
        start=date.fromisoformat(str(plan['start']))
        return cls(start,date.fromisoformat(str(plan['end_exclusive'])) if plan.get('end_exclusive') else add_months(start,12))

    @classmethod
    def selected(cls,start,inclusive_end):return cls(start,inclusive_end+timedelta(days=1))

    @classmethod
    def preset(cls,start,months):
        if months not in (3,6,12):raise ValueError('Choose 3, 6 or 12 months, or custom dates.')
        return cls(start,add_months(start,months))

    @property
    def inclusive_end(self):return self.end-timedelta(days=1)

    def contains(self,day):return self.start<=day<self.end

    def months(self):
        cursor=self.start.replace(day=1);rows=[]
        while cursor<self.end:
            following=add_months(cursor,1)
            rows.append((max(self.start,cursor),min(self.end,following)))
            cursor=following
        return rows


def period_end(plan):return BudgetPeriod.from_plan(plan).end


def month_starts(plan):
    return [left.replace(day=1) for left,_ in BudgetPeriod.from_plan(plan).months()]
