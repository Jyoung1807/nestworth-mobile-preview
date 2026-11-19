"""Household-local calendar dates. Weeks are Monday inclusive to next Monday exclusive.

Date-only financial records already represent household local dates and are never
shifted. UTC/aware timestamps are converted before selecting their calendar week.
Financial horizons and monthly boundaries remain independent from full week labels.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE='Australia/Brisbane'
AUSTRALIAN_TIMEZONES=('Australia/Brisbane','Australia/Sydney','Australia/Melbourne',
                      'Australia/Adelaide','Australia/Perth','Australia/Darwin','Australia/Hobart',
                      'Australia/Lord_Howe','Australia/Eucla','Australia/Broken_Hill')


def household_timezone(state):
    return state.get('profile',{}).get('timezone',DEFAULT_TIMEZONE)


def local_date(value,timezone=DEFAULT_TIMEZONE):
    zone=ZoneInfo(timezone)
    if isinstance(value,datetime):
        return (value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)).date()
    return value if isinstance(value,date) else date.fromisoformat(value)


def week_start(value,timezone=DEFAULT_TIMEZONE):
    day=local_date(value,timezone)
    return day-timedelta(days=day.weekday())


def week_bounds(value,timezone=DEFAULT_TIMEZONE):
    left=week_start(value,timezone)
    return left,left+timedelta(days=7)


def week_instants(value,timezone=DEFAULT_TIMEZONE):
    left,right=week_bounds(value,timezone)
    zone=ZoneInfo(timezone)
    return datetime.combine(left,time.min,zone),datetime.combine(right,time.min,zone)


def week_label(value,timezone=DEFAULT_TIMEZONE):
    left,right=week_bounds(value,timezone);sunday=right-timedelta(days=1)
    begin=left.strftime('%a %d %b')+(f' {left.year}' if left.year!=sunday.year else '')
    return begin+' – '+sunday.strftime('%a %d %b %Y')


def weeks_in_horizon(start,end):
    cursor=week_start(start);weeks=[]
    while cursor<end:
        weeks.append(cursor);cursor+=timedelta(days=7)
    return weeks
