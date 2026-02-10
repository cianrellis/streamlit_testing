"""
Tab: Daily KMC Analysis
Renders the Daily KMC Analysis tab (Tab 4) for the KMC Dashboard.
Shows daily KMC trends and usage patterns.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from dashboard_utils import safe_dataframe_display
from dashboard_metrics import calculate_daily_kmc_analysis


def render_daily_kmc_tab(filtered_data, discharge_data):
    """
    Render the Daily KMC Analysis tab (Tab 4).
    Shows daily KMC trends and usage patterns.
    """
    st.header("Daily KMC Analysis - Last 7 Days")

    # DEBUG: Add cache clear button for testing
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🗑️ Clear Cache", help="Clear calculation cache to force refresh"):
            st.cache_data.clear()
            st.success("Cache cleared! Refresh to see updated data.")
            st.rerun()

    # Add description of daily KMC metrics
    with st.expander("📊 About Daily KMC Analysis", expanded=False):
        st.markdown("""
        **Daily KMC Hours Calculation:**
        - **Data Source**: ageDays collection → totalKMCToday field (in minutes)
        - **Calculation**: Average KMC hours per baby = (Total KMC minutes ÷ Number of babies) ÷ 60
        - **Date Matching**: Uses ageDayDate timestamps from ageDays records
        - **Filtering**: Only includes babies with KMC > 0 minutes on that specific date
        - **Exclusions**: Babies discharged on the same date as their KMC session are excluded from that day's analysis
        - **Discharge Date Sources**: Checked hierarchically - discharges collection → baby collection → babyBackUp collection

        **Clinical Context:**
        - **Target**: 8+ hours/day of KMC for optimal outcomes
        - **Minimum**: 2+ hours/day shows clinical benefit
        - **Very low (<2h)**: May indicate calculation errors or poor adherence

        **Table Legend:**
        - 🟢 Green: >6 hours (excellent)
        - 🟡 Yellow: 2-6 hours (adequate)
        - 🔴 Red: <2 hours (needs attention)
        """)

    st.caption("Average KMC hours by hospital and baby location (Current Location of the Baby)")

    # Calculate daily KMC analysis
    analysis_data, hospitals, locations, excluded_counts = calculate_daily_kmc_analysis(filtered_data, discharge_data)
    
    if not analysis_data:
        st.info("No daily KMC data available for the last 7 days")
        return

    # Iterate over dates (newest first)
    for date_key in sorted(analysis_data.keys(), reverse=True):
        date_obj = datetime.strptime(date_key, '%Y-%m-%d')
        excluded_count = excluded_counts.get(date_key, 0)

        st.subheader(f"{date_obj.strftime('%A, %B %d, %Y')}")
        if excluded_count > 0:
            st.info(f"ℹ️ **{excluded_count} babies excluded** from analysis - discharged on same day as KMC session")
        else:
            st.info("ℹ️ **0 babies excluded** - no same-day discharges matching KMC sessions")
        
        # Create styled table data
        table_data = []
        for location in locations:
            row = {'Location': location}
            for hospital in hospitals:
                data = analysis_data[date_key].get(hospital, {}).get(location, {})
                avg_hours = data.get('average_kmc_hours', 0)
                baby_count = data.get('baby_count', 0)
                
                if baby_count > 0:
                    # Color coding based on hours
                    if avg_hours >= 6:
                        color = "#10B981"  # Green
                        emoji = "🟢"
                    elif avg_hours >= 4:
                        color = "#F59E0B"  # Yellow
                        emoji = "🟡"
                    elif avg_hours >= 1:
                        color = "#F97316"  # Orange
                        emoji = "🟠"
                    else:
                        color = "#EF4444"  # Red
                        emoji = "🔴"
                    
                    row[hospital] = f"{emoji} {avg_hours:.1f}h ({baby_count})"
                else:
                    row[hospital] = "-"
            table_data.append(row)
        
        # Display colored table
        df = pd.DataFrame(table_data)
        safe_dataframe_display(df, width='stretch')

        # Check for low hours (< 2) and show detailed data
        low_hours_entries = []
        for hospital in hospitals:
            for location in locations:
                data = analysis_data[date_key].get(hospital, {}).get(location, {})
                avg_hours = data.get('average_kmc_hours', 0)
                baby_count = data.get('baby_count', 0)
                total_minutes = data.get('total_kmc_minutes', 0)

                if baby_count > 0 and avg_hours < 2:
                    low_hours_entries.append({
                        'Hospital': hospital,
                        'Location': location,
                        'Avg Hours': f"{avg_hours:.1f}h",
                        'Baby Count': baby_count,
                        'Total Minutes': total_minutes,
                        'Details': f"{total_minutes} minutes ÷ {baby_count} babies = {avg_hours:.1f}h average"
                    })

        # Show warning and detailed data for low hours
        if low_hours_entries:
            st.warning(f"⚠️ **{len(low_hours_entries)} hospital-location combinations** with very low KMC hours (< 2h):")

            with st.expander("🔍 Detailed Analysis: Low KMC Hours", expanded=True):
                st.write("**Possible reasons for low KMC hours:**")
                st.write("• Data entry errors or missing sessions")
                st.write("• Babies too sick for extended KMC")
                st.write("• Staff training needs")
                st.write("• Equipment or space limitations")
                st.write("")

                low_hours_df = pd.DataFrame(low_hours_entries)
                safe_dataframe_display(low_hours_df, width='stretch')

    # Global Legend at bottom
    st.markdown("**Legend:** 🟢 ≥6h (Excellent) | 🟡 4-6h (Good) | 🟠 1-4h (Needs Improvement) | 🔴 <1h (Critical)")
    st.markdown("---")
