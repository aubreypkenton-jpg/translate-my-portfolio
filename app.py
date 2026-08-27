from datetime import datetime

from flask import Flask, render_template, request

from compute import compute_portfolio
from data_fetch import fetch_holdings_data
from explain import build_explanations

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", result=None, explanations=None, error=None, failed=[])


@app.route("/analyze", methods=["POST"])
def analyze():
    tickers = request.form.getlist("ticker")
    shares = request.form.getlist("shares")
    purchase_prices = request.form.getlist("purchase_price")
    purchase_dates = request.form.getlist("purchase_date")

    holdings = []
    for t, sh, pp, pd_ in zip(tickers, shares, purchase_prices, purchase_dates):
        if not t.strip() or not sh.strip():
            continue
        holdings.append({
            "ticker": t.strip(),
            "shares": sh.strip(),
            "purchase_price": pp.strip() or None,
            "purchase_date": pd_.strip() or None,
        })

    if not holdings:
        return render_template("index.html", result=None, explanations=None,
                                error="Add at least one holding (ticker + shares).", failed=[])

    unique_tickers = sorted({h["ticker"].upper() for h in holdings})
    current_prices, sectors, price_histories, failed = fetch_holdings_data(unique_tickers)

    usable_holdings = [h for h in holdings if h["ticker"].upper() in current_prices]

    if not usable_holdings:
        return render_template("index.html", result=None, explanations=None,
                                error="Couldn't fetch data for any of those tickers. Double-check the symbols.",
                                failed=failed)

    result = compute_portfolio(usable_holdings, current_prices, sectors, price_histories,
                                today=datetime.utcnow())
    explanations = build_explanations(result)

    return render_template("index.html", result=result, explanations=explanations,
                            error=None, failed=failed,
                            submitted_holdings=holdings)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
