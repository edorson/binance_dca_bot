from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.models import APIKeys, TradingSettings
from pydantic import ValidationError
from app.binance import BinanceClient
from app.calc import calculate_grid_orders
from app.trading_bot import TradingBot
import asyncio

import logging

current_bot = None
bot_lock = asyncio.Lock()


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

    global current_bot
    async with bot_lock:
        if current_bot is not None:
            return HTMLResponse("<h1>Бот уже создан</h1>", status_code=400)

        current_bot = TradingBot(api_key, api_secret, trading_pair, reposition_threshold_percent)
        try:
            result = await current_bot.start_cycle(
                usdt_amount=usdt_amount,
                grid_length_percent=grid_length_percent,
                first_order_offset_percent=first_order_offset_percent,
                num_grid_orders=num_grid_orders,
                increase_percent=percent_increase,
                profit_percent=profit_percent
            )
        except Exception as e:
            current_bot = None
            return HTMLResponse(f"<h1>Ошибка запуска цикла: {e}</h1>", status_code=500)
    
    # Return immediately that the grid is placed and monitoring is running.
    orders_html = "<table border='1' cellpadding='5' cellspacing='0'><tr><th>№</th><th>Цена</th><th>Выделение USDT</th><th>Количество актива</th><th>Order ID</th><th>Статус</th></tr>"
    for order in result["placed_orders"]:
        orders_html += f"""
            <tr>
                <td>{order['order_number']}</td>
                <td>{order['price']:.2f}</td>
                <td>{order['usdt_allocation']:.7f}</td>
                <td>{order['asset_quantity']:.5f}</td>
                <td>{order.get('order_id', 'N/A')}</td>
                <td>{order.get('status', 'N/A')}</td>
            </tr>
        """
    orders_html += "</table>"
    
    return HTMLResponse(
        f"<h1>{result['message']}</h1>"
        f"<p>Рыночная цена: {result['market_price']:.2f}</p>"
        f"{orders_html}"
        f"<br><a href='/setup'>Вернуться к настройкам</a>"
    )

@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    if current_bot is None:
        return HTMLResponse("<h1>Бот не запущен</h1>")

    config = current_bot.config if current_bot.config is not None else {}
    trading_pair = current_bot.symbol

    settings_html = "<h2>Настройки бота</h2><table border='1' cellpadding='5' cellspacing='0'>"
    settings_html += "<tr><th>Параметр</th><th>Значение</th></tr>"
    settings = {
        "Торговая пара": trading_pair,
        "Сумма USDT": config.get("usdt_amount", "N/A"),
        "Длина сетки (%)": config.get("grid_length_percent", "N/A"),
        "Отступ первого ордера (%)": config.get("first_order_offset_percent", "N/A"),
        "Количество ордеров в сетке": config.get("num_grid_orders", "N/A"),
        "Процент увеличения объёма ордеров (%)": config.get("increase_percent", "N/A"),
        "Процент увеличения цены для сдвига сетки (%)": current_bot.reposition_threshold_percent,
        "Процент желаемой прибыли": config.get("profit_percent", "N/A"),
    }
    for key, value in settings.items():
        settings_html += f"<tr><td>{key}</td><td>{value}</td></tr>"
    settings_html += "</table>"

    # Get ovarall stats from the bot
    completed_cycles = current_bot.completed_cycles
    profit_usdt = current_bot.total_profit_usdt
    unsold_asset = current_bot.total_unsold_asset

    # Get current market price for the bot's symbol
    try:
        price_data = await current_bot.client.get_spot_price(current_bot.symbol)
        current_market_price = float(price_data["price"])
    except Exception as e:
        current_market_price = None

    if current_market_price is not None:
        unsold_value = unsold_asset * current_market_price
        total_value = profit_usdt + unsold_value
    else:
        unsold_value = None
        total_value = None

    # Current cycle stats
    filled_buy_orders = [order for order in current_bot.current_grid_orders if order.get("status") == "FILLED"]
    num_filled = len(filled_buy_orders)
    if num_filled > 0:
        total_cost = sum(order["price"] * order["asset_quantity"] for order in filled_buy_orders)
        total_qty = sum(order["asset_quantity"] for order in filled_buy_orders)
        avg_purchase_price = total_cost / total_qty if total_qty > 0 else 0
    else:
        avg_purchase_price = None

    fixing_order = current_bot.fixing_order

    html = "<h1>Статистика работы бота</h1>"

    html += settings_html

    html += "<h2>Статистика завершённых циклов</h2>"
    html += f"<p><strong>Завершённых циклов:</strong> {completed_cycles}</p>"
    html += f"<p><strong>Прибыль (USDT):</strong> {profit_usdt:.2f}</p>"
    if current_market_price is not None:
        html += f"<p><strong>Остаток актива (в USDT):</strong> {unsold_value:.2f}</p>"
        html += f"<p><strong>Общая сумма (USDT):</strong> {total_value:.2f}</p>"
    else:
        html += f"<p><strong>Остаток актива (в USDT):</strong> N/A (не удалось получить рыночную цену)</p>"
    
    html += "<h2>Текущее состояние открытого цикла</h2>"
    html += f"<p><strong>Исполненных ордеров на покупку:</strong> {num_filled}</p>"
    if avg_purchase_price is not None:
        html += f"<p><strong>Средняя цена покупки:</strong> {avg_purchase_price:.2f}</p>"
    else:
        html += f"<p><strong>Средняя цена покупки:</strong> N/A</p>"
    if fixing_order:
        price_val = fixing_order.get('price')
        net_qty_val = fixing_order.get('net_quantity')
        fixing_price_str = f"{price_val:.2f}" if isinstance(price_val, (int, float)) else "N/A"
        net_qty_str = f"{net_qty_val:.5f}" if isinstance(net_qty_val, (int, float)) else "N/A"
        html += f"<p><strong>Фиксирующий ордер:</strong> Цена: {fixing_price_str}, Объём: {net_qty_str}</p>"
    else:
        html += "<p><strong>Фиксирующий ордер:</strong> не выставлен</p>"
    if current_market_price is not None:
        html += f"<p><strong>Текущая рыночная цена:</strong> {current_market_price:.2f}</p>"
    else:
        html += "<p><strong>Текущая рыночная цена:</strong> N/A</p>"
    
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
