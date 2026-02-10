"""
Dashboard Tabs Module
Re-exports tab rendering functions from individual tab modules.
This provides backward compatibility for existing imports.
"""

# Re-export all tab rendering functions from individual modules
# Re-export all tab rendering functions from individual modules
from tabs.tab_overview import render_overview_tab
from tabs.tab_clinical_kpis import render_clinical_kpis_tab
from tabs.tab_mortality import render_mortality_tab
from tabs.tab_daily_kmc import render_daily_kmc_tab
from tabs.tab_nurses import render_nurses_tab
from tabs.tab_sandbox import render_sandbox_tab

__all__ = [
    'render_overview_tab',
    'render_clinical_kpis_tab',
    'render_mortality_tab',
    'render_daily_kmc_tab',
    'render_nurses_tab',
    'render_sandbox_tab',
]
