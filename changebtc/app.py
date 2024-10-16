from flask import Flask, render_template, redirect, url_for, flash, request
import requests
from datetime import datetime
from flask_login import LoginManager, login_required, current_user, UserMixin, login_user, logout_user
import sqlite3
import re
import ccxt 
import numpy as np

app = Flask(__name__)
app.secret_key = 'hello'  # Додайте секретний ключ для флеш-повідомлень

# Підключення до бази даних
db = sqlite3.connect('cryptobase.db')

# SQL курсор
c = db.cursor()

# Створення таблиці users, якщо вона не існує
c.execute("""CREATE TABLE IF NOT EXISTS users (
              UserId INTEGER PRIMARY KEY AUTOINCREMENT,
              Email TEXT NOT NULL UNIQUE,
              Login TEXT NOT NULL,
              Password TEXT NOT NULL,
              Phone TEXT
          )""")

# Закриття з'єднання
db.commit()  # Підтвердження змін
db.close()

def validate_phone(phone):
    pattern = r'^\+380\d{9}$'  # Формат +380XXXXXXXXX, де X - цифри
    return re.match(pattern, phone) is not None

def register_user(email, login, password, phone):
    db = sqlite3.connect('cryptobase.db')
    c = db.cursor()
    
    # Вставка нового користувача
    c.execute("INSERT INTO users (Email, Login, Password, Phone) VALUES (?, ?, ?, ?)", 
              (email, login, password, phone))
    
    db.commit()  # Підтвердження змін
    db.close()


# Ініціалізація LoginManager, відповідає за керування сесіями користувачів та перенаправлення неавторизованих користувачів на сторінку входу.
login_manager = LoginManager()
login_manager.init_app(app)  # Реєструємо LoginManager у додатку Flask
login_manager.login_view = 'signin_page'  # Вказуємо, куди перенаправляти неавторизованих користувачів

# Клас користувача, що наслідує UserMixin(ідентифікація користувача)
class User(UserMixin):
    def __init__(self, id, email, login, password, phone):
        self.id = id
        self.email = email
        self.login = login
        self.password = password
        self.phone = phone

@login_manager.user_loader
def load_user(user_id):
    db = sqlite3.connect('cryptobase.db')
    c = db.cursor()
    c.execute("SELECT UserId, Email, Login, Password, Phone FROM users WHERE UserId = ?", (user_id,))
    user_data = c.fetchone()
    db.close()

    if user_data:
        return User(*user_data)
    return None

@app.route('/home')
def index():
    return render_template('index.html')


@app.route('/profile')
@login_required
def profile_page():
    return render_template('profile.html')


@app.route('/signin', methods=['GET', 'POST'])
def signin_page():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Пошук користувача за email
        db = sqlite3.connect('cryptobase.db')
        c = db.cursor()
        c.execute("SELECT UserId, Email, Login, Password, Phone FROM users WHERE Email = ?", (email,))
        user_data = c.fetchone()
        db.close()
        
        if user_data:
            stored_password = user_data[3]  # Password знаходиться на 4-му місці
            if password == stored_password:
                user = User(*user_data)
                login_user(user)  # Використовуємо Flask-Login для входу
                return redirect(url_for('profile_page'))  
            else:
                flash('Неправильний пароль.')
        else:
            flash('Користувача з таким email не існує.')
    
    return render_template('signin.html')


@app.route('/logout')
@login_required #Цей декоратор з Flask-Login перевіряє, чи користувач автентифікований.
def logout():
    logout_user()
    flash('Ви вийшли з системи.')
    return redirect(url_for('signin_page'))

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':
        email = request.form['email']
        login = request.form['login']
        password = request.form['password']
        phone = request.form['phone']
        
        # Валідація номера телефону
        if not validate_phone(phone):
            flash('Невірний формат номера телефону. Використовуйте формат +380XXXXXXXXX.')
            return render_template('signup.html')  # Повертаємося на сторінку реєстрації з повідомленням
        
        # Реєстрація користувача
        try:
            register_user(email, login, password, phone)
            flash('Реєстрація успішна!')
            return redirect(url_for('signin_page'))  # Перенаправлення на сторінку входу лише після успішної реєстрації
        except sqlite3.IntegrityError as e:
            print(f"Error: {e}")
            flash('Користувач з таким email вже існує.')
            return render_template('signup.html')  # Повертаємося на сторінку реєстрації з помилкою

    return render_template('signup.html')


# Функція для отримання історичних даних
def fetch_historical_data(symbol='BTC/USDT', timeframe='1d', limit=14):
    exchange = ccxt.binance()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return ohlcv

# Функція для отримання даних про BTC
def get_btc_data():
    exchange = ccxt.binance()  # Використовуємо біржу Binance
    symbol = 'BTC/USDT'  # Визначаємо символ
    try:
        ticker = exchange.fetch_ticker(symbol)  # Отримуємо тикер
        return ticker  # Повертаємо дані про BTC
    except Exception as e:
        print(f"Error fetching BTC data: {e}")
        return None

@app.route('/data')
def data_page():
    btc_data = get_btc_data()  # Отримуємо дані про BTC
    historical_data = fetch_historical_data()  # Отримуємо історичні дані

    if btc_data:  # Перевіряємо, чи отримали дані
        prices = np.array([data[4] for data in historical_data])  # Закриті ціни з історичних даних
        current_price = prices[-1]
        
        moving_average = calculate_moving_average(prices, 14)
        rsi = calculate_rsi(prices)
        decision = make_decision(current_price, moving_average, rsi)

        return render_template('data.html', btc_data=btc_data, current_price=current_price, moving_average=moving_average, rsi=rsi, decision=decision)  # Передаємо дані до шаблону
    else:
        return "Error fetching data from API", 500

def calculate_moving_average(prices, period):
    return np.mean(prices[-period:])

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    gain = np.where(deltas > 0, deltas, 0)
    loss = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    
    if avg_loss == 0:
        return 100  # Уникнути ділення на нуль
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def make_decision(current_price, moving_average, rsi):
    if current_price > moving_average:
        return "Buy"
    elif rsi > 70:
        return "Sell"
    elif rsi < 30:
        return "Hold"
    else:
        return "Hold"

@app.template_filter('to_datetime')
def to_datetime(timestamp):
    return datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')

if __name__ == '__main__':
    app.run(debug=True)
