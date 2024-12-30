import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import xlsxwriter

# Set page config
st.set_page_config(
    page_title="Retail Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main {
        padding: 0rem 1rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    h1, h2, h3 {
        color: #1f77b4;
    }
    .insight-box {
        background-color: #e1f5fe;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .recommendation-box {
        background-color: #e8f5e9;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    /* Make tables use full width */
    .stDataFrame {
        width: 100% !important;
    }
    .dataframe {
        width: 100% !important;
    }
    /* Improve table header styling */
    .dataframe th {
        background-color: #1f77b4;
        color: white;
        padding: 10px !important;
    }
    /* Improve table cell styling */
    .dataframe td {
        padding: 8px !important;
    }
</style>
""", unsafe_allow_html=True)

def clean_data(df, additional_excluded_clients=None):
    """Clean and prepare the data for analysis."""
    # List of staff members to exclude
    staff_members = [
        'Steve Scarver',
        'Rayvin Womack',
        'Breonna Holmes',
        'Angela King',
        'Nadia Jackson',
        'Rosalind Swain',
        'Alaina Sledge',
        'Brigitte Moore',
        'Jenaya Brooks',
        'Mercede Brooks'
    ]
    
    # Combine staff members with additional excluded clients
    excluded_clients = staff_members + (additional_excluded_clients or [])
    
    # Convert date to datetime
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Clean amount column
    df['Total'] = df['Total'].str.replace('$', '').str.replace(',', '').astype(float)
    
    # Filter for completed transactions only
    df = df[df['Completed'] == 'Yes']
    
    # Filter for loyalty customers (non-empty Customer field) and exclude staff members
    df = df[
        df['Customer'].notna() & 
        (df['Customer'] != '') & 
        ~df['Customer'].str.upper().isin([name.upper() for name in excluded_clients])
    ]
    
    # Remove negative values
    df = df[df['Total'] >= 0]
    
    return df

def calculate_repurchase_rate(df, window_days):
    """Calculate repurchase rate for a given time window."""
    # First, get first and last purchase dates for each customer
    customer_purchases = df.groupby('Customer').agg({
        'Date': ['min', 'max', 'count'],
        'Total': ['sum', 'mean']
    })
    
    # Reset index and rename columns properly
    customer_purchases.reset_index(inplace=True)
    customer_purchases.columns = ['Customer', 'first_purchase', 'last_purchase', 'visit_count', 'total_spend', 'avg_spend']
    
    # Separate one-time customers
    one_time_customers = customer_purchases[customer_purchases['visit_count'] == 1]
    returning_customers = customer_purchases[customer_purchases['visit_count'] > 1]
    
    # For returning customers, calculate time between visits
    if not returning_customers.empty:
        returning_customers['days_between'] = (returning_customers['last_purchase'] - returning_customers['first_purchase']).dt.days
        returning_customers['avg_days_between_visits'] = returning_customers['days_between'] / (returning_customers['visit_count'] - 1)  # Subtract 1 from visit count for intervals
    
    # Count customers who returned within window
    returned = returning_customers[returning_customers['days_between'] >= window_days]['Customer'].count() if not returning_customers.empty else 0
    total_customers = len(customer_purchases)
    
    # Calculate average spend for retained vs non-retained customers
    retained_customers = returning_customers[returning_customers['days_between'] >= window_days] if not returning_customers.empty else pd.DataFrame()
    non_retained_customers = pd.concat([
        one_time_customers,
        returning_customers[returning_customers['days_between'] < window_days] if not returning_customers.empty else pd.DataFrame()
    ])
    
    retention_stats = {
        'rate': (returned / total_customers * 100) if total_customers > 0 else 0,
        'retained_avg_spend': retained_customers['avg_spend'].mean() if not retained_customers.empty else 0,
        'non_retained_avg_spend': non_retained_customers['avg_spend'].mean() if not non_retained_customers.empty else 0,
        'retained_visit_freq': retained_customers['avg_days_between_visits'].mean() if not retained_customers.empty else 0,
        'non_retained_visit_freq': returning_customers[returning_customers['days_between'] < window_days]['avg_days_between_visits'].mean() if not returning_customers.empty else 0,
        'retained_total_revenue': retained_customers['total_spend'].sum() if not retained_customers.empty else 0,
        'non_retained_total_revenue': non_retained_customers['total_spend'].sum() if not non_retained_customers.empty else 0,
        'one_time_customers': len(one_time_customers),
        'one_time_revenue': one_time_customers['total_spend'].sum() if not one_time_customers.empty else 0,
        'returning_customers': len(returning_customers),
        'avg_visits_returning': returning_customers['visit_count'].mean() if not returning_customers.empty else 0
    }
    
    return retention_stats

def calculate_revenue_retention(df):
    """Calculate revenue retention rate by month with improved handling."""
    # Group by month and calculate total revenue
    monthly_revenue = df.groupby(pd.Grouper(key='Date', freq='M'))['Total'].sum().reset_index()
    monthly_revenue = monthly_revenue[monthly_revenue['Total'] > 0]  # Remove months with zero revenue
    
    if len(monthly_revenue) < 2:
        return pd.DataFrame()  # Return empty DataFrame if not enough data
    
    retention_rates = []
    for i in range(1, len(monthly_revenue)):
        prev_month = monthly_revenue.iloc[i-1]
        curr_month = monthly_revenue.iloc[i]
        
        # Calculate retention rate with a cap at 100%
        retention_rate = min((curr_month['Total'] / prev_month['Total'] * 100), 100) if prev_month['Total'] > 0 else 0
        
        retention_rates.append({
            'Month': curr_month['Date'],
            'Revenue': curr_month['Total'],
            'Previous Revenue': prev_month['Total'],
            'Retention Rate': retention_rate,
            'Change': 'Increase' if retention_rate > 100 else 'Decrease'
        })
    
    return pd.DataFrame(retention_rates)

def segment_customers(df):
    """Enhanced customer segmentation with more detailed metrics."""
    customer_metrics = df.groupby('Customer').agg({
        'Total': ['count', 'mean', 'sum'],
        'Date': ['min', 'max']
    })
    
    customer_metrics.reset_index(inplace=True)
    customer_metrics.columns = ['Customer', 'visit_count', 'avg_spend', 'total_spend', 'first_visit', 'last_visit']
    
    # Calculate additional metrics
    now = df['Date'].max()
    customer_metrics['recency'] = (now - customer_metrics['last_visit']).dt.days
    customer_metrics['frequency'] = customer_metrics['visit_count']
    customer_metrics['monetary'] = customer_metrics['total_spend']
    customer_metrics['customer_lifetime_days'] = (customer_metrics['last_visit'] - customer_metrics['first_visit']).dt.days
    
    # Handle one-time customers separately for avg_days_between_visits
    returning_customers = customer_metrics[customer_metrics['visit_count'] > 1].copy()
    one_time_customers = customer_metrics[customer_metrics['visit_count'] == 1].copy()
    
    # Calculate avg_days_between_visits only for returning customers
    if not returning_customers.empty:
        returning_customers['avg_days_between_visits'] = returning_customers['customer_lifetime_days'] / (returning_customers['visit_count'] - 1)
        # Ensure no zero values in avg_days_between_visits
        returning_customers.loc[returning_customers['avg_days_between_visits'] == 0, 'avg_days_between_visits'] = 1
    
    # For one-time customers, set avg_days_between_visits to None
    one_time_customers['avg_days_between_visits'] = None
    
    # Combine the dataframes back
    customer_metrics = pd.concat([returning_customers, one_time_customers])
    
    customer_metrics['days_since_last_visit'] = (now - customer_metrics['last_visit']).dt.days
    
    # Calculate quantiles excluding one-time customers for more accurate segmentation
    spend_75th = returning_customers['total_spend'].quantile(0.75) if not returning_customers.empty else customer_metrics['total_spend'].quantile(0.75)
    freq_75th = returning_customers['frequency'].quantile(0.75) if not returning_customers.empty else customer_metrics['frequency'].quantile(0.75)
    avg_days_median = returning_customers['avg_days_between_visits'].quantile(0.5) if not returning_customers.empty else float('inf')
    
    # Enhanced segmentation logic
    def assign_segment(row):
        if row['visit_count'] == 1:
            return 'One-Time Customer'
            
        if row['days_since_last_visit'] > 90:
            if row['total_spend'] > spend_75th:
                return 'Lost High-Value'
            return 'Lost Customer'
        
        if row['total_spend'] > spend_75th:
            if row['frequency'] > freq_75th:
                return 'Champions'
            return 'High Spender'
        
        if row['frequency'] > freq_75th:
            return 'Frequent Buyer'
        
        if row['days_since_last_visit'] <= 30:
            return 'Recent Customer'
        
        if pd.notna(row['avg_days_between_visits']) and row['avg_days_between_visits'] < avg_days_median:
            return 'Regular Customer'
        
        return 'Occasional Customer'
    
    customer_metrics['segment'] = customer_metrics.apply(assign_segment, axis=1)
    
    return customer_metrics

def analyze_clients(df_clean, customer_metrics):
    """Enhanced client analysis with detailed metrics."""
    now = df_clean['Date'].max()
    
    # Top clients by total spend
    top_spenders = customer_metrics.nlargest(10, 'total_spend')[
        ['Customer', 'total_spend', 'visit_count', 'avg_spend', 'days_since_last_visit', 'first_visit']
    ].copy()
    top_spenders['loyalty_days'] = (now - top_spenders['first_visit']).dt.days
    top_spenders['spend_per_day'] = top_spenders['total_spend'] / top_spenders['loyalty_days']
    
    # Most frequent customers
    most_frequent = customer_metrics.nlargest(10, 'visit_count')[
        ['Customer', 'visit_count', 'total_spend', 'avg_spend', 'days_since_last_visit', 'first_visit']
    ].copy()
    most_frequent['visits_per_month'] = most_frequent['visit_count'] / ((now - most_frequent['first_visit']).dt.days) * 30
    
    # Lost valuable customers
    lost_valuable = customer_metrics[
        (customer_metrics['days_since_last_visit'] > 90) &
        (customer_metrics['total_spend'] > customer_metrics['total_spend'].quantile(0.75))
    ].sort_values('total_spend', ascending=False)[
        ['Customer', 'total_spend', 'visit_count', 'days_since_last_visit', 'last_visit', 'avg_spend']
    ].copy()
    lost_valuable['potential_monthly_revenue_loss'] = lost_valuable['avg_spend'] * (lost_valuable['visit_count'] / ((lost_valuable['last_visit'] - customer_metrics['first_visit']).dt.days) * 30)
    
    # Recent new customers
    recent_new = customer_metrics[
        (now - customer_metrics['first_visit']).dt.days <= 30
    ].sort_values('total_spend', ascending=False)[
        ['Customer', 'first_visit', 'total_spend', 'visit_count', 'avg_spend']
    ].copy()
    recent_new['visits_per_week'] = recent_new['visit_count'] / ((now - recent_new['first_visit']).dt.days) * 7
    
    # At-risk customers (declining frequency)
    at_risk = customer_metrics[
        (customer_metrics['days_since_last_visit'].between(30, 60)) &
        (customer_metrics['total_spend'] > customer_metrics['total_spend'].quantile(0.5))
    ].sort_values('total_spend', ascending=False)[
        ['Customer', 'total_spend', 'visit_count', 'days_since_last_visit', 'avg_spend']
    ]
    
    # Best improvers (customers with increasing average spend)
    recent_transactions = df_clean.sort_values('Date').groupby('Customer').tail(3).groupby('Customer')['Total'].mean()
    overall_avg = df_clean.groupby('Customer')['Total'].mean()
    improving_customers = (recent_transactions - overall_avg).sort_values(ascending=False).head(10)
    best_improvers = customer_metrics[customer_metrics['Customer'].isin(improving_customers.index)][
        ['Customer', 'total_spend', 'visit_count', 'avg_spend', 'days_since_last_visit']
    ].copy()
    
    # Calculate improvement percentage for each improver
    best_improvers['improvement_percent'] = best_improvers['Customer'].map(
        lambda x: ((recent_transactions[x] / overall_avg[x] - 1) * 100)
    )
    
    return {
        'top_spenders': top_spenders.reset_index(drop=True),
        'most_frequent': most_frequent.reset_index(drop=True),
        'lost_valuable': lost_valuable.reset_index(drop=True),
        'recent_new': recent_new.reset_index(drop=True),
        'at_risk': at_risk.reset_index(drop=True),
        'best_improvers': best_improvers.reset_index(drop=True),
        'improvement_stats': {
            'avg_improvement': best_improvers['improvement_percent'].mean(),
            'total_revenue': best_improvers['total_spend'].sum(),
            'avg_visits': best_improvers['visit_count'].mean(),
            'active_last_30': len(best_improvers[best_improvers['days_since_last_visit'] <= 30])
        }
    }

def analyze_revenue(df):
    """Analyze revenue patterns and trends."""
    # Monthly revenue trends
    monthly_revenue = df.groupby(pd.Grouper(key='Date', freq='M')).agg({
        'Total': 'sum',
        'Customer': 'nunique',
        'ID': 'count'
    }).reset_index()
    
    monthly_revenue.columns = ['Month', 'Revenue', 'Unique_Customers', 'Transactions']
    monthly_revenue['Avg_Transaction_Value'] = monthly_revenue['Revenue'] / monthly_revenue['Transactions']
    monthly_revenue['Revenue_per_Customer'] = monthly_revenue['Revenue'] / monthly_revenue['Unique_Customers']
    
    # Daily revenue patterns
    daily_revenue = df.groupby(df['Date'].dt.day_name()).agg({
        'Total': ['sum', 'mean', 'count']
    }).reset_index()
    daily_revenue.columns = ['Day', 'Total_Revenue', 'Avg_Daily_Revenue', 'Transaction_Count']
    
    # Order the days correctly
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    daily_revenue['Day'] = pd.Categorical(daily_revenue['Day'], categories=day_order, ordered=True)
    daily_revenue = daily_revenue.sort_values('Day')
    
    return monthly_revenue, daily_revenue

def create_distribution_plots(df_clean, customer_metrics):
    """Create distribution plots with proper handling of edge cases."""
    # Get returning customers for better distribution analysis
    returning_customers = customer_metrics[
        (customer_metrics['visit_count'] > 1) & 
        (customer_metrics['avg_days_between_visits'].notna()) & 
        (customer_metrics['avg_days_between_visits'] > 0)
    ]
    
    # Transaction Value Distribution (excluding zero values)
    transaction_fig = px.histogram(
        df_clean[df_clean['Total'] > 0],
        x='Total',
        nbins=50,
        title='Distribution of Transaction Values (Excluding Zero Values)',
        labels={'Total': 'Transaction Amount ($)'}
    )
    transaction_fig.update_layout(
        height=400,
        showlegend=False,
        xaxis_title="Transaction Amount ($)",
        yaxis_title="Count"
    )
    
    # Visit Frequency Distribution (only for returning customers)
    if not returning_customers.empty:
        visit_freq_fig = px.histogram(
            returning_customers,
            x='avg_days_between_visits',
            nbins=30,
            title='Distribution of Visit Frequency (Returning Customers Only)',
            labels={'avg_days_between_visits': 'Average Days Between Visits'}
        )
        visit_freq_fig.update_layout(
            height=400,
            showlegend=False,
            xaxis_title="Days Between Visits",
            yaxis_title="Count",
            # Set x-axis minimum to slightly above 0 to exclude any remaining zero values
            xaxis=dict(range=[0.1, returning_customers['avg_days_between_visits'].quantile(0.95)])
        )
    else:
        visit_freq_fig = None
    
    return transaction_fig, visit_freq_fig

def create_excel_report(df_clean, customer_segments, segment_metrics, repurchase_data, retention_data, client_analysis):
    """Enhanced Excel report with client analysis."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Format definitions
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#1f77b4',
            'font_color': 'white',
            'border': 1
        })
        
        # Executive Summary Sheet
        summary_df = pd.DataFrame({
            'Metric': [
                'Total Customers',
                'Total Revenue',
                'Average Transaction Value',
                'Total Transactions',
                '30-Day Retention Rate',
                '90-Day Retention Rate'
            ],
            'Value': [
                f"{df_clean['Customer'].nunique():,}",
                f"${df_clean['Total'].sum():,.2f}",
                f"${df_clean['Total'].mean():.2f}",
                f"{len(df_clean):,}",
                f"{repurchase_data['rate']:.1f}%",
                f"{repurchase_data['rate']:.1f}%"
            ]
        })
        summary_df.to_excel(writer, sheet_name='Executive Summary', index=False)
        
        # Format Executive Summary sheet
        worksheet = writer.sheets['Executive Summary']
        for col_num, value in enumerate(summary_df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 25)
        
        # Customer Segments Sheet
        customer_segments.to_excel(writer, sheet_name='Customer Segments', index=False)
        worksheet = writer.sheets['Customer Segments']
        for col_num, value in enumerate(customer_segments.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 15)
        
        # Segment Performance Sheet
        segment_metrics.to_excel(writer, sheet_name='Segment Performance', index=False)
        worksheet = writer.sheets['Segment Performance']
        for col_num, value in enumerate(segment_metrics.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 15)
        
        # Client Analysis Sheets
        client_sheets = {
            'Top Spenders': client_analysis['top_spenders'],
            'Most Frequent': client_analysis['most_frequent'],
            'Lost Valuable': client_analysis['lost_valuable'],
            'Recent New': client_analysis['recent_new'],
            'At Risk': client_analysis['at_risk'],
            'Best Improvers': client_analysis['best_improvers']
        }
        
        for sheet_title, df in client_sheets.items():
            df.to_excel(writer, sheet_name=sheet_title, index=False)
            worksheet = writer.sheets[sheet_title]
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)
        
        # Save and return
        writer.close()
        output.seek(0)
        return output

def calculate_ltv(df):
    """Calculate customer lifetime value metrics."""
    # Calculate basic customer metrics
    customer_metrics = df.groupby('Customer').agg({
        'Total': ['count', 'mean', 'sum'],
        'Date': ['min', 'max']
    }).reset_index()
    
    customer_metrics.columns = ['Customer', 'visit_count', 'avg_transaction', 'total_spend', 'first_visit', 'last_visit']
    
    # Calculate time-based metrics
    customer_metrics['customer_lifetime_days'] = (customer_metrics['last_visit'] - customer_metrics['first_visit']).dt.days
    customer_metrics['days_since_first'] = (df['Date'].max() - customer_metrics['first_visit']).dt.days
    
    # Ensure we don't divide by zero by setting minimum days to 1
    customer_metrics.loc[customer_metrics['days_since_first'] == 0, 'days_since_first'] = 1
    customer_metrics.loc[customer_metrics['customer_lifetime_days'] == 0, 'customer_lifetime_days'] = 1
    
    # Handle one-time customers vs returning customers
    returning_customers = customer_metrics[customer_metrics['visit_count'] > 1].copy()
    one_time_customers = customer_metrics[customer_metrics['visit_count'] == 1].copy()
    
    # Calculate metrics for returning customers
    if not returning_customers.empty:
        # Average time between visits (excluding first visit)
        returning_customers['avg_days_between_visits'] = returning_customers['customer_lifetime_days'] / (returning_customers['visit_count'] - 1)
        # Ensure no zero values in avg_days_between_visits
        returning_customers.loc[returning_customers['avg_days_between_visits'] == 0, 'avg_days_between_visits'] = 1
        
        # Calculate annual values only for customers with sufficient history (>= 30 days)
        long_term_customers = returning_customers[returning_customers['days_since_first'] >= 30].copy()
        if not long_term_customers.empty:
            # Monthly visit frequency based on actual history
            long_term_customers['monthly_visit_frequency'] = (long_term_customers['visit_count'] / long_term_customers['days_since_first']) * 30
            # Monthly revenue based on actual history
            long_term_customers['monthly_revenue'] = (long_term_customers['total_spend'] / long_term_customers['days_since_first']) * 30
            # Projected annual value
            long_term_customers['projected_annual_value'] = long_term_customers['monthly_revenue'] * 12
            # Historical annual value
            long_term_customers['historical_annual_value'] = (long_term_customers['total_spend'] / long_term_customers['days_since_first']) * 365
            
            # Cap extremely high values at 3x the average total spend
            max_reasonable_value = returning_customers['total_spend'].mean() * 3
            long_term_customers.loc[long_term_customers['projected_annual_value'] > max_reasonable_value, 'projected_annual_value'] = max_reasonable_value
            long_term_customers.loc[long_term_customers['historical_annual_value'] > max_reasonable_value, 'historical_annual_value'] = max_reasonable_value
        else:
            long_term_customers = pd.DataFrame()
    else:
        long_term_customers = pd.DataFrame()
    
    # For one-time customers and short-term customers, set annual values to their total spend
    other_customers = pd.concat([
        one_time_customers,
        returning_customers[~returning_customers.index.isin(long_term_customers.index)] if not returning_customers.empty else pd.DataFrame()
    ])
    
    if not other_customers.empty:
        other_customers['monthly_visit_frequency'] = 0
        other_customers['monthly_revenue'] = 0
        other_customers['projected_annual_value'] = other_customers['total_spend']
        other_customers['historical_annual_value'] = other_customers['total_spend']
    
    # Combine all customer segments
    customer_metrics = pd.concat([long_term_customers, other_customers])
    
    # Calculate overall LTV metrics
    ltv_summary = {
        'avg_customer_lifetime_days': customer_metrics['customer_lifetime_days'].mean(),
        'avg_lifetime_visits': customer_metrics['visit_count'].mean(),
        'avg_lifetime_value': customer_metrics['total_spend'].mean(),
        'median_lifetime_value': customer_metrics['total_spend'].median(),
        'avg_transaction_value': customer_metrics['avg_transaction'].mean(),
        'total_customer_value': customer_metrics['total_spend'].sum(),
        'avg_annual_value': customer_metrics['historical_annual_value'].mean(),
        'projected_annual_value': long_term_customers['projected_annual_value'].mean() if not long_term_customers.empty else customer_metrics['total_spend'].mean(),
        'one_time_customer_ratio': len(one_time_customers) / len(customer_metrics) * 100,
        'returning_customer_ratio': len(returning_customers) / len(customer_metrics) * 100 if not returning_customers.empty else 0,
        'top_10_percent_value': customer_metrics.nlargest(int(len(customer_metrics) * 0.1), 'total_spend')['total_spend'].mean(),
        'bottom_10_percent_value': customer_metrics.nsmallest(int(len(customer_metrics) * 0.1), 'total_spend')['total_spend'].mean()
    }
    
    return customer_metrics, ltv_summary

def main():
    st.title("📊 Retail Analytics Dashboard")
    st.write("Upload your transaction data to analyze customer retention and revenue patterns.")
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        # Load data
        df = pd.read_csv(uploaded_file)
        
        # Add date range selector
        st.sidebar.header("📅 Time Range Selection")
        min_date = pd.to_datetime(df['Date']).min()
        max_date = pd.to_datetime(df['Date']).max()
        
        start_date = st.sidebar.date_input(
            "Start Date",
            min_date,
            min_value=min_date,
            max_value=max_date
        )
        
        end_date = st.sidebar.date_input(
            "End Date",
            max_date,
            min_value=min_date,
            max_value=max_date
        )
        
        # Add client filter section
        st.sidebar.header("👥 Client Filter")
        
        # Get all unique customers
        all_customers = sorted(df[df['Customer'].notna()]['Customer'].unique())
        
        # Staff members that should be excluded
        staff_members = [
            'Steve Scarver',
            'Rayvin Womack',
            'Breonna Holmes',
            'Angela King',
            'Nadia Jackson',
            'Rosalind Swain',
            'Alaina Sledge',
            'Brigitte Moore',
            'Jenaya Brooks',
            'Mercede Brooks'
        ]
        
        # Find which staff members exist in the data (case-insensitive)
        all_customers_upper = [c.upper() for c in all_customers]
        existing_staff = [
            customer for customer in all_customers
            if any(staff.upper() == customer.upper() for staff in staff_members)
        ]
        
        # Create a search box for clients
        client_search = st.sidebar.text_input(
            "Search Clients",
            help="Type to search for specific clients"
        ).upper()
        
        # Filter the customer list based on search
        filtered_customers = [
            customer for customer in all_customers
            if client_search in str(customer).upper()
        ] if client_search else all_customers
        
        # Multi-select for clients to exclude
        excluded_clients = st.sidebar.multiselect(
            "Select Clients to Exclude",
            options=filtered_customers,
            default=existing_staff,
            help="These clients will be excluded from the analysis"
        )
        
        # Clean data and filter by date range and excluded clients
        df_clean = clean_data(df, excluded_clients)
        df_clean = df_clean[
            (df_clean['Date'].dt.date >= start_date) &
            (df_clean['Date'].dt.date <= end_date)
        ]
        
        if len(df_clean) == 0:
            st.warning("No loyalty customer data available for the selected date range.")
            return
        
        # Calculate key metrics
        total_customers = df_clean['Customer'].nunique()
        total_revenue = df_clean['Total'].sum()
        avg_transaction = df_clean['Total'].mean()
        transactions_count = len(df_clean)
        
        # Calculate retention rates
        retention_30 = calculate_repurchase_rate(df_clean, 30)
        retention_60 = calculate_repurchase_rate(df_clean, 60)
        retention_90 = calculate_repurchase_rate(df_clean, 90)
        
        # Create repurchase data DataFrame
        repurchase_data = pd.DataFrame([
            {'Window': '30 Days', 'Rate': retention_30['rate']},
            {'Window': '60 Days', 'Rate': retention_60['rate']},
            {'Window': '90 Days', 'Rate': retention_90['rate']}
        ])
        
        # Calculate customer segments
        customer_segments = segment_customers(df_clean)
        
        # Calculate segment metrics
        segment_metrics = customer_segments.groupby('segment').agg({
            'total_spend': ['mean', 'sum'],
            'visit_count': 'mean',
            'avg_spend': 'mean'
        })
        
        # Reset index and flatten column names
        segment_metrics.reset_index(inplace=True)
        segment_metrics.columns = ['Segment', 'Avg Total Spend', 'Total Revenue', 'Avg Visits', 'Avg Transaction']
        
        # Calculate revenue retention
        retention_data = calculate_revenue_retention(df_clean)
        
        # Create tabs for different analyses
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📈 Overview",
            "🔄 Customer Retention",
            "👥 Customer Segments",
            "💰 Revenue Analysis",
            "👤 Client Analysis",
            "💎 Lifetime Value",
            "📊 Summary & Export"
        ])
        
        with tab1:
            st.header("Overview")
            st.markdown("""
            This dashboard provides insights into your customer behavior and business performance.
            Below are the key metrics from your data:
            """)
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Customers", f"{total_customers:,}")
            with col2:
                st.metric("Total Revenue", f"${total_revenue:,.2f}")
            with col3:
                st.metric("Avg Transaction", f"${avg_transaction:.2f}")
            with col4:
                st.metric("Total Transactions", f"{transactions_count:,}")
            
            st.markdown(f"""
            <div class='insight-box'>
                <h4>📌 Key Insights</h4>
                <ul>
                    <li>Your business has served {total_customers:,} unique customers</li>
                    <li>Average spending per transaction is ${avg_transaction:.2f}</li>
                    <li>Total revenue generated is ${total_revenue:,.2f}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        
        with tab2:
            st.header("Customer Retention Analysis")
            st.markdown("""
            This section provides a detailed analysis of customer retention patterns and their impact on revenue.
            Understanding these metrics helps identify opportunities to improve customer loyalty and revenue stability.
            
            > 💡 **Key Terms:**
            > - **Retention Rate**: Percentage of customers who return within a specific time window
            > - **Retained Revenue**: Revenue generated by returning customers
            > - **Visit Frequency**: How often retained customers make purchases
            """)
            
            # Calculate retention metrics for different time windows
            retention_30 = calculate_repurchase_rate(df_clean, 30)
            retention_60 = calculate_repurchase_rate(df_clean, 60)
            retention_90 = calculate_repurchase_rate(df_clean, 90)
            
            # Display retention rates with explanations
            st.subheader("🔄 Retention Rates")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "30-Day Retention",
                    f"{retention_30['rate']:.1f}%",
                    f"${retention_30['retained_avg_spend']:.2f} avg spend"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> {:.1f}% of customers return within a month, spending ${:.2f} on average. 
                    This is your short-term retention success rate.</p>
                </div>
                """.format(
                    retention_30['rate'],
                    retention_30['retained_avg_spend']
                ), unsafe_allow_html=True)
            
            with col2:
                st.metric(
                    "60-Day Retention",
                    f"{retention_60['rate']:.1f}%",
                    f"${retention_60['retained_avg_spend']:.2f} avg spend"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> {:.1f}% of customers return within two months, spending ${:.2f} on average. 
                    This shows medium-term customer loyalty.</p>
                </div>
                """.format(
                    retention_60['rate'],
                    retention_60['retained_avg_spend']
                ), unsafe_allow_html=True)
            
            with col3:
                st.metric(
                    "90-Day Retention",
                    f"{retention_90['rate']:.1f}%",
                    f"${retention_90['retained_avg_spend']:.2f} avg spend"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> {:.1f}% of customers return within three months, spending ${:.2f} on average. 
                    This indicates long-term customer relationships.</p>
                </div>
                """.format(
                    retention_90['rate'],
                    retention_90['retained_avg_spend']
                ), unsafe_allow_html=True)
            
            # Customer Composition Analysis
            st.subheader("👥 Customer Composition")
            
            # Create pie chart for customer types
            customer_types = pd.DataFrame([
                {'Type': 'One-Time Customers', 'Count': retention_30['one_time_customers']},
                {'Type': 'Returning Customers', 'Count': retention_30['returning_customers']}
            ])
            
            fig = px.pie(
                customer_types,
                values='Count',
                names='Type',
                title='Customer Base Composition',
                color_discrete_sequence=['#ff7f0e', '#1f77b4']
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            
            col1, col2 = st.columns([2, 1])
            with col1:
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("""
                <div class='insight-box'>
                    <h4>📊 Composition Insights</h4>
                    <ul>
                        <li><strong>One-Time Customers:</strong>
                            <ul>
                                <li>Count: {:,}</li>
                                <li>Revenue: ${:,.2f}</li>
                                <li>Avg Spend: ${:.2f}</li>
                            </ul>
                        </li>
                        <li><strong>Returning Customers:</strong>
                            <ul>
                                <li>Count: {:,}</li>
                                <li>Avg Visits: {:.1f}</li>
                                <li>Avg Spend/Visit: ${:.2f}</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """.format(
                    retention_30['one_time_customers'],
                    retention_30['one_time_revenue'],
                    retention_30['one_time_revenue'] / retention_30['one_time_customers'] if retention_30['one_time_customers'] > 0 else 0,
                    retention_30['returning_customers'],
                    retention_30['avg_visits_returning'],
                    retention_30['retained_avg_spend']
                ), unsafe_allow_html=True)
            
            # Retention Impact Analysis
            st.subheader("💰 Revenue Impact")
            
            # Create retention impact chart
            retention_data = pd.DataFrame({
                'Time Window': ['30 Days', '60 Days', '90 Days'],
                'Retention Rate': [retention_30['rate'], retention_60['rate'], retention_90['rate']],
                'Retained Revenue': [retention_30['retained_total_revenue'], retention_60['retained_total_revenue'], retention_90['retained_total_revenue']],
                'Lost Revenue': [retention_30['non_retained_total_revenue'], retention_60['non_retained_total_revenue'], retention_90['non_retained_total_revenue']]
            })
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig.add_trace(
                go.Bar(
                    x=retention_data['Time Window'],
                    y=retention_data['Retained Revenue'],
                    name="Retained Revenue",
                    marker_color='#2ecc71'
                ),
                secondary_y=False
            )
            
            fig.add_trace(
                go.Bar(
                    x=retention_data['Time Window'],
                    y=retention_data['Lost Revenue'],
                    name="Lost Revenue",
                    marker_color='#e74c3c'
                ),
                secondary_y=False
            )
            
            fig.add_trace(
                go.Scatter(
                    x=retention_data['Time Window'],
                    y=retention_data['Retention Rate'],
                    name="Retention Rate",
                    marker_color='#3498db',
                    mode='lines+markers'
                ),
                secondary_y=True
            )
            
            fig.update_layout(
                title="Revenue Impact of Customer Retention",
                barmode='stack',
                height=400
            )
            
            fig.update_yaxes(title_text="Revenue ($)", secondary_y=False)
            fig.update_yaxes(title_text="Retention Rate (%)", secondary_y=True)
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Retention Impact Insights
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("""
                <div class='insight-box'>
                    <h4>📈 Retention Impact Insights</h4>
                    <ul>
                        <li><strong>Revenue Impact:</strong>
                            <ul>
                                <li>30-day retained revenue: ${:,.2f}</li>
                                <li>60-day retained revenue: ${:,.2f}</li>
                                <li>90-day retained revenue: ${:,.2f}</li>
                            </ul>
                        </li>
                        <li><strong>Visit Patterns:</strong>
                            <ul>
                                <li>Retained customers visit every {:.1f} days</li>
                                <li>Spend ${:.2f} more per visit than non-retained</li>
                                <li>{:.1f}x higher lifetime value</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """.format(
                    retention_30['retained_total_revenue'],
                    retention_60['retained_total_revenue'],
                    retention_90['retained_total_revenue'],
                    retention_30['retained_visit_freq'],
                    retention_30['retained_avg_spend'] - retention_30['non_retained_avg_spend'],
                    retention_30['retained_avg_spend'] / retention_30['non_retained_avg_spend'] if retention_30['non_retained_avg_spend'] > 0 else 0
                ), unsafe_allow_html=True)
            
            with col2:
                st.markdown("""
                <div class='recommendation-box'>
                    <h4>💡 Retention Opportunities</h4>
                    <ul>
                        <li><strong>Quick Wins:</strong>
                            <ul>
                                <li>Follow up with customers after first purchase</li>
                                <li>Implement a "Welcome Back" program</li>
                                <li>Create early loyalty rewards</li>
                            </ul>
                        </li>
                        <li><strong>Strategic Actions:</strong>
                            <ul>
                                <li>Focus on ${:,.2f} at-risk revenue</li>
                                <li>Target {:.1f}% spending gap</li>
                                <li>Reduce time between visits ({:.1f} days)</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """.format(
                    retention_30['non_retained_total_revenue'],
                    ((retention_30['retained_avg_spend'] - retention_30['non_retained_avg_spend']) / retention_30['non_retained_avg_spend'] * 100) if retention_30['non_retained_avg_spend'] > 0 else 0,
                    retention_30['retained_visit_freq']
                ), unsafe_allow_html=True)
        
        with tab3:
            st.header("Customer Segmentation")
            customer_segments = segment_customers(df_clean)
            
            segment_dist = customer_segments['segment'].value_counts()
            fig = px.pie(
                values=segment_dist.values,
                names=segment_dist.index,
                title='Customer Segment Distribution'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("""
            <div class='insight-box'>
                <h4>📌 Understanding Customer Segments</h4>
                <ul>
                    <li><strong>Champions:</strong> Your most valuable and loyal customers</li>
                    <li><strong>High Spender:</strong> Big spenders who visit less frequently</li>
                    <li><strong>Frequent Buyer:</strong> Regular visitors with moderate spending</li>
                    <li><strong>Recent Customer:</strong> New or recently active customers</li>
                    <li><strong>Lost High-Value:</strong> Previously valuable customers who haven't returned</li>
                    <li><strong>Lost Customer:</strong> Inactive customers needing re-engagement</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            st.write("Segment Performance Metrics:")
            st.dataframe(segment_metrics.set_index('Segment'), use_container_width=True)
        
        with tab4:
            st.header("Revenue Analysis")
            st.markdown("""
            This section analyzes your revenue patterns across different time periods and customer segments. 
            Understanding these patterns helps optimize pricing, promotions, and business operations.
            """)
            
            monthly_revenue, daily_revenue = analyze_revenue(df_clean)
            
            # Monthly Revenue Trends
            st.subheader("📈 Monthly Revenue Trends")
            
            # Display key revenue metrics first
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Average Monthly Revenue",
                    f"${monthly_revenue['Revenue'].mean():,.2f}",
                    f"{((monthly_revenue['Revenue'].iloc[-1] / monthly_revenue['Revenue'].iloc[0]) - 1) * 100:.1f}% vs First Month"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> Your typical monthly revenue, with the percentage showing growth/decline 
                    compared to your first month. This helps track business growth over time.</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.metric(
                    "Average Transaction Value",
                    f"${monthly_revenue['Avg_Transaction_Value'].mean():,.2f}",
                    f"{((monthly_revenue['Avg_Transaction_Value'].iloc[-1] / monthly_revenue['Avg_Transaction_Value'].iloc[0]) - 1) * 100:.1f}% vs First Month"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> The average amount spent per transaction. 
                    The percentage shows how this has changed since your first month, indicating pricing or purchasing pattern changes.</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                st.metric(
                    "Revenue per Customer",
                    f"${monthly_revenue['Revenue_per_Customer'].mean():,.2f}",
                    f"{((monthly_revenue['Revenue_per_Customer'].iloc[-1] / monthly_revenue['Revenue_per_Customer'].iloc[0]) - 1) * 100:.1f}% vs First Month"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> How much revenue each customer generates on average per month. 
                    This metric combines both visit frequency and spending amount.</p>
                </div>
                """, unsafe_allow_html=True)
            
            # Monthly Revenue Chart
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig.add_trace(
                go.Bar(
                    x=monthly_revenue['Month'],
                    y=monthly_revenue['Revenue'],
                    name="Total Revenue",
                    marker_color='#1f77b4'
                ),
                secondary_y=False
            )
            
            fig.add_trace(
                go.Line(
                    x=monthly_revenue['Month'],
                    y=monthly_revenue['Avg_Transaction_Value'],
                    name="Avg Transaction Value",
                    marker_color='#ff7f0e'
                ),
                secondary_y=True
            )
            
            fig.update_layout(
                title="Monthly Revenue and Average Transaction Value",
                xaxis_title="Month",
                barmode='group',
                height=400
            )
            
            fig.update_yaxes(title_text="Total Revenue ($)", secondary_y=False)
            fig.update_yaxes(title_text="Avg Transaction Value ($)", secondary_y=True)
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Monthly Trends Insights
            st.markdown("""
            <div class='insight-box'>
                <h4>📊 Monthly Performance Insights</h4>
                <ul>
                    <li><strong>Revenue Trends:</strong>
                        <ul>
                            <li>Best month: {} (${:,.2f})</li>
                            <li>Average monthly growth: {:.1f}%</li>
                            <li>Month-over-month stability: {}</li>
                        </ul>
                    </li>
                    <li><strong>Customer Activity:</strong>
                        <ul>
                            <li>Average customers per month: {:.0f}</li>
                            <li>Transactions per customer: {:.1f}</li>
                            <li>Revenue concentration: {:.1f}% from top month</li>
                        </ul>
                    </li>
                </ul>
            </div>
            """.format(
                monthly_revenue.loc[monthly_revenue['Revenue'].idxmax(), 'Month'].strftime('%B %Y'),
                monthly_revenue['Revenue'].max(),
                ((monthly_revenue['Revenue'].iloc[-1] / monthly_revenue['Revenue'].iloc[0]) - 1) * 100,
                "Consistent" if monthly_revenue['Revenue'].std() / monthly_revenue['Revenue'].mean() < 0.2 else "Variable",
                monthly_revenue['Unique_Customers'].mean(),
                monthly_revenue['Transactions'].sum() / monthly_revenue['Unique_Customers'].sum(),
                (monthly_revenue['Revenue'].max() / monthly_revenue['Revenue'].sum()) * 100
            ), unsafe_allow_html=True)
            
            # Daily Revenue Patterns
            st.subheader("📊 Daily Revenue Patterns")
            st.markdown("""
            Understanding daily patterns helps optimize staffing, inventory, and operations. 
            This analysis shows how your business performs across different days of the week.
            """)
            
            # Daily metrics
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "Best Performing Day",
                    f"{daily_revenue.loc[daily_revenue['Total_Revenue'].idxmax(), 'Day']}",
                    f"${daily_revenue['Total_Revenue'].max():,.2f} revenue"
                )
            with col2:
                st.metric(
                    "Most Active Day",
                    f"{daily_revenue.loc[daily_revenue['Transaction_Count'].idxmax(), 'Day']}",
                    f"{daily_revenue['Transaction_Count'].max():,.0f} transactions"
                )
            
            # Daily Revenue Chart
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig.add_trace(
                go.Bar(
                    x=daily_revenue['Day'],
                    y=daily_revenue['Total_Revenue'],
                    name="Total Revenue",
                    marker_color='#1f77b4'
                ),
                secondary_y=False
            )
            
            fig.add_trace(
                go.Line(
                    x=daily_revenue['Day'],
                    y=daily_revenue['Transaction_Count'],
                    name="Transaction Count",
                    marker_color='#ff7f0e'
                ),
                secondary_y=True
            )
            
            fig.update_layout(
                title="Revenue and Transaction Count by Day of Week",
                xaxis_title="Day of Week",
                height=400
            )
            
            fig.update_yaxes(title_text="Total Revenue ($)", secondary_y=False)
            fig.update_yaxes(title_text="Number of Transactions", secondary_y=True)
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Daily Pattern Insights
            st.markdown("""
            <div class='insight-box'>
                <h4>📅 Daily Pattern Insights</h4>
                <ul>
                    <li><strong>Peak Performance:</strong>
                        <ul>
                            <li>Highest revenue day: {} (${:,.2f})</li>
                            <li>Busiest day: {} ({:,.0f} transactions)</li>
                            <li>Best average transaction: {} (${:,.2f})</li>
                        </ul>
                    </li>
                    <li><strong>Operational Insights:</strong>
                        <ul>
                            <li>Weekend vs Weekday revenue: {:.1f}% difference</li>
                            <li>Peak vs Off-peak variance: {:.1f}x</li>
                            <li>Daily transaction stability: {}</li>
                        </ul>
                    </li>
                </ul>
            </div>
            """.format(
                daily_revenue.loc[daily_revenue['Total_Revenue'].idxmax(), 'Day'],
                daily_revenue['Total_Revenue'].max(),
                daily_revenue.loc[daily_revenue['Transaction_Count'].idxmax(), 'Day'],
                daily_revenue['Transaction_Count'].max(),
                daily_revenue.loc[daily_revenue['Avg_Daily_Revenue'].idxmax(), 'Day'],
                daily_revenue['Avg_Daily_Revenue'].max(),
                ((daily_revenue[daily_revenue['Day'].isin(['Saturday', 'Sunday'])]['Total_Revenue'].mean() / 
                  daily_revenue[~daily_revenue['Day'].isin(['Saturday', 'Sunday'])]['Total_Revenue'].mean()) - 1) * 100,
                daily_revenue['Total_Revenue'].max() / daily_revenue['Total_Revenue'].min(),
                "Consistent" if daily_revenue['Transaction_Count'].std() / daily_revenue['Transaction_Count'].mean() < 0.2 else "Variable"
            ), unsafe_allow_html=True)
        
        with tab5:
            st.header("Client Analysis")
            
            client_analysis = analyze_clients(df_clean, customer_segments)
            
            # Top Spenders Section
            st.subheader("🌟 Top Spenders")
            st.dataframe(client_analysis['top_spenders'].set_index('Customer'), use_container_width=True)
            st.markdown("""
            <div class='insight-box'>
                <h4>💡 Top Spenders Insights</h4>
                <ul>
                    <li>Average spend of top 10 customers: ${:.2f}</li>
                    <li>They account for {:.1f}% of total revenue</li>
                    <li>{} of them visited in the last 30 days</li>
                    <li>Average daily spend: ${:.2f}</li>
                    <li>Average customer lifetime: {:.0f} days</li>
                </ul>
            </div>
            """.format(
                client_analysis['top_spenders']['total_spend'].mean(),
                (client_analysis['top_spenders']['total_spend'].sum() / total_revenue) * 100,
                len(client_analysis['top_spenders'][client_analysis['top_spenders']['days_since_last_visit'] <= 30]),
                client_analysis['top_spenders']['spend_per_day'].mean(),
                client_analysis['top_spenders']['loyalty_days'].mean()
            ), unsafe_allow_html=True)
            
            # Most Frequent Customers Section
            st.subheader("🔄 Most Frequent Customers")
            st.dataframe(client_analysis['most_frequent'].set_index('Customer'), use_container_width=True)
            st.markdown("""
            <div class='insight-box'>
                <h4>💡 Frequency Insights</h4>
                <ul>
                    <li>Average visits per month: {:.1f}</li>
                    <li>Average spend per visit: ${:.2f}</li>
                    <li>Total revenue from frequent customers: ${:.2f}</li>
                    <li>{} customers visit more than once per week</li>
                </ul>
            </div>
            """.format(
                client_analysis['most_frequent']['visits_per_month'].mean(),
                client_analysis['most_frequent']['avg_spend'].mean(),
                client_analysis['most_frequent']['total_spend'].sum(),
                len(client_analysis['most_frequent'][client_analysis['most_frequent']['visits_per_month'] > 4])
            ), unsafe_allow_html=True)
            
            # Lost Valuable Customers Section
            st.subheader("⚠️ Lost Valuable Customers")
            st.dataframe(client_analysis['lost_valuable'].set_index('Customer'), use_container_width=True)
            st.markdown("""
            <div class='recommendation-box'>
                <h4>🎯 Recovery Opportunities</h4>
                <ul>
                    <li>Potential monthly revenue at risk: ${:.2f}</li>
                    <li>Average customer value: ${:.2f}</li>
                    <li>Typical visit frequency: {:.1f} days</li>
                    <li>Last visit range: {} to {} days ago</li>
                </ul>
            </div>
            """.format(
                client_analysis['lost_valuable']['potential_monthly_revenue_loss'].sum(),
                client_analysis['lost_valuable']['avg_spend'].mean(),
                client_analysis['lost_valuable']['visit_count'].mean(),
                client_analysis['lost_valuable']['days_since_last_visit'].min(),
                client_analysis['lost_valuable']['days_since_last_visit'].max()
            ), unsafe_allow_html=True)
            
            # At-Risk Customers Section
            st.subheader("⚡ At-Risk Customers")
            st.dataframe(client_analysis['at_risk'].set_index('Customer'), use_container_width=True)
            st.markdown("""
            <div class='recommendation-box'>
                <h4>🎯 Retention Opportunities</h4>
                <ul>
                    <li>Total revenue at risk: ${:.2f}</li>
                    <li>Average days since last visit: {:.1f}</li>
                    <li>Typical customer value: ${:.2f}</li>
                    <li>Number of customers to target: {}</li>
                </ul>
            </div>
            """.format(
                client_analysis['at_risk']['total_spend'].sum(),
                client_analysis['at_risk']['days_since_last_visit'].mean(),
                client_analysis['at_risk']['avg_spend'].mean(),
                len(client_analysis['at_risk'])
            ), unsafe_allow_html=True)
            
            # Recent New Customers Section
            st.subheader("🆕 Recent New Customers")
            st.dataframe(client_analysis['recent_new'].set_index('Customer'), use_container_width=True)
            st.markdown("""
            <div class='insight-box'>
                <h4>💡 New Customer Insights</h4>
                <ul>
                    <li>Average first month spend: ${:.2f}</li>
                    <li>Visit frequency: {:.1f} times per week</li>
                    <li>High-value potential customers: {}</li>
                    <li>Total new customer revenue: ${:.2f}</li>
                </ul>
            </div>
            """.format(
                client_analysis['recent_new']['total_spend'].mean(),
                client_analysis['recent_new']['visits_per_week'].mean(),
                len(client_analysis['recent_new'][client_analysis['recent_new']['total_spend'] > client_analysis['recent_new']['total_spend'].quantile(0.75)]),
                client_analysis['recent_new']['total_spend'].sum()
            ), unsafe_allow_html=True)
            
            # Best Improving Customers Section
            st.subheader("📈 Best Improving Customers")
            st.dataframe(client_analysis['best_improvers'].set_index('Customer'), use_container_width=True)
            st.markdown("""
            <div class='insight-box'>
                <h4>💡 Growth Insights</h4>
                <ul>
                    <li>Average spend increase: {:.1f}%</li>
                    <li>Total revenue from improvers: ${:.2f}</li>
                    <li>Average visit frequency: {:.1f} days</li>
                    <li>Recent activity: {} active in last 30 days</li>
                </ul>
            </div>
            """.format(
                client_analysis['improvement_stats']['avg_improvement'],
                client_analysis['improvement_stats']['total_revenue'],
                client_analysis['improvement_stats']['avg_visits'],
                client_analysis['improvement_stats']['active_last_30']
            ), unsafe_allow_html=True)
        
        with tab6:
            st.header("Customer Lifetime Value Analysis")
            st.markdown("""
            Customer Lifetime Value (LTV) measures the total revenue a business can expect from a customer throughout their relationship. 
            This analysis helps identify your most valuable customers and opportunities for growth.
            """)
            
            # Calculate LTV metrics
            customer_ltv, ltv_summary = calculate_ltv(df_clean)
            
            # Display key LTV metrics with explanations
            st.subheader("🔑 Key Metrics")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Average Lifetime Value",
                    f"${ltv_summary['avg_lifetime_value']:,.2f}",
                    f"{ltv_summary['returning_customer_ratio']:.1f}% are returning customers"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> On average, each customer spends this amount over their entire relationship with your business. 
                    The percentage shows how many customers make repeat purchases, which is a key driver of lifetime value.</p>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.metric(
                    "Average Annual Value",
                    f"${ltv_summary['avg_annual_value']:,.2f}",
                    f"Projected: ${ltv_summary['projected_annual_value']:,.2f}"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> This shows the average revenue per customer per year:
                    <ul>
                        <li>Historical: Based on actual spending patterns</li>
                        <li>Projected: Expected future value based on current behavior</li>
                    </ul></p>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                st.metric(
                    "Average Customer Lifespan",
                    f"{ltv_summary['avg_customer_lifetime_days']:.1f} days",
                    f"{ltv_summary['avg_lifetime_visits']:.1f} visits on average"
                )
                st.markdown("""
                <div class='insight-box' style='font-size: 0.9em;'>
                    <p><strong>What this means:</strong> Shows how long customers typically stay active and how frequently they visit. 
                    This helps understand customer engagement and loyalty patterns.</p>
                </div>
                """, unsafe_allow_html=True)
            
            # Value Segments Analysis
            st.subheader("💎 Customer Value Segments")
            st.markdown("""
            Customers are segmented into four value tiers based on their total spending. This helps identify different 
            customer groups and their specific characteristics.
            """)
            
            value_segments = pd.qcut(
                customer_ltv['total_spend'],
                q=4,
                labels=['Bronze', 'Silver', 'Gold', 'Platinum']
            )
            segment_metrics = customer_ltv.groupby(value_segments).agg({
                'total_spend': ['mean', 'sum', 'count'],
                'visit_count': 'mean',
                'avg_transaction': 'mean'
            }).round(2)
            
            segment_metrics.columns = ['Avg LTV', 'Total Revenue', 'Customer Count', 'Avg Visits', 'Avg Transaction']
            st.dataframe(segment_metrics, use_container_width=True)
            
            # Detailed Value Analysis
            st.subheader("📊 Value Distribution Analysis")
            
            # Two columns for metrics and distribution
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.markdown("""
                <div class='insight-box'>
                    <h4>💡 Value Breakdown</h4>
                    <ul>
                        <li><strong>Customer Mix:</strong>
                            <ul>
                                <li>{:.1f}% One-time buyers</li>
                                <li>{:.1f}% Returning customers</li>
                            </ul>
                        </li>
                        <li><strong>Value Spread:</strong>
                            <ul>
                                <li>Median LTV: ${:,.2f}</li>
                                <li>Top 10% avg: ${:,.2f}</li>
                                <li>Bottom 10% avg: ${:,.2f}</li>
                            </ul>
                        </li>
                        <li><strong>Transaction Patterns:</strong>
                            <ul>
                                <li>Avg transaction: ${:,.2f}</li>
                                <li>Visits per customer: {:.1f}</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """.format(
                    ltv_summary['one_time_customer_ratio'],
                    ltv_summary['returning_customer_ratio'],
                    ltv_summary['median_lifetime_value'],
                    ltv_summary['top_10_percent_value'],
                    ltv_summary['bottom_10_percent_value'],
                    ltv_summary['avg_transaction_value'],
                    ltv_summary['avg_lifetime_visits']
                ), unsafe_allow_html=True)
            
            with col2:
                fig = px.histogram(
                    customer_ltv[customer_ltv['total_spend'] > 0],
                    x='total_spend',
                    nbins=50,
                    title='Distribution of Customer Lifetime Value',
                    labels={'total_spend': 'Lifetime Value ($)'}
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            
            # Key Insights
            st.subheader("🎯 Key Insights & Opportunities")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("""
                <div class='insight-box'>
                    <h4>📈 Current Performance</h4>
                    <ul>
                        <li><strong>Customer Base Health:</strong>
                            <ul>
                                <li>Half of your customers return for repeat purchases</li>
                                <li>Average customer stays active for 2 months</li>
                                <li>Significant value gap between top and bottom customers</li>
                            </ul>
                        </li>
                        <li><strong>Value Generation:</strong>
                            <ul>
                                <li>Platinum customers generate {:.1f}x more value than Bronze</li>
                                <li>Each additional visit adds ${:.2f} in average revenue</li>
                                <li>Top 10% of customers drive {:.1f}% of revenue</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """.format(
                    segment_metrics.iloc[3]['Avg LTV'] / segment_metrics.iloc[0]['Avg LTV'],
                    ltv_summary['avg_transaction_value'],
                    (ltv_summary['top_10_percent_value'] * (len(customer_ltv) * 0.1)) / ltv_summary['total_customer_value'] * 100
                ), unsafe_allow_html=True)
            
            with col2:
                st.markdown("""
                <div class='recommendation-box'>
                    <h4>💡 Growth Opportunities</h4>
                    <ul>
                        <li><strong>Immediate Actions:</strong>
                            <ul>
                                <li>Convert one-time buyers with targeted follow-up campaigns</li>
                                <li>Increase visit frequency through loyalty rewards</li>
                                <li>Focus on extending customer lifespan beyond 2 months</li>
                            </ul>
                        </li>
                        <li><strong>Strategic Initiatives:</strong>
                            <ul>
                                <li>Develop Bronze-to-Silver upgrade paths</li>
                                <li>Create VIP benefits for Gold/Platinum segments</li>
                                <li>Implement early warning system for customer churn</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
        
        with tab7:
            st.header("Summary & Export")
            st.markdown("Analysis Period: {} to {}".format(
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            ))
            
            st.markdown("""
            <div class='insight-box'>
                <h4>📌 Key Findings</h4>
                <ul>
                    <li>Customer Base: {:,} unique loyalty customers</li>
                    <li>Revenue Performance: ${:,.2f} total revenue</li>
                    <li>Customer Retention: {:.1f}% 30-day repurchase rate</li>
                    <li>Top Customer Segment: {}</li>
                    <li>Lost Valuable Customers: {}</li>
                    <li>New Customers (Last 30 Days): {}</li>
                </ul>
            </div>
            """.format(
                total_customers,
                total_revenue,
                retention_30['rate'],
                customer_segments['segment'].value_counts().index[0],
                len(client_analysis['lost_valuable']),
                len(client_analysis['recent_new'])
            ), unsafe_allow_html=True)
            
            # Calculate Excel report
            excel_report = create_excel_report(
                df_clean,
                customer_segments,
                segment_metrics,
                retention_30,
                retention_data,
                client_analysis
            )
            
            st.download_button(
                label="📥 Download Complete Analysis Report",
                data=excel_report,
                file_name=f"retail_analytics_report_{start_date}_to_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if __name__ == "__main__":
    main() 
