from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.models import APIKeys, TradingSettings
from pydantic import ValidationError
from app.binance import BinanceClient

app = FastAPI(title="Trading Bot Setup")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def setup_form(request: Request):
    return templates.TemplateResponse("setup.html", {"request": request})

@app.post("/setup", response_class=HTMLResponse)
async def submit_setup(
    request: Request,
    api_key: str = Form(...),
    api_secret: str = Form(...),
    trading_pair: str = Form(...),
    usdt_amount: float = Form(...),
    grid_length_percent: float = Form(...),
    first_order_offset_percent: float = Form(...),
    num_grid_orders: int = Form(...),
    percent_increase: float = Form(...),
    profit_percent: float = Form(...),
):
    try:
        keys = APIKeys(api_key=api_key, api_secret=api_secret)
        settings = TradingSettings(
            trading_pair=trading_pair,
            usdt_amount=usdt_amount,
            grid_length_percent=grid_length_percent,
            first_order_offset_percent=first_order_offset_percent,
            num_grid_orders=num_grid_orders,
            percent_increase=percent_increase,
            profit_percent=profit_percent,
        )
    except ValidationError as e:
        return HTMLResponse(f"Ошибка валидации: {e}", status_code=400)

    client = BinanceClient(api_key=api_key, api_secret=api_secret)
    try:
        balance = await client.get_asset_balance("USDT")
    except Exception as ex:
        return HTMLResponse(f"Ошибка получения баланса: {ex}", status_code=500)

    if balance < usdt_amount:
        return HTMLResponse(
            f"Недостаточно средств для торговли. Ваш баланс USDT: {balance}, требуется: {usdt_amount}",
            status_code=400,
        )

    return HTMLResponse(
        f"Ваш баланс USDT: {balance}.<br>"
        # f"API ключи: {keys.json()}<br>"
        f"Настройки торговли: {settings.json()}<br>"
        f"<a href='/'>Вернуться</a>"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
