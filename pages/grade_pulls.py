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
name_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")

# color-palettes
ipp_colors = {
    "On Track": "#1F77B4",
    "IPP": "#FF0000",
    "Warning": "#66B2FF"
}
assign_colors = {
    ">95%": "#1F77B4",
    "<85%": "#FF0000",
    "85-94%": "#66B2FF"
}


def check_password(password: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == PASSWORD_HASH


@st.cache_data(ttl=600)
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


@st.cache_data(ttl=600)
def get_assignments(end_date):
    closest_file = None
    closest_date = None

    for dirpath, _, filenames in conn.fs.walk(GRADE_SOURCE):
        for name in filenames:
            match = name_pattern.match(name)
            # files guaranteed to exist so no need to check for None
            datestr = match.group(1)

            # get date
            fdate = datetime.strptime(datestr, "%Y-%m-%d")

            if fdate <= end_date:
                if closest_date is None or fdate > closest_date:
                    closest_date = fdate
                    closest_file = name

    return conn.read(f"{dirpath}/{closest_file}", input_format="csv", ttl=600)


st.set_page_config(
    page_title="IPP Template",
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
            st.stop()
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
    student_data = get_students(start_date, end_date)
    assignment_data = get_assignments(end_date)

    # filter according to course id
    student_data = student_data[student_data["course"] == int(course_id)]
    assignment_data = assignment_data[assignment_data["course"] == int(course_id)]

    top_col1, top_col2, top_col3 = st.columns(
        3, gap="small", vertical_alignment="center", border=True
    )

    with top_col1:
        student_data["date"] = pd.to_datetime(student_data["date"])

        # get the latest data
        latest_grades = student_data[student_data["date"] == student_data["date"].max()]

        # label data
        latest_grades.loc[:, "category"] = np.where(latest_grades["current_grade"] >= 80, "On Track", None)
        latest_grades.loc[:, "category"] = np.where(
            (latest_grades["current_grade"] >= 75) & (latest_grades["current_grade"] < 80),
            "Warning", latest_grades["category"])
        latest_grades.loc[:, "category"] = np.where(latest_grades["current_grade"] <= 74, "IPP", latest_grades["category"])

        # calculate proportions of gpa sections while preserving student names
        agg_gpa = (
            latest_grades
            .groupby('category', as_index=False)
            .agg(
                proportion=("current_grade", "size"),
                students=("name", lambda x: "<br>".join(sorted(x)))
            )
        )
        agg_gpa["proportion"] = agg_gpa["proportion"] / agg_gpa["proportion"].sum()

        fig_gpa = px.pie(
            agg_gpa, values='proportion', names='category', color="category",
            color_discrete_map=ipp_colors, title='Current GPA', custom_data=["students"]
        )
        fig_gpa.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(255,255,255,0.8)"
            )
        )

        fig_gpa.update_traces(
            hole=0.6,
            hoverlabel=dict(font_size=11),
            name="",
            hovertemplate=(
                "<b>Students in %{label}</b><br>" +
                "%{customdata[0]}"
            )
        )

        select_gpa = st.plotly_chart(
            fig_gpa,
            use_container_width=True,
            key="gpa"
        )

    with top_col2:
        # filter for attendance
        attendance = assignment_data[assignment_data["title"] == "Roll Call Attendance"]

        # label attendance rates
        attendance.loc[:, "category"] = np.where(attendance["score"] >= 90, "On Track", None)
        attendance.loc[:, "category"] = np.where(
            (attendance["score"] >= 75) & (attendance["score"] < 90),
            "Warning", attendance["category"])
        attendance.loc[:, "category"] = np.where(attendance["score"] <= 74, "IPP", attendance["category"])

        # join with students to get names
        attend_names = pd.merge(attendance, latest_grades, left_on="user_id", right_on="user_id")[["user_id", "score", "name", "category_x"]]

        # calculate proportions of attendance sections while preserving student names
        agg_attend = (
            attend_names
            .groupby('category_x', as_index=False)
            .agg(
                proportion=("score", "size"),
                students=("name", lambda x: "<br>".join(sorted(x)))
            )
        )
        agg_attend["proportion"] = agg_attend["proportion"] / agg_attend["proportion"].sum()

        fig_attend = px.pie(
            agg_attend, values='proportion', names='category_x', color="category_x",
            color_discrete_map=ipp_colors, title='Current Attendance Rates', custom_data=["students"]
        )
        fig_attend.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(255,255,255,0.8)"
            )
        )

        fig_attend.update_traces(
            hole=0.6,
            hoverlabel=dict(font_size=11),
            name="",
            hovertemplate=(
                "<b>Students in %{label}</b><br>" +
                "%{customdata[0]}"
            )
        )

        select_attend = st.plotly_chart(
            fig_attend,
            use_container_width=True,
            key="attend"
        )

    with top_col3:
        # filter for applicable assignments
        filtered_assign = assignment_data[
            (assignment_data["title"] != "Roll Call Attendance") &
            (assignment_data["points_possible"].notna())
        ]
        # count up unsubmitted/late assignments
        filtered_assign.loc[:, "on_time"] = np.where(
            filtered_assign["submitted_at"].notna() & (filtered_assign["submitted_at"] <= filtered_assign["due"]),
            True,
            False
        )
        # calculate ratios of on-time assignments
        assign_ratios = (
            filtered_assign.groupby("user_id")["on_time"]
            .value_counts(normalize=True)
            .reset_index()
        )
        # select only ontime rates
        assign_ratios = assign_ratios[assign_ratios["on_time"]]

        # label student by ontime submission rate
        assign_ratios.loc[:, "category"] = np.where(
            assign_ratios["proportion"] >= 0.95,
            ">95%",
            None
        )
        assign_ratios.loc[:, "category"] = np.where(
            (assign_ratios["proportion"] >= 0.85) & (assign_ratios["proportion"] < 0.94),
            "85-94%",
            assign_ratios["category"]
        )
        assign_ratios.loc[:, "category"] = np.where(
            (assign_ratios["proportion"] < 0.85),
            "<85%",
            assign_ratios["category"]
        )

        # join with students to get names
        ontime_names = pd.merge(assign_ratios, latest_grades, left_on="user_id", right_on="user_id")[["user_id", "proportion", "name", "category_x"]]

        # calculate proportions of on-time submission sections while preserving student names
        agg_ontime = (
            ontime_names
            .groupby('category_x', as_index=False)
            .agg(
                proportion=("proportion", "size"),
                students=("name", lambda x: "<br>".join(sorted(x)))
            )
        )
        agg_ontime["proportion"] = agg_ontime["proportion"] / agg_ontime["proportion"].sum()

        fig_assign = px.pie(
            agg_ontime, values='proportion', names='category_x',
            color="category_x", color_discrete_map=assign_colors,
            title='Current On-Time Submission Rates', custom_data=["students"]
        )
        fig_assign.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5
            )
        )
        fig_assign.update_traces(
            hole=0.6,
            hoverlabel=dict(font_size=11),
            name="",
            hovertemplate=(
                "<b>Students in %{label}</b><br>" +
                "%{customdata[0]}"
            )
        )

        select_assign = st.plotly_chart(
            fig_assign,
            use_container_width=True,
            key="assign"
        )

    bottom_col1, bottom_col2 = st.columns(
        2, gap="small", vertical_alignment="center", border=True
    )

    student_data["date"] = pd.to_datetime(student_data["date"])

    with bottom_col1:
        # Flag students below threshold
        student_data["grade_outlier"] = student_data["current_grade"] < 75

        # Build figure
        fig_time = go.Figure()

        for uid, g in student_data.groupby("name"):
            is_outlier = g["grade_outlier"].any()
            color = "red" if is_outlier else "grey"

            fig_time.add_trace(
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
        fig_time.update_layout(
            title="GPA Over Time",
            xaxis_title="Date",
            yaxis_title="Current Grade",
            yaxis=dict(range=[0, 100]),
            template="plotly_white",
            height=600,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )

        st.plotly_chart(fig_time, use_container_width=True)

    with bottom_col2:
        # Flag students below 2 standard-deviation of log-transformed activity
        student_data["avg_hours_per_week"] = student_data["total_activity_time"] / 60 / 60 / 28
        log_vals = np.log1p(student_data["avg_hours_per_week"])
        threshold = np.expm1(log_vals.mean() - (1 * log_vals.std()))

        student_data["activity_outlier"] = student_data["avg_hours_per_week"] < threshold

        # Build figure
        fig_time = go.Figure()

        for uid, g in student_data.groupby("name"):
            is_outlier = g["activity_outlier"].any()
            color = "red" if is_outlier else "grey"

            fig_time.add_trace(
                go.Scatter(
                    x=g["date"],
                    y=g["avg_hours_per_week"],
                    mode="lines+markers",
                    name=str(uid),
                    line=dict(color=color),
                    marker=dict(color=color),
                    showlegend=False
                )
            )

        # Update layout
        fig_time.update_layout(
            title="Average Activity Spent per Week",
            xaxis_title="Date",
            yaxis_title="Rolling Average of Hours per Week",
            template="plotly_white",
            height=600,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )

        st.plotly_chart(fig_time, use_container_width=True)