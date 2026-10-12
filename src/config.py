"""Project-wide constants. Keeping them in one place means one edit changes behaviour everywhere."""

REQUIRED_COLUMNS = [
    "Date", "Order_ID", "Customer_ID", "Region", "State",
    "Product_Category", "Product", "Quantity", "Sales", "Cost", "Discount", "Profit",
]
# Optional columns that unlock extra analysis when present
OPTIONAL_COLUMNS = ["Customer_Segment", "Sub_Category", "Payment_Method", "Sales_Channel"]

NUMERIC_COLUMNS = ["Quantity", "Sales", "Cost", "Discount", "Profit"]
TEXT_COLUMNS = ["Region", "State", "Product_Category", "Sub_Category", "Product", "Customer_Segment", "Payment_Method", "Sales_Channel"]

# Dimensions used for driver analysis (Customer_Segment is used only if it exists)
DRIVER_DIMENSIONS = ["Region", "Product_Category", "Sub_Category", "Product", "Customer_Segment",
                     "Sales_Channel", "Payment_Method"]

# Fix common region typos/abbreviations
REGION_ALIASES = {
    "n": "North", "north": "North", "s": "South", "south": "South",
    "e": "East", "east": "East", "w": "West", "west": "West",
}

# State -> Region (used to repair a missing Region)
STATE_TO_REGION = {
    "Delhi": "North", "Punjab": "North", "Haryana": "North", "Uttar Pradesh": "North",
    "Karnataka": "South", "Tamil Nadu": "South", "Kerala": "South", "Telangana": "South",
    "West Bengal": "East", "Odisha": "East", "Bihar": "East", "Assam": "East",
    "Maharashtra": "West", "Gujarat": "West", "Rajasthan": "West", "Goa": "West",
}

CURRENCIES = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
CURRENCY_SYMBOL = CURRENCIES["INR"]  # default
