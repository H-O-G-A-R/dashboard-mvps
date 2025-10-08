"""
I pledge that this script will not be the end-all/be-all product
"""

import streamlit as st
from st_files_connection import FilesConnection

import hashlib
from datetime import datetime, date
import re

import pandas as pd
import numpy as np

import plotly.express as px
import plotly.graph_objects as go

# constants
PASSWORD_HASH = "27e51d34338d8d346e1574cb9a10c11787754a892e2916562c6fa785abec8249"
# connections
conn = st.connection('gcs', type=FilesConnection)

STUDENT_SOURCE = "dsteam-data/canvas/students"
ATTEND_SOURCE = "dsteam-data/zoom/participants"

# regex patterns
name_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")

# associated course-ids
course_names = {
    "172": "IF '25 Data Science Cohort A",
    "176": "IF '25 Data Science Cohort B",
}

# color-palettes
ipp_colors = {
    "On Track": "#1F77B4",
    "IPP": "#FF0000",
    "Warning": "#66B2FF"
}


def check_password(password: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == PASSWORD_HASH


def get_students(start_date: datetime, end_date: datetime):
    """Function to pull student data between dates
    """

    for dirpath, _, filenames in conn.fs.walk(STUDENT_SOURCE):
        valid_files = []
        # parse all files that fall between the datetime and match the courseid
        for name in filenames:
            match = name_pattern.match(name)
            # files guaranteed to exist so no need to check for None
            datestr = match.group(1)

            # get date
            fdate = datetime.strptime(datestr, "%Y-%m-%d")

            if start_date <= fdate <= end_date:
                # open data as pd object
                df = conn.read(f"{dirpath}/{name}", input_format="csv", ttl=600)
                # append as files to process
                valid_files.append(df)

    joined_students = pd.concat(valid_files)
    return joined_students


def get_attendance(course_id: str, start_date: datetime, end_date: datetime):
    """Function to pull attendance data between dates
    """

    for dirpath, _, filenames in conn.fs.walk(ATTEND_SOURCE):
        valid_files = []
        # parse all files that fall between the datetime and match the courseid
        for name in filenames:
            match = name_pattern.match(name)
            # files guaranteed to exist so no need to check for None
            datestr = match.group(1)

            # get date
            fdate = datetime.strptime(datestr, "%Y-%m-%d")

            if start_date <= fdate <= end_date:
                # open data as pd object
                df = conn.read(f"{dirpath}/{name}", input_format="csv", ttl=600)
                # check for correct course-id
                if df.loc[1, "Topic"] != course_names[course_id]:
                    continue
                # grab data beyond header
                df = df.iloc[3:].reset_index(drop=True)
                df.columns = df.iloc[0]
                df = df[1:].reset_index(drop=True)

                # append as files to process
                valid_files.append(df)

    joined_attendance = pd.concat(valid_files)
    return joined_attendance


st.set_page_config(
    page_title="Attendance Template",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("Locked")
    password_input = st.text_input("Enter password:", type="password")
    if password_input:
        if check_password(password_input):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
else:
    st.sidebar.header("Filter")
    course_id = st.sidebar.selectbox(
        "Select Course ID",
        options=[172, 176],
        index=0
    )
    start_date = st.sidebar.date_input(
        "Start Date",
        value=date(2025, 8, 1),
        min_value=date(2024, 3, 1),
        max_value=date.today()
    )
    end_date = st.sidebar.date_input(
        "End Date",
        value=date.today(),
        min_value=start_date,
        max_value=date.today()
    )
    st.sidebar.subheader("Actions")
    if st.sidebar.button("View Raw Grades", key="Grades"):
        st.session_state["show_grade_modal"] = True
    if st.sidebar.button("Generate IPP Report", key="Report"):
        st.session_state["show_ipp_modal"] = True

    # transform datetimes
    start_date = datetime.combine(start_date, datetime.min.time())
    end_date = datetime.combine(end_date, datetime.min.time())

    # pull data
    attend_data = get_attendance(course_id, start_date, end_date)

    top_col1, top_col2, top_col3 = st.columns(
        3, gap="small", vertical_alignment="center", border=True
    )