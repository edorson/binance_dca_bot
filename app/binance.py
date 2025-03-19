# app/binance.py
import time
import hmac
import hashlib
import httpx
from urllib.parse import urlencode

class BinanceClient:
    BASE_URL = "https://api.binance.com"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def _get_headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    def _sign_params(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def get_spot_price(self, symbol: str) -> dict:
        """
        Get actual spot price for a provided symbol (for example, BTCUSDT).
        """
        url = f"{self.BASE_URL}/api/v3/ticker/price"
        params = {"symbol": symbol}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def get_account_info(self) -> dict:
        """
        Get Account information, including all assets balances.
        Requires authorization and sig.
        """
        url = f"{self.BASE_URL}/api/v3/account"
        params = {}
        signed_params = self._sign_params(params)
        headers = self._get_headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=signed_params, headers=headers)
            response.raise_for_status()
            return response.json()

    async def get_asset_balance(self, asset: str) -> float:
        """
        Get balance for a given asset (for example, USDT).
        """
        account_info = await self.get_account_info()
        for balance in account_info.get("balances", []):
            if balance["asset"] == asset:
                return float(balance["free"])
        return 0.0

    async def get_trade_history(self, symbol: str) -> dict:
        """
        Get trading history for a provided asset symbol.
        """
        url = f"{self.BASE_URL}/api/v3/myTrades"
        params = {"symbol": symbol}
        signed_params = self._sign_params(params)
        headers = self._get_headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=signed_params, headers=headers)
            response.raise_for_status()
            return response.json()

    async def create_order(self, symbol: str, side: str, quantity: float, price: float, order_type: str = "LIMIT", timeInForce: str = "GTC") -> dict:
        """
        Create a new order.
        """
        url = f"{self.BASE_URL}/api/v3/order"
        params = {
            "symbol": symbol,
            "side": side.upper(), # BUY or SELL
            "type": order_type.upper(), # LIMIT or MARKET
            "timeInForce": timeInForce, # GTC
            "quantity": '%.8f' % quantity,
            "price": price,
        }
        # print(params["quantity"])
        signed_params = self._sign_params(params)
        headers = self._get_headers()
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=signed_params, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                print("Order creation error from Binance:", exc.response.text)
                raise exc
            return response.json()

    async def cancel_order(self, symbol: str, orderId: int) -> dict:
        """
        Canced the order by its id for a provided asset symbol.
        """
        url = f"{self.BASE_URL}/api/v3/order"
        params = {"symbol": symbol, "orderId": orderId}
        signed_params = self._sign_params(params)
        headers = self._get_headers()
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, params=signed_params, headers=headers)
            response.raise_for_status()
            return response.json()

    async def get_exchange_info(self) -> dict:
        url = f"{self.BASE_URL}/api/v3/exchangeInfo"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def get_order_status(self, symbol: str, orderId: int) -> dict:
        """
        Retrieves the status of an order.
        """
        url = f"{self.BASE_URL}/api/v3/order"
        params = {"symbol": symbol, "orderId": orderId}
        signed_params = self._sign_params(params)
        headers = self._get_headers()
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=signed_params, headers=headers)
            response.raise_for_status()
            return response.json()
