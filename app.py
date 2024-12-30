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
        'Date': ['min', 'max'],
        'ID': 'count',
        'Total': ['sum', 'mean']
    })
    
    # Reset index and rename columns properly
    customer_purchases.reset_index(inplace=True)
    customer_purchases.columns = ['Customer', 'first_purchase', 'last_purchase', 'visit_count', 'total_spend', 'avg_spend']
    
    # Calculate time difference between first and last purchase
    customer_purchases['days_between'] = (customer_purchases['last_purchase'] - customer_purchases['first_purchase']).dt.days
    customer_purchases['avg_days_between_visits'] = customer_purchases['days_between'] / customer_purchases['visit_count']
    
    # Count customers who returned within window
    returned = customer_purchases[customer_purchases['days_between'] >= window_days]['Customer'].count()
    total_customers = len(customer_purchases)
    
    # Calculate average spend for retained vs non-retained customers
    retained_customers = customer_purchases[customer_purchases['days_between'] >= window_days]
    non_retained_customers = customer_purchases[customer_purchases['days_between'] < window_days]
    
    retention_stats = {
        'rate': (returned / total_customers * 100) if total_customers > 0 else 0,
        'retained_avg_spend': retained_customers['avg_spend'].mean() if not retained_customers.empty else 0,
        'non_retained_avg_spend': non_retained_customers['avg_spend'].mean() if not non_retained_customers.empty else 0,
        'retained_visit_freq': retained_customers['avg_days_between_visits'].mean() if not retained_customers.empty else 0,
        'non_retained_visit_freq': non_retained_customers['avg_days_between_visits'].mean() if not non_retained_customers.empty else 0,
        'retained_total_revenue': retained_customers['total_spend'].sum() if not retained_customers.empty else 0,
        'non_retained_total_revenue': non_retained_customers['total_spend'].sum() if not non_retained_customers.empty else 0
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
    customer_metrics['avg_days_between_visits'] = customer_metrics['customer_lifetime_days'] / customer_metrics['visit_count']
    customer_metrics['days_since_last_visit'] = (now - customer_metrics['last_visit']).dt.days
    
    # Calculate quantiles for segmentation
    spend_75th = customer_metrics['total_spend'].quantile(0.75)
    freq_75th = customer_metrics['frequency'].quantile(0.75)
    avg_days_median = customer_metrics['avg_days_between_visits'].quantile(0.5)
    
    # Enhanced segmentation logic
    def assign_segment(row):
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
        
        if row['avg_days_between_visits'] < avg_days_median:
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
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📈 Overview",
            "🔄 Customer Retention",
            "👥 Customer Segments",
            "💰 Revenue Analysis",
            "👤 Client Analysis",
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
            """)
            
            # Calculate retention metrics for different time windows
            retention_30 = calculate_repurchase_rate(df_clean, 30)
            retention_60 = calculate_repurchase_rate(df_clean, 60)
            retention_90 = calculate_repurchase_rate(df_clean, 90)
            
            # Display retention rates
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "30-Day Retention",
                    f"{retention_30['rate']:.1f}%",
                    f"${retention_30['retained_avg_spend']:.2f} avg spend"
                )
            
            with col2:
                st.metric(
                    "60-Day Retention",
                    f"{retention_60['rate']:.1f}%",
                    f"${retention_60['retained_avg_spend']:.2f} avg spend"
                )
            
            with col3:
                st.metric(
                    "90-Day Retention",
                    f"{retention_90['rate']:.1f}%",
                    f"${retention_90['retained_avg_spend']:.2f} avg spend"
                )
            
            # Explanation of retention metrics
            st.markdown("""
            <div class='insight-box'>
                <h4>📊 Understanding Retention Metrics</h4>
                <p>The metrics above show how well we retain customers over different time periods:</p>
                <ul>
                    <li><strong>30-Day Retention:</strong> Percentage of customers who return within a month. This is a key indicator of short-term customer satisfaction.</li>
                    <li><strong>60-Day Retention:</strong> Medium-term retention showing customer loyalty over two months.</li>
                    <li><strong>90-Day Retention:</strong> Long-term retention indicating strong customer relationships.</li>
                </ul>
                <p>The "avg spend" below each percentage shows how much retained customers typically spend, helping identify the value of retained customers.</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Retention vs Revenue Analysis
            st.subheader("📊 Retention Impact on Revenue")
            st.markdown("""
            The graph below shows how customer retention affects revenue across different time periods. 
            It combines three key metrics:
            1. **Retained Revenue** (Green bars): Revenue from customers who continue to shop with us
            2. **Lost Revenue** (Red bars): Revenue we've lost from customers who haven't returned
            3. **Retention Rate** (Blue line): Percentage of customers we retain over time
            
            This visualization helps identify the financial impact of customer retention and where we might be losing valuable customers.
            """)
            
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
            
            # Customer Behavior Analysis
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("""
                <div class='insight-box'>
                    <h4>📈 Retention Insights</h4>
                    <ul>
                        <li><strong>Short-term Retention (30 days):</strong>
                            <ul>
                                <li>Retention Rate: {:.1f}%</li>
                                <li>Retained Customer Avg Spend: ${:.2f}</li>
                                <li>Visit Frequency: {:.1f} days</li>
                                <li>Revenue Impact: ${:,.2f}</li>
                            </ul>
                        </li>
                        <li><strong>Long-term Retention (90 days):</strong>
                            <ul>
                                <li>Retention Rate: {:.1f}%</li>
                                <li>Retained Customer Avg Spend: ${:.2f}</li>
                                <li>Visit Frequency: {:.1f} days</li>
                                <li>Revenue Impact: ${:,.2f}</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """.format(
                    retention_30['rate'],
                    retention_30['retained_avg_spend'],
                    retention_30['retained_visit_freq'],
                    retention_30['retained_total_revenue'],
                    retention_90['rate'],
                    retention_90['retained_avg_spend'],
                    retention_90['retained_visit_freq'],
                    retention_90['retained_total_revenue']
                ), unsafe_allow_html=True)
            
            with col2:
                st.markdown("""
                <div class='recommendation-box'>
                    <h4>🎯 Retention Strategy Recommendations</h4>
                    <ul>
                        <li><strong>Short-term Actions:</strong>
                            <ul>
                                <li>Implement 30-day follow-up communications</li>
                                <li>Offer "Welcome Back" promotions after 14 days</li>
                                <li>Create early-stage loyalty rewards</li>
                            </ul>
                        </li>
                        <li><strong>Long-term Strategy:</strong>
                            <ul>
                                <li>Develop tiered loyalty program</li>
                                <li>Personalize offers based on spending patterns</li>
                                <li>Focus on high-value customer retention</li>
                            </ul>
                        </li>
                        <li><strong>Revenue Recovery:</strong>
                            <ul>
                                <li>Target ${:,.2f} in at-risk revenue</li>
                                <li>Focus on {:.1f}% spending gap between retained and lost customers</li>
                            </ul>
                        </li>
                    </ul>
                </div>
                """.format(
                    retention_30['non_retained_total_revenue'],
                    ((retention_30['retained_avg_spend'] - retention_30['non_retained_avg_spend']) / retention_30['non_retained_avg_spend'] * 100 if retention_30['non_retained_avg_spend'] > 0 else 0)
                ), unsafe_allow_html=True)
            
            # Visit Pattern Analysis
            st.subheader("📅 Customer Visit Patterns")
            st.markdown("""
            The histogram below shows how frequently customers visit. Understanding these patterns helps in:
            1. Identifying optimal times for customer engagement
            2. Planning inventory and staffing
            3. Developing targeted marketing campaigns
            4. Setting realistic retention goals
            """)
            
            # Calculate visit frequency distribution
            customer_visits = df_clean.groupby('Customer').agg({
                'Date': lambda x: (x.max() - x.min()).days,
                'ID': 'count'
            }).reset_index()
            
            customer_visits['avg_days_between_visits'] = customer_visits['Date'] / customer_visits['ID']
            
            fig = px.histogram(
                customer_visits,
                x='avg_days_between_visits',
                nbins=30,
                title='Distribution of Visit Frequency',
                labels={'avg_days_between_visits': 'Average Days Between Visits'}
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Visit Pattern Insights
            st.markdown("""
            <div class='insight-box'>
                <h4>🔍 Visit Pattern Analysis</h4>
                <p>Understanding how often customers visit is crucial for business planning:</p>
                <ul>
                    <li><strong>Visit Frequency:</strong>
                        <ul>
                            <li>Most frequent customers visit every {:.1f} days</li>
                            <li>Average customer visits every {:.1f} days</li>
                            <li>Least frequent customers visit every {:.1f} days</li>
                        </ul>
                    </li>
                    <li><strong>Customer Groups:</strong>
                        <ul>
                            <li>Frequent visitors (< 7 days): {:.1f}% of customers</li>
                            <li>Regular visitors (7-30 days): {:.1f}% of customers</li>
                            <li>Occasional visitors (> 30 days): {:.1f}% of customers</li>
                        </ul>
                    </li>
                </ul>
                <p>This information helps in creating targeted marketing campaigns and setting appropriate customer engagement strategies for each group.</p>
            </div>
            """.format(
                customer_visits['avg_days_between_visits'].min(),
                customer_visits['avg_days_between_visits'].mean(),
                customer_visits['avg_days_between_visits'].max(),
                len(customer_visits[customer_visits['avg_days_between_visits'] < 7]) / len(customer_visits) * 100,
                len(customer_visits[(customer_visits['avg_days_between_visits'] >= 7) & (customer_visits['avg_days_between_visits'] <= 30)]) / len(customer_visits) * 100,
                len(customer_visits[customer_visits['avg_days_between_visits'] > 30]) / len(customer_visits) * 100
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
            
            monthly_revenue, daily_revenue = analyze_revenue(df_clean)
            
            # Monthly Revenue Trends
            st.subheader("📈 Monthly Revenue Trends")
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
            
            # Revenue Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Average Monthly Revenue",
                    f"${monthly_revenue['Revenue'].mean():,.2f}",
                    f"{((monthly_revenue['Revenue'].iloc[-1] / monthly_revenue['Revenue'].iloc[0]) - 1) * 100:.1f}% vs First Month"
                )
            with col2:
                st.metric(
                    "Average Transaction Value",
                    f"${monthly_revenue['Avg_Transaction_Value'].mean():,.2f}",
                    f"{((monthly_revenue['Avg_Transaction_Value'].iloc[-1] / monthly_revenue['Avg_Transaction_Value'].iloc[0]) - 1) * 100:.1f}% vs First Month"
                )
            with col3:
                st.metric(
                    "Revenue per Customer",
                    f"${monthly_revenue['Revenue_per_Customer'].mean():,.2f}",
                    f"{((monthly_revenue['Revenue_per_Customer'].iloc[-1] / monthly_revenue['Revenue_per_Customer'].iloc[0]) - 1) * 100:.1f}% vs First Month"
                )
            
            # Daily Revenue Patterns
            st.subheader("📊 Daily Revenue Patterns")
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
            
            # Transaction Value Distribution
            st.subheader("💰 Transaction Value Distribution")
            fig = px.histogram(
                df_clean,
                x='Total',
                nbins=50,
                title='Distribution of Transaction Values',
                labels={'Total': 'Transaction Amount ($)'}
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
            
            # Revenue Insights
            st.markdown("""
            <div class='insight-box'>
                <h4>📌 Revenue Insights</h4>
                <ul>
                    <li>Most transactions fall in the ${:.2f} - ${:.2f} range</li>
                    <li>Highest revenue day: {}</li>
                    <li>Average daily revenue: ${:.2f}</li>
                    <li>Best performing month: {} (${:,.2f})</li>
                    <li>Average revenue per customer: ${:.2f}</li>
                </ul>
            </div>
            """.format(
                df_clean['Total'].quantile(0.25),
                df_clean['Total'].quantile(0.75),
                daily_revenue.loc[daily_revenue['Total_Revenue'].idxmax(), 'Day'],
                daily_revenue['Avg_Daily_Revenue'].mean(),
                monthly_revenue.loc[monthly_revenue['Revenue'].idxmax(), 'Month'].strftime('%B %Y'),
                monthly_revenue['Revenue'].max(),
                monthly_revenue['Revenue_per_Customer'].mean()
            ), unsafe_allow_html=True)
            
            # Recommendations
            st.markdown("""
            <div class='recommendation-box'>
                <h4>💡 Revenue Optimization Recommendations</h4>
                <ul>
                    <li>Focus marketing efforts on {} when customer activity is highest</li>
                    <li>Consider special promotions for {} when revenue is typically lower</li>
                    <li>Target average transaction value increase through upselling strategies</li>
                    <li>Implement loyalty rewards for high-value customers (>${:.2f} per visit)</li>
                </ul>
            </div>
            """.format(
                daily_revenue.loc[daily_revenue['Transaction_Count'].idxmax(), 'Day'],
                daily_revenue.loc[daily_revenue['Total_Revenue'].idxmin(), 'Day'],
                df_clean['Total'].quantile(0.75)
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
