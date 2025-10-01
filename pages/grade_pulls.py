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
GRADE_SOURCE = "dsteam-data/canvas/grades"
# regex patterns
name_pattern = re.compile(r"^(\d{3,})_(\d{4}-\d{2}-\d{2})\.csv$")


def check_password(password: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == PASSWORD_HASH


def get_students(course_id: str, start_date: datetime, end_date: datetime):
    """Function to pull student data between dates
    """

    for dirpath, _, filenames in conn.fs.walk(STUDENT_SOURCE):
        valid_files = []
        # parse all files that fall between the datetime and match the courseid
        for name in filenames:
            match = name_pattern.match(name)
            # files guaranteed to exist so no need to check for None
            cid, datestr = match.groups()

            # get date
            fdate = datetime.strptime(datestr, "%Y-%m-%d")

            if cid == course_id and (start_date <= fdate <= end_date):
                # open data as pd object
                df = conn.read(f"{dirpath}/{name}", input_format="csv", ttl=600)
                # append as files to process
                valid_files.append(df)

    joined_students = pd.concat(valid_files)
    return joined_students


def get_assignments(course_id, end_date):
    closest_file = None
    closest_date = None

    for dirpath, _, filenames in conn.fs.walk(GRADE_SOURCE):
        for name in filenames:
            match = name_pattern.match(name)
            # files guaranteed to exist so no need to check for None
            cid, datestr = match.groups()

            # get date
            fdate = datetime.strptime(datestr, "%Y-%m-%d")

            if course_id == cid and fdate <= end_date:
                if closest_date is None or fdate > closest_date:
                    closest_date = fdate
                    closest_file = name

    return conn.read(f"{dirpath}/{closest_file}", input_format="csv", ttl=600)


st.set_page_config(
    page_title="Dashboard Template",
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
    st.sidebar.subheader("Actions")
    st.sidebar.button("View Raw Grades")
    st.sidebar.button("Generate IPP Report")
    st.sidebar.button("Email Students Below Threshold")

    # transform datetimes
    start_date = datetime.combine(start_date, datetime.min.time())
    end_date = datetime.combine(end_date, datetime.min.time())

    # pull data
    student_data = get_students(course_id, start_date, end_date)
    assignment_data = get_assignments(course_id, end_date)

    top_col1, top_col2, top_col3 = st.columns(3, gap="large")
    with top_col1:
        student_data["date"] = pd.to_datetime(student_data["date"])

        # get the latest data
        latest_grades = student_data[student_data["date"] == student_data["date"].max()]

        # label data
        latest_grades.loc[:, "category"] = np.where(latest_grades["current_grade"] >= 80, "On Track", None)
        latest_grades.loc[:, "category"] = np.where(
            (latest_grades["current_grade"] >= 75) & (latest_grades["current_grade"] < 80),
            "Warning", latest_grades["category"])
        latest_grades.loc[:, "category"] = np.where(latest_grades["current_grade"] <= 74, "Below 75% - IPP", latest_grades["category"])

        gpa_ratios = latest_grades["category"].value_counts(normalize=True).reset_index()

        fig_gpa = px.pie(gpa_ratios, values='proportion', names='category', title='GPA')
        fig_gpa.update_traces(hole=0.5)

        select_gpa = st.plotly_chart(
            fig_gpa,
            use_container_width=True,
            on_select="rerun",
            key="gpa"
        )

        if select_gpa.selection:
            print(select_gpa)
            #selected_category = gpa_ratios.loc[select_gpa[0], 'Category']

    with top_col2:
        # filter for attendance
        attendance = assignment_data[assignment_data["title"] == "Roll Call Attendance"]

        # label attendance rates
        attendance.loc[:, "category"] = np.where(attendance["score"] >= 90, "On Track", None)
        attendance.loc[:, "category"] = np.where(
            (attendance["score"] >= 75) & (attendance["score"] < 89),
            "Warning", attendance["category"])
        attendance.loc[:, "category"] = np.where(attendance["score"] <= 74, "Below 75% - IPP", attendance["category"])

        attend_ratios = attendance["category"].value_counts(normalize=True).reset_index()

        fig_attend = px.pie(attend_ratios, values='proportion', names='category', title='Attendance Rates')
        fig_attend.update_traces(hole=0.5)

        st.plotly_chart(fig_attend, use_container_width=True)

    with top_col3:
        st.subheader("Unsubmitted Assignments")
        # filter for applicable assignments
        filtered_data = assignment_data[
            (assignment_data["title"] != "Roll Call Attendance") &
            (assignment_data["points_possible"].notna())
        ][["assign_id", "title", "user_id", "submitted_at"]]
        # count up null assignments
        missing_assign = filtered_data.isna().\
            groupby(filtered_data["user_id"])["submitted_at"].\
            sum().reset_index()

        #st.plotly_chart(fig, use_container_width=True)

    st.subheader("GPA Progression")
    student_data["date"] = pd.to_datetime(student_data["date"])

    mean_grade = student_data["current_grade"].mean()
    std_grade = student_data["current_grade"].std()
    threshold = mean_grade - 2 * std_grade

    # Flag students below threshold
    student_data["outlier"] = student_data["current_grade"] < threshold

    # Build figure
    fig = go.Figure()

    for uid, g in student_data.groupby("name"):
        is_outlier = g["outlier"].any()
        color = "red" if is_outlier else "grey"

        fig.add_trace(
            go.Scatter(
                x=g["date"],
                y=g["current_grade"],
                mode="lines+markers",
                name=str(uid),
                line=dict(color=color),
                marker=dict(color=color),
                showlegend=False
            )
        )

    # Update layout
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Current Grade",
        template="plotly_white",
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)
