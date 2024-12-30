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
</style>
""", unsafe_allow_html=True)

def clean_data(df):
    """Clean and prepare the data for analysis."""
    # Convert date to datetime
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Clean amount column
    df['Total'] = df['Total'].str.replace('$', '').str.replace(',', '').astype(float)
    
    # Filter for completed transactions only
    df = df[df['Completed'] == 'Yes']
    
    # Filter for loyalty customers (non-empty Customer field)
    df = df[df['Customer'].notna() & (df['Customer'] != '')]
    
    return df

def calculate_repurchase_rate(df, window_days):
    """Calculate repurchase rate for a given time window."""
    # First, get first and last purchase dates for each customer
    customer_purchases = df.groupby('Customer').agg({
        'Date': ['min', 'max'],
        'ID': 'count'
    })
    
    # Reset index and rename columns properly
    customer_purchases.reset_index(inplace=True)
    customer_purchases.columns = ['Customer', 'first_purchase', 'last_purchase', 'total_purchases']
    
    # Calculate time difference between first and last purchase
    customer_purchases['days_between'] = (customer_purchases['last_purchase'] - customer_purchases['first_purchase']).dt.days
    
    # Count customers who returned within window
    returned = customer_purchases[customer_purchases['days_between'] >= window_days]['Customer'].count()
    total_customers = len(customer_purchases)
    
    return (returned / total_customers * 100) if total_customers > 0 else 0

def calculate_revenue_retention(df):
    """Calculate revenue retention rate by month."""
    monthly_revenue = df.groupby(pd.Grouper(key='Date', freq='M'))['Total'].sum()
    retention_rates = []
    
    for i in range(1, len(monthly_revenue)):
        prev_month = monthly_revenue.iloc[i-1]
        curr_month = monthly_revenue.iloc[i]
        retention_rate = (curr_month / prev_month * 100) if prev_month > 0 else 0
        retention_rates.append({
            'Month': monthly_revenue.index[i],
            'Retention Rate': retention_rate
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
    """Detailed client analysis."""
    now = df_clean['Date'].max()
    
    # Top clients by total spend
    top_spenders = customer_metrics.nlargest(10, 'total_spend')[
        ['Customer', 'total_spend', 'visit_count', 'avg_spend', 'days_since_last_visit']
    ]
    
    # Most frequent customers
    most_frequent = customer_metrics.nlargest(10, 'visit_count')[
        ['Customer', 'visit_count', 'total_spend', 'avg_spend', 'days_since_last_visit']
    ]
    
    # Lost valuable customers (no visit in last 90 days and high total spend)
    lost_valuable = customer_metrics[
        (customer_metrics['days_since_last_visit'] > 90) &
        (customer_metrics['total_spend'] > customer_metrics['total_spend'].quantile(0.75))
    ].sort_values('total_spend', ascending=False)[
        ['Customer', 'total_spend', 'visit_count', 'days_since_last_visit', 'last_visit']
    ]
    
    # Recent new customers (first purchase in last 30 days)
    recent_new = customer_metrics[
        (now - customer_metrics['first_visit']).dt.days <= 30
    ].sort_values('total_spend', ascending=False)[
        ['Customer', 'first_visit', 'total_spend', 'visit_count']
    ]
    
    return {
        'top_spenders': top_spenders,
        'most_frequent': most_frequent,
        'lost_valuable': lost_valuable,
        'recent_new': recent_new
    }

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
                '30-Day Repurchase Rate',
                '90-Day Repurchase Rate'
            ],
            'Value': [
                f"{df_clean['Customer'].nunique():,}",
                f"${df_clean['Total'].sum():,.2f}",
                f"${df_clean['Total'].mean():.2f}",
                f"{len(df_clean):,}",
                f"{repurchase_data.iloc[0]['Rate']:.1f}%",
                f"{repurchase_data.iloc[2]['Rate']:.1f}%"
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
        
        # Revenue Retention Sheet (if data available)
        if not retention_data.empty:
            retention_data.to_excel(writer, sheet_name='Revenue Retention', index=False)
            worksheet = writer.sheets['Revenue Retention']
            for col_num, value in enumerate(retention_data.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)
        
        # Add Client Analysis sheets
        for sheet_name, df in client_analysis.items():
            sheet_title = sheet_name.replace('_', ' ').title()
            df.to_excel(writer, sheet_name=sheet_title, index=False)
            worksheet = writer.sheets[sheet_title]
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 15)
    
    return output.getvalue()

def main():
    st.title("📊 Retail Analytics Dashboard")
    st.write("Upload your transaction data to analyze customer retention and revenue patterns.")
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        # Load and clean data
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
        
        # Clean data and filter by date range
        df_clean = clean_data(df)
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
        rate_30 = calculate_repurchase_rate(df_clean, 30)
        rate_60 = calculate_repurchase_rate(df_clean, 60)
        rate_90 = calculate_repurchase_rate(df_clean, 90)
        
        # Create repurchase data DataFrame
        repurchase_data = pd.DataFrame([
            {'Window': '30 Days', 'Rate': rate_30},
            {'Window': '60 Days', 'Rate': rate_60},
            {'Window': '90 Days', 'Rate': rate_90}
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
            This section shows how well your business retains customers over different time periods.
            A higher repurchase rate indicates stronger customer loyalty.
            """)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                rate_30 = calculate_repurchase_rate(df_clean, 30)
                st.metric("30-Day Repurchase", f"{rate_30:.1f}%")
            with col2:
                rate_60 = calculate_repurchase_rate(df_clean, 60)
                st.metric("60-Day Repurchase", f"{rate_60:.1f}%")
            with col3:
                rate_90 = calculate_repurchase_rate(df_clean, 90)
                st.metric("90-Day Repurchase", f"{rate_90:.1f}%")
            
            repurchase_data = pd.DataFrame({
                'Window': ['30 Days', '60 Days', '90 Days'],
                'Rate': [rate_30, rate_60, rate_90]
            })
            
            fig = px.bar(
                repurchase_data,
                x='Window',
                y='Rate',
                title='Repurchase Rates by Time Window',
                labels={'Rate': 'Repurchase Rate (%)'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown(f"""
            <div class='insight-box'>
                <h4>📌 What This Means</h4>
                <ul>
                    <li>{rate_30:.1f}% of customers return within 30 days</li>
                    <li>{rate_90:.1f}% of customers return within 90 days</li>
                    <li>The trend {'increases' if rate_90 > rate_30 else 'decreases'} over time</li>
                </ul>
            </div>
            
            <div class='recommendation-box'>
                <h4>💡 Recommendations</h4>
                <ul>
                    <li>{'Consider implementing a loyalty program to improve retention' if rate_30 < 30 else 'Your retention rate is healthy'}</li>
                    <li>Focus on engaging customers during the first 30 days</li>
                    <li>Monitor customer feedback to identify areas for improvement</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        
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
            
            segment_metrics = customer_segments.groupby('segment').agg({
                'total_spend': ['mean', 'sum'],
                'visit_count': 'mean',
                'avg_spend': 'mean'
            })
            
            segment_metrics.columns = [
                'Avg Total Spend',
                'Total Revenue',
                'Avg Visits',
                'Avg Transaction'
            ]
            
            st.markdown("""
            <div class='insight-box'>
                <h4>📌 Understanding Customer Segments</h4>
                <ul>
                    <li><strong>Champions:</strong> Your most valuable and loyal customers</li>
                    <li><strong>Loyal Customers:</strong> Regular customers with consistent spending</li>
                    <li><strong>Potential Loyalists:</strong> Customers showing promise for loyalty</li>
                    <li><strong>At Risk:</strong> Customers who may need attention to prevent churn</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            st.write("Segment Performance Metrics:")
            st.dataframe(segment_metrics)
        
        with tab4:
            st.header("Revenue Analysis")
            retention_data = calculate_revenue_retention(df_clean)
            
            if not retention_data.empty:
                fig = px.line(
                    retention_data,
                    x='Month',
                    y='Retention Rate',
                    title='Monthly Revenue Retention Rate',
                    labels={'Retention Rate': 'Retention Rate (%)'}
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Not enough data to calculate revenue retention (need at least 2 months of data)")
            
            # Customer Spend Distribution
            fig = px.histogram(
                df_clean,
                x='Total',
                nbins=50,
                title='Distribution of Transaction Values',
                labels={'Total': 'Transaction Amount ($)'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("""
            <div class='insight-box'>
                <h4>📌 Revenue Insights</h4>
                <ul>
                    <li>Most transactions fall in the ${:.2f} - ${:.2f} range</li>
                    <li>The highest single transaction was ${:.2f}</li>
                    <li>The average transaction value is ${:.2f}</li>
                </ul>
            </div>
            """.format(
                df_clean['Total'].quantile(0.25),
                df_clean['Total'].quantile(0.75),
                df_clean['Total'].max(),
                df_clean['Total'].mean()
            ), unsafe_allow_html=True)
        
        with tab5:
            st.header("Client Analysis")
            
            client_analysis = analyze_clients(df_clean, customer_segments)
            
            st.subheader("🌟 Top Spenders")
            st.dataframe(client_analysis['top_spenders'])
            
            st.markdown("""
            <div class='insight-box'>
                <h4>💡 Top Spenders Insights</h4>
                <ul>
                    <li>Average spend of top 10 customers: ${:.2f}</li>
                    <li>They account for {:.1f}% of total revenue</li>
                    <li>{} of them visited in the last 30 days</li>
                </ul>
            </div>
            """.format(
                client_analysis['top_spenders']['total_spend'].mean(),
                (client_analysis['top_spenders']['total_spend'].sum() / total_revenue) * 100,
                len(client_analysis['top_spenders'][client_analysis['top_spenders']['days_since_last_visit'] <= 30])
            ), unsafe_allow_html=True)
            
            st.subheader("🔄 Most Frequent Customers")
            st.dataframe(client_analysis['most_frequent'])
            
            st.subheader("⚠️ Lost Valuable Customers")
            st.dataframe(client_analysis['lost_valuable'])
            
            st.markdown("""
            <div class='recommendation-box'>
                <h4>🎯 Action Items</h4>
                <ul>
                    <li>Reach out to lost valuable customers with personalized offers</li>
                    <li>Consider implementing a win-back campaign</li>
                    <li>Analyze reasons for customer churn</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            st.subheader("🆕 Recent New Customers")
            st.dataframe(client_analysis['recent_new'])
        
        with tab6:
            st.header("Summary & Export")
            st.markdown(f"""
            This analysis covers loyalty customers from {start_date} to {end_date}.
            """)
            
            st.markdown(f"""
            <div class='insight-box'>
                <h4>📌 Key Findings</h4>
                <ul>
                    <li>Customer Base: {total_customers:,} unique loyalty customers</li>
                    <li>Revenue Performance: ${total_revenue:,.2f} total revenue</li>
                    <li>Customer Retention: {rate_30:.1f}% 30-day repurchase rate</li>
                    <li>Top Customer Segment: {customer_segments['segment'].value_counts().index[0]}</li>
                    <li>Lost Valuable Customers: {len(client_analysis['lost_valuable'])}</li>
                    <li>New Customers (Last 30 Days): {len(client_analysis['recent_new'])}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            excel_report = create_excel_report(
                df_clean,
                customer_segments,
                segment_metrics,
                repurchase_data,
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