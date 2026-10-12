# Power BI Dashboard Guide

Power BI complements the Python app: Python generates *AI insights*, Power BI gives managers an *interactive, self-service dashboard* on the **same cleaned data**.

> A `.pbix` file cannot be generated from code, so this folder contains everything you need to build it in ~45 minutes:
> the data file, the data model, copy-paste DAX (`dax_measures.dax`), the page layout and a validation checklist.

## 1. Get the data
Run once: `python scripts/run_pipeline.py` -> creates **`data/sales_data_clean.csv`** (cleaned by the same Python pipeline, so Python and Power BI show identical numbers).

## 2. Load and shape data (Power Query)
`Home > Get data > Text/CSV > sales_data_clean.csv > Transform Data`

1. Set types: `Date` = Date, `Sales/Cost/Profit` = Fixed decimal number, `Discount` = Decimal number, `Quantity` = Whole number, text columns = Text.
2. Rename the query to **Sales**.
3. Build dimension tables (right-click query > *Reference*, keep the listed columns, *Remove Duplicates*):

| New query | Columns kept | Key |
|---|---|---|
| **DimProduct** | Product, Product_Category | Product |
| **DimGeography** | State, Region | State |
| **DimCustomer** | Customer_ID, Customer_Segment | Customer_ID |

Optional: if your file has `Sales_Channel` or `Payment_Method`, keep them in **Sales** and add them as extra slicers or as small dimension tables in the same way.

4. In **Sales**, remove `Product_Category`, `Region`, `Customer_Segment`, `Cost_Imputed` (they now live in the dimensions). Keep `Is_Outlier` if you want to filter outliers.
5. `Close & Apply`.

## 3. Data model (star schema)

```
DimDate ──┐                    ┌── DimProduct   (Product)
          ├── 1 : *  [ Sales ] *: 1 ──┤
DimGeography (State) ─ 1 : *   └── DimCustomer  (Customer_ID)
```

* Create **DimDate** with the DAX in `dax_measures.dax`, then *Mark as date table*.
* Relationships (all **one-to-many, single direction**, dimension -> fact):
  `DimDate[Date] -> Sales[Date]`, `DimProduct[Product] -> Sales[Product]`, `DimGeography[State] -> Sales[State]`, `DimCustomer[Customer_ID] -> Sales[Customer_ID]`.

**Why a star schema?** Slicers filter small dimension tables, which filter the big fact table: fast, unambiguous, and the standard answer in interviews. Time-intelligence functions (`DATEADD`, `SAMEPERIODLASTYEAR`) *require* a proper date table.

## 4. Measures
Create a blank table `_Measures` and paste every measure from [`dax_measures.dax`](dax_measures.dax).

## 5. Report layout (one page, 16:9)

```
┌────────────────────────────────────────────────────────────────────────┐
│ AI Business Insight Generator - Sales Dashboard      [Date slicer]     │
├──────────┬──────────┬────────┬──────────┬───────────┬─────────────────┤
│ Revenue  │ Profit   │ Orders │ Customers│ Margin %  │ Revenue Growth %│  <- 6 KPI cards
├──────────┴──────────┴────────┴──────────┴───────────┴─────────────────┤
│ Monthly Revenue Trend (column+line: Profit)  │ Monthly Profit Trend    │
├──────────────────────────────────────────────┼─────────────────────────┤
│ Revenue by Region (bar)  │ Profit by Region  │ Sales by Category (donut)│
├──────────────────────────┴───────────────────┴─────────────────────────┤
│ Sales by Product (bar)  │ Top 10 Products │ Bottom 10 Products         │
└────────────────────────────────────────────────────────────────────────┘
Slicers: Date (between), Region, Product_Category, Product
```

| Visual | Fields |
|---|---|
| KPI cards | `Total Revenue`, `Total Profit`, `Total Orders`, `Total Customers`, `Profit Margin %`, `Revenue Growth %` |
| Monthly Revenue Trend | X: `DimDate[Year-Month]`, Y: `Total Revenue`, line: `Total Profit` |
| Monthly Profit Trend | X: `DimDate[Year-Month]`, Y: `Total Profit` (+ `Profit Margin %` as line) |
| Revenue / Profit by Region | Axis: `DimGeography[Region]`, Values: `Total Revenue` / `Total Profit` |
| Sales by Product / Category | Axis: `DimProduct[Product]` / `[Product_Category]`, Values: `Total Revenue` |
| Top 10 / Bottom 10 Products | Axis: `DimProduct[Product]`, Value: `Total Revenue`; Filters pane > *Top N* = 10 by `Total Revenue` (Top) / *Bottom N* (Bottom). The sample data has only 11 products, so with your own data these become more meaningful. |

Tips: sort the month axis ascending by `Year-Month`; format the cards with Indian currency (`[$₹-4009] #,##0`); use conditional formatting (green/red) for growth cards.

## 6. Validate against Python (do this - interviewers love it)
With **no slicers selected**, the cards must match `calculate_kpis()` on the sample dataset (seed 42):

| Measure | Expected |
|---|---|
| Total Revenue | ₹23,30,49,482 (233,049,482.27) |
| Total Profit | ₹4,59,36,558 |
| Total Orders | 11,785 |
| Total Customers | 1,500 |
| Profit Margin % | 19.7% |
| Revenue Growth % (latest month) | +6.7% (₹1,03,95,191 vs ₹97,38,780) |

If a number differs, the cause is almost always a missing relationship, a wrong data type, or a slicer left on.

## 7. Publish / present
Take screenshots into `docs/screenshots/` for the README. For the interview demo, open the `.pbix` and click through slicers to show interactivity; keep the Streamlit app for the "AI insights" part.
