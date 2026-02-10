"""
Tab: Clinical KPIs
Renders the Clinical KPIs tab (Tab 2) for the KMC Dashboard.
Shows registration timeliness, KMC initiation, discharge outcomes, etc.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dashboard_utils import THEME_A_COLORS, convert_unix_to_datetime, safe_dataframe_display


def render_clinical_kpis_tab(filtered_data, discharge_data, followup_data, start_date, end_date):
    """
    Render the Clinical KPIs tab (Tab 2).
    Shows registration timeliness, KMC initiation, discharge outcomes, etc.
    """
    from dashboard_metrics import (
        calculate_registration_timeliness,
        calculate_kmc_initiation_metrics,
        calculate_average_kmc_by_location,
        calculate_discharge_outcomes,
        calculate_followup_metrics,
        calculate_hospital_stay_duration,
        calculate_skin_contact_metrics,
        calculate_individual_critical_reasons,
        calculate_discharged_babies_without_kmc,
    )
    
    st.header("Clinical KPIs")
    
    # ============ REGISTRATION TIMELINESS ============
    st.subheader("Registration Timeliness (Inborn Babies)")

    # Add description of registration timeliness metrics
    with st.expander("📊 About Registration Timeliness Metrics", expanded=False):
        st.markdown("""
        **Registration Timeliness Analysis:**
        - **Data Source**: dateOfBirth vs registrationDate for inborn babies only
        - **Same Day**: Registration within 24 hours of birth
        - **Next Day**: Registration 24-48 hours after birth
        - **Delayed**: Registration more than 48 hours after birth
        - **Inborn Definition**: placeOfDelivery = 'यह अस्पताल' or 'this hospital'

        **Clinical Importance:**
        - **Target**: Same-day registration (within 24h) for optimal care continuity
        - **Acceptable**: Next-day registration (24-48h)
        - **Concerning**: Delayed registration (>48h) may indicate workflow issues

        **Data Quality Notes:**
        - Only includes babies with valid birth and registration dates
        - Excludes outborn babies (different registration workflow)
        """)

    reg_metrics = calculate_registration_timeliness(filtered_data)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Inborn", f"{reg_metrics['total_inborn']:,} out of {len(filtered_data):,} total babies")
    with col2:
        st.metric("Within 24h", f"{reg_metrics['within_24h_percentage']:.1f}%", 
                 f"{reg_metrics['within_24h_count']} babies")
    with col3:
        st.metric("Within 12h", f"{reg_metrics['within_12h_percentage']:.1f}%",
                 f"{reg_metrics['within_12h_count']} babies")
    
    # Registration pie chart
    if reg_metrics['total_inborn'] > 0:
        fig = go.Figure(data=[go.Pie(
            labels=['Within 12h', '12-24h', '>24h'],
            values=[
                reg_metrics['within_12h_count'],
                reg_metrics['within_24h_count'] - reg_metrics['within_12h_count'],
                reg_metrics['total_inborn'] - reg_metrics['within_24h_count']
            ],
            marker_colors=[THEME_A_COLORS['primary'], THEME_A_COLORS['secondary'], '#E5E7EB']
        )])
        fig.update_layout(title="Registration Timeliness Distribution")
        st.plotly_chart(fig, width='stretch')

    # Hospital-wise Registration Metrics Table
    st.subheader("Registration Metrics by Hospital")
    hospital_reg_data = []

    # Group data by hospital
    hospital_registration = {}
    for baby in filtered_data:
        hospital = baby.get('hospitalName', 'Unknown')

        # Check if baby is inborn using same logic as registration_timeliness function
        place_of_delivery = baby.get('placeOfDelivery', '')
        is_inborn = place_of_delivery in ['यह अस्पताल', 'this hospital']

        if is_inborn:
            if hospital not in hospital_registration:
                hospital_registration[hospital] = {
                    'total_inborn': 0,
                    'within_12h': 0,
                    'within_24h': 0
                }

            hospital_registration[hospital]['total_inborn'] += 1

            # Check registration timing
            birth_date = convert_unix_to_datetime(baby.get('dateOfBirth'))
            reg_date = convert_unix_to_datetime(baby.get('registrationDate'))

            if birth_date and reg_date:
                time_diff = reg_date - birth_date
                hours_diff = time_diff.total_seconds() / 3600

                if hours_diff <= 12:
                    hospital_registration[hospital]['within_12h'] += 1
                    hospital_registration[hospital]['within_24h'] += 1
                elif hours_diff <= 24:
                    hospital_registration[hospital]['within_24h'] += 1

    # Create table data
    for hospital, data in hospital_registration.items():
        if data['total_inborn'] > 0:
            within_12h_pct = (data['within_12h'] / data['total_inborn']) * 100
            within_24h_pct = (data['within_24h'] / data['total_inborn']) * 100

            hospital_reg_data.append({
                'Hospital': hospital,
                'Total Inborn Babies': data['total_inborn'],
                'Registered Within 12h': f"{data['within_12h']} ({within_12h_pct:.1f}%)",
                'Registered Within 24h': f"{data['within_24h']} ({within_24h_pct:.1f}%)"
            })

    if hospital_reg_data:
        hospital_reg_df = pd.DataFrame(hospital_reg_data)
        st.dataframe(hospital_reg_df, width='stretch', hide_index=True)
    else:
        st.info("No inborn babies found for hospital registration analysis.")

    st.markdown("---")

    # ============ HOSPITAL STAY DURATION ============
    st.subheader("Average Hospital Stay Duration by Location and Hospital")

    # Add description of hospital stay metrics
    with st.expander("📊 About Hospital Stay Duration Metrics", expanded=False):
        st.markdown("""
        **Hospital Stay Duration Analysis:**
        - **Data Source**: dateOfBirth (or registrationDate) to dischargeDate
        - **Calculation**: Days between admission and discharge
        - **Format**: "X days Y hours" for better readability
        - **Grouping**: By currentLocationOfTheBaby and hospitalName
        - **Include**: Only babies with valid birth/registration and discharge dates

        **Clinical Context:**
        - **Preterm babies**: Typically 10-60+ days depending on gestational age
        - **Term LBW babies**: Usually 5-20 days depending on complications
        - **NICU stays**: Generally longer than PNC stays
        - **Location differences**: SNCU_NICU > Step_Down > PNC expected

        **Data Quality:**
        - Excludes babies without discharge dates (still admitted)
        - Handles cases where birth date might be missing (uses registration date)
        - Deduplicates by UID to avoid double counting
        """)

    stay_duration = calculate_hospital_stay_duration(filtered_data)

    if stay_duration['total_babies'] > 0:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Discharged Babies", stay_duration['total_babies'])

        # Build location_hospital_stats from raw_data
        location_hospital_stats = {}
        if stay_duration.get('raw_data'):
            for record in stay_duration['raw_data']:
                location = record['location']
                hospital = record['hospital']
                key = f"{location} - {hospital}"

                if key not in location_hospital_stats:
                    location_hospital_stats[key] = {
                        'location': location,
                        'hospital': hospital,
                        'durations': [],
                        'count': 0,
                        'total_days': 0,
                        'avg_days': 0,
                        'avg_formatted': '0 days 0 hours'
                    }

                location_hospital_stats[key]['durations'].append(record['stay_duration_days'])
                location_hospital_stats[key]['count'] += 1
                location_hospital_stats[key]['total_days'] += record['stay_duration_days']

            # Calculate averages and format for location+hospital stats
            for key, stats in location_hospital_stats.items():
                if stats['count'] > 0:
                    avg_days_float = stats['total_days'] / stats['count']
                    days = int(avg_days_float)
                    hours = int((avg_days_float - days) * 24)

                    stats['avg_days'] = avg_days_float
                    stats['avg_formatted'] = f"{days} days {hours} hours"

        # Display by location and hospital
        if location_hospital_stats:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("By Location Only")
                if stay_duration['location_stats']:
                    location_df = []
                    for location, stats in stay_duration['location_stats'].items():
                        location_df.append({
                            'Location': location,
                            'Babies': stats['count'],
                            'Average Stay': stats['avg_formatted'],
                            'Days (decimal)': f"{stats['avg_days']:.1f}"
                        })

                    df_location = pd.DataFrame(location_df)
                    st.dataframe(df_location, width='stretch', hide_index=True)

            with col2:
                st.subheader("By Location and Hospital")
                location_hospital_df = []
                for key, stats in location_hospital_stats.items():
                    location_hospital_df.append({
                        'Location': stats['location'],
                        'Hospital': stats['hospital'],
                        'Babies': stats['count'],
                        'Average Stay': stats['avg_formatted'],
                        'Days (decimal)': f"{stats['avg_days']:.1f}"
                    })

                df_location_hospital = pd.DataFrame(location_hospital_df)
                st.dataframe(df_location_hospital, width='stretch', hide_index=True)

    else:
        st.info("No discharged babies found with valid birth and discharge dates.")

    st.markdown("---")

    # ============ KMC INITIATION ============
    st.subheader("KMC Initiation Timing - Inborn vs Outborn")

    # Add description of KMC initiation metrics
    with st.expander("📊 About KMC Initiation Metrics", expanded=False):
        st.markdown("""
        **KMC Initiation Timing Analysis:**
        - **Time to Initiation**: Hours from birth (dateOfBirth) to first KMC session using actual timeStartKMC timestamps
        - **Methodology**: Finds earliest timeStartKMC in observationDay.timeInKMC arrays (fallback to ageDay if timestamps unavailable)
        - **Within 24h/48h**: Percentage of babies who started KMC within these timeframes
        - **Inborn vs Outborn**: Babies born in hospital vs transferred from elsewhere
        - **Data Source**: timeStartKMC timestamps from timeInKMC session arrays in observationDay records

        **Clinical Significance:** Earlier KMC initiation (within 24-48h) improves outcomes for low birth weight babies.

        **Recent Fix**: Now uses actual KMC session start times instead of day-of-life calculations for accurate timing.
        """)

    kmc_initiation = calculate_kmc_initiation_metrics(filtered_data)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        babies_without_kmc = len(filtered_data) - kmc_initiation['total_babies_with_kmc']
        st.metric("Babies with KMC", f"{kmc_initiation['total_babies_with_kmc']:,} out of {len(filtered_data):,}")
        st.caption(f"{babies_without_kmc:,} babies without KMC")
    with col2:
        avg_hours = kmc_initiation['avg_time_to_initiation_hours']
        st.metric("Avg Time to Initiation", f"{avg_hours:.1f}h")
        if avg_hours < 2:
            st.warning("⚠️ Very fast initiation - see details below")
    with col3:
        st.metric("Within 24h", f"{kmc_initiation['within_24h_percentage']:.1f}%",
                 f"{kmc_initiation['within_24h_count']} babies")
    with col4:
        st.metric("Within 48h", f"{kmc_initiation['within_48h_percentage']:.1f}%",
                 f"{kmc_initiation['within_48h_count']} babies")

    # Show detailed data for very fast initiation (< 2 hours)
    if avg_hours < 2:
        st.subheader("🔍 Detailed Analysis: Fast KMC Initiation (< 2 hours)")
        fast_initiation_babies = [baby for baby in kmc_initiation['initiation_data']
                                if baby['time_to_initiation_hours'] < 2]

        if fast_initiation_babies:
            st.warning(f"Found {len(fast_initiation_babies)} babies with KMC initiation < 2 hours. This may indicate:")
            st.write("• Data entry errors (KMC time recorded before actual birth time)")
            st.write("• Timezone issues in timestamp recording")
            st.write("• Immediate post-delivery KMC (rare but possible)")

            # Show the specific babies
            fast_df = pd.DataFrame(fast_initiation_babies)
            fast_df['birth_date'] = fast_df['birth_date'].dt.strftime('%Y-%m-%d %H:%M')
            fast_df['first_kmc_date'] = fast_df['first_kmc_date'].dt.strftime('%Y-%m-%d %H:%M')
            fast_df['time_to_initiation_hours'] = fast_df['time_to_initiation_hours'].round(2)

            st.write("**Babies with KMC initiation < 2 hours:**")
            display_cols = ['UID', 'hospital', 'birth_date', 'first_kmc_date',
                          'time_to_initiation_hours', 'delivery_type', 'current_location']
            safe_dataframe_display(fast_df[display_cols], width='stretch')
    
    # KMC initiation chart
    if kmc_initiation['total_babies_with_kmc'] > 0:
        fig = go.Figure(data=[go.Pie(
            labels=['Within 24h', '24-48h', '>48h'],
            values=[
                kmc_initiation['within_24h_count'],
                kmc_initiation['within_48h_count'] - kmc_initiation['within_24h_count'],
                kmc_initiation['total_babies_with_kmc'] - kmc_initiation['within_48h_count']
            ],
            marker_colors=['#10B981', THEME_A_COLORS['secondary'], '#EF4444']
        )])
        fig.update_layout(title="KMC Initiation Timing Distribution")
        st.plotly_chart(fig, width='stretch')

    # Detailed breakdown by Inborn/Outborn
    col1, col2 = st.columns(2)

    # Inborn statistics
    if kmc_initiation.get('inborn_stats'):
        with col1:
            st.subheader("Inborn Babies")
            inborn = kmc_initiation['inborn_stats']
            st.metric("Total Inborn with KMC", f"{inborn['count']:,}")
            inborn_avg = inborn['avg_time_hours']
            st.metric("Avg Time to Initiation", f"{inborn_avg:.1f}h")
            if inborn_avg < 2:
                st.warning("⚠️ Very fast inborn initiation")
            st.metric("Within 24h", f"{inborn['within_24h_percentage']:.1f}%", f"{inborn['within_24h_count']:,} babies")
            st.metric("Within 48h", f"{inborn['within_48h_percentage']:.1f}%", f"{inborn['within_48h_count']:,} babies")

            # Show fast inborn babies if any
            if inborn_avg < 2:
                fast_inborn = [baby for baby in kmc_initiation['initiation_data']
                              if baby['is_inborn'] and baby['time_to_initiation_hours'] < 2]
                if fast_inborn:
                    with st.expander(f"🔍 {len(fast_inborn)} Inborn babies with < 2h initiation"):
                        fast_inborn_df = pd.DataFrame(fast_inborn)
                        fast_inborn_df['time_to_initiation_hours'] = fast_inborn_df['time_to_initiation_hours'].round(2)
                        cols = ['UID', 'hospital', 'time_to_initiation_hours', 'current_location']
                        safe_dataframe_display(fast_inborn_df[cols], width='stretch')

    # Outborn statistics
    if kmc_initiation.get('outborn_stats'):
        with col2:
            st.subheader("Outborn Babies")
            outborn = kmc_initiation['outborn_stats']
            st.metric("Total Outborn with KMC", f"{outborn['count']:,}")
            outborn_avg = outborn['avg_time_hours']
            st.metric("Avg Time to Initiation", f"{outborn_avg:.1f}h")
            if outborn_avg < 2:
                st.warning("⚠️ Very fast outborn initiation")
            st.metric("Within 24h", f"{outborn['within_24h_percentage']:.1f}%", f"{outborn['within_24h_count']:,} babies")
            st.metric("Within 48h", f"{outborn['within_48h_percentage']:.1f}%", f"{outborn['within_48h_count']:,} babies")

            # Show fast outborn babies if any
            if outborn_avg < 2:
                fast_outborn = [baby for baby in kmc_initiation['initiation_data']
                               if not baby['is_inborn'] and baby['time_to_initiation_hours'] < 2]
                if fast_outborn:
                    with st.expander(f"🔍 {len(fast_outborn)} Outborn babies with < 2h initiation"):
                        fast_outborn_df = pd.DataFrame(fast_outborn)
                        fast_outborn_df['time_to_initiation_hours'] = fast_outborn_df['time_to_initiation_hours'].round(2)
                        cols = ['UID', 'hospital', 'time_to_initiation_hours', 'current_location']
                        safe_dataframe_display(fast_outborn_df[cols], width='stretch')

    # Inborn by location breakdown
    if kmc_initiation.get('inborn_location_stats'):
        st.subheader("Inborn Babies by Current Location")

        with st.expander("📊 About Location-Based KMC Analysis", expanded=False):
            st.markdown("""
            **Location-Based KMC Initiation Analysis:**
            - **Current Location**: Where baby is currently located (PNC, SNCU_NICU, etc.)
            - **Avg Time**: Average hours from birth to first KMC session for babies in this location
            - **Within 24h/48h**: Percentage meeting early initiation guidelines
            - **Data Note**: Compares initiation timing by current location to identify patterns

            **Clinical Context:** Different locations may have different KMC protocols and staff training levels.
            """)

        location_data = []
        fast_locations = []

        for location, stats in kmc_initiation['inborn_location_stats'].items():
            avg_time = stats['avg_time_hours']
            location_data.append({
                'Location': location,
                'Count': stats['count'],
                'Avg Time (hours)': f"{avg_time:.1f}",
                'Within 24h': f"{stats['within_24h_percentage']:.1f}% ({stats['within_24h_count']})",
                'Within 48h': f"{stats['within_48h_percentage']:.1f}% ({stats['within_48h_count']})"
            })

            if avg_time < 2:
                fast_locations.append((location, avg_time, stats['count']))

        if location_data:
            location_df = pd.DataFrame(location_data)
            safe_dataframe_display(location_df, width='stretch')

            # Show warnings for fast locations
            if fast_locations:
                st.warning("⚠️ Locations with very fast KMC initiation (< 2 hours):")
                for location, avg_time, count in fast_locations:
                    st.write(f"• **{location}**: {avg_time:.1f}h average ({count} babies)")
                st.info("This may indicate data entry issues or immediate post-delivery KMC practices.")

    # Inborn Babies by Current Location and Hospital
    if kmc_initiation.get('inborn_location_hospital_stats'):
        st.subheader("Inborn Babies by Current Location and Hospital")
        location_hospital_data = []
        for key, stats in kmc_initiation['inborn_location_hospital_stats'].items():
            location_hospital_data.append({
                'Location': stats['location'],
                'Hospital': stats['hospital'],
                'Count': stats['count'],
                'Avg Time to Initiation (hours)': f"{stats['avg_time_hours']:.1f}",
                'Within 24h': f"{stats['within_24h_percentage']:.1f}% ({stats['within_24h_count']})",
                'Within 48h': f"{stats['within_48h_percentage']:.1f}% ({stats['within_48h_count']})"
            })

        if location_hospital_data:
            location_hospital_df = pd.DataFrame(location_hospital_data)
            safe_dataframe_display(location_hospital_df, width='stretch')

    st.markdown("---")

    st.markdown("---")

    # Average KMC Hours by Location
    st.subheader("Average KMC Hours by Location & Hospital")
    avg_kmc_data = calculate_average_kmc_by_location(filtered_data, start_date, end_date)
    
    if avg_kmc_data:
        avg_kmc_df_data = []
        for data in avg_kmc_data:
            avg_kmc_df_data.append({
                'Hospital': data['hospital'],
                'Location': data['location'],
                'Avg Hours/Day': f"{data['avg_hours_per_day']:.1f}h",
                'Avg Hours/Baby': f"{data['avg_hours_per_baby']:.1f}h",
                'Baby Count': data['baby_count'],
                'Observation Days': data['observation_days']
            })
        
        avg_kmc_df = pd.DataFrame(avg_kmc_df_data)
        st.dataframe(avg_kmc_df, width='stretch', hide_index=True)
    else:
        st.info("No KMC data found for the selected time period.")

    st.markdown("---")

    # ============ KMC ADHERENCE (SKIN CONTACT) ============
    st.subheader("KMC Adherence During Follow-ups (Excluding Follow-up 28)")

    # Add description of KMC adherence metrics
    with st.expander("📊 About KMC Adherence During Follow-ups", expanded=False):
        st.markdown("""
        **KMC Adherence Monitoring:**
        - **numberSkinContact**: Measures how many times per day babies receive skin-to-skin contact during follow-up visits
        - **Follow-up Types**: Includes follow-up visits at 2, 7, and 14 days (excludes 28-day follow-up)
        - **Data Source**: followUp array entries with numberSkinContact field in baby/babyBackup collections
        - **Target**: Aim for 6-8+ skin contacts per day during early follow-up periods
        """)

    kmc_adherence = calculate_skin_contact_metrics(filtered_data)
    if kmc_adherence['total_babies_with_data'] > 0:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Babies with Follow-ups", kmc_adherence['total_babies_with_data'])
        with col2:
            st.metric("Avg numberSkinContact", f"{kmc_adherence['average_skin_contact']:.1f}")
        with col3:
            st.metric("Min numberSkinContact", f"{kmc_adherence['min_skin_contact']:.1f}")
        with col4:
            st.metric("Max numberSkinContact", f"{kmc_adherence['max_skin_contact']:.1f}")
    else:
        st.info("No follow-up data with numberSkinContact information found.")

    st.markdown("---")

    # ============ FOLLOW-UP COMPLETION ============
    st.subheader("Follow-up Completion Analysis")
    followup_metrics = calculate_followup_metrics(followup_data, filtered_data)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Eligible", followup_metrics['total_eligible'])
    with col2:
        st.metric("Completed", followup_metrics['total_completed'])
    with col3:
        st.metric("Completion Rate", f"{followup_metrics['overall_completion_rate']:.1f}%")

    # Follow-up requirements info
    st.info("""
    **Follow-up Tracking:** (Excludes dead babies, checks baby and babybackup collections only)
    • Follow up 2: Checks if followUpNumber = 2 exists in followUp array
    • Follow up 7: Checks if followUpNumber = 7 exists in followUp array
    • Follow up 14: Checks if followUpNumber = 14 exists in followUp array
    • Follow up 28: Checks if followUpNumber = 28 exists in followUp array

    **Note:** All babies are considered eligible. Completion is based on presence of followUp entries, not date calculations.
    """)

    # Follow-up details table
    if followup_metrics.get('hospital_summary'):
        followup_df_data = []
        for item in followup_metrics['hospital_summary']:
            followup_df_data.append({
                'Hospital': item['hospital'],
                'Follow-up Type': item['followup_type'],
                'Eligible': item['eligible'],
                'Completed': item['completed'],
                'Completion Rate': f"{item['completion_rate']:.1f}%",
                'Due': item.get('due', 0),
                'Overdue': item.get('overdue', 0)
            })

        followup_df = pd.DataFrame(followup_df_data)
        st.dataframe(followup_df, width='stretch', hide_index=True)
    else:
        st.info("No follow-up data available for the selected criteria.")

    st.markdown("---")

    # ============ DISCHARGE OUTCOMES ============
    st.subheader("Discharge Outcomes Analysis")
    
    # Add description of discharge outcome analysis
    with st.expander("📊 About Discharge Outcomes Analysis", expanded=False):
        st.markdown("""
        **Discharge Categorization:**
        - **Critical & Home**: Babies discharged home despite critical condition (may need close monitoring)
        - **Stable & Home**: Babies discharged home in stable condition according to criteria
        - **Critical & Referred**: Babies referred to higher care facilities due to critical condition
        - **Died**: Babies who died before discharge
        - **Other**: Unclear or mixed discharge status

        **Data Sources** (Hierarchical - No Double Counting):
        - **Step 1**: Discharges collection (dischargeStatus, dischargeType fields) - highest priority
        - **Step 2**: Baby collection (lastDischargeStatus, lastDischargeType fields) - fallback
        - **Step 3**: BabyBackUp collection (dischargeStatusString field) - final fallback

        **Clinical Significance**: Tracks quality of care and appropriateness of discharge decisions. High critical-home rates may indicate need for better stabilization before discharge.
        """)

    st.caption("Based on discharges and babyBackUp collections with updated categorization rules")

    outcomes = calculate_discharge_outcomes(filtered_data, discharge_data)
    
    if outcomes and outcomes.get('total_discharged', 0) > 0:
        col1, col2, col3, col4 = st.columns(4)
        total = outcomes['total_discharged']
        cats = outcomes['categories']
        
        with col1:
            st.metric("Total Discharged", total)
            st.caption(f"({outcomes['unique_babies_processed']} unique babies)")
        with col2:
            pct = (cats['critical_home']['count'] / total * 100) if total > 0 else 0
            st.metric("Critical & Home", f"{pct:.1f}%", f"{cats['critical_home']['count']} babies")
        with col3:
            pct = (cats['stable_home']['count'] / total * 100) if total > 0 else 0
            st.metric("Stable & Home", f"{pct:.1f}%", f"{cats['stable_home']['count']} babies")
        with col4:
            pct = (cats['died']['count'] / total * 100) if total > 0 else 0
            st.metric("Deaths", f"{pct:.1f}%", f"{cats['died']['count']} babies")
        
        # Pie chart
        fig = go.Figure(data=[go.Pie(
            labels=['Critical & Home', 'Stable & Home', 'Critical & Referred', 'Died', 'Other'],
            values=[
                cats['critical_home']['count'],
                cats['stable_home']['count'],
                cats['critical_referred']['count'],
                cats['died']['count'],
                cats['other']['count']
            ],
            marker_colors=[THEME_A_COLORS['secondary'], '#10B981', '#F59E0B', '#EF4444', '#9CA3AF']
        )])
        fig.update_layout(title="Discharge Outcomes Distribution")
        st.plotly_chart(fig, width='stretch')
        
        # Detailed breakdown table
        category_names = {
            'critical_home': 'Critical and sent home',
            'stable_home': 'Stable and sent home',
            'critical_referred': 'Critical and referred',
            'died': 'Died',
            'other': 'Other/Unknown'
        }
        breakdown_data = []
        for category, data in cats.items():
            pct = (data['count'] / total * 100) if total > 0 else 0
            breakdown_data.append({
                'Discharge Category': category_names.get(category, category),
                'Count': data['count'],
                'Percentage': f"{pct:.1f}%"
            })
        st.dataframe(pd.DataFrame(breakdown_data), width='stretch', hide_index=True)
    else:
        st.info("No discharge outcome data available")

    st.markdown("---")

    # ============ CRITICAL REASONS ============
    st.subheader("Critical Reasons Analysis")
    st.caption("Individual critical reasons from discharges collection")
    
    critical_reasons = calculate_individual_critical_reasons(filtered_data, discharge_data)
    
    if critical_reasons['total_babies_with_reasons'] > 0:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Babies with Critical Reasons", critical_reasons['total_babies_with_reasons'])
        with col2:
            st.metric("Unique Critical Reasons", critical_reasons['total_unique_reasons'])
        
        # Bar chart for top 10 reasons
        reasons_list = []
        for reason, data in critical_reasons['individual_reasons'].items():
            reasons_list.append({
                'Reason': reason,
                'Count': data['count'],
                'Percentage': (data['count'] / critical_reasons['total_babies_with_reasons'] * 100)
            })
        reasons_sorted = sorted(reasons_list, key=lambda x: x['Count'], reverse=True)[:10]
        
        if reasons_sorted:
            df_reasons = pd.DataFrame(reasons_sorted)
            fig = px.bar(
                df_reasons,
                y='Reason',
                x='Count',
                orientation='h',
                title="Top 10 Critical Reasons",
                color='Count',
                color_continuous_scale='Blues'
            )
            fig.update_layout(height=400, yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig, width='stretch')
            
            # Full table
            all_reasons = sorted(reasons_list, key=lambda x: x['Count'], reverse=True)
            st.dataframe(pd.DataFrame([{
                'Critical Reason': r['Reason'],
                'Count': r['Count'],
                'Percentage': f"{r['Percentage']:.1f}%"
            } for r in all_reasons]), width='stretch', hide_index=True)
    else:
        st.info("No critical reasons data found in the discharges collection.")

    st.markdown("---")

    # ============ DISCHARGED WITHOUT KMC ============
    st.subheader("🏥 Discharged Babies Without KMC Analysis")
    
    with st.expander("📊 About Discharged Babies Without KMC Analysis", expanded=False):
        st.markdown("""
        **Analysis Purpose:**
        - Identifies babies who were discharged but received no KMC during their hospital stay
        - Tracks hospital-wise performance in KMC implementation
        
        **Target**: Aim for <5% of discharged babies without any KMC exposure.
        """)

    no_kmc = calculate_discharged_babies_without_kmc(filtered_data, discharge_data)
    
    if no_kmc['total_discharged'] > 0:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Discharged Babies", no_kmc['total_discharged'])
        with col2:
            st.metric("Without Any KMC", no_kmc['total_without_kmc'])
        with col3:
            st.metric("Percentage Without KMC", f"{no_kmc['overall_percentage']:.1f}%")
        
        # Hospital breakdown table
        hospital_data = []
        for hospital, data in no_kmc['hospital_data'].items():
            hospital_data.append({
                'Hospital': hospital,
                'Total Discharged': data['total_discharged'],
                'Without KMC': data['without_kmc'],
                'Percentage Without KMC': f"{data['percentage_without_kmc']:.1f}%"
            })
        hospital_data.sort(key=lambda x: float(x['Percentage Without KMC'].rstrip('%')), reverse=True)
        st.dataframe(pd.DataFrame(hospital_data), width='stretch', hide_index=True)
        
        # Show details for hospitals with high percentages
        for hospital, data in no_kmc['hospital_data'].items():
            if data['percentage_without_kmc'] > 10 and data['babies_without_kmc']:
                with st.expander(f"🔍 {hospital} - {len(data['babies_without_kmc'])} babies without KMC"):
                    babies_df = pd.DataFrame(data['babies_without_kmc'])
                    st.dataframe(babies_df, width='stretch', hide_index=True)
    else:
        st.info("No discharged babies found in the selected criteria.")
