import threading
import time
from kucoin.client import User, Trade, Market

# Configuración de la API de KuCoin
API_KEY = 'TU_API_KEY'
API_SECRET = 'TU_API_SECRET'
API_PASSPHRASE = 'TU_API_PASSPHRASE'
SYMBOL = 'DOGE-USDT'
TAKE_PROFIT = 0.01  # Ejemplo: 1 centavo por encima del precio actual
STOP_LOSS = 0.01   # Ejemplo: 1 centavo por debajo del precio actual

# Clientes de la API
user_client = User(API_KEY, API_SECRET, API_PASSPHRASE)
trade_client = Trade(API_KEY, API_SECRET, API_PASSPHRASE)
market_client = Market()

# Variables globales
operation_in_progress = False
current_order = {}

def get_balance(currency):
    """Obtener balance de una moneda específica."""
    try:
        accounts = user_client.get_account_list()
        for account in accounts:
            if account['currency'] == currency and account['type'] == 'trade':
                return float(account['balance'])
        return 0.0
    except Exception as e:
        print(f"Error obteniendo balance para {currency}: {e}")
        return 0.0

def monitor_price():
    """Monitorea el precio del mercado para tomar decisiones según la orden actual."""
    global operation_in_progress
    try:
        while operation_in_progress:
            ticker = market_client.get_ticker(SYMBOL)
            current_price = float(ticker['price'])
            print(f"Precio actual monitoreado: {current_price}")

            if current_order.get('side') == 'buy' and current_price >= current_order.get('tp_price', float('inf')):
                print("Take Profit alcanzado. Ejecutando venta...")
                execute_trade('sell')
                break

            elif current_order.get('side') == 'sell' and current_price <= current_order.get('tp_price', float('-inf')):
                print("Take Profit alcanzado. Ejecutando compra...")
                execute_trade('buy')
                break

            time.sleep(5)  # Esperar antes de verificar nuevamente
    except Exception as e:
        print(f"Error monitoreando el precio: {e}")
    finally:
        operation_in_progress = False

def execute_trade(action):
    """Ejecuta una operación de compra o venta."""
    global operation_in_progress, current_order
    try:
        ticker = market_client.get_ticker(SYMBOL)
        current_price = float(ticker['price'])
        print(f"Precio actual del mercado para {SYMBOL}: {current_price}")

        if action == "buy":
            usdt_balance = get_balance("USDT")
            if usdt_balance > 0:
                response = trade_client.create_market_order(SYMBOL, "buy", funds=usdt_balance)
                print(f"Compra ejecutada: {response}")
                current_order.update({
                    "side": "buy",
                    "tp_price": current_price + TAKE_PROFIT,
                    "sl_price": current_price - STOP_LOSS
                })
            else:
                print("Saldo insuficiente de USDT.")

        elif action == "sell":
            doge_balance = get_balance("DOGE")
            if doge_balance > 0:
                response = trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
                print(f"Venta ejecutada: {response}")
                current_order.update({
                    "side": "sell",
                    "tp_price": current_price - TAKE_PROFIT,
                    "sl_price": current_price + STOP_LOSS
                })
            else:
                print("Saldo insuficiente de DOGE.")

        print(f"Orden actualizada: {current_order}")
        operation_in_progress = True
        threading.Thread(target=monitor_price).start()

    except Exception as e:
        print(f"Error ejecutando la operación: {e}")
        operation_in_progress = False

def webhook_listener(data):
    """Procesa las señales recibidas por webhook."""
    global operation_in_progress
    action = data.get('action')

    if action in ["buy", "sell"] and not operation_in_progress:
        execute_trade(action)
    else:
        print("Operación en curso o acción inválida.")

# Simulación de recepción de webhook para pruebas
data = {"action": "buy"}  # Ejemplo de señal de compra
webhook_listener(data)
