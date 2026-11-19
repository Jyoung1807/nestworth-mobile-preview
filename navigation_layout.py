"""Supported presentation-only component, sharing the recovery bridge technology."""
from pathlib import Path
import streamlit.components.v2 as components

_layout=components.component('household_navigation_layout',js=Path(__file__).with_suffix('.js').read_text())


def navigation_layout(st,route):
    # Only enum-based route names, never financial/account data. The component
    # emits no server events and uses no persistent browser storage.
    _layout(data={'route':route},key='household_navigation_layout')
