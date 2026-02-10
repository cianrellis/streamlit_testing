"""
Nurses Analysis Tab - Performance and activity monitoring
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from utils.dashboard_utils import safe_dataframe_display
from utils.dashboard_metrics import calculate_nurse_activity

def render_nurses_tab(baby_data, discharge_data, start_date, end_date, selected_hospitals):
    """Render the Nurses Analysis tab"""
    st.header("👩‍⚕️ Nurses Analysis")
    st.caption("Analysis of nurse activities: Follow-ups, Discharges, and Registrations")

    # Processing Data Sources
    st.subheader("📋 Processing Data Sources...")

    try:
        with st.spinner("Analyzing nurse activity data..."):
            nurse_analysis, discharge_counts = calculate_nurse_activity(
                baby_data, discharge_data, start_date, end_date, selected_hospitals
            )

        # Display hierarchical processing summary for discharges if available
        if discharge_counts:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Discharge Collection", discharge_counts['discharge_collection'])
            with col2:
                st.metric("Baby Collection", discharge_counts['baby_collection'])
            with col3:
                st.metric("BabyBackUp Collection", discharge_counts['babybackup_collection'])
            with col4:
                st.metric("Total Unique Discharges", 
                          discharge_counts['discharge_collection'] + 
                          discharge_counts['baby_collection'] + 
                          discharge_counts['babybackup_collection'])
            
            st.success(f"✅ Hierarchical discharge processing completed! Unique UIDs processed (no double counting)")

    except Exception as e:
        st.error(f"Error processing nurse data: {str(e)}")
        nurse_analysis = {}

    # Display results
    if not nurse_analysis:
        st.info("No nurse data found for the selected date range and hospital filter.")
    else:
        # Convert to list for better display
        nurse_list = list(nurse_analysis.values())

        # Summary metrics
        total_nurses = len(nurse_list)
        total_followups = sum(nurse['followUps'] for nurse in nurse_list)
        total_discharges = sum(nurse['discharges'] for nurse in nurse_list)
        total_registrations = sum(nurse['registrations'] for nurse in nurse_list)

        st.subheader("📊 Summary Metrics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Nurses", total_nurses)
        with col2:
            st.metric("Total Follow-ups", total_followups)
        with col3:
            st.metric("Total Discharges", total_discharges)
        with col4:
            st.metric("Total Registrations", total_registrations)

        # Create detailed table
        st.subheader("📋 Detailed Nurse Activity Report")

        # Sort options
        col1, col2 = st.columns(2)
        with col1:
            sort_by = st.selectbox(
                "Sort by:",
                options=['Total Activity', 'Follow-ups', 'Discharges', 'Registrations', 'Nurse Name'],
                key="nurse_sort_option"
            )
        with col2:
            show_zero_activity = st.checkbox("Show nurses with zero activity", value=False)

        # Calculate total activity and sort
        for nurse in nurse_list:
            nurse['totalActivity'] = nurse['followUps'] + nurse['discharges'] + nurse['registrations']

        # Filter zero activity if needed
        if not show_zero_activity:
            nurse_list = [nurse for nurse in nurse_list if nurse['totalActivity'] > 0]

        # Sort data
        if sort_by == 'Total Activity':
            nurse_list.sort(key=lambda x: x['totalActivity'], reverse=True)
        elif sort_by == 'Follow-ups':
            nurse_list.sort(key=lambda x: x['followUps'], reverse=True)
        elif sort_by == 'Discharges':
            nurse_list.sort(key=lambda x: x['discharges'], reverse=True)
        elif sort_by == 'Registrations':
            nurse_list.sort(key=lambda x: x['registrations'], reverse=True)
        elif sort_by == 'Nurse Name':
            nurse_list.sort(key=lambda x: x['nurseName'])

        # Create DataFrame for display
        display_data = []
        for nurse in nurse_list:
            display_data.append({
                'Nurse Name': nurse['nurseName'],
                'Hospital': nurse['hospital'],
                'Follow-ups': nurse['followUps'],
                'Discharges': nurse['discharges'],
                'Registrations': nurse['registrations'],
                'Total Activity': nurse['totalActivity']
            })

        df = pd.DataFrame(display_data)
        safe_dataframe_display(df, width='stretch', hide_index=True)

        # Export functionality
        st.subheader("📥 Export Data")
        if len(display_data) > 0:
            csv = df.to_csv(index=False)
            st.download_button(
                label="📊 Download Nurse Activity Report (CSV)",
                data=csv,
                file_name=f"nurse_activity_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

        # Data source information
        with st.expander("ℹ️ Data Source Information"):
            st.markdown("""
            **Data Sources:**
            - **Follow-ups**: Counted from Baby and BabyBackup collections using `nurseName` field
                - Each baby record has a `followUp` array containing follow-up entries
                - Each entry has `followUpNumber` (1, 2, 3, 7, 14, 28) and is counted separately
                - Only follow-ups with valid dates within the selected date range are counted
            - **Discharges**: Counted using hierarchical approach (no double counting):
                - **Step 1**: Discharge collection using `dischargeNurseName` field (highest priority)
                - **Step 2**: Baby collection using `nurseName` field as fallback (when `discharged = true`)
                - **Step 3**: BabyBackup collection using `nurseName` field as final fallback (when `discharged = true`)
                - Each UID is processed only once to prevent double counting
            - **Registrations**: Counted from BOTH Baby and BabyBackup collections using `nurseName` field (when baby was registered)

            **Filters Applied:**
            - Date Range: All activities are filtered by the selected date range
            - Hospital: Activities are filtered by the selected hospital (if not 'All')
            - Only nurses with specified names are included (excludes 'Not specified')
            """)
