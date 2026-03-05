import streamlit as st
st.title("CAM TEST")
img = st.camera_input("Take photo")
st.write("img:", "OK" if img else "None")
if img:
    st.image(img)