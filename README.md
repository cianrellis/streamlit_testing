# KMC Dashboard

A Streamlit-based monitoring and evaluation dashboard for Kangaroo Mother Care (KMC) programs in healthcare facilities.

## Overview

The KMC Dashboard is a data visualization and analytics tool designed to track and monitor key performance indicators for KMC programs. It connects to Google Cloud Firestore to retrieve patient data, clinical events, and program metrics, presenting them through an interactive web interface.

The dashboard provides three main views:
- **Overview**: High-level statistics on babies per hospital, discharge status, and user information
- **M&E Dashboard**: Comprehensive monitoring and evaluation metrics including program snapshots, KMC initiation timing, adherence metrics, and mortality analysis
- **Standard Metrics (Weekly)**: Weekly performance metrics aligned with program standards, including coverage, timing, dose, feeding, temperature, continuity, and safety indicators

## Features

- Real-time data visualization from Google Cloud Firestore
- Hospital-level breakdowns of all metrics
- Weekly standard metrics calculation
- Support for local synthetic data for testing and development
- Comprehensive M&E analytics including:
  - Program snapshot and summary metrics
  - Inborn/outborn registration timing
  - KMC initiation and adherence tracking
  - Discharge outcomes and critical reasons analysis
  - Mortality analysis by hospital, location, and birth type
  - Daily and weekly KMC hour tracking

## Installation

### Prerequisites

- Python 3.8 or higher
- Google Cloud Platform account with Firestore access (for production use)
- Streamlit

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd kmc-dashboard
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure credentials (see Configuration section below)

4. Run the application:
   ```bash
   streamlit run kmc_dashboard.py
   ```

## Configuration

### Production Mode (Firestore)

To connect to Google Cloud Firestore, you need to provide service account credentials via Streamlit Secrets.

Create a `.streamlit/secrets.toml` file:

```toml
[firestore]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

### Development Mode (Synthetic Data)

For local development and testing without Firestore access, you can use synthetic data:

**Option 1: Command-line flag**
```bash
streamlit run kmc_dashboard.py -- --fake-data
```

**Option 2: Environment variable**
```bash
export USE_FAKE_DATA=1
streamlit run kmc_dashboard.py
```

## Project Structure

```
kmc-dashboard/
├── kmc_dashboard.py          # Main application entry point
├── config.py                 # Configuration constants and flags
├── dashboard_firebase.py     # Firestore connection and data fetching
├── dashboard_utils.py        # Utility functions for data transformation
├── dashboard_metrics.py      # Metric computation functions
├── dashboard_tabs.py         # UI rendering functions
└── requirements.txt          # Python dependencies
```

## License

See LICENSE file for details.
