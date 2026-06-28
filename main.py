import asyncio
import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from scraper import scrape_itemscout_rankings
from utils import save_rankings_data

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
            
        # Convert to DataFrame
        new_df = pd.DataFrame(rows)
        
        # Save rankings using utility function (handles CSV and Excel generation)
        save_rankings_data(new_df)
        print(f"[Success] Successfully processed {len(new_df)} rank records.")
        
        # Print summary of today's ranks
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_df = new_df[new_df["date"] == today_str] if "date" in new_df.columns else new_df
        print("\n--- Summary of Scraped Rankings ---")
        if not today_df.empty and "product_name" in today_df.columns:
            print(today_df[["product_name", "keyword", "rank"]].to_string(index=False))
        elif not new_df.empty and "product_name" in new_df.columns:
            print(new_df[["product_name", "keyword", "rank"]].to_string(index=False))
        else:
            print("No new data available for summary.")
        print("-----------------------------------")
        
    except Exception as e:
        print(f"[Error] Failed to complete the scraper execution: {e}")

if __name__ == "__main__":
    asyncio.run(main())
