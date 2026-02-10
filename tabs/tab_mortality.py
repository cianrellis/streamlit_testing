"""
Mortality Analysis Tab - Visualization of death rates and causes
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime
from utils.dashboard_utils import THEME_A_COLORS, safe_dataframe_display
from utils.dashboard_metrics import (
    calculate_death_rates, 
    calculate_comprehensive_hospital_mortality,
    calculate_detailed_mortality_list
)


def render_mortality_tab(baby_data, filtered_data, discharge_data):
    """Render the Mortality Analysis tab"""
    st.header("📋 Mortality Analysis")
    
    # Calculate main metrics using filtered data
    death_metrics = calculate_death_rates(filtered_data, discharge_data)
    
    # Overview Metrics
    st.subheader("Overview")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Babies", death_metrics['total_babies'])
    with col2:
        st.metric("Total Deaths", death_metrics['dead_babies'])
    with col3:
        st.metric("Mortality Rate", f"{death_metrics['mortality_rate']:.2f}%")
        
    st.markdown("---")
    
    # Hospital-wise Analysis (Chart)
    st.subheader("🏥 Hospital-wise Mortality Analysis")
    
    hospital_data = death_metrics['hospital_data']
    hospital_df = pd.DataFrame({
        'Hospital': hospital_data['hospitals'],
        'Deaths': hospital_data['deaths'],
        'Total': hospital_data['totals'],
        'Rate': hospital_data['rates']
    })
    
    # Sort for better visualization
    hospital_df = hospital_df.sort_values('Rate', ascending=False)
    
    fig_hospital = go.Figure(data=[
        go.Bar(name='Deaths', x=hospital_df['Hospital'], y=hospital_df['Deaths'], 
               marker_color='#EF4444', text=hospital_df['Deaths'], textposition='auto'),
        go.Bar(name='Survivors', x=hospital_df['Hospital'], y=hospital_df['Total'] - hospital_df['Deaths'], 
               marker_color='#10B981')
    ])
    
    fig_hospital.update_layout(
        barmode='stack', 
        title="Mortality Distribution by Hospital",
        xaxis_title="Hospital",
        yaxis_title="Number of Babies"
    )
    st.plotly_chart(fig_hospital, width='stretch')
    
    # Comprehensive Hospital-wise Mortality Table
    st.subheader("Detailed Hospital Risk Profile")
    st.caption("Breakdown of deaths by hospital, including inborn/outborn and KMC stability status")
    
    comp_data = calculate_comprehensive_hospital_mortality(filtered_data, discharge_data)
    
    comp_rows = []
    for hospital, data in comp_data.items():
        total = data['total_babies']
        deaths = data['total_deaths']
        rate = (deaths / total * 100) if total > 0 else 0
        
        # Dead Inborn Rate (of total deaths)
        inborn_death_pct = (data['dead_inborn_babies'] / deaths * 100) if deaths > 0 else 0
        
        # Dead KMC Stable Rate (of total deaths) - Indication of preventable deaths?
        stable_death_pct = (data['dead_kmc_stable'] / deaths * 100) if deaths > 0 else 0
        
        comp_rows.append({
            'Hospital': hospital,
            'Total Babies': total,
            'Total Deaths': deaths,
            'Mortality Rate': f"{rate:.1f}%",
            'Dead Inborn': f"{data['dead_inborn_babies']} ({inborn_death_pct:.0f}%)",
            'Dead Outborn': f"{data['dead_outborn_babies']}",
            'Dead KMC Stable': f"{data['dead_kmc_stable']} ({stable_death_pct:.0f}%)",
            'Dead KMC Unstable': f"{data['dead_kmc_unstable']}"
        })
        
    comp_df = pd.DataFrame(comp_rows)
    safe_dataframe_display(comp_df, width='stretch', hide_index=True)
    
    # Two-column detailed analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Inborn vs Outborn")
        birth_place = death_metrics['birth_place']
        
        if birth_place['inborn']['total'] > 0 or birth_place['outborn']['total'] > 0:
            inborn_rate = (birth_place['inborn']['deaths'] / birth_place['inborn']['total'] * 100) if birth_place['inborn']['total'] > 0 else 0
            outborn_rate = (birth_place['outborn']['deaths'] / birth_place['outborn']['total'] * 100) if birth_place['outborn']['total'] > 0 else 0
            
            fig = go.Figure(data=[
                go.Bar(name='Total', x=['Inborn', 'Outborn'], 
                      y=[birth_place['inborn']['total'], birth_place['outborn']['total']],
                      marker_color=THEME_A_COLORS['light']),
                go.Bar(name='Deaths', x=['Inborn', 'Outborn'], 
                      y=[birth_place['inborn']['deaths'], birth_place['outborn']['deaths']],
                      marker_color='#EF4444')
            ])
            
            fig.update_layout(title="Mortality: Inborn vs Outborn", barmode='group')
            st.plotly_chart(fig, width='stretch')
            
            st.metric("Inborn Mortality Rate", f"{inborn_rate:.2f}%", 
                     f"{birth_place['inborn']['deaths']}/{birth_place['inborn']['total']}")
            st.metric("Outborn Mortality Rate", f"{outborn_rate:.2f}%", 
                     f"{birth_place['outborn']['deaths']}/{birth_place['outborn']['total']}")
        else:
            st.info("No inborn/outborn data available")
            
    with col2:
        st.subheader("Dead Babies by Discharge Status")
        st.caption("Analysis based on discharge outcomes for dead babies")
        
        discharge_outcomes = death_metrics['discharge_outcomes']
        
        if discharge_outcomes['total_discharged'] > 0:
            category_names = {
                'critical_home': 'Critical and sent home',
                'stable_home': 'Stable and sent home', 
                'critical_referred': 'Critical and referred',
                'died': 'Died',
                'other': 'Other/Unknown'
            }
            
            # Pie Chart
            categories_with_deaths = [(cat, data) for cat, data in discharge_outcomes['categories'].items() if data['count'] > 0]
            if categories_with_deaths:
                fig = go.Figure(data=[go.Pie(
                    labels=[category_names.get(cat, cat) for cat, data in categories_with_deaths],
                    values=[data['count'] for cat, data in categories_with_deaths],
                    marker_colors=[THEME_A_COLORS['secondary'], '#10B981', '#F59E0B', '#EF4444', '#9CA3AF']
                )])
                fig.update_layout(title="Dead Babies Distribution by Discharge Status")
                st.plotly_chart(fig, width='stretch')
                
                # Simple list below chart
                for cat, data in categories_with_deaths:
                    st.write(f"**{category_names.get(cat, cat)}**: {data['count']} babies ({data['count']/discharge_outcomes['total_discharged']*100:.1f}%)")
            else:
                st.info("No dead babies found in current dataset.")
        else:
            st.info("No discharge data available for dead babies.")

    # Location Analysis
    st.subheader("📍 Mortality by Current Location")
    with st.expander("📊 About Mortality by Current Location", expanded=False):
        st.markdown("""
        **Purpose**: Analyze where babies were located at the time of death
        **Clinical Insight**: High deaths in specific locations may indicate need for enhanced care protocols.
        """)
        
    location_data = death_metrics['location_analysis']
    if location_data:
        loc_df_data = []
        for location, data in location_data.items():
            rate = (data['deaths'] / data['total'] * 100) if data['total'] > 0 else 0
            loc_df_data.append({
                'Location': location,
                'Total Babies': data['total'],
                'Deaths': data['deaths'],
                'Mortality Rate (%)': f"{rate:.2f}%"
            })
        
        loc_df = pd.DataFrame(loc_df_data)
        st.dataframe(loc_df, width='stretch', hide_index=True)
        
    # KMC Stability Analysis
    st.subheader("🌟 KMC Stability Analysis")
    st.caption("Unstable = 0 KMC hours AND (unstableForKMC=true OR danger sign 'केएमसी के लिए अस्थिर 🦘🚫')")
    
    kmc_data = death_metrics['kmc_stability']
    col1, col2 = st.columns(2)
    
    with col1:
        stable_rate = (kmc_data['stable']['deaths'] / kmc_data['stable']['total'] * 100) if kmc_data['stable']['total'] > 0 else 0
        unstable_rate = (kmc_data['unstable']['deaths'] / kmc_data['unstable']['total'] * 100) if kmc_data['unstable']['total'] > 0 else 0
        
        st.metric("KMC Stable Babies", kmc_data['stable']['total'])
        st.metric("Stable Mortality Rate", f"{stable_rate:.2f}%", f"{kmc_data['stable']['deaths']} deaths")
        st.metric("KMC Unstable Babies", kmc_data['unstable']['total'])
        st.metric("Unstable Mortality Rate", f"{unstable_rate:.2f}%", f"{kmc_data['unstable']['deaths']} deaths")
        
    with col2:
        if kmc_data['stable']['total'] > 0 or kmc_data['unstable']['total'] > 0:
            fig = go.Figure(data=[
                go.Bar(name='Total', x=['KMC Stable', 'KMC Unstable'],
                      y=[kmc_data['stable']['total'], kmc_data['unstable']['total']],
                      marker_color=THEME_A_COLORS['light']),
                go.Bar(name='Deaths', x=['KMC Stable', 'KMC Unstable'],
                      y=[kmc_data['stable']['deaths'], kmc_data['unstable']['deaths']],
                      marker_color='#EF4444')
            ])
            fig.update_layout(title="Mortality by Stability", barmode='group')
            st.plotly_chart(fig, width='stretch')
            
    # Neonatal vs Infant
    st.subheader("👶 Neonatal vs Infant Mortality Analysis")
    neonatal_data = death_metrics['neonatal_vs_infant']
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Babies who died ≤28 days old", neonatal_data['neonatal']['deaths'])
    with col2:
        st.metric("Babies who died >28 days old", neonatal_data['infant']['deaths'])
        
    # Detailed Data Section
    st.subheader("📄 Detailed Mortality Data")
    
    # Filter by discharge status
    discharge_status_options = ['All', 'Died', 'Critical & Home', 'Stable & Home', 'Critical & Referred', 'Other']
    selected_discharge_status = st.selectbox(
        "Filter by Discharge Status:",
        options=discharge_status_options,
        index=0,
        key="mortality_discharge_filter_tab"
    )
    
    # Get detailed list
    detailed_list = calculate_detailed_mortality_list(filtered_data, discharge_data)
    
    # Filter
    if selected_discharge_status != 'All':
        detailed_list = [d for d in detailed_list if d['Discharge Status'] == selected_discharge_status]
        
    if detailed_list:
        st.write(f"**Showing {len(detailed_list)} deceased babies:**")
        detailed_df = pd.DataFrame(detailed_list)
        safe_dataframe_display(detailed_df, width='stretch')
        
        # Enhanced Analysis Charts
        st.subheader("📊 Enhanced Mortality Analysis Charts")
        with st.expander("📊 About Enhanced Charts", expanded=False):
            st.markdown("Visual analysis of mortality patterns and associated factors.")
            
        col1, col2 = st.columns(2)
        with col1:
            # KMC Status Analysis
            st.subheader("KMC Analysis for Deceased Babies")
            if 'KMC Started' in detailed_df.columns:
                kmc_started = detailed_df['KMC Started'].value_counts()
                if not kmc_started.empty:
                    fig_kmc = px.pie(values=kmc_started.values, names=kmc_started.index,
                                   title="KMC Initiation Status", 
                                   color_discrete_map={'Yes': '#10B981', 'No': '#EF4444'})
                    st.plotly_chart(fig_kmc, width='stretch')
                else:
                    st.info("No data for KMC status breakdown.")
        
        # Download
        csv = detailed_df.to_csv(index=False)
        st.download_button(
            label="Download Deceased Babies Data (CSV)",
            data=csv,
            file_name=f"deceased_babies_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No deceased babies found matching the criteria.")
