"""Separate fictional-only mobile preview. Never use as the production entry point.

This entry point does not import the production app, secrets or a Supabase SDK.
Its identity is a local scenario namespace, not an authenticated real user.
"""
from types import SimpleNamespace
import streamlit as st
from nestworth_design import styles,brand
from populated_demo import load_demo
from demo_ui import render_demo

st.set_page_config(page_title='Nestworth · Fictional mobile preview',page_icon='⌂',layout='wide')
styles(st);brand(st)
st.sidebar.caption('ISOLATED TEST APP · Fictional · No Supabase connection · Session only')
base='demo:preview-session:fictional-household'
if st.session_state.get('preview_publication')!='8e479d4-uat-2026-11-23':
    load_demo(st.session_state,base);st.session_state['preview_publication']='8e479d4-uat-2026-11-23'
identity=SimpleNamespace(auth=SimpleNamespace(get_user=lambda:SimpleNamespace(user=SimpleNamespace(id='preview-session'))))
render_demo(st,identity,'fictional-household','Nora & Sam · Fictional preview')
