from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.models import APIKeys, TradingSettings
from pydantic import ValidationError
from app.binance import BinanceClient
from app.calc import calculate_grid_orders
from app.trading_bot import TradingBot

import logging

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

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
    reposition_threshold_percent: float = Form(...),
    profit_percent: float = Form(...),
):
    # Create an instance of TradingBot; all grid calculation and monitoring are encapsulated in it.
    bot = TradingBot(api_key, api_secret, trading_pair, reposition_threshold_percent)
    
    try:
        result = await bot.start_cycle(
            usdt_amount=usdt_amount,
            grid_length_percent=grid_length_percent,
            first_order_offset_percent=first_order_offset_percent,
            num_grid_orders=num_grid_orders,
            increase_percent=percent_increase,
            profit_percent=profit_percent
        )
    except Exception as e:
        return HTMLResponse(f"<h1>Ошибка запуска цикла: {e}</h1>", status_code=500)
    
    # Return immediately that the grid is placed and monitoring is running.
    orders_html = "<table border='1' cellpadding='5' cellspacing='0'><tr><th>№</th><th>Цена</th><th>Выделение USDT</th><th>Количество актива</th><th>Order ID</th><th>Статус</th></tr>"
    for order in result["placed_orders"]:
        orders_html += f"""
            <tr>
                <td>{order['order_number']}</td>
                <td>{order['price']}</td>
                <td>{order['usdt_allocation']}</td>
                <td>{order['asset_quantity']}</td>
                <td>{order.get('order_id', 'N/A')}</td>
                <td>{order.get('status', 'N/A')}</td>
            </tr>
        """
    orders_html += "</table>"
    
    return HTMLResponse(
        f"<h1>{result['message']}</h1>"
        f"<p>Рыночная цена: {result['market_price']}</p>"
        f"{orders_html}"
        f"<br><a href='/setup'>Вернуться к настройкам</a>"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
