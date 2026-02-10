import streamlit as st
import pandas as pd
from dashboard_metrics import calculate_sandbox_system_metrics, calculate_sandbox_program_metrics

def render_sandbox_tab(baby_data, discharge_data, followup_data, kmc_session_data=None):
    """Render the Sandbox Metrics tab with System and Program sub-tabs."""
    st.header("Sandbox Metrics")
    st.markdown("Metrics based on 'Eligible' babies (Birth Weight < 2500g OR Gestational Age <= 36 weeks).")

    if kmc_session_data is None:
        kmc_session_data = []

    # 2. Tabs
    tab_system, tab_program = st.tabs(["Sandbox System Monitoring", "Sandbox Program Monitoring"])

    # Compute metrics
    # Note: We pass the data we have. If kmc_session_data is empty, the metric functions 
    # should try to extract it from baby_data (if supported) or return partial results.
    metrics_sys = calculate_sandbox_system_metrics(baby_data, discharge_data, followup_data, kmc_session_data)
    
    # --- SYSTEM METRICS ---
    with tab_system:
        st.subheader("Sandbox System Monitoring")

        # 1. Identification & Registration
        st.markdown("#### Identification & Registration")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("1\. Eligible Registered (Inborn)", metrics_sys['m1_registered'], help="Born at hospital & eligible")
        c2.metric("2\. Eligible Admitted", metrics_sys['m2_admitted'], help="All eligible babies in system")
        c3.metric("3\. Total Baby-Days", f"{metrics_sys['m3_baby_days']:,.0f}")
        c4.metric("4\. Identified", metrics_sys['m4_identified'])

        c5, c6 = st.columns(2)
        c5.metric("5\. ID Coverage", f"{metrics_sys.get('m5_coverage_pct', 0):.1f}% ({metrics_sys.get('m5_coverage_num', 0)}/{metrics_sys.get('m5_coverage_denom', 0)})", help="Target: 95%")
        c6.metric("6\. Registration Completeness", f"{metrics_sys.get('m6_completeness_pct', 0):.1f}% ({metrics_sys.get('m6_completeness_num', 0)}/{metrics_sys.get('m6_completeness_denom', 0)})", help="Target: 95%")

        st.markdown("---")

        # 2. Clinical Status
        st.markdown("#### Clinical Status")
        c7, c8 = st.columns(2)
        c7.metric("7\. Early Transfer (<24h)", f"{metrics_sys.get('m7_early_transfer_pct', 0):.1f}% ({metrics_sys.get('m7_early_transfer_num', 0)}/{metrics_sys.get('m7_early_transfer_denom', 0)})")
        c8.metric("8\. Unstable at 24h", f"{metrics_sys.get('m8_unstable_pct', 0):.1f}% ({metrics_sys.get('m8_unstable_num', 0)}/{metrics_sys.get('m8_unstable_denom', 0)})", help="Placeholder")

        st.markdown("---")

        # 3. Follow-up Contactability
        st.markdown("#### Caregiver Contactability")
        c9, c10, c11, c12 = st.columns(4)
        c9.metric("9\. Day 7", f"{metrics_sys.get('m9_d7_pct', 0):.1f}% ({metrics_sys.get('m9_d7_num', 0)}/{metrics_sys.get('m9_d7_denom', 0)})")
        c10.metric("10\. Day 14", f"{metrics_sys.get('m10_d14_pct', 0):.1f}% ({metrics_sys.get('m10_d14_num', 0)}/{metrics_sys.get('m10_d14_denom', 0)})")
        c11.metric("11\. Day 21", f"{metrics_sys.get('m11_d21_pct', 0):.1f}% ({metrics_sys.get('m11_d21_num', 0)}/{metrics_sys.get('m11_d21_denom', 0)})")
        c12.metric("12\. Day 28", f"{metrics_sys.get('m12_d28_pct', 0):.1f}% ({metrics_sys.get('m12_d28_num', 0)}/{metrics_sys.get('m12_d28_denom', 0)})")

        st.markdown("---")

        # 4. KMC Exposure
        st.markdown("#### KMC Exposure Distribution (Inpatient Days)")
        
        m13_dist = metrics_sys.get('m13_distribution', {})
        m13_counts = metrics_sys.get('m13_counts', {})
        
        exposure_data = [
            {"Duration": "0-2 hours", "Percentage": m13_dist.get('0-2h', 0), "Days": m13_counts.get('0-2h', 0)},
            {"Duration": "2-8 hours", "Percentage": m13_dist.get('2-8h', 0), "Days": m13_counts.get('2-8h', 0)},
            {"Duration": "8-12 hours", "Percentage": m13_dist.get('8-12h', 0), "Days": m13_counts.get('8-12h', 0)},
            {"Duration": "12+ hours", "Percentage": m13_dist.get('12h+', 0), "Days": m13_counts.get('12h+', 0)},
        ]
        st.caption(f"Total Baby-Days Analyzed: {metrics_sys.get('m13_total_days', 0)}")
        st.dataframe(pd.DataFrame(exposure_data).style.format({"Percentage": "{:.1f}%"}), hide_index=True, use_container_width=True)

    # --- PROGRAM METRICS ---
    with tab_program:
        st.subheader("Sandbox Program Monitoring")
        metrics_prog = calculate_sandbox_program_metrics(baby_data, discharge_data, followup_data, kmc_session_data) # feedings, observations implied if we had them
        
        # 1. KMC Initiation
        st.markdown("#### KMC Initiation")
        p1, p2 = st.columns(2)
        p1.metric("1\. Any KMC Initiation", f"{metrics_prog.get('m1_any_init_pct', 0):.1f}% ({metrics_prog.get('m1_any_init_num', 0)}/{metrics_prog.get('m1_any_init_den', 0)})", help="Target: 95%")
        p2.metric("2\. KMC Init < 24h", f"{metrics_prog.get('m2_init_24h_pct', 0):.1f}% ({metrics_prog.get('m2_init_24h_num', 0)}/{metrics_prog.get('m2_init_24h_den', 0)})", help="Target: 95%")
        
        st.markdown("---")

        # 2. KMC Dose
        st.markdown("#### KMC Dose (Inpatient)")
        p3, p4 = st.columns(2)
        p3.metric("3\. Mean Daily KMC (Hours)", f"{metrics_prog.get('m3_mean_daily_kmc', 0):.1f}")
        p4.metric("4\. Days with KMC >= 12h", f"{metrics_prog.get('m4_days_12h_pct', 0):.1f}% ({metrics_prog.get('m4_days_12h_num', 0)}/{metrics_prog.get('m4_days_12h_den', 0)})", help="Target: 95%")
        
        st.markdown("---")

        # 3. Clinical Care
        st.markdown("#### Clinical Care")
        p5, p6 = st.columns(2)
        p5.metric("5\. Daily Exclusive Breastfeeding", f"{metrics_prog.get('m5_exclusive_pct', 0):.1f}% ({metrics_prog.get('m5_exclusive_num', 0)}/{metrics_prog.get('m5_exclusive_den', 0)})", help="Target: 95%")
        p6.metric("6\. Hypothermia < 72h", f"{metrics_prog.get('m6_hypo_pct', 0):.1f}% ({metrics_prog.get('m6_hypo_num', 0)}/{metrics_prog.get('m6_hypo_den', 0)})")
        
        st.markdown("---")
        
        # 4. Discharge
        st.markdown("#### Discharge Outcomes")
        p7, p8 = st.columns(2)
        p7.metric("7\. Discharged Critical", f"{metrics_prog.get('m7_critical_pct', 0):.1f}% ({metrics_prog.get('m7_critical_num', 0)}/{metrics_prog.get('m7_critical_den', 0)})")
        p8.metric("8\. Discharge Counselling", f"{metrics_prog.get('m8_counselling_score', 0):.1f}", help="Placeholder Score")
        
        st.markdown("---")
        
        # 5. Follow-up
        st.markdown("#### Post-Discharge Continuity")
        p9, p10, p11, p12 = st.columns(4)
        p9.metric("9\. KMC Cont. Day 7", f"{metrics_prog.get('m9_kmc_cont_d7_pct', 0):.1f}% ({metrics_prog.get('m9_kmc_cont_d7_num', 0)}/{metrics_prog.get('m9_kmc_cont_d7_den', 0)})")
        p10.metric("10\. KMC Cont. Day 28", f"{metrics_prog.get('m10_kmc_cont_d28_pct', 0):.1f}% ({metrics_prog.get('m10_kmc_cont_d28_num', 0)}/{metrics_prog.get('m10_kmc_cont_d28_den', 0)})")
        p11.metric("11\. Care Seeking Day 7", f"{metrics_prog.get('m11_care_d7_pct', 0):.1f}% ({metrics_prog.get('m11_care_d7_num', 0)}/{metrics_prog.get('m11_care_d7_den', 0)})")
        p12.metric("12\. Care Seeking Day 28", f"{metrics_prog.get('m12_care_d28_pct', 0):.1f}% ({metrics_prog.get('m12_care_d28_num', 0)}/{metrics_prog.get('m12_care_d28_den', 0)})")

        st.markdown("---")
        
        # 6. Safety
        st.markdown("#### Safety")
        st.metric("13\. Adverse Events", metrics_prog.get('m13_adverse_events', 0))

    # Detailed Data View (Shared)
    with st.expander("View Eligible Babies Data"):
        if metrics_sys.get('eligible_babies_list'):
            display_data = []
            for baby in metrics_sys['eligible_babies_list']:
                display_data.append({
                    'UID': baby.get('UID'),
                    'Hospital': baby.get('hospitalName'),
                    'Birth Weight': baby.get('birthWeight'),
                    'GA': baby.get('gestationalAge'),
                    'In Program': baby.get('babyInProgram'),
                })
            st.dataframe(pd.DataFrame(display_data), hide_index=True)
        else:
            st.info("No eligible babies found.")
