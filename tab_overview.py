"""
Tab: Overview
Renders the Overview tab (Tab 1) for the KMC Dashboard.
Shows basic program metrics and hospital distribution.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard_utils import THEME_A_COLORS


def render_overview_tab(baby_data, filtered_data):
    """
    Render the Overview tab (Tab 1).
    Shows basic program metrics and hospital distribution.
    """
    st.header("Program Overview")

    # Add description of overview metrics
    with st.expander("📊 About Overview Metrics", expanded=False):
        st.markdown("""
        **Program Overview Definitions:**
        - **Total Babies**: All babies from 'baby' + 'babyBackUp' collections
        - **Active Cases**: Babies where babyInProgram = true
        - **Current Babies**: Active Cases - Discharged Cases (babies currently in hospital)
        - **Discharged**: Babies where discharged = true (from active cases)
        - **Hospitals**: Number of unique hospitals in filtered data

        **Hospital Distribution**: Shows baby count per hospital from current filtered data
        **Location Analysis**: Breakdown by currentLocationOfTheBaby field
        **KMC Participation**: Percentage of babies who have started KMC (any totalKMCtimeDay > 0)

        **Data Sources**: Firebase collections 'baby', 'babyBackUp', and 'discharges'
        """)

    # Basic metrics - Updated definitions
    total_babies = len(baby_data)  # All babies from both baby and babyBackUp collections
    
    # Get active babies list for discharged calculation
    active_babies_list = [baby for baby in baby_data if baby.get('babyInProgram')]
    active_babies = len(active_babies_list)  # Baby in program is true
    
    discharged_babies = len([baby for baby in active_babies_list if baby.get('discharged')])  # Discharged is true out of active babies
    hospitals_count = len(set(baby.get('hospitalName') for baby in filtered_data if baby.get('hospitalName')))
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Babies", f"{total_babies:,}")
    with col2:
        st.metric("Active Cases", f"{active_babies:,}")
    with col3:
        st.metric("Current Babies", f"{active_babies - discharged_babies:,}")
    with col4:
        st.metric("Discharged", f"{discharged_babies:,}")
    with col5:
        st.metric("Hospitals", hospitals_count)
    
    # Hospital distribution
    hospital_counts = {}
    for baby in filtered_data:
        hospital = baby.get('hospitalName', 'Unknown')
        hospital_counts[hospital] = hospital_counts.get(hospital, 0) + 1
    
    if hospital_counts:
        # Sort alphabetically by hospital name
        sorted_hospitals = sorted(hospital_counts.items(), key=lambda x: x[0])
        x_vals = [item[0] for item in sorted_hospitals]
        y_vals = [item[1] for item in sorted_hospitals]

        fig = px.bar(
            x=x_vals,
            y=y_vals,
            title="Baby Count by Hospital (Alphabetical)",
            color_discrete_sequence=[THEME_A_COLORS['primary']],
            text=y_vals
        )
        fig.update_layout(
            xaxis_title="Hospital",
            yaxis_title="Number of Babies"
        )
        fig.update_traces(texttemplate='%{text}', textposition='outside')
        st.plotly_chart(fig, width='stretch')
