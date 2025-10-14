"""
I pledge that this script will not be the end-all/be-all product
"""

import streamlit as st
from st_files_connection import FilesConnection

import hashlib
from datetime import datetime, date, timedelta
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
name_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})\.csv$")

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


def get_students(course_id: str, end_date: datetime):
    """Function to pull most recent students
    """
    closest_date = None
    closest_df = pd.DataFrame()

    for dirpath, _, filenames in conn.fs.walk(STUDENT_SOURCE):
        for name in filenames:
            match = name_pattern.search(name)

            if match:
                # files guaranteed to exist so no need to check for None
                datestr = match.group(1)

                # get date
                fdate = datetime.strptime(datestr, "%Y-%m-%d").date()

                if fdate <= end_date:
                    if closest_date is None or fdate > closest_date:
                        closest_df = conn.read(f"{dirpath}/{name}", input_format="csv", ttl=600)
                        # check for correct course-id
                        closest_df = closest_df[closest_df["course"] == int(course_id)]
                        closest_date = fdate

    # grab data beyond header
    return closest_df


def get_attendance(course_id: str, start_date: datetime, end_date: datetime):
    """Function to pull attendance data between dates
    """

    for dirpath, _, filenames in conn.fs.walk(ATTEND_SOURCE):
        valid_files = []
        # parse all files that fall between the datetime and match the courseid
        for name in filenames:
            match = name_pattern.search(name)
            if match:
                # files guaranteed to exist so no need to check for None
                datestr = match.group(1)

                # get date
                fdate = datetime.strptime(datestr, "%Y-%m-%d").date()

                if start_date <= fdate <= end_date:
                    # open data as text object for initial
                    new_cols = [
                        "Topic", "ID", "Host", "Duration (minutes)",
                        "Start time", "End time", "Participants", "Extra"
                    ]
                    df = conn.read(f"{dirpath}/{name}", input_format="csv", names=new_cols, ttl=600)

                    # check for correct course-id
                    if df.loc[1, "Topic"] != course_names[course_id]:
                        continue
                    # grab data beyond header
                    data = df.iloc[2:].reset_index(drop=True)
                    data.columns = data.iloc[0]
                    data = data[1:].reset_index(drop=True)
                    data["date"] = fdate - timedelta(days=1)
                    data["end_time"] = df.loc[1, "End time"]
                    data["start_time"] = df.loc[1, "Start time"]
                    data["total_duration"] = df.loc[1, "Duration (minutes)"]

                    # append as files to process
                    valid_files.append(data)

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
        options=["172", "176"],
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
    # pull data
    attend_data = get_attendance(course_id, start_date, end_date)
    student_data = get_students(course_id, end_date)

    student = st.sidebar.multiselect(
        "Select Students",
        options=student_data["name"].tolist(),
        default=student_data["name"].tolist()
    )
    st.sidebar.subheader("Actions")
    if st.sidebar.button("Generate Attendance Report", key="Report"):
        st.session_state["show_attend_modal"] = True

    # transform datetimes
    start_date = datetime.combine(start_date, datetime.min.time())
    end_date = datetime.combine(end_date, datetime.min.time())

    # transform columns
    attend_data["Duration (minutes)"] = attend_data["Duration (minutes)"].astype(int)

    # perform data transforms to get attendance on all students
    # TODO: find join strat between students and attendance (idea map common names to present names)
    student_report = attend_data.groupby(["Name (original name)", "date"]).agg(
        {
            "Duration (minutes)": 'sum',
            "Join time": "min",
            "Leave time": "max"
        }
    ).reset_index()

    student_report["date"] = pd.to_datetime(student_report["date"])

    daily_student = (
        student_report
        .resample(rule="1D", on="date")[["Name (original name)", "Duration (minutes)", "Join time", "Leave time"]]
        .max().fillna(0).reset_index()
    )

    #daily_student

    top_col1, top_col2 = st.columns(
        2, gap="small", vertical_alignment="center", border=True
    )