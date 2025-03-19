import math

def calculate_grid_orders(
    market_price: float,
    offset_percent: float,
    grid_length_percent: float,
    num_orders: int,
    total_usdt: float,
    increase_percent: float,
    asset: str  # "BTC" or "ETH"
):
    orders = []
    # Calculate first order price using offset
    first_price = market_price * (1 - offset_percent / 100)
    # Calculate lower bound for the grid relative to the first order price
    lower_price = first_price * (1 - grid_length_percent / 100)
    
    # Calculate prices evenly distributed between first_price and lower_price
    if num_orders == 1:
        prices = [first_price]
    else:
        step = (first_price - lower_price) / (num_orders - 1)
        prices = [first_price - i * step for i in range(num_orders)]
    
    # Round prices to 2 decimal places (tick size 0.01)
    prices = [round(p, 2) for p in prices]
    
    # Calculate USDT allocations using geometric progression (without rounding to 2 decimals)
    r = 1 + increase_percent / 100
    if r == 1:
        allocations = [total_usdt / num_orders] * num_orders
    else:
        # Solve for X: total_usdt = X * (r^num_orders - 1)/(r - 1)
        X = total_usdt * (r - 1) / (r ** num_orders - 1)
        allocations = [X * (r ** i) for i in range(num_orders)]
    
    # Do not round allocations here to preserve precision
    # Determine minimal step for asset quantity based on asset type
    asset = asset.upper()
    if asset == "BTC":
        min_step = 0.00001  # BTC minimal lot
        precision = 5
    elif asset == "ETH":
        min_step = 0.0001   # ETH minimal lot
        precision = 4
    else:
        min_step = 0.000001
        precision = 8
    
    computed_orders = []
    # Calculate asset quantity for each order using floor rounding to min_step
    for i in range(num_orders):
        alloc = allocations[i]
        price = prices[i]
        raw_qty = alloc / price
        qty = round(raw_qty / min_step) * min_step
        effective_usdt = qty * price
        computed_orders.append({
            "order_number": i + 1,
            "price": price,
            "initial_allocation": alloc,  # unrounded allocation for debugging if needed
            "usdt_allocation": effective_usdt,
            "asset_quantity": qty
        })

    # Calculate total effective USDT usage
    total_effective = round(sum(order["usdt_allocation"] for order in computed_orders), 2)

    # If total effective usage exceeds total_usdt, adjust the last order by reducing its asset quantity
    while total_effective > total_usdt and computed_orders[-1]["asset_quantity"] >= min_step:
        print(total_effective)
        last_order = computed_orders[-1]
        # Reduce asset_quantity by min_step
        last_order["asset_quantity"] = round(last_order["asset_quantity"] - min_step, precision)
        # Recalculate effective USDT usage for last order
        last_order["usdt_allocation"] = round(last_order["asset_quantity"] * last_order["price"], 2)
        computed_orders[-1] = last_order
        total_effective = round(sum(order["usdt_allocation"] for order in computed_orders), 2)

    return computed_orders

# Example usage:
if __name__ == "__main__":
    market_price = 83206.0
    offset_percent = 1.0
    grid_length_percent = 10.0
    num_orders = 3
    total_usdt = 19.99
    increase_percent = 10.0
    asset = "BTC"

    orders = calculate_grid_orders(
        market_price,
        offset_percent,
        grid_length_percent,
        num_orders,
        total_usdt,
        increase_percent,
        asset
    )
    for order in orders:
        print(order)
