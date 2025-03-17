# app/main.py
from fastapi import FastAPI, HTTPException, Query
from app.config import BINANCE_API_KEY, BINANCE_API_SECRET
from app.binance import BinanceClient

app = FastAPI(title="Binance API Integration")

binance_client = BinanceClient(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)

@app.get("/")
async def root():
    return {"message": "a FastAPI app for spot trading with Binance API"}

@app.get("/price")
async def get_price(symbol: str = Query(..., description="A trading pair, for example: BTCUSDT")):
    try:
        price_data = await binance_client.get_spot_price(symbol)
        return price_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/balance")
async def get_balance(asset: str = Query(..., description="An asset code, for example: USDT")):
    try:
        balance = await binance_client.get_asset_balance(asset)
        return {"asset": asset, "balance": balance}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/account")
async def account_info():
    try:
        account = await binance_client.get_account_info()
        return account
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trades")
async def trade_history(symbol: str = Query(..., description="A trading pair, for example: BTCUSDT")):
    try:
        trades = await binance_client.get_trade_history(symbol)
        return trades
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/order")
async def create_order(
    symbol: str = Query(..., description="Trading pair, for example: BTCUSDT"),
    side: str = Query(..., description="Order side: BUY or SELL"),
    order_type: str = Query(..., description="Order type: LIMIT or MARKET"),
    quantity: float = Query(..., description="Order quantity (volume)"),
    price: float = Query(..., description="Order Price"),
    timeInForce: str = Query("GTC", description="Time in force (usually, GTC for a LIMIT order)")
):
    try:
        order = await binance_client.create_order(symbol, side, quantity, price, order_type, timeInForce)
        return order
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/order")
async def cancel_order(
    symbol: str = Query(..., description="Trading pair, for example: BTCUSDT"),
    orderId: int = Query(..., description="Id of the order to be cancelled")
):
    try:
        result = await binance_client.cancel_order(symbol, orderId)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
