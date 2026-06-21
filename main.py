import asyncio
import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from scraper import scrape_itemscout_rankings

async def main():
    # Load environment variables
    load_dotenv()
    username = os.getenv("ITEMSCOUT_USERNAME")
    password = os.getenv("ITEMSCOUT_PASSWORD")
    
    if not username or not password:
        print("[Error] ITEMSCOUT_USERNAME or ITEMSCOUT_PASSWORD is not set in .env file.")
        print("Please check your .env file in the project directory.")
        return
        
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting ItemScout Daily Rank Scraper...")
    
    try:
        # Run scraper
        rows = await scrape_itemscout_rankings(username, password)
        
        if not rows:
            print("[Warning] No data was scraped from ItemScout. Check if any items are registered.")
            return
            
        # Get current date
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Convert to DataFrame
        new_df = pd.DataFrame(rows)
        new_df["product_id"] = new_df["product_id"].astype(str)
        new_df.insert(0, "date", today_str)
        
        # Output directory and file path
        output_dir = "data"
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, "rankings.csv")
        
        # Append logic with duplicate prevention
        if os.path.exists(csv_path):
            print(f"[Info] Found existing file: {csv_path}. Appending new data...")
            existing_df = pd.read_csv(csv_path, dtype={"product_id": str})
            
            # Combine existing and new data
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Drop duplicates (if run multiple times on the same date, keep the latest run)
            # Duplicate definition: same date, same product_id, same keyword
            combined_df.drop_duplicates(subset=["date", "product_id", "keyword"], keep="last", inplace=True)
        else:
            print(f"[Info] Creating new file: {csv_path}...")
            combined_df = new_df
            
        # Sort by date and product name for readability
        combined_df.sort_values(by=["date", "product_name", "keyword"], ascending=[True, True, True], inplace=True)
        
        # Save to CSV
        combined_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"[Success] Successfully saved {len(new_df)} rows to {csv_path}.")
        
        # Print summary
        print("\n--- Summary of Scraped Rankings ---")
        print(new_df[["product_name", "keyword", "rank"]].to_string(index=False))
        print("-----------------------------------")
        
    except Exception as e:
        print(f"[Error] Failed to complete the scraper execution: {e}")

if __name__ == "__main__":
    asyncio.run(main())
