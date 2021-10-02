import os
import re
from cs50 import SQL
from datetime import datetime, timedelta
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    # Get the details for the stock owned by a particular person:
    rows = db.execute("SELECT * FROM purchases WHERE id=:id", id=session["user_id"])
    cash_left = db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id'])
    # Check if the user actusally bought anything:
    if len(rows) == 0:
        # Nothing brought, thus:
        return render_template("index.html", purchased=False, grand_total=cash_left[0]['cash'], cash_left=cash_left[0]['cash'], rows=rows)

    else:
        # The cash left is automatically updated inside of the user's user table!
        total_shares = db.execute("SELECT SUM(total) FROM purchases WHERE id=:id", id=session["user_id"])

        cash_left = cash_left[0]['cash']
        total_shares = total_shares[0]['SUM(total)']
        # The following returns a list of dict of key value pairs:
        return render_template("index.html", purchased=True,rows=rows, cash_left=cash_left, grand_total=total_shares+cash_left)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    # Check if request is made via GET or via POST:
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        # Check if the stock actually exists:
        if not stock:
            return apology("The stock for your symbol doesn't exist", 358)

        # Total cost of the Stock:
        price = float(stock["price"]) * int(request.form.get("shares"))

        # We access the user's information using his id which was stored inside of session["user_id"] when user had logged in
        cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = cash[0]['cash']
        cash_left = cash - price

        if cash_left < 0:
            return apology("Not enough cash", 420)

        else:
            # The time of purchase:
            time = datetime.now() + timedelta(hours=5.5)
            time = time.strftime("%d/%m/%Y %H:%M:%S")

            # Not the first purchase:
            # The purchase number:
            purchases = db.execute("SELECT * FROM purchases WHERE id=:id", id=session["user_id"])

            # Check if the stock is already bought once, if yes, update the shares to how many were bought:
            bought = db.execute("SELECT * FROM purchases WHERE symbol=:symbol AND id=:id", symbol=stock["symbol"], id=session["user_id"])

            if len(bought) == 0:
                # This stock wasn't bought yet:

                db.execute("INSERT INTO purchases (id, purchase_id, symbol, name, price, shares, total) VALUES (:id, :purchase_id, :symbol, :name, :price, :shares, :total)",
                            id=session["user_id"], purchase_id=len(purchases) + 1, shares=request.form.get("shares"), price=stock["price"], symbol=stock["symbol"],
                            name=stock["name"], total=price)

            else:
                # The stock was bought already, so we update the number of shares:
                og = db.execute("SELECT * FROM purchases WHERE symbol=:symbol", symbol=stock["symbol"])

                db.execute("UPDATE purchases SET shares=:shares, total=:total WHERE symbol=:symbol AND id=:id",
                shares=int(request.form.get("shares"))+og[0]['shares'], total=og[0]["total"]+price,
                symbol=stock["symbol"], id=session["user_id"])

            # INSERT the new transaction details INTO the details table:
            db.execute("INSERT INTO details (id, symbol, time, shares, total) VALUES (:id, :symbol, :time, :shares, :total)",
            id=session["user_id"], symbol=stock['symbol'], time=time, shares=request.form.get("shares"), total=price)

            # Update users database to store the new cash values:
            db.execute("UPDATE users SET cash=:current_cash WHERE id=:id", current_cash=cash_left, id=session["user_id"])

            flash("Bought!")
            return redirect ("/")

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    # GET all the transactions for a particular user who is logged in:
    rows = db.execute("SELECT * FROM details WHERE id=:id ORDER BY time DESC", id=session["user_id"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Tell the user that he logged in successfully!
        flash("Login Successful!")
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    # Check for a request method:
    if request.method == "POST":
        # Check whether a certain stock exists and return it if so:
        symbol = request.form.get("symbol")

        # Check if nothing was entered:
        if not symbol:
            return apology("Enter the symbol of a stock", 333)

        else:
            stocks = lookup(symbol)
            if not stocks:
                flash("Not found!")
                return render_template("quote.html")

            return render_template("quote.html", price=stocks['price'], symbol=stocks['symbol'], name_of_company=stocks['name'], method="POST")


    else:
        # Simply get the template for quoting price of a stock.
        return render_template("quote.html", method="GET")
    return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Register the user if he submits via POST:
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Check if username was entered or not:
        if not username:
            return apology("Please enter username", 397)

        elif not password or not confirmation:
            return apology("Please enter and confirm your password!", 369)

        elif password != confirmation:
            return apology("Your password and reconfirmation do not match.", 69)

        # Now we check if the username already exists:
        else:
            rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)

            # Check if a user already exists:
            if len(rows) == 0:
                # Insert the data into our table:
                db.execute("INSERT INTO users ('username', 'hash') VALUES (:username, :hashes)",
                            username=username, hashes = generate_password_hash(password))

                # Tell the user that the registration was successful!
                flash("Registered Successfully!")

                return redirect("/")

            # The username already exists, so ask the user for creating a new username:
            else:
                return apology("Username already exists! Please try another username", 303)


    else:
        return render_template("register.html")
    return apology("TODO")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        # Check if the user entered a valid stock:
        symbol = request.form.get("symbol")
        shares_sold = int(request.form.get("shares"))
        available = db.execute("SELECT * FROM purchases WHERE symbol=:symbol and id=:id",symbol=symbol, id=session["user_id"])

        if int(shares_sold) > int(available[0]["shares"]):
            # User is trying to sell more shares than he currently owns:
            return apology("NOT ENOUGH SHARES", 420)

        else:
            time = datetime.now() + timedelta(hours=5.5)
            time = time.strftime("%d/%m/%Y %H:%M:%S")

            shares_sold_cost = float(lookup(symbol)["price"]) * float(shares_sold)
            # Now update the users table, purchases table:
            og_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id'])

            new_shares= int(available[0]["shares"]) - shares_sold
            new_total = lookup(symbol)["price"] * new_shares

            # Update the purchases table to get rid of shares sold:
            db.execute("UPDATE purchases SET shares=:shares, price=:price, total=:total WHERE symbol=:symbol",
            shares=new_shares, total=new_total ,price=lookup(symbol)["price"], symbol=symbol)

            # Update the details table:
            db.execute("INSERT INTO details (id, symbol, time, shares, total) VALUES (:id, :symbol, :time, :shares, :total)",
            id=session["user_id"], symbol=symbol, time=time, shares=-shares_sold, total=shares_sold_cost)

            # Update cash owned by user:
            db.execute("UPDATE users SET cash=:cash WHERE id=:id", cash=og_cash[0]["cash"] + shares_sold_cost, id=session["user_id"])

            # Tell the user the stock was sold!
            flash("Sold!")
            return redirect("/")

    else:
        # We don't want the user to have similar stock symbols displayed twice:
        symbols = db.execute("SELECT DISTINCT symbol FROM purchases WHERE id=:id", id=session["user_id"])

        # We give
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

# Define a function here:
def isnum(text):
    return any(character.isdigit() for character in text)

def isdigit(text):
    return any(character.isalpha() for character in text)