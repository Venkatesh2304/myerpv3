import os
import pickle
import datetime
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from custom.classes import Billing
from core.models import Company

class Command(BaseCommand):
    help = 'Analyze stock sales and values over a period'

    def add_arguments(self, parser):
        parser.add_argument('--company', type=str, default='lakme_urban', help='Company name')
        parser.add_argument('--start', type=str, default='2026-01-01', help='Start date (YYYY-MM-DD)')
        parser.add_argument('--end', type=str, default='2026-01-31', help='End date (YYYY-MM-DD)')
        parser.add_argument('--parallel', type=int, default=5, help='Number of parallel downloads')
        parser.add_argument('--godown', type=str, default='MAIN GODOWN', help='Godown name or ALL')

    def handle(self, *args, **options):
        company_name = options['company']
        start_date = datetime.datetime.strptime(options['start'], '%Y-%m-%d').date()
        end_date = datetime.datetime.strptime(options['end'], '%Y-%m-%d').date()
        parallel_workers = options['parallel']
        godown_filter = options['godown']

        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Company {company_name} not found"))
            return

        # Setup temp cache folder
        cache_dir = os.path.join('.temp', 'stock_analysis', company_name)
        os.makedirs(cache_dir, exist_ok=True)

        billing = Billing(company_name)
        
        dates = []
        curr = start_date
        while curr <= end_date:
            dates.append(curr)
            curr += datetime.timedelta(days=1)

        self.stdout.write(f"Analyzing period: {start_date} to {end_date} ({len(dates)} days)")
        self.stdout.write(f"Godown Filter: {godown_filter}")
        self.stdout.write(f"Using parallel workers: {parallel_workers}")

        stock_data_by_date = {}

        def fetch_date_stock(date):
            cache_path = os.path.join(cache_dir, f"{date.isoformat()}.pkl")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, 'rb') as f:
                        df = pickle.load(f)
                        return date, df
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Cache corrupted for {date}: {e}. Redownloading..."))
            
            self.stdout.write(f"Fetching data for {date}...")
            try:
                # current_stock(date) returns a DataFrame
                df = billing.current_stock(date)
                with open(cache_path, 'wb') as f:
                    pickle.dump(df, f)
                return date, df
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed for {date}: {e}"))
                return date, None

        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            future_to_date = {executor.submit(fetch_date_stock, d): d for d in dates}
            for future in as_completed(future_to_date):
                date, df = future.result()
                if df is not None:
                    stock_data_by_date[date] = df

        if not stock_data_by_date:
            self.stdout.write(self.style.ERROR("No data could be retrieved. Check your connection or company name."))
            return

        self.stdout.write(self.style.SUCCESS(f"Successfully retrieved data for {len(stock_data_by_date)} days."))

        # Mappings from StockReport/test results
        column_mapping = {
            "SKU7": "stock_id",
            "Product Name": "name",
            "Units": "qty",
            "Cur.Stk Value": "value",
            "Location": "godown"
        }

        all_dfs = []
        for date, df in stock_data_by_date.items():
            # Apply mapping
            df_mapped = df.rename(columns=column_mapping)
            
            # Apply Godown Filter
            if godown_filter.upper() != "ALL" and "godown" in df_mapped.columns:
                df_mapped = df_mapped[df_mapped["godown"].astype(str).str.upper() == godown_filter.upper()]
            
            # Ensure necessary columns exist
            cols_to_keep = ["stock_id", "name", "qty", "value"]
            available_cols = [c for c in cols_to_keep if c in df_mapped.columns]
            
            df_cleaned = df_mapped[available_cols].copy()
            
            # Clean numeric columns
            for col in ["qty", "value"]:
                if col in df_cleaned.columns:
                    df_cleaned[col] = pd.to_numeric(df_cleaned[col], errors='coerce').fillna(0)
            
            # Group by stock_id because multiple rows (batches/locations) can exist for same ID
            df_grouped = df_cleaned.groupby("stock_id").agg({
                "name": "first",
                "qty": "sum",
                "value": "sum"
            }).reset_index()
            
            df_grouped['date'] = date
            all_dfs.append(df_grouped)

        if not all_dfs:
            self.stdout.write(self.style.ERROR("No data left after filtering and grouping. Exiting."))
            return

        master_df = pd.concat(all_dfs, ignore_index=True)

        # Average value per stock_id over all days in the requested period
        self.stdout.write("Calculating averages and sorting...")
        analysis_agg = master_df.groupby('stock_id').agg({
            'value': 'sum',
            'name': 'first'
        })
        analysis_agg['avg_value'] = analysis_agg['value'] / len(dates)
        analysis_agg = analysis_agg.sort_values('avg_value', ascending=False)

        total_stocks = len(analysis_agg)
        self.stdout.write(f"Found {total_stocks} unique products.")

        for idx, (stock_id, row) in enumerate(analysis_agg.iterrows(), 1):
            product_name = row['name']
            avg_value = row['avg_value']
            
            stock_timeline_raw = master_df[master_df['stock_id'] == stock_id]
            
            full_date_df = pd.DataFrame({'date': dates})
            stock_timeline = pd.merge(full_date_df, stock_timeline_raw, on='date', how='left')
            
            stock_timeline['qty'] = stock_timeline['qty'].fillna(0)
            stock_timeline['value'] = stock_timeline['value'].fillna(0)
            stock_timeline['name'] = product_name
            stock_timeline['stock_id'] = stock_id
            
            stock_timeline = stock_timeline.sort_values('date')
            
            qtys = stock_timeline['qty'].values

            self.stdout.write("\n" + "="*70)
            self.stdout.write(self.style.MIGRATE_HEADING(f"[{idx}/{total_stocks}] PRODUCT: {product_name} ({stock_id})"))
            self.stdout.write(f"Average Value (Closing across {len(dates)} days): ₹{avg_value:,.2f}")
            
            # Statistics
            stats_data = qtys.astype(float)
            self.stdout.write("\n--- Statistics (Quantity) ---")
            self.stdout.write(f"Mean: {np.mean(stats_data):.2f}")
            self.stdout.write(f"Std Dev: {np.std(stats_data):.2f}")
            self.stdout.write(f"90th Percentile: {np.percentile(stats_data, 90):.2f}")
            self.stdout.write(f"Min: {np.min(stats_data):.2f} | Max: {np.max(stats_data):.2f}")

            # ASCII Chart
            self.stdout.write("\n--- Stock Level Trend (Quantity) ---")
            self.print_chart(stock_timeline)

            # Interactive Prompt
            prompt = input(f"\nProceed to next stock? (Enter for next, 'q' to quit, 'd' for data points): ").strip().lower()
            
            if prompt == 'q':
                self.stdout.write("Exiting analysis.")
                break
            elif prompt == 'd':
                self.stdout.write("\nDate       | Qty   | Value")
                self.stdout.write("-" * 25)
                for _, r in stock_timeline.iterrows():
                    self.stdout.write(f"{r['date']} | {int(r['qty']):<5} | ₹{r['value']:,.0f}")
                input("\nPress Enter to continue to next stock...")

    def print_chart(self, df, height=12, width=80):
        if df.empty:
            return
        
        qtys = df['qty'].values
        dates = df['date'].tolist()
        
        q_min = min(qtys)
        q_max = max(qtys)
        
        if q_max == q_min:
            q_max = q_min + 1
            
        scaled = [int((q - q_min) / (q_max - q_min) * (height - 1)) for q in qtys]
        
        for h in range(height - 1, -1, -1):
            line = "  "
            if h == height - 1:
                line = f"{int(q_max):>4} ┤"
            elif h == 0:
                line = f"{int(q_min):>4} ┤"
            else:
                line = "     │"
            
            for s in scaled:
                if s >= h:
                    line += "█"
                else:
                    line += " "
            self.stdout.write(line)
        
        self.stdout.write("     └" + "─" * len(dates))
        
        start_label = dates[0].strftime("%d/%m")
        end_label = dates[-1].strftime("%d/%m")
        
        needed_space = len(start_label) + len(end_label)
        if len(dates) > needed_space:
            padding = " " * (len(dates) - needed_space)
            self.stdout.write("      " + start_label + padding + end_label)
        else:
            self.stdout.write("      " + start_label + " (to) " + end_label)
