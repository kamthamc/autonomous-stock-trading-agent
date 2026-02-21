import argparse
import asyncio
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from rich.console import Console
from strategy.technical import TechAnalyzer
from strategy.ai import AIAnalyzer

console = Console()

async def run_backtest(symbol: str, days: int, initial_capital: float):
    console.print(f"[bold cyan]Starting AI Backtest for {symbol} over the last {days} trading days...[/bold cyan]")
    console.print("[yellow]WARNING: This will make 1 LLM API call per trading day. Ensure you have sufficient quota/budget.[/yellow]\n")
    
    # Fetch historical data (we need extra days for technical indicators like 200 SMA)
    end_date = datetime.now()
    start_date_fetch = end_date - timedelta(days=days + 400) # buffer for 200 SMA
    
    console.print(f"Fetching data for {symbol}...")
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date_fetch, end=end_date)
    except Exception as e:
        console.print(f"[red]Failed to fetch data: {str(e)}[/red]")
        return
        
    if df.empty:
        console.print("[red]No data found for this symbol.[/red]")
        return
        
    df.index = df.index.tz_localize(None)
    
    # The backtest period is the last `days` available rows
    backtest_period = df.tail(days)
    
    if len(backtest_period) == 0:
        console.print("[red]Not enough data for the requested backtest period.[/red]")
        return
        
    tech_analyzer = TechAnalyzer()
    ai_analyzer = AIAnalyzer()
    
    capital = initial_capital
    position = 0 # shares held
    
    trades = []
    
    for current_date, current_row in backtest_period.iterrows():
        # Slice data up to current_date
        history_slice = df.loc[:current_date].copy()
        
        # Calculate tech indicators for this slice exactly as the engine would
        tech = tech_analyzer.analyze(history_slice)
        
        if tech is None:
            continue
            
        current_price = current_row['Close']
        
        console.print(f"Processing [bold]{current_date.strftime('%Y-%m-%d')}[/bold] | Price: ${current_price:.2f}...", end=" ")
        
        # Call AI Analyzer
        # Note: Historical news and options are not natively available via free APIs, 
        # so we pass empty lists to isolate the technical and macro strategy logic.
        try:
            signal = await ai_analyzer.analyze(
                symbol=symbol,
                price=current_price,
                tech=tech.__dict__,
                news=[], 
                options=[], 
                earnings=None,
                cross_impact=None
            )
            decision = signal.decision
            confidence = signal.confidence
            alloc = getattr(signal, "allocation_pct", 0) or 0
        except Exception as e:
            console.print(f"[red]AI Error: {str(e)}[/red]")
            continue
            
        if "BUY" in decision:
            # How much to buy? Use confidence and allocation to simulate Kelly-like sizing
            invest_amount = capital * alloc * confidence
            shares_to_buy = int(invest_amount / current_price)
            if shares_to_buy > 0:
                cost = shares_to_buy * current_price
                if cost <= capital:
                    capital -= cost
                    position += shares_to_buy
                    trades.append(("BUY", current_date, current_price, shares_to_buy))
                    console.print(f"[green]BUY {shares_to_buy} @ ${current_price:.2f} (Conf: {confidence:.2f})[/green]")
                else:
                    console.print("[yellow]HOLD (Insufficient Funds)[/yellow]")
            else:
                console.print(f"[yellow]{decision} (But 0 shares allocated)[/yellow]")
                
        elif "SELL" in decision and position > 0:
            shares_to_sell = int(position * alloc)
            if shares_to_sell == 0 and alloc > 0:
                shares_to_sell = position # Sell at least 1 or all remaining if small
                
            if shares_to_sell > 0:
                revenue = shares_to_sell * current_price
                capital += revenue
                position -= shares_to_sell
                trades.append(("SELL", current_date, current_price, shares_to_sell))
                console.print(f"[red]SELL {shares_to_sell} @ ${current_price:.2f} (Conf: {confidence:.2f})[/red]")
            else:
                 console.print("[yellow]HOLD (Position too small to sell fraction)[/yellow]")
        else:
            console.print("[white]HOLD[/white]")
                
    # --- End of backtest ---
    current_price = backtest_period.iloc[-1]['Close']
    final_value = capital + (position * current_price)
    pnl = final_value - initial_capital
    pnl_pct = (pnl / initial_capital) * 100
    
    # Buy and hold return for comparison
    start_price = backtest_period.iloc[0]['Close']
    bnh_ret = ((current_price - start_price) / start_price) * 100
    
    console.print(f"\n[bold underline]Backtest Results for {symbol}[/bold underline]")
    console.print(f"Period: {backtest_period.index[0].strftime('%Y-%m-%d')} to {backtest_period.index[-1].strftime('%Y-%m-%d')} ({len(backtest_period)} trading days)")
    console.print(f"Initial Capital: ${initial_capital:,.2f}")
    console.print(f"Final Value:   ${final_value:,.2f}")
    console.print(f"Net Profit:    ${pnl:,.2f} ({pnl_pct:+.2f}%)")
    console.print(f"Buy & Hold Return: {bnh_ret:+.2f}%")
    console.print(f"Total Trades:  {len(trades)}")
    
    if len(trades) > 0:
        console.print("\n[bold]Trade Log:[/bold]")
        for action, date, price, qty in trades:
            color = "green" if action == "BUY" else "red"
            console.print(f"[{color}]{date.strftime('%Y-%m-%d')}: {action} {qty} @ ${price:.2f}[/{color}]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Strategy Backtesting Engine")
    parser.add_argument("--symbol", type=str, default="SPY", help="Ticker symbol to backtest")
    parser.add_argument("--days", type=int, default=30, help="Number of trading days to backtest (WARNING: 1 day = 1 LLM API call)")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial capital in USD/INR")
    
    args = parser.parse_args()
    asyncio.run(run_backtest(args.symbol, args.days, args.capital))
