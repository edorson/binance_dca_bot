from pydantic import BaseModel, Field

class APIKeys(BaseModel):
    api_key: str = Field(..., min_length=1, title="API Key")
    api_secret: str = Field(..., min_length=1, title="API Secret")

class TradingSettings(BaseModel):
    trading_pair: str = Field(..., pattern=r"^(BTC|ETH)/USDT$", title="Trading Pair")
    usdt_amount: float = Field(..., ge=5.0, title="USDT Amount")
    grid_length_percent: float = Field(..., gt=0, lt=100, title="Grid Length (%)")
    first_order_offset_percent: float = Field(..., gt=0, lt=100, title="First Order Offset (%)")
    num_grid_orders: int = Field(..., ge=1, le=200, title="Number of Grid Orders")
    percent_increase: float = Field(..., ge=0, title="Percent Increase for Orders (%)")
    profit_percent: float = Field(..., gt=0, title="Profit Percent (%)")
