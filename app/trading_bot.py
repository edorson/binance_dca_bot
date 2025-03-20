import asyncio
import logging
import math
from app.binance import BinanceClient
from app.calc import calculate_grid_orders

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MONITOR_INTERVAL = 2

class TradingBot:
    def __init__(self, api_key: str, api_secret: str, trading_pair: str, reposition_threshold_percent: float):
        self.client = BinanceClient(api_key, api_secret)
        self.symbol = trading_pair.replace("/", "")  # e.g. "BTC/USDT" -> "BTCUSDT"
        self.reposition_threshold_percent = reposition_threshold_percent
        self.current_grid_orders = []
        self.fixing_order = None
        self.cycle_started = False
        self.monitor_task = None
        self.config = None
        self.initial_market_price = None
        self.completed_cycles = 0
        self.total_profit_usdt = 0.0
        self.total_unsold_asset = 0.0

    async def start_cycle(
        self,
        usdt_amount: float,
        grid_length_percent: float,
        first_order_offset_percent: float,
        num_grid_orders: int,
        increase_percent: float,
        profit_percent: float
    ) -> dict:
        self.config = {
            "usdt_amount": usdt_amount,
            "grid_length_percent": grid_length_percent,
            "first_order_offset_percent": first_order_offset_percent,
            "num_grid_orders": num_grid_orders,
            "increase_percent": increase_percent,
            "profit_percent": profit_percent
        }
        price_data = await self.client.get_spot_price(self.symbol)
        self.initial_market_price = float(price_data["price"])
        
        asset = self.symbol.replace("USDT", "")
        grid_orders = calculate_grid_orders(
            market_price=self.initial_market_price,
            offset_percent=first_order_offset_percent,
            grid_length_percent=grid_length_percent,
            num_orders=num_grid_orders,
            total_usdt=usdt_amount,
            increase_percent=increase_percent,
            asset=asset
        )
        
        self.current_grid_orders = []
        for order in grid_orders:
            volume = order["asset_quantity"] * order["price"]
            if volume < 5:
                raise ValueError(f"Объём каждого ордера должен быть не менее 5 USDT, вычисленный объём: {volume:.7f} USDT")

            res = await self.client.create_order(
                symbol=self.symbol,
                side="BUY",
                order_type="LIMIT",
                quantity=order["asset_quantity"],
                price=order["price"],
                timeInForce="GTC"
            )
            order["order_id"] = res.get("orderId")
            order["status"] = res.get("status")
            self.current_grid_orders.append(order)
        
        # Start asynchronous monitoring task if not already running
        if self.monitor_task is None or self.monitor_task.done():
            self.monitor_task = asyncio.create_task(self.monitor_cycle())
        
        return {
            "message": "Сетка ордеров установлена, бот запущен",
            "market_price": self.initial_market_price,
            "placed_orders": self.current_grid_orders
        }

    async def monitor_cycle(self):
        while True:
            # Phase 1: Wait for cycle to start
            while not self.cycle_started:
                for order in self.current_grid_orders:
                    try:
                        status = await self.client.get_order_status(self.symbol, order["order_id"])
                        if status.get("status") == "FILLED":
                            order["status"] = "FILLED"
                            self.cycle_started = True
                            logger.info(f"Cycle started: Order {order['order_id']} filled.")
                            # Create fixing order immediately after first fill.
                            await self.create_fixing_order(self.config["profit_percent"])
                            break
                    except Exception as e:
                        logger.error(f"Error checking status for order {order['order_id']}: {e}")
                if not self.cycle_started:
                    try:
                        price_data = await self.client.get_spot_price(self.symbol)
                        current_price = float(price_data["price"])
                        # Trigger price is based on the initial market price
                        trigger_price = self.initial_market_price * (1 + self.reposition_threshold_percent / 100)
                        if current_price >= trigger_price:
                            logger.info(f"Repositioning grid: Current price {current_price} >= trigger price {trigger_price}.")
                            await self.cancel_all_orders()
                            await self._recreate_grid()
                            price_data = await self.client.get_spot_price(self.symbol)
                            self.initial_market_price = float(price_data["price"])
                    except Exception as e:
                        logger.error(f"Error during reposition check: {e}")
                await asyncio.sleep(MONITOR_INTERVAL)
            
            # Phase 2: Cycle started – monitor the fixing order and additional fills.
            while self.cycle_started:
                # Check fixing order status
                if self.fixing_order is not None:
                    try:
                        status = await self.client.get_order_status(self.symbol, self.fixing_order["order_id"])
                        if status.get("status") == "FILLED":
                            # weighted_avg = self.fixing_order.get("weighted_avg_price", 0)
                            # profit_usdt = (self.fixing_order["price"] - weighted_avg) * self.fixing_order["net_quantity"]
                            fixing_order_income = await self.get_fixing_order_income()
                            profit_usdt = fixing_order_income - self.fixing_order.get("total_sold_cost", 0)
                            self.total_profit_usdt += profit_usdt
                            self.total_unsold_asset += self.fixing_order["unsold_asset"]
                            self.completed_cycles += 1
                            logger.info(f"Fixing order {self.fixing_order['order_id']} filled. Cycle completed. Profit: {profit_usdt} USDT.")
                            await self.cancel_all_orders()
                            self.cycle_started = False
                            break
                    except Exception as e:
                        logger.error(f"Error checking fixing order status: {e}")
                
                # Check for additional buy order fills and update fixing order if needed.
                additional_fill = False
                for order in self.current_grid_orders:
                    try:
                        status = await self.client.get_order_status(self.symbol, order["order_id"])
                        if status.get("status") == "FILLED" and order.get("status") != "FILLED":
                            order["status"] = "FILLED"
                            additional_fill = True
                    except Exception as e:
                        logger.error(f"Error checking status for order {order['order_id']}: {e}")
                if additional_fill:
                    logger.info("Additional buy orders filled. Updating fixing order.")
                    await self.update_fixing_order(self.config["profit_percent"])
                
                await asyncio.sleep(MONITOR_INTERVAL)
            
            # Cycle completed – automatically start a new cycle using stored configuration.
            logger.info("Cycle completed. Starting new cycle automatically.")
            await self.start_cycle(
                usdt_amount=self.config["usdt_amount"],
                grid_length_percent=self.config["grid_length_percent"],
                first_order_offset_percent=self.config["first_order_offset_percent"],
                num_grid_orders=self.config["num_grid_orders"],
                increase_percent=self.config["increase_percent"],
                profit_percent=self.config["profit_percent"]
            )

    async def create_fixing_order(self, profit_percent: float) -> dict:
        asset = self.symbol.replace("USDT", "")  # e.g. "BTC" or "ETH"
        # Get orderIds for filled buy orders from the grid
        filled_order_ids = {order["order_id"] for order in self.current_grid_orders if order.get("status") == "FILLED"}
        if not filled_order_ids:
            logger.info("No executed buy orders, fixing order not created.")
            return {}

        # Get trade history from Binance
        trades = await self.client.get_trade_history(self.symbol)
        
        # Get all orderIds that the bot has placed
        bot_order_ids = {order["order_id"] for order in self.current_grid_orders}
        # Determine filled orderIds by filtering trades:
        filled_order_ids = {int(trade["orderId"]) for trade in trades if trade.get("isBuyer") and int(trade["orderId"]) in bot_order_ids}
        
        # Filter trades: only those from our bot's orders (by orderId) and on the buy side.
        relevant_trades = [
            trade for trade in trades
            if trade.get("isBuyer") and trade.get("orderId") in filled_order_ids
        ]
        
        if not relevant_trades:
            logger.info("No relevant trades found for filled orders, fixing order not created.")
            return {}
        
        # Aggregate total quantity and total cost, and sum commission where commissionAsset equals the asset.
        total_qty = sum(float(trade["qty"]) for trade in relevant_trades)
        total_cost = sum(float(trade["qty"]) * float(trade["price"]) for trade in relevant_trades)
        total_commission = sum(float(trade["commission"]) for trade in relevant_trades if trade.get("commissionAsset") == asset)
        
        net_qty_bought = total_qty - total_commission
        if net_qty_bought <= 0:
            logger.error("Net quantity after commission is non-positive. Cannot create fixing order.")
            return {}
        
        weighted_avg_price = total_cost / total_qty  # weighted average purchase price
        sell_price = round(weighted_avg_price * (1 + profit_percent / 100), 2)
        
        # Determine rounding precision based on asset type
        precision = 8  # default
        if asset.upper() == "BTC":
            precision = 5  # 0.00001
        elif asset.upper() == "ETH":
            precision = 4  # 0.0001
        
        factor = 10 ** precision
        net_qty = math.floor(net_qty_bought * factor) / factor  # round down
        
        res = await self.client.create_order(
            symbol=self.symbol,
            side="SELL",
            order_type="LIMIT",
            quantity=net_qty,
            price=sell_price,
            timeInForce="GTC"
        )
        self.fixing_order = {
            "order_id": res.get("orderId"),
            "price": sell_price,
            "net_quantity": net_qty,
            "unsold_asset":  net_qty_bought - net_qty,
            "status": res.get("status"),
            "weighted_avg_price": weighted_avg_price,
            "total_sold_cost": total_cost,
        }
        logger.info(f"Created fixing order at price {sell_price} for quantity {net_qty_bought}")
        return res

    async def get_fixing_order_income(self) -> float:
        trades = await self.client.get_trade_history(self.symbol)
        self.fixing_order["comission"] = 0.0
        self.fixing_order["quoteQty"] = 0.0
        for trade in trades:
            if trade.get("orderId") == self.fixing_order["order_id"] and trade.get("commissionAsset") == "USDT":
                self.fixing_order["comission"] += float(trade.get("commission", 0))
                self.fixing_order["quoteQty"] += float(trade.get("quoteQty", 0))
        return self.fixing_order["quoteQty"] - self.fixing_order["comission"]

    async def update_fixing_order(self, profit_percent: float) -> dict:
        """
        Cancels the current fixing order and creates a new one based on updated executed buy orders.
        """
        if self.fixing_order is not None:
            try:
                await self.client.cancel_order(self.symbol, self.fixing_order["order_id"])
                logger.info(f"Cancelled fixing order {self.fixing_order['order_id']}")
            except Exception as e:
                logger.error(f"Error cancelling fixing order: {e}")
        # Create new fixing order with updated parameters
        return await self.create_fixing_order(profit_percent)

    async def _recreate_grid(self):
        await self.cancel_all_orders()
        price_data = await self.client.get_spot_price(self.symbol)
        self.initial_market_price = float(price_data["price"])
        logger.info(f"Recreating grid using new market price: {self.initial_market_price}")
        
        asset = self.symbol.replace("USDT", "")
        grid_orders = calculate_grid_orders(
            market_price=self.initial_market_price,
            offset_percent=self.config["first_order_offset_percent"],
            grid_length_percent=self.config["grid_length_percent"],
            num_orders=self.config["num_grid_orders"],
            total_usdt=self.config["usdt_amount"],
            increase_percent=self.config["increase_percent"],
            asset=asset
        )
        
        self.current_grid_orders = []
        for order in grid_orders:
            res = await self.client.create_order(
                symbol=self.symbol,
                side="BUY",
                order_type="LIMIT",
                quantity=order["asset_quantity"],
                price=order["price"],
                timeInForce="GTC"
            )
            order["order_id"] = res.get("orderId")
            order["status"] = res.get("status")
            self.current_grid_orders.append(order)
        logger.info("New grid orders placed.")
        # Reset fixing order
        self.fixing_order = None

    async def cancel_all_orders(self):
        """Cancels all currently placed buy orders and the fixing order if it exists."""
        for order in self.current_grid_orders:
            order_id = order.get("order_id")
            try:
                await self.client.cancel_order(self.symbol, order_id)
                logger.info(f"Cancelled buy order {order_id}")
            except Exception as e:
                logger.error(f"Error cancelling buy order {order_id}: {e}")
        self.current_grid_orders = []
        if self.fixing_order:
            try:
                await self.client.cancel_order(self.symbol, self.fixing_order["order_id"])
                logger.info(f"Cancelled fixing order {self.fixing_order['order_id']}")
            except Exception as e:
                logger.error(f"Error cancelling fixing order: {e}")
            self.fixing_order = None
